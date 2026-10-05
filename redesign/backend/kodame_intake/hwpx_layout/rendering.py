from __future__ import annotations

import httpx

from backend.oda_me.hwpx.patchers import toc_page_map_from_page_texts


from backend.oda_me.hwpx.toc_registry import TOC_LABELS

REQUIRED_TOC_KEYS = frozenset(TOC_LABELS)
EVALUATION_HEADING_TOC_KEYS = {
    "1. 적절성": "criteria_relevance_page",
    "2. 일관성": "criteria_coherence_page",
    "3. 효과성": "criteria_effectiveness_page",
    "4. 효율성": "criteria_efficiency_page",
    "5. 지속가능성": "criteria_sustainability_page",
    "6. 범분야 이슈": "criteria_crosscutting_page",
    "7. 그 외 평가기준": "criteria_other_page",
}
ORPHAN_HEADING_TRAILING_CHARS = 80
ORPHAN_HEADING_LEADING_CHARS = 80


def analyze_hwpx(data: bytes, kordoc_url: str, *, stage: str) -> dict:
    """Call kordoc and normalize transport/application failures in one place."""

    with httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        response = client.post(
            f"{kordoc_url}/analyze",
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"{stage} 실패: HTTP {response.status_code} {response.text[:240]}")
    validation = response.json()
    if not validation.get("ok"):
        raise RuntimeError(f"{stage} 실패: {validation.get('error') or '유효하지 않은 HWPX'}")
    return validation


def toc_page_map_from_analysis(analysis: dict) -> dict[str, str]:
    """Extract and validate every TOC destination from the first render pass."""

    rows = ((analysis.get("render") or {}).get("page_texts") or [])
    page_texts = [
        (int(row.get("page_number") or 0), str(row.get("text") or ""))
        for row in rows
        if int(row.get("page_number") or 0) > 0
    ]
    page_map = toc_page_map_from_page_texts(page_texts)
    missing = sorted(REQUIRED_TOC_KEYS - set(page_map))
    if missing:
        raise RuntimeError("kordoc 목차 쪽수 계산 실패: " + ", ".join(missing))
    return page_map


def validate_summary_page_span(analysis: dict, minimum_pages: int = 4) -> dict[str, int]:
    """Require the Korean summary to occupy the requested rendered span."""

    rows = ((analysis.get("render") or {}).get("page_texts") or [])
    page_map = toc_page_map_from_page_texts(
        [
            (int(row.get("page_number") or 0), str(row.get("text") or ""))
            for row in rows
            if int(row.get("page_number") or 0) > 0
        ]
    )
    missing = [key for key in ("summary_ko_page", "project_background_page") if key not in page_map]
    if missing:
        raise RuntimeError("국문 요약 조판 분량 계산 실패: " + ", ".join(missing))
    start_page = int(page_map["summary_ko_page"])
    next_section_page = int(page_map["project_background_page"])
    rendered_pages = max(0, next_section_page - start_page)
    if rendered_pages < minimum_pages:
        raise RuntimeError(
            "국문 요약 조판 분량 검증 실패: "
            f"{rendered_pages}쪽(시작 {start_page}, 다음 섹션 {next_section_page}) / 최소 {minimum_pages}쪽"
        )
    return {
        "start_page": start_page,
        "next_section_page": next_section_page,
        "rendered_pages": rendered_pages,
        "minimum_pages": minimum_pages,
    }


def orphan_heading_adjustments_from_analysis(
    analysis: dict,
) -> tuple[set[str], dict[str, str], list[dict]]:
    """Find evaluation headings left alone at a rendered page tail.

    Moving such a heading to the next page does not add a physical page: its
    body is already on that page. Only that heading's TOC destination changes.
    """

    rows = ((analysis.get("render") or {}).get("page_texts") or [])
    orphan_headings: set[str] = set()
    toc_corrections: dict[str, str] = {}
    evidence: list[dict] = []
    for heading, toc_key in EVALUATION_HEADING_TOC_KEYS.items():
        for row in rows:
            page_number = int(row.get("page_number") or 0)
            text = str(row.get("text") or "")
            if page_number <= 20:
                continue
            position = text.find(heading)
            if position < 0:
                continue
            trailing_chars = len(text) - position - len(heading)
            if (
                position > ORPHAN_HEADING_LEADING_CHARS
                and trailing_chars <= ORPHAN_HEADING_TRAILING_CHARS
            ):
                orphan_headings.add(heading)
                toc_corrections[toc_key] = str(page_number + 1)
                evidence.append(
                    {
                        "heading": heading,
                        "render_page": page_number,
                        "corrected_page": page_number + 1,
                        "trailing_chars": trailing_chars,
                    }
                )
            break
    return orphan_headings, toc_corrections, evidence


def validate_render_result(analysis: dict) -> tuple[int, int]:
    """Enforce structural bounds and reject rendered line collisions."""

    render = analysis.get("render") or {}
    stats = render.get("stats") or {}
    page_count = int(render.get("page_count") or render.get("pageCount") or 0)
    table_count = int(stats.get("table_count") or stats.get("tables") or 0)
    if not 20 <= page_count <= 100:
        raise RuntimeError(f"kordoc 조판 검증 실패: 예상 범위를 벗어난 {page_count}쪽")
    if table_count < 9:
        raise RuntimeError(f"kordoc 조판 검증 실패: 원본 표가 충분히 보존되지 않음 ({table_count}개)")
    overlap_risks = render.get("line_overlap_risks") or []
    if overlap_risks:
        samples = "; ".join(
            (
                f"{int(item.get('page_number') or 0)}쪽 "
                f"'{str(item.get('upper_text') or '')[:28]}'/"
                f"'{str(item.get('lower_text') or '')[:28]}' "
                f"간격 {float(item.get('baseline_gap') or 0):.1f}pt"
            )
            for item in overlap_risks[:5]
        )
        raise RuntimeError(
            "kordoc 조판 검증 실패: 여러 줄 글자 겹침 위험 "
            f"{len(overlap_risks)}건({samples})"
        )
    return page_count, table_count
