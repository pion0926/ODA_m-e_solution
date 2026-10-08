from __future__ import annotations

import re


_INTERNAL_REF_GROUP = re.compile(
    r"[\[(]\s*[EDS]\d{2,3}(?:\s*[,;/·]\s*[EDS]\d{2,3})*\s*[\])]",
    re.IGNORECASE,
)
_INTERNAL_REF = re.compile(r"(?<![A-Za-z0-9])[EDS]\d{2,3}(?![A-Za-z0-9])", re.IGNORECASE)


def sanitize_report_text(value: object) -> str:
    """Remove corpus-only identifiers and generation notes from reader-facing prose."""
    text = str(value or "")
    # Some legacy HWPX templates stored control elements as escaped reader text.
    text = re.sub(
        r"(?:<|&lt;)\s*hp:(?:tab|lineBreak)\b[^>]*?/(?:>|&gt;)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = _INTERNAL_REF_GROUP.sub("", text)
    text = _INTERNAL_REF.sub("", text)
    # Removing internal evidence references can leave citation-only punctuation
    # such as ``(~, )`` or ``;, )``. These fragments are never reader-facing
    # content, so clean them before normal whitespace normalization.
    text = re.sub(r"\(\s*~?(?:\s*[,;/·]\s*)*\)", "", text)
    text = re.sub(r"(?:[;,]\s*)+\)(?:\s*,)?", "", text)
    text = re.sub(r"(?<!\d),{2,}(?!\d)", "", text)
    text = re.sub(r";\s*,", "", text)
    text = re.sub(r"자동\s*초안\s*생성\s*제약\s*[:：]?", "자료 한계", text)
    text = re.sub(r"\s*\((?:ongoing|ended|unknown)\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+([,.;:!?。、])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\(\s*\)|\[\s*\]", "", text)
    return text.strip()


def sanitize_text_list(values: object, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = [sanitize_report_text(value)[:limit] for value in values]
    return [value for value in cleaned if value]
