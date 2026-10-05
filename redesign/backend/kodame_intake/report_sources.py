from __future__ import annotations

import re
from pathlib import Path

from backend.oda_me.reports.citations import strip_inline_source_citations


OPERATIONAL_SOURCE_TOKENS = (
    "readme",
    "업로드_안내",
    "업로드 안내",
    "자료요청",
    "자료 요청",
    "메일초안",
    "메일 초안",
    "google_drive_생성",
    "google drive 생성",
    "공유_절차",
    "공유 절차",
    "자료없음",
    "자료 없음",
)

_SOURCE_EXTENSION_RE = re.compile(
    r"(?i)\.(?:pdf|xlsx?|txt|md|zip|docx?|hwp|hwpx|pptx?|csv)(?![A-Za-z0-9])"
)
_FULL_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_.](?:0?[1-9]|1[0-2])[-_.](?:0?[1-9]|[12]\d|3[01])(?!\d)")
_STORAGE_PATH_RE = re.compile(
    r"(?i)(?:(?<![A-Za-z0-9])[A-Z]:[\\/](?:[^\s<>:\"|?*]+[\\/])+|/(?:app|uploads?|data-redesign|tmp)/|"
    r"(?:^|[\s(])(?:uploads?|data-redesign)[\\/][^\s)]+)"
)
_MANAGEMENT_PREFIX_RE = re.compile(
    r"^(?:(?:사업기본자료|미분류|DAC[ _-]*PDM|운영자료|업로드자료|실적증빙|첨부자료|참고자료)[ _-]+)+",
    re.IGNORECASE,
)


def is_report_evidence_document(name: object, analysis: object = None) -> bool:
    """Return False for upload-operation artifacts that are not report evidence."""
    from .document_classification import VERSION
    metadata = analysis if isinstance(analysis, dict) else {}
    classification = metadata.get("content_classification") or {}
    if classification.get("version") == VERSION:
        return bool(classification.get("is_project_plan") or classification.get("is_pdm_source")
                    or classification.get("slot_matches"))
    normalized = str(name or "").replace("\\", "/").lower()
    if any(token in normalized for token in OPERATIONAL_SOURCE_TOKENS):
        return False
    metadata = analysis if isinstance(analysis, dict) else {}
    document_type = str(metadata.get("document_type") or "").lower()
    return not any(token in document_type for token in ("운영 안내", "업로드 안내", "빈 자료", "readme"))


def reader_source_label(name: object, analysis: object = None) -> str:
    """Convert an upload/storage filename into a reader-facing bibliography label."""
    raw = Path(str(name or "").replace("\\", "/")).name
    # Bulk imports preserve a numbered Drive folder before a double underscore.
    # This namespace belongs to storage, not the document's bibliographic title.
    raw = re.sub(r"^\d{2}_(?:(?!__).)+__", "", raw)
    stem = _SOURCE_EXTENSION_RE.sub("", raw).strip()
    stem = _FULL_DATE_RE.sub(" ", stem)
    stem = _MANAGEMENT_PREFIX_RE.sub("", stem)
    stem = re.sub(r"(?i)^DAC[ _-]+(?=최신\s*PDM|PDM\b)", "", stem)
    stem = re.sub(r"(?i)(?<![A-Za-z])PDM(?![A-Za-z])", "사업설계매트릭스(PDM)", stem)
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s*[-–—]\s*", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .,_-()")
    stem = re.sub(r"\s+(?:국립)?한국교통대(?:학교)?$|\s+교통대$", "", stem).strip()
    if not stem:
        metadata = analysis if isinstance(analysis, dict) else {}
        stem = str(metadata.get("title") or metadata.get("document_type") or "사업 근거자료").strip()
    return stem[:180]


def normalize_source_mentions(text: object, source_names: list[str] | tuple[str, ...]) -> str:
    """Replace raw upload identifiers with stable reader-facing source labels."""
    value = str(text or "")
    for raw_name in sorted({str(item) for item in source_names if str(item)}, key=len, reverse=True):
        label = reader_source_label(raw_name)
        candidates = {
            raw_name,
            Path(raw_name.replace("\\", "/")).name,
        }
        for candidate in sorted(candidates, key=len, reverse=True):
            value = re.sub(re.escape(candidate), lambda _match, replacement=label: replacement, value, flags=re.IGNORECASE)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"(?i)(?<![\w가-힣])(?:사업기본자료|미분류|DAC[ _-]*PDM|운영자료|업로드자료)[ _-]+", "", value)
    value = re.sub(r"(?i)\.(?:pdf|xlsx?|txt|md|zip|docx?|hwp|hwpx|pptx?|csv)(?![A-Za-z0-9])", "", value)
    value = value.replace("_", " ")
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\s+([,.;:!?。、])", r"\1", value)
    return value.strip()


def ensure_authoritative_pdm_notice(content: str, execution_scope: dict) -> str:
    """Attach verified document metadata, never a model-invented citation.

    This is stored in the canonical draft before conversion. It does not
    change indicators, scores or prose, and is idempotent across repairs.
    """
    label = str((execution_scope.get("authoritative_pdm") or {}).get("source_label") or "").strip()
    if not content.strip() or not label or label in content:
        return content
    return f"ㅇ 설계 기준 문서\n- 본 섹션의 설계 기준 문서는 {label}임.\n\n{content}"


def source_artifact_issues(text: object, source_names: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Describe upload/storage identifiers that must never reach a final report."""
    value = str(text or "")
    issues: list[str] = []
    leaked_names = [
        Path(name.replace("\\", "/")).name
        for name in source_names
        if name and Path(name.replace("\\", "/")).name in value
    ]
    if leaked_names:
        issues.append("원본 업로드 파일명 노출: " + ", ".join(leaked_names[:3]))
    extensions = sorted(set(match.group(0).lower() for match in _SOURCE_EXTENSION_RE.finditer(value)))
    if extensions:
        issues.append("원본 파일 확장자 노출: " + ", ".join(extensions))
    if re.search(r"(?i)(?:사업기본자료|미분류|DAC[ _-]*PDM|운영자료|업로드자료)[ _-]", value):
        issues.append("관리용 문서 접두어 노출")
    if _STORAGE_PATH_RE.search(value):
        issues.append("내부 저장 경로 노출")

    # ISO 날짜 자체는 평가 기준일·사업일정에도 쓰이므로 금지하지 않는다. 대신
    # 업로드 파일명에서 추출한 날짜가 해당 문헌명 주변에 남은 경우만 관리정보로 판정한다.
    for raw_name in source_names:
        dates = {match.group(0).replace("_", "-").replace(".", "-") for match in _FULL_DATE_RE.finditer(str(raw_name))}
        if not dates:
            continue
        label = reader_source_label(raw_name)
        for upload_date in dates:
            context_pattern = re.compile(
                rf"(?:{re.escape(label)}.{{0,80}}{re.escape(upload_date)}|"
                rf"{re.escape(upload_date)}.{{0,80}}{re.escape(label)})",
                re.IGNORECASE | re.DOTALL,
            )
            if label and context_pattern.search(value):
                issues.append(f"업로드일 관리정보 노출: {upload_date}")
                break
        if any(issue.startswith("업로드일 관리정보 노출") for issue in issues):
            break
    return issues
