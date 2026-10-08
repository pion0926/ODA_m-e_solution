from __future__ import annotations

import re
from typing import Iterable

from backend.oda_me.hwpx.adapters.summary_ko import (
    SUMMARY_KO_ADAPTER,
    assert_summary_ko_payload,
    parse_summary_ko_section,
)


_UNUSABLE_VALUE_MARKERS = (
    "확인 필요",
    "확인 중",
    "추가 정보 필요",
    "미기재",
    "자동 초안 생성 제약",
)


def _usable(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or any(marker in text for marker in _UNUSABLE_VALUE_MARKERS):
        return ""
    return text


def _clean_inline(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"\*\*(.*?)\*\*|__(.*?)__|`([^`]*)`", lambda match: next((group for group in match.groups() if group is not None), ""), text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _paragraphs(value: object) -> list[str]:
    result: list[str] = []
    for raw_line in str(value or "").replace("\r", "").split("\n"):
        line = re.sub(r"^\s*#{1,6}\s*", "", raw_line).strip()
        if not line or re.match(r"^\|?\s*:?-{3,}(?:\s*\|\s*:?-{3,})+\s*\|?$", line):
            continue
        if "|" in line:
            cells = [_clean_inline(cell) for cell in line.strip("|").split("|")]
            line = " · ".join(cell for cell in cells if cell)
        if re.match(r"^[가-하]\.[^.!?]{1,80}$", line):
            continue
        if line.startswith("- ") and result:
            result[-1] = f"{result[-1]} {line[2:]}".strip()
        else:
            result.append(line)
    return result


def _compact(value: object, limit: int, fallback: str = "") -> str:
    text = " ".join(_paragraphs(value)) or _clean_inline(value)
    text = re.sub(r"\s+", " ", text).strip(" -")
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    # A bare ``[^.]+`` splitter treats every dot in dates and decimals as a
    # sentence boundary (for example ``2022. 04. 01.``), which previously
    # copied half a period into the fixed Korean-summary slot.  Split only at
    # natural sentence punctuation; a dot preceded by a digit stays inside
    # the current sentence.
    sentences = re.split(
        r"(?<=[!?。])\s+|(?<!\d)(?<=\.)\s+(?=[가-힣A-Z\"“'‘「『(])",
        text,
    )
    selected = ""
    for sentence in (item.strip() for item in sentences if item.strip()):
        if len(selected) + len(sentence) + 1 > limit:
            break
        selected = f"{selected} {sentence}".strip()
    if selected:
        return selected

    clipped = text[:limit].rstrip(" ,;:-")
    for boundary in ("다. ", "함. ", "됨. ", "; ", ", "):
        position = clipped.rfind(boundary)
        if position >= max(40, limit // 2):
            clipped = clipped[: position + len(boundary)].strip()
            break
    # Never export a half-open date/citation parenthesis into the summary.
    while clipped.count("(") > clipped.count(")") and "(" in clipped:
        clipped = clipped[:clipped.rfind("(")].rstrip(" ,;:-")
    return clipped if clipped.endswith((".", "!", "?", "。")) else clipped + "."


def summary_fragment(value: object, limit: int, fallback: str = "") -> str:
    """Create citation-free, heading-free prose for one fixed summary slot."""
    text = str(value or "")
    text = re.sub(
        r"\s*\([^()\n]{0,220}(?:pp?\.\s*\d+(?:\s*[-–~]\s*\d+)?|\d+\s*쪽)[^()\n]{0,120}\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("ongoing", "진행 중").replace("온고잉", "진행 중").replace("ended", "종료")
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(
        r"^\s*(?:[-*•ㅇ❍∙ㆍ]\s*)?(?:\d+(?:\.\d+)*[.)]|[가-하][.)])\s*",
        "",
        text,
    )
    return _compact(text, limit, fallback)


def _keyword_fragment(value: object, keywords: Iterable[str], limit: int) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if any(keyword in line for keyword in keywords):
            chosen = [line]
            for following in lines[index + 1:index + 4]:
                if re.match(r"^[가-하]\.|^\d+[.)]", following):
                    break
                chosen.append(following)
            return summary_fragment(" ".join(chosen), limit)
    return ""


def _markdown_tables(value: object) -> list[dict[str, list]]:
    lines = str(value or "").replace("\r", "").split("\n")
    tables: list[dict[str, list]] = []
    index = 0
    while index < len(lines) - 1:
        if "|" not in lines[index] or not re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            index += 1
            continue
        header = [_clean_inline(item) for item in lines[index].strip().strip("|").split("|")]
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index]:
            row = [_clean_inline(item) for item in lines[index].strip().strip("|").split("|")]
            if any(row):
                rows.append(row)
            index += 1
        tables.append({"header": header, "rows": rows})
    return tables


def _table_field_fragment(
    value: object,
    row_keywords: Iterable[str],
    column_keywords: Iterable[str],
    limit: int,
) -> str:
    for table in _markdown_tables(value):
        headers = [re.sub(r"\s+", "", str(item)) for item in table["header"]]
        field_index = next(
            (
                index
                for index, header in enumerate(headers)
                if any(keyword.replace(" ", "") in header for keyword in column_keywords)
            ),
            -1,
        )
        if field_index < 0:
            continue
        for row in table["rows"]:
            category = str(row[0] if row else "")
            if any(keyword in category for keyword in row_keywords) and field_index < len(row):
                result = summary_fragment(row[field_index], limit)
                if result:
                    return result
    return ""


def _first_lesson_fragment(value: object, limit: int) -> str:
    for table in _markdown_tables(value):
        headers = [re.sub(r"\s+", "", str(item)) for item in table["header"]]
        field_index = next((index for index, header in enumerate(headers) if "교훈내용" in header), -1)
        if field_index >= 0 and table["rows"] and field_index < len(table["rows"][0]):
            result = summary_fragment(table["rows"][0][field_index], limit)
            if result:
                return result
    return summary_fragment(value, limit)


def _criterion_fragment(context: dict, criterion_id: str, limit: int) -> str:
    for criterion in context.get("criteria") or []:
        if str(criterion.get("id") or "") != criterion_id:
            continue
        result = criterion.get("evaluationResult") if isinstance(criterion.get("evaluationResult"), dict) else {}
        return summary_fragment(result.get("summary") or result.get("rationale"), limit)
    return ""


def _dac_synthesis(context: dict, limit: int) -> str:
    pieces: list[str] = []
    for criterion_id, label in (
        ("relevance", "적절성"),
        ("coherence", "일관성"),
        ("effectiveness", "효과성"),
        ("efficiency", "효율성"),
        ("sustainability", "지속가능성"),
    ):
        fragment = _criterion_fragment(context, criterion_id, 75)
        if fragment:
            pieces.append(f"{label}은 {fragment}")
    return _compact(" ".join(pieces), limit)


def _project_fallbacks(context: dict) -> dict[str, str]:
    project = context.get("project") if isinstance(context.get("project"), dict) else {}
    title = _usable(project.get("title"))
    if not title:
        raise RuntimeError("국문 요약을 합성하려면 사업명이 필요합니다.")
    country = _usable(project.get("country"))
    location = _usable(project.get("location"))
    objective = _usable(project.get("objective"))
    activities = _usable(project.get("activities"))
    outputs = _usable(project.get("outputs"))
    outcomes = _usable(project.get("outcomes"))
    period = _usable(project.get("period"))
    budget = _usable(project.get("budget"))
    background = _usable(project.get("background"))
    evidence_gaps = _usable(project.get("evidence_gaps"))
    place = " ".join(item for item in (country, location) if item) or "대상지역"
    overview_fields = " · ".join(item for item in (period, budget) if item)
    overview_opening = f"{title}({overview_fields})" if overview_fields else title
    purpose = objective or "사업이 계획한 산출과 성과의 달성 여부"
    activity_text = f" 주요 활동은 {activities}." if activities else ""
    return {
        "business_background": background or f"본 사업은 {place}의 개발수요에 대응하고 {purpose}을 지원하기 위해 추진되었다.",
        "business_overview": f"{overview_opening}은 {purpose}을 목적으로 수행되었다.{activity_text}",
        "achievement_summary": (
            f"최신 PDM의 성과·산출 지표와 등록된 실적자료를 대조하였다. 확인된 핵심 산출은 {outputs}."
            if outputs
            else f"최신 PDM의 성과·산출 지표와 등록된 실적자료를 대조하여 {outcomes or purpose}의 달성 정도를 판단하였다."
        ),
        "evaluation_limitations": evidence_gaps or "등록 문헌만으로 확인하기 어려운 실적과 이해관계자 의견은 판단의 제한으로 반영하고 보수적으로 해석하였다.",
    }


def _choose(
    key: str,
    candidates: Iterable[tuple[str, object]],
    limit: int,
    fallback: str,
    provenance: dict[str, tuple[str, ...]],
    fallback_slots: list[str],
) -> str:
    for source_id, value in candidates:
        fragment = summary_fragment(value, limit)
        if fragment:
            provenance[key] = (source_id,)
            return fragment
    provenance[key] = ("deterministic-fallback",)
    fallback_slots.append(key)
    return summary_fragment(fallback, limit, fallback)


def _prefixed(key: str, body: str) -> str:
    return f"{SUMMARY_KO_ADAPTER.slots_by_key[key].authoring_prefix}{body}".strip()


def compose_summary_ko(context: dict, prepared: dict[str, str]):
    """Use the five-heading draft verbatim; compose only for legacy/empty drafts."""
    # Local import prevents the registry dataclass from forming an import cycle.
    from .registry import AdapterComposition

    project = context.get("project") if isinstance(context.get("project"), dict) else {}
    fallbacks = _project_fallbacks(context)
    source = prepared.get("summary-ko", "")
    try:
        slots = parse_summary_ko_section(source)
        return AdapterComposition(
            adapter_id="summary_5_blocks",
            part_id="summary-ko",
            slots=slots,
            provenance={key: ("summary-ko",) for key in slots},
            fallback_slots=(),
        )
    except Exception:
        pass

    title = _usable(project.get("title")) or "평가대상 사업"
    period_budget = " · ".join(
        item for item in (_usable(project.get("period")), _usable(project.get("budget"))) if item
    )
    country_region = " · ".join(
        item for item in (_usable(project.get("country")), _usable(project.get("location"))) if item
    )
    methods = summary_fragment(
        prepared.get("eval-methods"),
        420,
        "등록된 사업계획·PDM·수행실적·성과자료를 문헌검토하고 자료 간 일치 여부를 교차대조하였다.",
    )
    purpose = summary_fragment(
        prepared.get("eval-purpose"),
        420,
        "사업의 계획 대비 성과와 수행과정을 검토하고 5개 DAC 기준별 판단 및 후속 개선과제를 도출하였다.",
    )
    limitation = summary_fragment(
        prepared.get("eval-limitations"), 360, fallbacks["evaluation_limitations"]
    )
    achievement = summary_fragment(
        prepared.get("achievement"), 760, fallbacks["achievement_summary"]
    )

    criteria_lines: list[str] = []
    criterion_defaults = {
        "relevance": "사업목적과 대상지역 수요·정책의 부합성을 등록 근거 범위에서 검토하였다.",
        "coherence": "사업 내부 논리와 관련 정책·기관·사업 간 연계 및 중복 여부를 검토하였다.",
        "effectiveness": "계획한 산출과 성과의 달성 정도 및 기여·저해요인을 검토하였다.",
        "efficiency": "예산·일정·투입 관리와 산출 간 관계를 검토하였다.",
        "sustainability": "제도·재원·조직역량·유지관리와 현지 소유권의 지속 조건을 검토하였다.",
    }
    for criterion_id, label in (
        ("relevance", "적절성"),
        ("coherence", "일관성"),
        ("effectiveness", "효과성"),
        ("efficiency", "효율성"),
        ("sustainability", "지속가능성"),
    ):
        detail = summary_fragment(
            prepared.get(f"criteria-{criterion_id}") or _criterion_fragment(context, criterion_id, 360),
            360,
            criterion_defaults[criterion_id],
        )
        criteria_lines.extend((f" ㅇ {label}", f"- {detail}"))

    conclusion = summary_fragment(
        prepared.get("conclusion"), 540, "5개 평가기준과 성과달성도 판단을 종합하였다."
    )
    working = summary_fragment(
        prepared.get("working-factors"),
        300,
        "수요와 사업목적의 정합성, 역할 분담 및 근거 기반 관리가 성과를 촉진하였다.",
    )
    nonworking = summary_fragment(
        prepared.get("nonworking-factors"),
        300,
        "자료 공백과 지표·검증수단의 연결 부족이 성과 판단과 후속관리를 제약하였다.",
    )
    feedback = summary_fragment(
        prepared.get("feedback") or prepared.get("lessons"),
        420,
        "지표별 실적·검증자료·담당자·갱신주기를 통합 관리하고 후속 점검자료를 축적한다.",
    )

    project_details = [f"사업명: {title}"]
    if period_budget:
        project_details.append(f"기간·예산: {period_budget}")
    if country_region:
        project_details.append(f"대상국·지역: {country_region}")
    slots = {
        "project_overview": "\n".join((
            " ㅇ 사업 기본정보",
            *(f"- {item}" for item in project_details),
            " ㅇ 추진배경 및 주요내용",
            f"- {summary_fragment(prepared.get('project-background'), 460, fallbacks['business_background'])}",
            f"- {summary_fragment(prepared.get('project-overview'), 460, fallbacks['business_overview'])}",
        )),
        "evaluation_overview": "\n".join((
            " ㅇ 평가 목적과 범위",
            f"- {purpose}",
            " ㅇ 평가 방법",
            f"- {methods}",
            " ㅇ 평가의 한계",
            f"- {limitation}",
        )),
        "achievement": "\n".join((" ㅇ 주요 성과달성도", f"- {achievement}")),
        "criteria_results": "\n".join(criteria_lines),
        "conclusion": "\n".join((
            " ㅇ 종합 결론", f"- {conclusion}",
            " ㅇ 작동요인", f"- {working}",
            " ㅇ 비작동요인", f"- {nonworking}",
            " ㅇ 환류과제 및 교훈", f"- {feedback}",
        )),
    }
    slots = assert_summary_ko_payload(slots)
    return AdapterComposition(
        adapter_id="summary_5_blocks",
        part_id="summary-ko",
        slots=slots,
        provenance={key: ("deterministic-fallback",) for key in slots},
        fallback_slots=tuple(slots),
    )


# Backward-compatible test/import names while ownership lives in this module.
_summary_fragment = summary_fragment
_summary_slots = lambda context, prepared: compose_summary_ko(context, prepared).slots
