from __future__ import annotations

from ..core import *

def clean_title_candidate(value: str) -> str | None:
    candidate = re.sub(r"\s+", " ", value).strip(" \t\r\n:：-–—|[]()")
    candidate = re.sub(r"^(?:[\dIVXivx]+[.)-]\s*)+", "", candidate).strip()
    candidate = re.sub(r"\s*\((?:Project|프로젝트).*$", "", candidate, flags=re.IGNORECASE).strip()
    if not 5 <= len(candidate) <= 160:
        return None
    lower_candidate = candidate.lower()
    blocked = (
        "\ubaa9\ucc28",
        "\ud45c ",
        "\uadf8\ub9bc",
        "\ucc38\uace0",
        "\uc5c6\uc74c",
        "table",
        "figure",
    )
    if any(token in lower_candidate for token in blocked):
        return None
    return candidate


def infer_project_title(extracted_text: str, fallback_filename: str) -> str | None:
    labels = (
        "\uc0ac\uc5c5\uba85",
        "\uc0ac\uc5c5 \uba85",
        "\uc0ac\uc5c5\uc81c\ubaa9",
        "\uc0ac\uc5c5 \uc81c\ubaa9",
        "\uacfc\uc81c\uba85",
        "\ud504\ub85c\uc81d\ud2b8\uba85",
        "project title",
        "project name",
        "title",
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    joined = "\n".join(lines[:200])
    spaced_korean_match = re.search(r"사\s*업\s*명\s*[<>\s:：\-|▪ㆍ]*\s*(.+?)(?:>|$|\n)", joined, re.IGNORECASE)
    if spaced_korean_match:
        title = clean_title_candidate(spaced_korean_match.group(1))
        if title:
            return title
    table_match = re.search(rf"(?:{label_pattern})\s*[<>\s:：\-|▪ㆍ]*\s*(.+?)(?:>|$|\n)", joined, re.IGNORECASE)
    if table_match:
        title = clean_title_candidate(table_match.group(1))
        if title:
            return title
    for index, line in enumerate(lines[:200]):
        normalized = re.sub(r"\s+", " ", line)
        match = re.match(rf"^(?:{label_pattern})\s*[:：\-|]?\s*(.+)$", normalized, re.IGNORECASE)
        if match:
            title = clean_title_candidate(match.group(1))
            if title:
                return title
            if index + 1 < len(lines):
                title = clean_title_candidate(lines[index + 1])
                if title:
                    return title

    keywords = (
        "ODA",
        "KOICA",
        "CTS",
        "\uc131\uacfc\uad00\ub9ac",
        "\ud3c9\uac00",
        "\uc790\ub3d9\ud654",
        "\uc194\ub8e8\uc158",
        "\uc0ac\uc5c5",
    )
    for line in lines[:120]:
        title = clean_title_candidate(line)
        if title and sum(1 for keyword in keywords if keyword.lower() in title.lower()) >= 2:
            return title

    stem = Path(fallback_filename).stem
    stem = re.sub(r"^\d+(?:-\d+)?\.\s*", "", stem)
    stem = re.sub(r"\([^)]*\)", " ", stem)
    return clean_title_candidate(stem)


def normalize_period(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    value = value.replace("~", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"년", "", value)
    return value.strip("-")


def clean_budget_candidate(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n:：-–—/|<>[]()▪")


def extract_project_period_budget(extracted_text: str) -> tuple[str | None, str | None]:
    text = normalize_extracted_text(extracted_text)
    labels = (
        "사업규모/기간",
        "사업 규모/기간",
        "사업비/기간",
        "사업비 / 기간",
        "사업기간/사업비",
        "기간/사업비",
        "사업기간",
        "사업 기간",
        "사업규모",
        "사업 규모",
        "사업비",
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    period_pattern = r"(?:19|20)\d{2}\s*(?:[.~\-–—]\s*(?:19|20)\d{2}|년\s*[.~\-–—]?\s*(?:19|20)\d{2}\s*년?)"
    budget_patterns = (
        r"\d[\d,.]*\s*만\s*불\s*(?:\([^)]{1,80}\))?",
        r"\d[\d,.]*\s*불\s*(?:\([^)]{1,80}\))?",
        r"\d[\d,.]*\s*억\s*\d*[\d,.]*\s*만?\s*원",
        r"\d[\d,.]*\s*만\s*원",
        r"\d[\d,.]*\s*원",
    )

    contexts = []
    for match in re.finditer(label_pattern, text, re.IGNORECASE):
        contexts.append(text[match.start() : match.start() + 260])
    contexts.append(text[:3000])

    for context in contexts:
        period_match = re.search(period_pattern, context)
        budget_match = next((re.search(pattern, context) for pattern in budget_patterns if re.search(pattern, context)), None)
        if period_match or budget_match:
            period = normalize_period(period_match.group(0)) if period_match else None
            budget = re.sub(r"\s+", " ", budget_match.group(0)).strip(" \t\r\n:：-–—/|<>[]▪") if budget_match else None
            return period, budget
    return None, None


