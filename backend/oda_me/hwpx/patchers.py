from __future__ import annotations

import binascii
import struct

from ..core import *
from ..reports.context import (
    SECTION6_PROJECT_BACKGROUND_SLOT_KEYS,
    SECTION7_PROJECT_OVERVIEW_SLOT_KEYS,
    SECTION10_EVAL_MATRIX_SLOT_KEYS,
    normalize_feedback_section,
    normalize_lessons_section,
    parse_section1_cover_slots,
    parse_structured_section_slots,
    short_text,
)
from ..reports.citations import strip_inline_source_citations
from ..reports.editor import read_report_editor_state, save_report_editor, validate_exported_hwpx
from ..reports.export_builders import current_report_context
from ..utils.common import safe_filename
from .adapters.summary_ko import (
    SUMMARY_KO_ADAPTER,
    SUMMARY_KO_BLOCKS,
    normalize_summary_ko_value,
    parse_summary_ko_section,
    render_summary_ko_document,
    validate_summary_ko_manifest,
)
from .adapters.lesson_records import parse_lesson_outline
from .formatting import compact_report_sentence, criterion_grade_rows, format_score, infer_report_people
from .grade_reasons import readable_grade_reason
from report_writing_policy import writing_profile


def strip_inline_page_citations(value: object) -> str:
    """Backward-compatible wrapper for reader-facing citation cleanup."""

    return strip_inline_source_citations(value)


def grade_total_reason(label: str, reason: object, limit: int = 90) -> str:
    cleaned = re.sub(r"^\s*[^:：]{0,20}종합\s*(?:평균|평가)\s*[:：]\s*", "", str(reason or "")).strip()
    cleaned = re.sub(r"^(?:핵심\s*확인사항\s*[:：]\s*)+", "", cleaned).strip()
    cleaned = cleaned or f"{label} 질문별 점수와 근거를 종합해 산정함"
    return grade_reason_sentence(f"{label} 종합: {cleaned}", limit)


def grade_reason_sentence(reason: object, limit: int = 90) -> str:
    """Return a complete one-line grade-table reason without ellipsis."""
    def finalize(value: str) -> str:
        value = value.strip(" ,.;·/-")
        replacements = [
            ("되었으며", "되었음"),
            ("하였으며", "하였음"),
            ("했으며", "했음"),
            ("확인되었으며", "확인됨"),
            ("반영하여", "반영함"),
            ("고려하여", "고려함"),
            ("달성하여", "달성함"),
            ("제고하여", "제고함"),
        ]
        for old, new in replacements:
            if value.endswith(old):
                value = value[: -len(old)] + new
                break
        if value.endswith("유연하게"):
            value += " 대응함"
        elif value.endswith("지속가능성에"):
            value += " 제약이 확인됨"
        elif value.endswith(("에서", "으로", "로", "및", "과", "와", "을", "를", "에")):
            value = re.sub(r"(에서|으로|로|및|과|와|을|를|에)$", "", value).strip()
        if re.search(r"(다|음|함|됨|임|있음|없음|확인됨|판단됨|필요함|미흡함|부족함)$", value):
            return value + "."
        # Preserve the concrete fragment and close it with an evaluative
        # consequence.  The former ``관련 근거가 확인됨`` fallback repeated in
        # almost every row and did not explain why the fact affected a score.
        return f"{value}; 해당 사실을 질문별 점수 산정에 반영함."

    text = strip_inline_page_citations(reason)
    text = re.sub(r"\.{3,}|…+", "", text).strip()
    text = re.sub(r"^(?:본\s*(?:사업|평가)(?:은|는)\s*|핵심\s*확인사항\s*[:：]\s*)+", "", text).strip()
    text = re.sub(
        r"(신설|개설|구축|승인|확보|도입|설립)으로\s*판단됨",
        r"\1 사실을 확인함",
        text,
    )
    if not text:
        text = "평가 근거를 종합하여 보수적으로 점수를 산정함"
    pattern_summaries = [
        (["보건의료 정책", "모자보건 수요"], "보건의료 정책과 무구지역 모자보건 수요를 반영해 설계됨."),
        (["UNICEF", "중복"], "UNICEF 등 공여기관과 협력해 중복을 방지하고 공동 목표 달성에 기여함."),
        (["병원 신축", "기자재", "역량강화"], "병원 신축·기자재 지원·역량강화 등 핵심 산출물을 달성함."),
        (["사무소 운영 전략", "유연"], "열악한 현지 여건에 맞춰 사무소 운영 전략을 유연하게 조정함."),
        (["기자재 관리", "자립 역량"], "기자재 관리와 병원 운영의 현지 자립역량 부족이 확인됨."),
    ]
    for required, summary in pattern_summaries:
        if all(part in text for part in required):
            return summary
    sentence = compact_report_sentence(text, limit)
    sentence = re.sub(r"\.{3,}|…+", "", sentence).strip()
    if len(sentence) <= limit:
        return finalize(sentence) if sentence else "평가 근거를 종합하여 점수를 산정함."
    clause = re.split(r"[,;]| 및 | 그리고 | 다만 | 그러나 ", sentence, maxsplit=1)[0].strip()
    if 18 <= len(clause) <= limit:
        return finalize(clause)
    cut = sentence.rfind(" ", 0, limit - 7)
    if cut < 18:
        cut = limit - 7
    clipped = sentence[:cut].strip(" ,.;·/-")
    clipped = re.sub(r"(하며|하고|하여|에서|으로|로|및|과|와|을|를)$", "", clipped).strip(" ,.;·/-")
    if not clipped:
        clipped = "평가 근거를 종합"
    return finalize(clipped)


def grade_question_reason(reason: object, limit: int = 90) -> str:
    """Keep the saved question-level 핵심 판단 for grade-table reason cells."""
    original = strip_inline_page_citations(reason)
    text = readable_grade_reason(original)
    projected_diagnostic = text != original
    text = re.sub(r"(?:\*\*|__|`|#{1,6})", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*•ㅇ❍∙ㆍ]|\d+(?:\.\d+)*[.)])\s*", "", text)
    text = re.sub(r"\b(?:E|D|S)\d{2,}\b", "", text)
    text = re.sub(r"^(?:본\s*(?:사업|평가)(?:은|는)\s*|핵심\s*확인사항\s*[:：]\s*)+", "", text).strip()
    # Model/editor payloads sometimes contain a literal backslash-t token or
    # control whitespace. Neither belongs in a fixed HWPX table cell: it can
    # be interpreted as a paragraph tab and create large visual gaps.
    text = text.replace("\\t", " ")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return grade_reason_sentence(reason, limit)
    if projected_diagnostic or len(text) <= limit:
        # The reader limitation introduces a sentence boundary. Do not let
        # the legacy two-sentence summary then drop the following real facts.
        return text.rstrip(".") + "."
    # The character target is advisory. Keep at least the first two complete
    # sentences so an initial positive finding retains its following limit.
    # Table pagination handles long reasons; never splice a grammatical fragment
    # into an invented conclusion. Splitting on punctuation followed by whitespace
    # also preserves decimal values such as 1.7 and numeric dates.
    sentences = re.split(r"(?<=[.!?。])\s+", text)
    selected = sentences[:2]
    if len(sentences) > 2 and len(" ".join(selected + sentences[2:3])) <= limit:
        selected.append(sentences[2])
    return " ".join(selected).rstrip(".") + "."


# Question rationales are allowed to reflow over a two-page grade table. The
# subtotal rows intentionally have no rationale: they contain only the
# criterion label and the system-calculated average score.
GRADE_REASON_CELL_LIMITS: dict[int, int] = {
    8: 120, 12: 120,
    21: 120, 25: 120,
    34: 120, 38: 120, 42: 120,
    51: 120, 55: 120,
    64: 120, 68: 120,
}


GRADE_QUESTION_REASON_CELLS = tuple(GRADE_REASON_CELL_LIMITS)
GRADE_SUBTOTAL_REASON_CELLS = (16, 29, 46, 59, 72)
GRADE_QUESTION_REASON_SLOT_KEYS = (
    "relevance_policy_reason",
    "relevance_adaptation_reason",
    "coherence_internal_reason",
    "coherence_external_reason",
    "effectiveness_output_reason",
    "effectiveness_outcome_reason",
    "effectiveness_equity_reason",
    "efficiency_timeliness_reason",
    "efficiency_balance_reason",
    "sustainability_capacity_reason",
    "sustainability_environment_reason",
)
GRADE_SUBTOTAL_REASON_SLOT_KEYS = (
    "relevance_total_reason",
    "coherence_total_reason",
    "effectiveness_total_reason",
    "efficiency_total_reason",
    "sustainability_total_reason",
)


GRADE_SCORE_REASON_CELLS: dict[str, list[tuple[int, int]]] = {
    "relevance": [(6, 8), (10, 12), (14, 16)],
    "coherence": [(19, 21), (23, 25), (27, 29)],
    "effectiveness": [(32, 34), (36, 38), (40, 42), (44, 46)],
    "efficiency": [(49, 51), (53, 55), (57, 59)],
    "sustainability": [(62, 64), (66, 68), (70, 72)],
}


def patch_hwpx_cover(root: ET.Element, context: dict) -> None:
    project = context.get("project", {})
    title = str(project.get("title") or "사업명 확인 필요").strip()
    year_month = datetime.now().strftime("%Y. %m")
    people = infer_report_people([])
    replace_hwpx_paragraph_text(root, "ㅇㅇ사업 종료평가 결과보고서", f"{title}\n종료평가 결과보고서", exact=True)
    replace_hwpx_paragraph_text(root, "2023. 12", year_month, exact=True)
    replace_hwpx_paragraph_text(root, "평가책임자 OOO", people.get("managerLine") or "평가책임자 확인 대상", exact=True)
    replace_hwpx_paragraph_text(root, "평가수행기관 OOO(혹은 로고)", people.get("institutionLine") or "평가수행기관 확인 대상", exact=True)
    replace_hwpx_paragraph_text(root, "평가책임자 확인 필요", people.get("managerLine") or "평가책임자 확인 대상", exact=True)
    replace_hwpx_paragraph_text(root, "평가수행기관 확인 필요", people.get("institutionLine") or "평가수행기관 확인 대상", exact=True)


def patch_hwpx_grade_section(root: ET.Element, context: dict) -> None:
    project = context.get("project", {})
    project_label = f"ㅇ 평가대상 사업명 : {project.get('title') or '사업명 확인 필요'}"
    replace_hwpx_paragraph_text(root, "ㅇ 평가대상 사업명 : 사업명(사업기간/예산)", project_label, exact=True)
    replace_hwpx_paragraph_text(root, "※ 평가자는 주어진 평가표에 의거하여 종합 평가 등급과 점수를 모두 제시해야 함.", "", exact=True)
    replace_hwpx_paragraph_text(root, "※ 구간별 점수 산정 참고 사항은 별도 엑셀파일 참조 요망.", "", exact=True)

    table = find_hwpx_grade_table(root)
    if table is None:
        raise ValueError("HWPX template grade table was not found")
    cells = table.findall(".//hp:tc", HWPX_NS)
    criteria = criterion_grade_rows(context)
    for item in criteria:
        cell_pairs = GRADE_SCORE_REASON_CELLS.get(str(item.get("id")), [])
        for pair_index, (score_cell, reason_cell) in enumerate(cell_pairs):
            is_average = pair_index == len(cell_pairs) - 1
            question_rows = item.get("questionRows") if isinstance(item.get("questionRows"), list) else []
            if is_average:
                score_value = item["score"]
                reason = ""
            else:
                question = question_rows[pair_index] if pair_index < len(question_rows) else {}
                score_value = question.get("score", item["score"]) if isinstance(question, dict) else item["score"]
                reason = question.get("reason") or question.get("question") or item["reason"] if isinstance(question, dict) else item["reason"]
            if score_cell < len(cells):
                set_hwpx_scope_text(cells[score_cell], format_score(score_value, '점'))
            if reason_cell < len(cells):
                formatted = "" if is_average else grade_question_reason(reason, GRADE_REASON_CELL_LIMITS[reason_cell])
                set_hwpx_scope_text(cells[reason_cell], formatted)
    overall = context.get("overall") or {}
    if 74 < len(cells):
        set_hwpx_scope_text(cells[74], format_score(overall.get('score'), '/20점'))
    if 76 < len(cells):
        set_hwpx_scope_text(cells[76], str(overall.get("governmentGrade") or "미흡"))
    if 78 < len(cells):
        set_hwpx_scope_text(cells[78], str(overall.get("koicaGrade") or "F"))


def patch_hwpx_core_body(root: ET.Element, sections_by_id: dict[str, str]) -> None:
    replacements = [
        ("ㅇ 보고서 주요 내용 위주로 3~5쪽 이내 요약 작성", sections_by_id.get("summary") or sections_by_id.get("summary-ko") or ""),
        ("ㅇ 평가매트릭스 상 평가질문(연번 함께 표기)에 대한 평가결과 제시", sections_by_id.get("criteria-relevance") or ""),
        ("ㅇ 결론은 평가목표와 대상 사업의 전반적인 목표에 관한 내용", sections_by_id.get("conclusion") or ""),
        ("ㅇ 평가결과를 기반으로, 사업의 성과달성에 기여한 요인과 그 원인(What worked, why) 제시", sections_by_id.get("working-factors") or ""),
        ("ㅇ 평가결과를 기반으로, 사업의 성과 달성을 저해했거나 성과 미달성의 원인(What did not work, why) 제시", sections_by_id.get("nonworking-factors") or ""),
        ("(작성 예시) 보고서 작성시 삭제", ""),
        ("보고서 작성 시 TIP (보고서 작성시 삭제)", ""),
        ("효율성 평가사례 및 참고문헌 (보고서 작성시 삭제)", ""),
        ("작동요인 작성 예시 (보고서 작성시 삭제)", ""),
        ("비작동요인 작성 예시 (보고서 작성시 삭제)", ""),
    ]
    for old_text, new_text in replacements:
        if new_text:
            replace_hwpx_paragraph_text(root, old_text, short_text(new_text, 1800), exact=True)
        else:
            replace_hwpx_paragraph_text(root, old_text, "", exact=True)


def patch_hwpx_editor_snapshot(root: ET.Element, section_index: int, snapshot: dict) -> None:
    if not isinstance(snapshot, dict):
        return
    body_paragraphs = root.findall("hp:p", HWPX_NS)
    for item in snapshot.get("paragraphs", []):
        if not isinstance(item, dict) or int(item.get("sec", -1)) != section_index:
            continue
        para_index = int(item.get("para", -1))
        if para_index < 0 or para_index >= len(body_paragraphs):
            continue
        paragraph = body_paragraphs[para_index]
        if paragraph.find("hp:tbl", HWPX_NS) is not None:
            continue
        set_hwpx_scope_text(paragraph, str(item.get("text") or ""))

    section_cells = [
        item for item in snapshot.get("cells", [])
        if isinstance(item, dict) and int(item.get("sec", -1)) == section_index
    ]
    if not section_cells:
        return
    for item in section_cells:
        para_index = int(item.get("para", -1))
        cell_index = int(item.get("cellIndex", -1))
        if cell_index < 0:
            continue
        target_table = None
        if para_index < 0 or para_index >= len(body_paragraphs):
            tables = []
        else:
            paragraph = body_paragraphs[para_index]
            tables = paragraph.findall("hp:tbl", HWPX_NS)
        control_index = int(item.get("controlIndex", 0) or 0)
        if 0 <= control_index < len(tables):
            target_table = tables[control_index]
        if target_table is None and section_index == 2:
            target_table = find_hwpx_grade_table(root)
        if target_table is None:
            candidates = [
                table for table in root.findall(".//hp:tbl", HWPX_NS)
                if len(table.findall(".//hp:tc", HWPX_NS)) > cell_index
            ]
            if candidates:
                target_table = candidates[0]
        if target_table is None:
            continue
        cells = target_table.findall(".//hp:tc", HWPX_NS)
        if cell_index >= len(cells):
            continue
        set_hwpx_scope_text(cells[cell_index], str(item.get("text") or ""))


TAG_SPAN_CACHE_LIMIT = 0


def hwpx_escape_text(value: object) -> str:
    text = re.sub(r"[ \t]*[\r\n]+[ \t]*", " ", str(value or ""))
    text = text.replace("\t", " ")
    # JSON can legally carry escaped NUL/control codes and lone surrogates;
    # XML 1.0 cannot. A bad model character must not corrupt the HWPX package.
    # Substitute visibly rather than silently remove neighbouring prose.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "\ufffd", text)
    text = re.sub(r"(?<=\S) {2,}(?=\S)", " ", text)
    return escape(text)


def get_hwpx_xml_scope_text(scope_xml: str) -> str:
    return "".join(
        match.group(2)
        for match in re.finditer(r"(<hp:t\b[^>]*>)(.*?)(</hp:t>)", scope_xml, re.DOTALL)
    )


def find_hwpx_tag_spans(xml_text: str, tag_name: str) -> list[tuple[int, int]]:
    """Return outer tag spans while preserving the original XML text."""
    safe_tag = re.escape(tag_name)
    tag_re = re.compile(rf"<{safe_tag}\b[^>]*/>|<{safe_tag}\b[^>]*>|</{safe_tag}>", re.DOTALL)
    spans: list[tuple[int, int]] = []
    depth = 0
    start = -1
    for match in tag_re.finditer(xml_text):
        token = match.group(0)
        is_close = token.startswith("</")
        is_self_close = token.endswith("/>")
        if is_close:
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    spans.append((start, match.end()))
                    start = -1
            continue
        if depth == 0:
            start = match.start()
        if not is_self_close:
            depth += 1
        elif depth == 0:
            spans.append((match.start(), match.end()))
            start = -1
    return spans


def find_hwpx_all_tag_spans(xml_text: str, tag_name: str) -> list[tuple[int, int]]:
    """Return all tag spans, including tags nested inside same-name ancestors."""
    safe_tag = re.escape(tag_name)
    tag_re = re.compile(rf"<{safe_tag}\b[^>]*/>|<{safe_tag}\b[^>]*>|</{safe_tag}>", re.DOTALL)
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for match in tag_re.finditer(xml_text):
        token = match.group(0)
        if token.startswith("</"):
            if stack:
                spans.append((stack.pop(), match.end()))
            continue
        if token.endswith("/>"):
            spans.append((match.start(), match.end()))
        else:
            stack.append(match.start())
    return sorted(spans, key=lambda item: item[0])


def set_hwpx_xml_scope_text(
    scope_xml: str,
    text: object,
    *,
    preserve_edge_whitespace: bool = True,
) -> str:
    """Replace only text nodes inside a paragraph/cell XML fragment."""
    current_text = get_hwpx_xml_scope_text(scope_xml)
    next_text = str(text or "")
    if preserve_edge_whitespace and next_text and current_text:
        leading = re.match(r"^\s*", current_text).group(0)
        trailing = re.search(r"\s*$", current_text).group(0)
        if leading and not next_text[:1].isspace():
            next_text = leading + next_text
        if trailing and not next_text[-1:].isspace():
            next_text = next_text + trailing
    if current_text == next_text:
        return scope_xml
    escaped = hwpx_escape_text(next_text)
    text_re = re.compile(r"(<hp:t\b[^>]*>)(.*?)(</hp:t>)", re.DOTALL)
    matches = list(text_re.finditer(scope_xml))
    if matches:
        parts: list[str] = []
        cursor = 0
        for index, match in enumerate(matches):
            parts.append(scope_xml[cursor:match.start()])
            parts.append(match.group(1))
            parts.append(escaped if index == 0 else "")
            parts.append(match.group(3))
            cursor = match.end()
        parts.append(scope_xml[cursor:])
        updated = "".join(parts)
        # linesegarray is a cached result of Hancom's old line layout.  Keeping
        # a one-line placeholder cache after inserting long prose makes rhwp,
        # kordoc and Hancom render the new text on top of itself.  Only the
        # changed scope is touched; the rest of the template keeps its cache.
        return re.sub(r"<hp:linesegarray>[\s\S]*?</hp:linesegarray>", "", updated)

    # Many official HWPX templates express an empty writing area as a
    # self-closing run (``<hp:run .../>``) without an hp:t node.  Treating
    # that as non-writable silently drops the generated section body.  Keep
    # the run's original character style and materialise only the missing
    # text node.
    if next_text:
        self_closing_run = re.search(r"<hp:run\b([^>]*)/>", scope_xml, re.DOTALL)
        if self_closing_run:
            attrs = self_closing_run.group(1)
            run_xml = f"<hp:run{attrs}><hp:t>{escaped}</hp:t></hp:run>"
            updated = scope_xml[:self_closing_run.start()] + run_xml + scope_xml[self_closing_run.end():]
            return re.sub(r"<hp:linesegarray>[\s\S]*?</hp:linesegarray>", "", updated)
        open_run = re.search(r"<hp:run\b[^>]*>", scope_xml, re.DOTALL)
        if open_run:
            run_end = scope_xml.find("</hp:run>", open_run.end())
            if run_end >= 0:
                updated = scope_xml[:run_end] + f"<hp:t>{escaped}</hp:t>" + scope_xml[run_end:]
                return re.sub(r"<hp:linesegarray>[\s\S]*?</hp:linesegarray>", "", updated)

    return scope_xml


def reconcile_hwpx_linesegarray_for_text(scope_xml: str, text: object) -> str:
    """Drop stale line segments whose text positions point past the replaced text."""
    text_length = len(str(text or ""))
    array_re = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.DOTALL)

    def update_array(match: re.Match) -> str:
        array_xml = match.group(0)
        line_matches = list(re.finditer(r"<hp:lineseg\b[^>]*/>", array_xml, re.DOTALL))
        if len(line_matches) <= 1:
            return array_xml
        kept: list[str] = []
        for index, line_match in enumerate(line_matches):
            line_xml = line_match.group(0)
            textpos_match = re.search(r'textpos="(\d+)"', line_xml)
            textpos = int(textpos_match.group(1)) if textpos_match else 0
            if index == 0 or textpos < text_length:
                kept.append(line_xml)
        if not kept:
            kept = [line_matches[0].group(0)]
        if len(kept) == len(line_matches):
            return array_xml
        return "<hp:linesegarray>" + "".join(kept) + "</hp:linesegarray>"

    return array_re.sub(update_array, scope_xml)


def is_hwpx_blank_bullet_line(line: object) -> bool:
    """Return true for lines that contain only a bullet marker."""
    return bool(re.match(r"^\s*(?:[-\u2022\u3147\u274d\u2219\u318d]|\d+[.)])\s*$", str(line or "")))


def set_hwpx_xml_scope_lines(scope_xml: str, lines: list[str]) -> str:
    """Set multiline text inside the existing XML scope without adding paragraphs."""
    clean_lines = [
        str(line or "").rstrip()
        for line in lines
        if not is_hwpx_blank_bullet_line(line)
    ]
    while clean_lines and not clean_lines[0].strip():
        clean_lines.pop(0)
    while clean_lines and not clean_lines[-1].strip():
        clean_lines.pop()
    if not clean_lines:
        return set_hwpx_xml_scope_text(scope_xml, "")
    content = "\n".join(clean_lines)
    return set_hwpx_xml_scope_text(scope_xml, content)


def remove_hwpx_section_properties_xml(paragraph_xml: str) -> str:
    """Avoid cloning section properties when a paragraph is expanded into many paragraphs."""
    spans = find_hwpx_tag_spans(paragraph_xml, "hp:secPr")
    for start, end in reversed(spans):
        paragraph_xml = paragraph_xml[:start] + paragraph_xml[end:]
    return paragraph_xml


def clone_hwpx_paragraph_for_semantic_lines(paragraph_xml: str, lines: list[str]) -> str:
    """Expand a placeholder paragraph to one template-styled paragraph per block."""
    clean_lines = [str(line or "").rstrip() for line in lines if str(line or "").strip()]
    if not clean_lines:
        return set_hwpx_xml_scope_text(paragraph_xml, "")
    clones: list[str] = []
    base_id_match = re.search(r'<hp:p\b[^>]*\bid="(\d+)"', paragraph_xml)
    base_id = int(base_id_match.group(1)) if base_id_match else 0
    for index, line in enumerate(clean_lines):
        clone = paragraph_xml if index == 0 else remove_hwpx_section_properties_xml(paragraph_xml)
        if index:
            paragraph_id = binascii.crc32(f"{base_id}|{index}|{line}".encode("utf-8")) & 0xFFFFFFFF
            clone = re.sub(
                r'(<hp:p\b[^>]*\bid=")\d+("[^>]*>)',
                rf"\g<1>{paragraph_id}\2",
                clone,
                count=1,
            )
        clone = set_hwpx_xml_scope_text(clone, line)
        clones.append(style_hwpx_detail_summary_label_xml(clone))
    return "".join(clones)


def parse_hwpx_tag_attrs(tag: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r'([A-Za-z_:][\w:.-]*)="([^"]*)"', tag)
    }


def set_hwpx_linesegarray_for_lines(scope_xml: str, lines: list[str]) -> str:
    """Keep Hancom line layout metadata aligned with inserted hp:lineBreak tags."""
    line_count = max(1, len(lines))
    array_re = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.DOTALL)
    match = array_re.search(scope_xml)
    if not match:
        return scope_xml
    first_line = re.search(r"<hp:lineseg\b[^>]*/>", match.group(0), re.DOTALL)
    if not first_line:
        return scope_xml
    attrs = parse_hwpx_tag_attrs(first_line.group(0))
    base_vert = int(attrs.get("vertpos", "0") or 0)
    vert_size = int(attrs.get("vertsize", attrs.get("textheight", "1000")) or 1000)
    spacing = int(attrs.get("spacing", "300") or 300)
    step = max(1, vert_size + spacing)
    text_pos = 0
    new_linesegs = []
    for index in range(line_count):
        attrs["textpos"] = str(text_pos)
        attrs["vertpos"] = str(base_vert + (step * index))
        new_linesegs.append("<hp:lineseg " + " ".join(f'{key}="{value}"' for key, value in attrs.items()) + "/>")
        if index < len(lines):
            text_pos += len(lines[index]) + 1
    return scope_xml[:match.start()] + "<hp:linesegarray>" + "".join(new_linesegs) + "</hp:linesegarray>" + scope_xml[match.end():]


def set_hwpx_paragraph_text_xml(xml_text: str, para_index: int, text: object) -> tuple[str, bool]:
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    if para_index < 0 or para_index >= len(spans):
        return xml_text, False
    start, end = spans[para_index]
    paragraph_xml = xml_text[start:end]
    if "<hp:tbl" in paragraph_xml:
        return xml_text, False
    updated = set_hwpx_xml_scope_text(paragraph_xml, text)
    if updated == paragraph_xml:
        return xml_text, False
    return xml_text[:start] + updated + xml_text[end:], True


def set_hwpx_paragraph_containing_text_xml(xml_text: str, required_parts: list[str], text: object) -> tuple[str, bool]:
    required = [str(part or "") for part in required_parts if str(part or "")]
    if not required:
        return xml_text, False
    for start, end in find_hwpx_all_tag_spans(xml_text, "hp:p"):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        current = get_hwpx_xml_scope_text(paragraph_xml)
        if not all(part in current for part in required):
            continue
        updated = set_hwpx_xml_scope_text(paragraph_xml, text)
        if updated == paragraph_xml:
            return xml_text, False
        return xml_text[:start] + updated + xml_text[end:], True
    return xml_text, False


def set_hwpx_manifest_paragraph_text_xml(
    xml_text: str,
    para_index: int,
    text: object,
    *,
    para_pr_id: int | None = None,
) -> tuple[str, bool]:
    spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    if para_index < 0 or para_index >= len(spans):
        return xml_text, False
    start, end = spans[para_index]
    paragraph_xml = xml_text[start:end]
    updated = set_hwpx_xml_scope_text(paragraph_xml, text)
    if para_pr_id is not None:
        updated = re.sub(
            r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*>)',
            rf"\g<1>{para_pr_id}\2",
            updated,
            count=1,
        )
    if updated == paragraph_xml:
        return xml_text, False
    return xml_text[:start] + updated + xml_text[end:], True


def set_hwpx_paragraph_lines_xml(xml_text: str, para_index: int, lines: list[str]) -> tuple[str, bool]:
    spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    if para_index < 0 or para_index >= len(spans):
        return xml_text, False
    start, end = spans[para_index]
    paragraph_xml = xml_text[start:end]
    if "<hp:tbl" in paragraph_xml:
        return xml_text, False
    updated = clone_hwpx_paragraph_for_semantic_lines(paragraph_xml, lines)
    if updated == paragraph_xml:
        return xml_text, False
    return xml_text[:start] + updated + xml_text[end:], True


def set_hwpx_paragraph_run_text_xml(xml_text: str, para_index: int, run_index: int, text: object) -> tuple[str, bool]:
    paragraph_spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    if para_index < 0 or para_index >= len(paragraph_spans):
        return xml_text, False
    para_start, para_end = paragraph_spans[para_index]
    paragraph_xml = xml_text[para_start:para_end]
    run_spans = find_hwpx_tag_spans(paragraph_xml, "hp:run")
    if run_index < 0 or run_index >= len(run_spans):
        return xml_text, False
    run_start, run_end = run_spans[run_index]
    run_xml = paragraph_xml[run_start:run_end]
    updated_run = set_hwpx_xml_scope_text(run_xml, text)
    if updated_run == run_xml:
        return xml_text, False
    updated_paragraph = paragraph_xml[:run_start] + updated_run + paragraph_xml[run_end:]
    return xml_text[:para_start] + updated_paragraph + xml_text[para_end:], True


def set_hwpx_paragraph_text_node_xml(
    xml_text: str,
    para_index: int,
    text_node_index: int,
    text: object,
    *,
    expected_source_text: str | None = None,
) -> tuple[str, bool]:
    paragraph_spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    if para_index < 0 or para_index >= len(paragraph_spans):
        raise ValueError(f"HWPX text slot paragraph not found: paragraph_index={para_index}")
    para_start, para_end = paragraph_spans[para_index]
    paragraph_xml = xml_text[para_start:para_end]
    text_re = re.compile(r"(<hp:t\b[^>]*>)(.*?)(</hp:t>)", re.DOTALL)
    matches = list(text_re.finditer(paragraph_xml))
    if text_node_index < 0 or text_node_index >= len(matches):
        raise ValueError(
            f"HWPX text slot node not found: paragraph_index={para_index}, text_node_index={text_node_index}"
        )
    match = matches[text_node_index]
    if expected_source_text is not None and match.group(2) != expected_source_text:
        raise ValueError(
            "HWPX text slot source mismatch: "
            f"paragraph_index={para_index}, text_node_index={text_node_index}, "
            f"expected={expected_source_text!r}, actual={match.group(2)!r}"
        )
    escaped = hwpx_escape_text(text)
    updated_paragraph = (
        paragraph_xml[:match.start()]
        + match.group(1)
        + escaped
        + match.group(3)
        + paragraph_xml[match.end():]
    )
    if updated_paragraph == paragraph_xml:
        return xml_text, False
    return xml_text[:para_start] + updated_paragraph + xml_text[para_end:], True


def replace_hwpx_paragraph_last_text_xml(
    xml_text: str,
    para_index: int,
    old_text: str,
    new_text: object,
) -> tuple[str, bool]:
    paragraph_spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    if para_index < 0 or para_index >= len(paragraph_spans):
        return xml_text, False
    para_start, para_end = paragraph_spans[para_index]
    paragraph_xml = xml_text[para_start:para_end]
    text_re = re.compile(r"(<hp:t\b[^>]*>)(.*?)(</hp:t>)", re.DOTALL)
    matches = [match for match in text_re.finditer(paragraph_xml) if match.group(2).strip() == old_text]
    if not matches:
        return xml_text, False
    match = matches[-1]
    leading = re.match(r"^\s*", match.group(2)).group(0)
    trailing = re.search(r"\s*$", match.group(2)).group(0)
    updated_paragraph = (
        paragraph_xml[:match.start()]
        + match.group(1)
        + leading
        + hwpx_escape_text(new_text)
        + trailing
        + match.group(3)
        + paragraph_xml[match.end():]
    )
    return xml_text[:para_start] + updated_paragraph + xml_text[para_end:], True


def replace_hwpx_paragraph_last_text_by_label_xml(
    xml_text: str,
    label: str,
    old_text: str,
    new_text: object,
) -> tuple[str, bool]:
    paragraph_spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    for index, (para_start, para_end) in enumerate(paragraph_spans):
        paragraph_xml = xml_text[para_start:para_end]
        if label not in get_hwpx_xml_scope_text(paragraph_xml):
            continue
        text_re = re.compile(r"(<hp:t\b[^>]*>)(.*?)(</hp:t>)", re.DOTALL)
        matches = [match for match in text_re.finditer(paragraph_xml) if match.group(2).strip() == old_text]
        if not matches:
            if index + 1 < len(paragraph_spans):
                next_start, next_end = paragraph_spans[index + 1]
                next_paragraph_xml = xml_text[next_start:next_end]
                if get_hwpx_xml_scope_text(next_paragraph_xml).strip() == old_text:
                    next_matches = [match for match in text_re.finditer(next_paragraph_xml) if match.group(2).strip() == old_text]
                    if next_matches:
                        match = next_matches[-1]
                        leading = re.match(r"^\s*", match.group(2)).group(0)
                        trailing = re.search(r"\s*$", match.group(2)).group(0)
                        updated_paragraph = (
                            next_paragraph_xml[:match.start()]
                            + match.group(1)
                            + leading
                            + hwpx_escape_text(new_text)
                            + trailing
                            + match.group(3)
                            + next_paragraph_xml[match.end():]
                        )
                        return xml_text[:next_start] + updated_paragraph + xml_text[next_end:], True
            continue
        match = matches[-1]
        leading = re.match(r"^\s*", match.group(2)).group(0)
        trailing = re.search(r"\s*$", match.group(2)).group(0)
        updated_paragraph = (
            paragraph_xml[:match.start()]
            + match.group(1)
            + leading
            + hwpx_escape_text(new_text)
            + trailing
            + match.group(3)
            + paragraph_xml[match.end():]
            )
        return xml_text[:para_start] + updated_paragraph + xml_text[para_end:], True
    return xml_text, False


def _toc_labeled_numeric_target(
    xml_text: str,
    label: str,
) -> tuple[int, int, str, re.Match[str]] | None:
    from .toc_registry import normalized_title
    candidates: list[tuple[int, int, str]] = []
    for start, end in find_hwpx_all_tag_spans(xml_text, "hp:p"):
        paragraph = xml_text[start:end]
        # Only an individual row may own this number. Never fall through to
        # the surrounding text box and accidentally use another row's number.
        own_row = len(re.findall(r'<hp:p\b', paragraph)) == 1 or (
            paragraph.count('name="toc_number_') == 1 and paragraph.count('name="toc_label_') == 1)
        if own_row and normalized_title(get_hwpx_xml_scope_text(paragraph)).startswith(normalized_title(label)):
            candidates.append((start, end, paragraph))
    for start, end, paragraph in sorted(candidates, key=lambda row: len(row[2])):
        matches = list(re.finditer(r"(<hp:t\b[^>]*>)(\s*\d+\s*)(</hp:t>)", paragraph))
        if matches:
            return start, end, paragraph, matches[-1]
    return None


def _overwrite_toc_labeled_page_number(
    xml_text: str,
    label: str,
    value: object,
) -> tuple[str, bool]:
    target = _toc_labeled_numeric_target(xml_text, label)
    if target is None:
        return xml_text, False
    start, end, paragraph, match = target
    leading = re.match(r"^\s*", match.group(2)).group(0)
    trailing = re.search(r"\s*$", match.group(2)).group(0)
    updated = (
        paragraph[:match.start()]
        + match.group(1)
        + leading
        + hwpx_escape_text(value)
        + trailing
        + match.group(3)
        + paragraph[match.end():]
    )
    if updated == paragraph:
        return xml_text, False
    return xml_text[:start] + updated + xml_text[end:], True


def _remove_legacy_achievement_toc_page_paragraph_xml(xml_text: str) -> tuple[str, bool]:
    """Remove the template's now-obsolete blank dotted page-number row.

    The source template stores the IV heading and its page number in adjacent
    paragraphs.  After both values are merged into the heading, leaving the
    second paragraph behind renders a leader-only row below ``성과달성도``.
    Only the immediately following, text-empty dotted-tab paragraph is
    removed; the intentional spacer paragraph after it is preserved.
    """

    spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    candidates = sorted(
        (
            (start, end)
            for start, end in spans
            if "성과달성도" in get_hwpx_xml_scope_text(xml_text[start:end])
        ),
        key=lambda span: span[1] - span[0],
    )
    for start, end in candidates:
        following = next(
            ((next_start, next_end) for next_start, next_end in spans if next_start >= end),
            None,
        )
        if following is None:
            continue
        next_start, next_end = following
        next_paragraph = xml_text[next_start:next_end]
        visible_text = re.sub(r"<[^>]+>", "", get_hwpx_xml_scope_text(next_paragraph)).strip()
        if visible_text:
            continue
        tab = re.search(r'<hp:tab\b[^>]*\bleader="3"[^>]*/>', next_paragraph)
        if tab is None:
            continue
        return xml_text[:next_start] + xml_text[next_end:], True
    return xml_text, False


def _ensure_achievement_toc_leader_xml(xml_text: str, page_value: object = "") -> tuple[str, bool]:
    """Guarantee the achievement TOC entry has its dotted leader and page run."""

    # Fixed-column rows already contain their leader and machine-owned number.
    # Do not insert a second number into their nested label paragraph.
    if 'name="toc_number_achievement_page"' in xml_text:
        return xml_text, False

    candidates = [
        (start, end, xml_text[start:end])
        for start, end in find_hwpx_all_tag_spans(xml_text, "hp:p")
        if "성과달성도" in get_hwpx_xml_scope_text(xml_text[start:end])
    ]
    for start, end, paragraph in sorted(candidates, key=lambda row: len(row[2])):
        updated = paragraph
        tab = re.search(r"<hp:tab\b[^>]*/>", updated)
        if tab:
            tab_xml = tab.group(0)
            for attribute, value in (("width", "33800"), ("leader", "3"), ("type", "2")):
                if re.search(rf'\b{attribute}="[^"]*"', tab_xml):
                    tab_xml = re.sub(rf'(\b{attribute}=")[^"]*(")', rf"\g<1>{value}\2", tab_xml, count=1)
                else:
                    tab_xml = tab_xml[:-2] + f' {attribute}="{value}"/>'
            updated = updated[:tab.start()] + tab_xml + updated[tab.end():]
        else:
            heading_run_end = updated.find("</hp:run>")
            if heading_run_end >= 0:
                heading_run_end += len("</hp:run>")
                leader_run = '<hp:run charPrIDRef="83"><hp:t><hp:tab width="33800" leader="3" type="1"/></hp:t></hp:run>'
                updated = updated[:heading_run_end] + leader_run + updated[heading_run_end:]
        value = str(page_value or "").strip()
        if value:
            number_run = re.search(r'(<hp:run\b[^>]*\bcharPrIDRef="61"[^>]*>\s*<hp:t\b[^>]*>)(\s*\d*\s*)(</hp:t>\s*</hp:run>)', updated)
            if number_run:
                updated = (
                    updated[:number_run.start()]
                    + number_run.group(1)
                    + hwpx_escape_text(value)
                    + number_run.group(3)
                    + updated[number_run.end():]
                )
            else:
                page_run = f'<hp:run charPrIDRef="61"><hp:t>{hwpx_escape_text(value)}</hp:t></hp:run>'
                insert_at = updated.find("<hp:linesegarray")
                if insert_at < 0:
                    insert_at = updated.rfind("</hp:p>")
                updated = updated[:insert_at] + page_run + updated[insert_at:]
        # RHWP follows the official TOC pattern where the label and leader
        # live in the same hp:t. A leader placed in a separate run is rendered
        # as a detached line at the top of the page even with a valid cache.
        label_run = re.search(
            r'<hp:run\b[^>]*\bcharPrIDRef="78"[^>]*>\s*<hp:t\b[^>]*>([\s\S]*?)</hp:t>\s*</hp:run>',
            updated,
        )
        tab_run = re.search(
            r'<hp:run\b[^>]*\bcharPrIDRef="83"[^>]*>\s*<hp:t\b[^>]*>\s*(<hp:tab\b[^>]*/>)\s*</hp:t>\s*</hp:run>',
            updated,
        )
        if label_run and tab_run and label_run.end() <= tab_run.start():
            label_xml = label_run.group(0).replace("</hp:t>", tab_run.group(1) + "</hp:t>", 1)
            updated = (
                updated[:label_run.start()]
                + label_xml
                + updated[label_run.end():tab_run.start()]
                + updated[tab_run.end():]
            )
        # TOC paragraphs use reviewed absolute line coordinates. Dropping this
        # one cache while every neighbouring entry keeps its cache makes rhwp
        # place IV at the top of the page. The text still fits the original
        # one-line geometry, so preserve its linesegarray.
        rewritten = xml_text[:start] + updated + xml_text[end:]
        rewritten, removed_legacy_row = _remove_legacy_achievement_toc_page_paragraph_xml(rewritten)
        return rewritten, updated != paragraph or removed_legacy_row
    return xml_text, False


def patch_hwpx_section2_toc_page_numbers_xml(xml_text: str, page_numbers: dict) -> tuple[str, int]:
    # After the normal second pass, the achievement number is merged into its
    # heading and the old number-only paragraph is removed. Static paragraph
    # indexes no longer apply at that point, so RHWP visual-QA synchronization
    # must update entries by their stable visible labels.
    is_populated = any(
        target is not None and target[3].group(2).strip() not in {"", "0"}
        for key, label in TOC_SECTION2_LABELS.items()
        if key in page_numbers
        for target in [_toc_labeled_numeric_target(xml_text, label)]
    )
    if is_populated:
        changed_count = 0
        for key, label in TOC_SECTION2_LABELS.items():
            value = str(page_numbers.get(key) or "").strip()
            if not value:
                continue
            xml_text, changed = _overwrite_toc_labeled_page_number(xml_text, label, value)
            changed_count += int(changed)
        xml_text, changed = _ensure_achievement_toc_leader_xml(
            xml_text, page_numbers.get("achievement_page")
        )
        changed_count += int(changed)
        return xml_text, changed_count

    changed_count = 0
    xml_text, changed = set_hwpx_manifest_paragraph_text_xml(xml_text, TOC_SECTION2_NOTICE_SPAN_INDEX, "")
    changed_count += 1 if changed else 0
    for key, para_index in TOC_SECTION2_TEXT_SPAN_INDEXES.items():
        if key == "achievement_page":
            # The source template places the IV heading and its page number
            # in two separate paragraphs. Handle that exceptional layout
            # after every regular entry so later indexes remain stable.
            continue
        value = str(page_numbers.get(key) or "").strip()
        xml_text, changed = replace_hwpx_paragraph_last_text_xml(xml_text, para_index, "0", value)
        if value and not changed:
            # The first pass deliberately clears placeholder zeroes.  The
            # second pass therefore writes into the same now-empty text node.
            xml_text, changed = replace_hwpx_paragraph_last_text_xml(xml_text, para_index, "", value)
        if value and not changed:
            # RHWP visual QA can provide an authoritative page map after the
            # kordoc pass. Allow that third pass to overwrite an existing
            # numeric value instead of treating the fixed TOC as immutable.
            spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
            if 0 <= para_index < len(spans):
                start, end = spans[para_index]
                paragraph = xml_text[start:end]
                matches = list(re.finditer(r"(<hp:t\b[^>]*>)(\s*\d+\s*)(</hp:t>)", paragraph))
                if matches:
                    match = matches[-1]
                    leading = re.match(r"^\s*", match.group(2)).group(0)
                    trailing = re.search(r"\s*$", match.group(2)).group(0)
                    updated = (
                        paragraph[:match.start()]
                        + match.group(1)
                        + leading
                        + hwpx_escape_text(value)
                        + trailing
                        + match.group(3)
                        + paragraph[match.end():]
                    )
                    if updated != paragraph:
                        xml_text = xml_text[:start] + updated + xml_text[end:]
                        changed = True
        changed_count += 1 if changed else 0
    achievement_value = str(page_numbers.get("achievement_page") or "").strip()
    achievement_index = TOC_SECTION2_TEXT_SPAN_INDEXES["achievement_page"]
    if not achievement_value:
        xml_text, changed = replace_hwpx_paragraph_last_text_xml(xml_text, achievement_index, "0", "")
        changed_count += 1 if changed else 0
    else:
        # Once populated, the achievement page number lives in the same
        # paragraph as the IV heading and its old number-only paragraph has
        # been removed. Update that inline run during a RHWP-sync pass.
        existing_heading_changed = False
        for heading_start, heading_end in find_hwpx_all_tag_spans(xml_text, "hp:p"):
            heading_xml = xml_text[heading_start:heading_end]
            if "성과달성도" not in get_hwpx_xml_scope_text(heading_xml):
                continue
            matches = list(re.finditer(r"(<hp:t\b[^>]*>)(\s*\d+\s*)(</hp:t>)", heading_xml))
            if not matches:
                continue
            match = matches[-1]
            leading = re.match(r"^\s*", match.group(2)).group(0)
            trailing = re.search(r"\s*$", match.group(2)).group(0)
            updated_heading = (
                heading_xml[:match.start()]
                + match.group(1)
                + leading
                + hwpx_escape_text(achievement_value)
                + trailing
                + match.group(3)
                + heading_xml[match.end():]
            )
            if updated_heading != heading_xml:
                xml_text = xml_text[:heading_start] + updated_heading + xml_text[heading_end:]
                changed_count += 1
            existing_heading_changed = True
            break
        if existing_heading_changed:
            xml_text, changed = _ensure_achievement_toc_leader_xml(xml_text, achievement_value)
            changed_count += int(changed)
            return xml_text, changed_count
        spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
        heading_index = achievement_index - 1
        if achievement_index < len(spans) and heading_index >= 0:
            heading_start, heading_end = spans[heading_index]
            page_start, page_end = spans[achievement_index]
            heading_xml = xml_text[heading_start:heading_end]
            page_xml = xml_text[page_start:page_end]
            page_tab = re.search(r"<hp:tab\b[^>]*/>", page_xml)
            heading_tab = re.search(r"<hp:tab\b[^>]*/>", heading_xml)
            if page_tab and heading_tab:
                achievement_tab = re.sub(
                    r'\bwidth="\d+"',
                    'width="33800"',
                    page_tab.group(0),
                    count=1,
                )
                heading_xml = (
                    heading_xml[:heading_tab.start()]
                    + achievement_tab
                    + heading_xml[heading_tab.end():]
                )
                page_run = f'<hp:run charPrIDRef="61"><hp:t>{hwpx_escape_text(achievement_value)}</hp:t></hp:run>'
                lineseg_at = heading_xml.find("<hp:linesegarray")
                if lineseg_at < 0:
                    lineseg_at = heading_xml.rfind("</hp:p>")
                heading_xml = heading_xml[:lineseg_at] + page_run + heading_xml[lineseg_at:]
                # Remove the old number-only paragraph only on the populated
                # second pass so no blank line remains below the heading.
                xml_text = (
                    xml_text[:heading_start]
                    + heading_xml
                    + xml_text[heading_end:page_start]
                    + xml_text[page_end:]
                )
                changed_count += 1
    if achievement_value:
        xml_text, changed = _ensure_achievement_toc_leader_xml(xml_text, achievement_value)
        changed_count += int(changed)
    return xml_text, changed_count


def replace_hwpx_text_xml(xml_text: str, old_text: str, new_text: object) -> tuple[str, int]:
    escaped_old = re.escape(old_text)
    text_re = re.compile(rf"(<hp:t\b[^>]*>){escaped_old}(</hp:t>)", re.DOTALL)
    escaped_new = hwpx_escape_text(new_text)
    xml_text, count = text_re.subn(lambda match: f"{match.group(1)}{escaped_new}{match.group(2)}", xml_text)
    return xml_text, count


def wrap_hwpx_report_line(line: str, width: int = 48) -> list[str]:
    line = re.sub(r"\s+", " ", str(line or "")).strip()
    if not line:
        return []
    if len(line) <= width:
        return [line]
    parts: list[str] = []
    current = line
    while len(current) > width:
        split_at = -1
        for pattern in ("다. ", "음. ", "함. ", ". ", ", ", " "):
            pos = current.rfind(pattern, 0, width + 1)
            if pos >= max(18, width // 2):
                split_at = pos + len(pattern)
                break
        if split_at < 0:
            split_at = width
        parts.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        parts.append(current)
    return parts


def hwpx_report_body_lines(text: object, max_chars: int = 10000) -> list[str]:
    # Final report prose must retain sentence punctuation and outline tokens.
    # ``short_text`` is designed for legacy evaluation cards and calls
    # ``clean_evaluation_text``, which deliberately removes Korean full stops
    # (including the dot in ``가.``). Applying it here collapsed both sentence
    # boundaries and indentation semantics in the exported HWPX.
    raw = str(text or "")
    if len(raw) > max_chars:
        raw = raw[: max_chars - 1].rstrip() + "…"
    raw = raw.replace("\r", "\n")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines: list[str] = []
    for block in raw.split("\n"):
        line = str(block or "").rstrip()
        if not line.strip():
            # Empty template paragraphs often carry a coloured bullet style.
            # Paragraph spacing is controlled by the report styles, so a
            # semantic blank line must not become a visible red/black marker.
            continue
        if is_hwpx_blank_bullet_line(line):
            continue
        line = line.lstrip() if re.match(r"^\s*(?:[-•ㅇ❍∙ㆍ]|\d+[.)])\s+", line) else line.strip()
        # Keep the report's two-level list hierarchy. Decorative glyphs are
        # normalized to the black reader-text marker, while a literal hyphen
        # remains a second-level item instead of being flattened to another
        # circle.
        line = re.sub(r"^(?:[•❍∙ㆍ])\s+", "ㅇ ", line)
        if re.match(r"^ㅇ\s+", line):
            line = " ㅇ " + re.sub(r"^ㅇ\s+", "", line)
        elif re.match(r"^-\s+", line):
            line = "  - " + re.sub(r"^-\s+", "", line)

        # Long LLM prose should reflow as report paragraphs, not as a single
        # wall of text. Only plain narrative is split; headings and list items
        # keep their semantic grouping.
        if (
            len(line) > 180
            and not re.match(r"^\s*(?:[-ㅇ]|[가-하][.)]|\(?\d+(?:\.\d+)*(?:[.)]))\s+", line)
        ):
            sentences = [item.strip() for item in re.split(r"(?<=[.!?。])\s+", line) if item.strip()]
            if len(sentences) > 1:
                paragraph = ""
                for sentence in sentences:
                    candidate = f"{paragraph} {sentence}".strip()
                    if paragraph and len(candidate) > 180:
                        lines.append(paragraph)
                        paragraph = sentence
                    else:
                        paragraph = candidate
                if paragraph:
                    lines.append(paragraph)
                continue
        lines.append(line)
    return deduplicate_hwpx_outline_labels(lines) or ["확인 필요"]


# Fixed evaluation-report outline contract.
#
# The paragraph definitions live in the official HWPX template header.  In
# HWPUNIT character coordinates their active values are:
#
#   subheading (67): marker 0,    text 0
#   bullet     (69): fixed first-level position from the report template
#   detail     (92): marker 3831, continuation 4831
#
# Therefore a detail dash starts exactly where its parent ``ㅇ`` text starts,
# while wrapped lines start 1000 HWPUNIT farther right, aligned with the first
# line's prose after the literal ``- `` marker. Keep this mapping explicit
# instead of inheriting the paragraph being replaced.
HWPX_REPORT_OUTLINE_STYLE_BY_KIND: dict[str, tuple[str, str, str]] = {
    "subheading": ("67", "0", "18"),
    "bullet": ("69", "0", "28"),
    "detail": ("92", "0", "28"),
    "body": ("71", "0", "28"),
}


HWPX_REPORT_OUTLINE_MARGIN_BY_PARA_PR: dict[str, tuple[int, int, int, int]] = {
    # case left, case intent, default left, default intent
    # First-line marker = left + intent = 3831/7662. Continuation lines use
    # one 10pt tab (1000/2000) after the marker, matching ``ㅇ`` paragraph
    # wrapping and the reference report's literal ``- `` text start.
    "92": (4831, -1000, 9662, -2000),
}


HWPX_REPORT_DETAIL_AFTER_SPACING = int(
    (writing_profile().get("narrative_detail_layout") or {}).get(
        "paragraph_spacing_after_hwpunit"
    )
    or 300
)


def patch_hwpx_report_outline_header_xml(xml_text: str) -> str:
    """Tune hanging indents for literal ``ㅇ `` and ``- `` markers.

    ``ㅇ`` keeps the official template's fixed first-level position. ``-``
    keeps its marker at the parent text start, while the paragraph's left
    margin is placed after the literal marker. A negative first-line intent
    brings only the dash back to the marker position, so every wrapped line
    begins at the first line's prose position in both HWPUNIT branches.
    """

    def replace_margin_value(scope: str, tag: str, value: int) -> str:
        return re.sub(
            rf'(<hc:{tag}\b[^>]*\bvalue=")-?\d+("[^>]*/>)',
            rf"\g<1>{value}\g<2>",
            scope,
            count=1,
        )

    for para_pr_id, (case_left, case_intent, default_left, default_intent) in HWPX_REPORT_OUTLINE_MARGIN_BY_PARA_PR.items():
        paragraph_re = re.compile(
            rf'(<hh:paraPr\b[^>]*\bid="{para_pr_id}"[^>]*>)(.*?)(</hh:paraPr>)',
            re.DOTALL,
        )
        paragraph_match = paragraph_re.search(xml_text)
        if not paragraph_match:
            continue
        paragraph_xml = paragraph_match.group(0)

        def patch_branch(branch_match: re.Match[str], left: int, intent: int) -> str:
            branch_xml = replace_margin_value(branch_match.group(0), "intent", intent)
            branch_xml = replace_margin_value(branch_xml, "left", left)
            if para_pr_id == "92":
                branch_xml = replace_margin_value(
                    branch_xml,
                    "next",
                    HWPX_REPORT_DETAIL_AFTER_SPACING,
                )
            return branch_xml

        paragraph_xml = re.sub(
            r"<hp:case\b.*?</hp:case>",
            lambda match: patch_branch(match, case_left, case_intent),
            paragraph_xml,
            count=1,
            flags=re.DOTALL,
        )
        paragraph_xml = re.sub(
            r"<hp:default\b.*?</hp:default>",
            lambda match: patch_branch(match, default_left, default_intent),
            paragraph_xml,
            count=1,
            flags=re.DOTALL,
        )
        xml_text = xml_text[:paragraph_match.start()] + paragraph_xml + xml_text[paragraph_match.end():]
    return xml_text


def hwpx_report_outline_kind(value: object) -> str:
    """Classify a report paragraph into the fixed three-level hierarchy."""
    stripped = str(value or "").strip()
    if re.match(r"^-\s*\S", stripped):
        return "detail"
    if re.match(r"^(?:[•ㅇ❍∙ㆍ])\s*\S", stripped):
        return "bullet"
    if (
        len(stripped) <= 110
        and re.match(r"^(?:[가-하][.)]|\(?\d+(?:\.\d+)*(?:[.)])|[①-⑳])\s*", stripped)
    ):
        return "subheading"
    return "body"


def apply_hwpx_report_outline_style_xml(paragraph_xml: str, kind: str) -> str:
    """Apply the canonical indent/font tuple for a semantic outline level."""
    para_pr, style_id, char_pr = HWPX_REPORT_OUTLINE_STYLE_BY_KIND.get(
        kind,
        HWPX_REPORT_OUTLINE_STYLE_BY_KIND["body"],
    )
    paragraph_xml = re.sub(
        r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+("[^>]*\bstyleIDRef=")\d+("[^>]*>)',
        rf"\g<1>{para_pr}\g<2>{style_id}\g<3>",
        paragraph_xml,
        count=1,
    )
    return re.sub(
        r'(<hp:run\b[^>]*\bcharPrIDRef=")\d+("[^>]*>)',
        rf"\g<1>{char_pr}\g<2>",
        paragraph_xml,
    )


def style_hwpx_detail_summary_label_xml(paragraph_xml: str) -> str:
    """Bold only ``(핵심어)`` in a canonical ``-`` detail paragraph.

    Character style 18 is the template's existing 11pt bold counterpart of
    the regular 11pt body style 28, so the label gains emphasis without a
    font-size change or a new character definition.
    """

    text = re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph_xml)).strip()
    match = re.match(r"^-\s+(\([^()]{2,15}\))\s+(.+)$", text)
    if not match or "<hp:tbl" in paragraph_xml:
        return paragraph_xml
    run_spans = find_hwpx_tag_spans(paragraph_xml, "hp:run")
    if not run_spans:
        return paragraph_xml

    def run(char_pr_id: int, value: str) -> str:
        return (
            f'<hp:run charPrIDRef="{char_pr_id}">'
            f'<hp:t xml:space="preserve">{hwpx_escape_text(value)}</hp:t>'
            '</hp:run>'
        )

    first_start = run_spans[0][0]
    last_end = run_spans[-1][1]
    styled_runs = (
        run(28, "- ")
        + run(18, match.group(1))
        + run(28, " " + match.group(2))
    )
    return paragraph_xml[:first_start] + styled_runs + paragraph_xml[last_end:]


def normalize_hwpx_report_outline_styles_xml(xml_text: str) -> tuple[str, int]:
    """Force ``가./나.`` → ``ㅇ`` → ``-`` alignment outside tables.

    This final pass also covers the static summary labels (for example
    ``나. 사업개요`` and ``ㅇ 추진개요``), not only dynamic slot values.
    """
    changed_count = 0
    for start, end in reversed(find_hwpx_tag_spans(xml_text, "hp:p")):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        kind = hwpx_report_outline_kind(paragraph_text)
        if kind not in {"subheading", "bullet", "detail"}:
            continue
        updated = paragraph_xml
        if kind == "detail":
            # No literal indentation belongs before a child dash. paraPr 92
            # positions the marker at the parent ㅇ text start for every
            # narrative section, including legacy drafts that contain spaces.
            updated = set_hwpx_xml_scope_text(
                updated,
                "- " + re.sub(r"^-\s*", "", paragraph_text),
                preserve_edge_whitespace=False,
            )
        updated = apply_hwpx_report_outline_style_xml(updated, kind)
        updated = style_hwpx_detail_summary_label_xml(updated)
        if updated == paragraph_xml:
            continue
        xml_text = xml_text[:start] + updated + xml_text[end:]
        changed_count += 1
    return xml_text, changed_count


def normalized_hwpx_outline_label(value: object) -> str:
    """Return a comparison key for an outline label without its marker."""
    label = str(value or "").strip()
    previous = None
    # A repeated title may carry more than one prefix, for example
    # ``ㅇ 7. 그 외 평가기준``.  Peel every leading outline token instead of
    # stopping after the first marker.
    while label and label != previous:
        previous = label
        label = re.sub(
            r"^\s*(?:[-•ㅇ❍∙ㆍ]|[가-하][.)]|\(?\d+(?:\.\d+)*(?:[.)]))\s*",
            "",
            label,
        ).strip()
    label = label.strip().strip("()[]【】").strip()
    label = re.sub(r"\s*[:：]\s*$", "", label)
    return re.sub(r"[\s·ㆍ_-]+", "", label).strip().casefold()


def strip_redundant_hwpx_outer_heading_lines(lines: list[str], heading: object) -> list[str]:
    """Drop body paragraphs that exactly repeat the fixed HWPX heading."""

    heading_key = normalized_hwpx_outline_label(heading)
    if not heading_key:
        return list(lines)
    return [
        line for line in lines
        if normalized_hwpx_outline_label(line) != heading_key
    ]


def strip_redundant_hwpx_child_label(line: object, parent_label: object) -> str:
    """Remove only an explicit child label that repeats its parent heading."""
    value = str(line or "")
    match = re.match(
        r"^(?P<prefix>\s*(?:[-•ㅇ❍∙ㆍ]\s*)?)[\(\[【]\s*(?P<label>[^\)\]】]{1,60})\s*[\)\]】]\s*[:：]?\s*(?P<body>.+)$",
        value,
    )
    if not match:
        match = re.match(
            r"^(?P<prefix>\s*(?:[-•ㅇ❍∙ㆍ]\s*)?)(?P<label>[^:：]{1,60})\s*[:：]\s*(?P<body>.+)$",
            value,
        )
    if not match:
        return value
    if normalized_hwpx_outline_label(match.group("label")) != normalized_hwpx_outline_label(parent_label):
        return value
    return f'{match.group("prefix")}{match.group("body").lstrip()}'


def deduplicate_hwpx_outline_labels(lines: list[str]) -> list[str]:
    """Normalize outline markers while preserving every detail summary label.

    ``- (핵심어)`` is a reviewed reader-facing element even when the summary
    resembles its parent ``ㅇ`` topic. Fixed HWPX section-title duplication is
    handled independently by ``strip_redundant_hwpx_outer_heading_lines``.
    """
    normalized: list[str] = []
    parent_label = ""
    for raw_line in lines:
        line = str(raw_line or "").strip()
        parent_match = re.match(r"^(?:[•ㅇ❍∙ㆍ])\s+(.+?)\s*$", line)
        if parent_match:
            parent_label = parent_match.group(1)
            normalized.append(" ㅇ " + parent_label)
            continue
        if not re.match(r"^-\s+", line):
            parent_label = ""
        normalized.append("  - " + re.sub(r"^-\s+", "", line) if re.match(r"^-\s+", line) else line)
    return normalized


def replace_hwpx_paragraph_exact_with_lines_xml(xml_text: str, old_text: str, lines: list[str]) -> tuple[str, int]:
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    for start, end in spans:
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        if get_hwpx_xml_scope_text(paragraph_xml).strip() != old_text:
            continue
        updated_paragraph = clone_hwpx_paragraph_for_semantic_lines(paragraph_xml, lines)
        return xml_text[:start] + updated_paragraph + xml_text[end:], 1
    return xml_text, 0


def replace_hwpx_paragraph_containing_with_lines_xml(
    xml_text: str,
    required_parts: list[str],
    lines: list[str],
) -> tuple[str, int]:
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    required = [part for part in required_parts if part]
    for start, end in spans:
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if not paragraph_text or not all(part in paragraph_text for part in required):
            continue
        updated_paragraph = clone_hwpx_paragraph_for_semantic_lines(paragraph_xml, lines)
        return xml_text[:start] + updated_paragraph + xml_text[end:], 1
    return xml_text, 0


def replace_blank_paragraph_before_heading_xml(
    xml_text: str,
    heading_text: str,
    lines: list[str],
) -> tuple[str, int]:
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    heading_index = -1
    for index, (start, end) in enumerate(spans):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        if heading_text in get_hwpx_xml_scope_text(paragraph_xml).strip():
            heading_index = index
            break
    if heading_index < 0:
        return xml_text, 0
    for index in range(heading_index - 1, -1, -1):
        start, end = spans[index]
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if paragraph_text:
            break
        updated_paragraph = set_hwpx_xml_scope_lines(paragraph_xml, lines)
        return xml_text[:start] + updated_paragraph + xml_text[end:], 1
    return xml_text, 0


def replace_last_paragraph_containing_before_heading_xml(
    xml_text: str,
    required_parts: list[str],
    heading_text: str,
    lines: list[str],
) -> tuple[str, int]:
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    heading_index = -1
    for index, (start, end) in enumerate(spans):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        if heading_text in get_hwpx_xml_scope_text(paragraph_xml).strip():
            heading_index = index
            break
    if heading_index < 0:
        return xml_text, 0
    required = [part for part in required_parts if part]
    for index in range(heading_index - 1, -1, -1):
        start, end = spans[index]
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if paragraph_text and all(part in paragraph_text for part in required):
            updated_paragraph = set_hwpx_xml_scope_lines(paragraph_xml, lines)
            if updated_paragraph != paragraph_xml:
                return xml_text[:start] + updated_paragraph + xml_text[end:], 1
    return xml_text, 0


def append_hwpx_lines_to_heading_text_xml(xml_text: str, heading_text: str, body: object) -> tuple[str, bool]:
    """Append body lines after a heading paragraph without dense lineBreak runs."""
    lines = hwpx_report_body_lines(body, 10000)
    if not lines:
        return xml_text, False
    if hwpx_body_lines_present_xml(xml_text, lines):
        return xml_text, False
    for start, end in find_hwpx_tag_spans(xml_text, "hp:p"):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if heading_text not in paragraph_text:
            continue
        if any(line and line in paragraph_text for line in lines[:2]):
            return xml_text, False
        updated_paragraphs = clone_hwpx_paragraph_for_semantic_lines(
            remove_hwpx_section_properties_xml(paragraph_xml), lines
        )
        updated = xml_text[:end] + updated_paragraphs + xml_text[end:]
        return updated, True
    return xml_text, False


def append_hwpx_section_block_xml(
    xml_text: str,
    anchor_text: str,
    section_heading: str,
    body: object,
) -> str:
    if not str(body or "").strip():
        return xml_text
    block = f"{section_heading}\n{body}"
    xml_text, _ = append_hwpx_lines_to_heading_text_xml(xml_text, anchor_text, block)
    return xml_text


def hwpx_body_lines_present_xml(xml_text: str, lines: list[str]) -> bool:
    meaningful = [line for line in lines[:2] if str(line).strip()]
    if not meaningful:
        return False
    return all(line in xml_text or hwpx_escape_text(line) in xml_text for line in meaningful)


def remove_hwpx_table_containing_xml(xml_text: str, required_parts: list[str]) -> tuple[str, int]:
    required = [part for part in required_parts if part]
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        table_text = get_hwpx_xml_scope_text(table_xml)
        if required and not all(part in table_text for part in required):
            continue
        return xml_text[:start] + xml_text[end:], 1
    return xml_text, 0


def patch_hwpx_body_after_heading_xml(xml_text: str, heading: str, body: object, *, fallback_heading_body: bool = True) -> tuple[str, int]:
    lines = strip_redundant_hwpx_outer_heading_lines(
        hwpx_report_body_lines(body, 10000),
        heading,
    )
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    for index, (start, end) in enumerate(spans):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if paragraph_text != heading:
            continue
        for next_index in range(index + 1, min(index + 4, len(spans))):
            next_start, next_end = spans[next_index]
            next_xml = xml_text[next_start:next_end]
            if "<hp:tbl" in next_xml:
                continue
            if not get_hwpx_xml_scope_text(next_xml).strip():
                updated = clone_hwpx_paragraph_for_semantic_lines(next_xml, lines)
                return xml_text[:next_start] + updated + xml_text[next_end:], 1
        if fallback_heading_body:
            body_paragraphs = clone_hwpx_paragraph_for_semantic_lines(
                remove_hwpx_section_properties_xml(paragraph_xml), lines
            )
            return xml_text[:end] + body_paragraphs + xml_text[end:], 1
    return xml_text, 0


def normalized_hwpx_heading_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def paragraph_text_matches_anchor(text: str, anchor: str) -> bool:
    if not anchor:
        return False
    stripped = str(text or "").strip()
    normalized = normalized_hwpx_heading_text(stripped)
    normalized_anchor = normalized_hwpx_heading_text(anchor)
    return stripped == anchor or normalized == normalized_anchor or normalized.startswith(normalized_anchor)


def replace_hwpx_heading_block_xml(
    xml_text: str,
    heading: str,
    body: object,
    stop_headings: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, int]:
    lines = strip_redundant_hwpx_outer_heading_lines(
        hwpx_report_body_lines(body),
        heading,
    )
    if not lines:
        return xml_text, 0
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    heading_index = -1
    heading_text = ""
    for index, (start, end) in enumerate(spans):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if paragraph_text_matches_anchor(paragraph_text, heading):
            heading_index = index
            heading_text = paragraph_text or heading
            break
    if heading_index < 0:
        return xml_text, 0

    stop_index = len(spans)
    stop_candidates = [str(item) for item in (stop_headings or []) if str(item or "").strip()]
    for index in range(heading_index + 1, len(spans)):
        paragraph_xml = xml_text[spans[index][0]:spans[index][1]]
        # A template may anchor a table inside the same paragraph as its
        # heading (the evaluation matrix does this).  Its text still defines
        # the narrative block boundary even though the paragraph itself must
        # remain protected from replacement.
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if any(paragraph_text_matches_anchor(paragraph_text, candidate) for candidate in stop_candidates):
            stop_index = index
            break

    def protected_layout_paragraph(paragraph_xml: str) -> bool:
        # Tables, pictures and embedded objects belong to the fixed template
        # layout.  Narrative replacement may move around them, but must never
        # clone or delete them.
        return any(
            marker in paragraph_xml
            for marker in ("<hp:tbl", "<hp:pic", "<hp:ole", "<hp:equation", "<hp:chart", "<hp:video")
        )

    def clean_template_paragraph(paragraph_xml: str) -> str:
        cleaned = remove_hwpx_section_properties_xml(paragraph_xml)
        # Footnotes and input controls from the sample report must not follow
        # newly generated prose.  Media controls are excluded above.
        for ctrl_start, ctrl_end in reversed(find_hwpx_tag_spans(cleaned, "hp:ctrl")):
            cleaned = cleaned[:ctrl_start] + cleaned[ctrl_end:]
        cleaned = re.sub(r"<hp:(?:fieldBegin|fieldEnd|bookmark)\b[^>]*/>", "", cleaned)
        return cleaned

    editable: list[tuple[int, str, str]] = []
    for index in range(heading_index + 1, stop_index):
        start, end = spans[index]
        paragraph_xml = xml_text[start:end]
        if protected_layout_paragraph(paragraph_xml):
            continue
        editable.append((index, paragraph_xml, get_hwpx_xml_scope_text(paragraph_xml).strip()))

    # Pick existing paragraph styles by semantic role.  This keeps the
    # template's font, indentation and spacing while allowing arbitrary text
    # length and paragraph counts.
    templates: dict[str, str] = {}
    for _index, paragraph_xml, paragraph_text in editable:
        if paragraph_text:
            templates.setdefault(hwpx_report_outline_kind(paragraph_text), paragraph_xml)
    blank_template = next((paragraph_xml for _index, paragraph_xml, text in editable if not text), "")
    fallback_template = templates.get("body") or blank_template or next((item[1] for item in editable), "")
    if not fallback_template:
        fallback_template = remove_hwpx_section_properties_xml(
            xml_text[spans[heading_index][0]:spans[heading_index][1]]
        )
    templates.setdefault("body", fallback_template)
    templates.setdefault("bullet", templates.get("body", fallback_template))
    templates.setdefault("detail", templates.get("bullet") or templates.get("body", fallback_template))
    templates.setdefault("subheading", templates.get("bullet") or templates.get("body", fallback_template))

    def spacer_paragraph(label: str) -> str:
        """Return a neutral empty paragraph used between heading levels.

        The reference evaluation reports leave a full reader-visible line
        after a numbered heading and after a Korean outline subheading.  A
        bare newline inside ``hp:t`` does not create that vertical rhythm in
        Hancom/rhwp, so the exporter emits an actual neutral paragraph.
        """
        template = clean_template_paragraph(blank_template or templates.get("body", fallback_template))
        template = apply_hwpx_report_outline_style_xml(template, "body")
        paragraph_id = binascii.crc32(f"section-spacer|{heading}|{label}".encode("utf-8")) & 0xFFFFFFFF
        template = re.sub(
            r'(<hp:p\b[^>]*\bid=")\d+(")',
            rf"\g<1>{paragraph_id}\2",
            template,
            count=1,
        )
        return set_hwpx_xml_scope_text(template, "")

    # Keep one full blank line between the fixed numbered heading and the
    # first generated child/body paragraph, matching the published report
    # hierarchy used as the visual reference.
    rendered: list[str] = [spacer_paragraph("after-outer-heading")]
    last_was_spacer = True
    for ordinal, line in enumerate(lines, 1):
        kind = hwpx_report_outline_kind(line)
        # Every top-level ``ㅇ`` starts a new visual thought group.  Insert
        # one real empty paragraph above it, while avoiding a second blank
        # when the fixed outer heading/subheading already supplied one.
        if kind == "bullet" and not last_was_spacer:
            rendered.append(spacer_paragraph(f"before-bullet-{ordinal}"))
            last_was_spacer = True
        template = clean_template_paragraph(templates.get(kind, fallback_template))
        template = apply_hwpx_report_outline_style_xml(template, kind)
        paragraph_id = binascii.crc32(f"section-block|{heading}|{ordinal}|{line}".encode("utf-8")) & 0xFFFFFFFF
        template = re.sub(
            r'(<hp:p\b[^>]*\bid=")\d+(")',
            rf"\g<1>{paragraph_id}\2",
            template,
            count=1,
        )
        visible_line = (
            "- " + re.sub(r"^\s*-\s*", "", line)
            if kind == "detail"
            else line
        )
        template = set_hwpx_xml_scope_text(
            template,
            visible_line,
            preserve_edge_whitespace=kind != "detail",
        )
        rendered.append(style_hwpx_detail_summary_label_xml(template))
        last_was_spacer = False
        if kind == "subheading" and ordinal < len(lines):
            rendered.append(spacer_paragraph(f"after-subheading-{ordinal}"))
            last_was_spacer = True
    body_xml = "".join(rendered)

    if not editable:
        heading_end = spans[heading_index][1]
        return xml_text[:heading_end] + body_xml + xml_text[heading_end:], 1

    first_editable = editable[0][0]
    replacements: dict[int, str] = {first_editable: body_xml}
    for index, _paragraph_xml, _paragraph_text in editable[1:]:
        # Delete sample prose instead of leaving dozens of empty paragraphs,
        # which previously produced blank pages after reflow.
        replacements[index] = ""
    for index in sorted(replacements.keys(), reverse=True):
        start, end = spans[index]
        xml_text = xml_text[:start] + replacements[index] + xml_text[end:]
    return xml_text, 1


def section_body_or_gap(sections_by_id: dict[str, str], section_id: str, label: str) -> str:
    body = str(sections_by_id.get(section_id) or "").strip()
    if body:
        if section_id == "feedback":
            return normalize_feedback_section(body)
        if section_id == "lessons":
            return normalize_lessons_section(body)
        return body
    return f"자동 초안 생성 제약: {label} 작성을 위해 관련 원문 문서, 성과자료, 예산·운영자료 또는 담당자 확인 내용이 필요함."


def ensure_korean_bullet(text: object) -> str:
    bullet = "\u3147"
    value = str(text or "").strip()
    if not value:
        return f"{bullet} \ucd94\uac00 \uc815\ubcf4 \ud544\uc694"
    return value if value.startswith(bullet) else f"{bullet} {value}"


PROJECT_BACKGROUND_SLOT_TITLES = {
    "mdg_maternal_health_context": "개발문제와 구조적 취약성",
    "government_policy_context": "정부 정책과 제도적 방향",
    "target_region_need": "대상지역의 수요와 지원 필요성",
    "koica_policy_alignment": "ODA 정책 및 지원전략과의 정합성",
    "project_selection_rationale": "사업 선정과 형성 논리",
}


def normalize_project_background_slot(value_key: str, value: object) -> str:
    """Return the section-6 ``(소제목) 본문`` contract without legacy bullets."""

    text = str(value or "").strip()
    # Markdown emphasis must not hide an existing circle/title from detection.
    text = text.replace("**", "")
    text = re.sub(r"^(?:[•ㅇ❍∙ㆍ]\s*|#{1,6}\s*|\d+(?:\.\d+)*[.)]\s*)+", "", text).strip()
    if re.match(r"^\([^()]{2,90}\)\s+\S", text):
        return text
    title = PROJECT_BACKGROUND_SLOT_TITLES.get(value_key, "사업 추진배경")
    return f"({title}) {text or '등록 자료를 종합하여 해당 배경을 검토하였다.'}"

def extract_labeled_report_fragment(text: object, labels: list[str], fallback: str) -> str:
    body = str(text or "").strip()
    if not body:
        return fallback
    lines = [line.strip(" -\t") for line in body.splitlines() if line.strip()]
    for label in labels:
        for index, line in enumerate(lines):
            if label not in line:
                continue
            collected = [line]
            for next_line in lines[index + 1:index + 3]:
                if re.match(r"^[가-힣A-Za-z ]{2,20}\s*[:：]", next_line) or re.match(r"^-?\s*(상위목표|사업목표|성과|산출물|활동|투입|전제조건)\s*[:：]", next_line):
                    break
                collected.append(next_line)
            return short_text(" ".join(collected), 140)
    return fallback


def read_hwpx_section_manifest(section_number: int) -> dict:
    if not (ROOT / "hwpx_sections").exists():
        return {}
    pattern = f"Section{section_number}_*"
    section_dirs = sorted((ROOT / "hwpx_sections").glob(pattern))
    if not section_dirs:
        return {}
    manifest_path = section_dirs[0] / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def report_people_from_sections(sections_by_id: dict[str, str]) -> dict:
    return infer_report_people([
        {"body": body}
        for body in sections_by_id.values()
        if str(body or "").strip()
    ])


def existing_notice_values_from_sections(sections_by_id: dict[str, str], people: dict) -> dict:
    text = str(sections_by_id.get("notice") or "")
    values = {
        "responsible_evaluator_name": people.get("managerName") or "",
        "completion_date": people.get("completedAt") if people.get("completedAt") != "평가 완료일 확인 대상" else "",
        "country_name": "",
    }
    evaluator_match = re.search(r"(?:평가\s*책임자|책\s*임\s*평\s*가\s*자)\s*[:：]?\s*([^\n(]+)", text)
    if evaluator_match:
        values["responsible_evaluator_name"] = evaluator_match.group(1).strip()
    completion_match = re.search(r"평가\s*완료일\s*[:：]\s*([^\n]+)", text)
    if completion_match:
        values["completion_date"] = completion_match.group(1).strip()
    country_match = re.search(r"KOICA\s*본부\s*및\s*([^\s]+)\s*사무소", text)
    if country_match:
        values["country_name"] = country_match.group(1).strip()
    return values


def infer_project_country(project: dict, existing_values: dict) -> str:
    if existing_values.get("country_name"):
        return str(existing_values["country_name"]).strip()
    title = str(project.get("title") or "")
    known_countries = ["네팔", "라오스", "캄보디아", "베트남", "몽골", "우즈베키스탄", "필리핀", "인도네시아", "방글라데시", "탄자니아", "에티오피아", "르완다", "가나", "세네갈", "페루", "볼리비아"]
    for country in known_countries:
        if country in title:
            return country
    return ""


TOC_PDF_PAGE_HEADINGS = {
    "summary_ko_page": ["국문 요약", "요 약"],
    "project_background_page": ["사업 추진배경", "추진배경"],
    "project_overview_page": ["사업개요", "사업 개요"],
    "pdm_page": ["PDM"],
    "evaluation_purpose_page": ["평가 목적과 범위", "평가목적", "평가 범위"],
    "evaluation_matrix_page": ["평가매트릭스", "평가 매트릭스"],
    "evaluation_methods_page": ["평가방법", "평가 방법"],
    "evaluation_limitations_page": ["평가의 한계", "평가 한계"],
    "evaluation_team_page": ["평가팀 구성", "시행체계"],
    "achievement_page": ["성과 달성도", "성과달성도"],
    "criteria_relevance_page": ["적절성"],
    "criteria_coherence_page": ["일관성"],
    "criteria_effectiveness_page": ["효과성"],
    "criteria_efficiency_page": ["효율성"],
    "criteria_sustainability_page": ["지속가능성"],
    "criteria_crosscutting_page": ["범분야 이슈", "범분야"],
    "criteria_other_page": ["그 외 평가기준", "기타 평가기준"],
    "conclusion_page": ["결론"],
    "factors_page": ["작동요인", "비작동요인"],
    "feedback_lessons_page": ["환류과제", "교훈"],
    "appendix_summary_en_page": ["영문 요약", "영문요약"],
    "appendix_fieldwork_page": ["현지조사", "조사일정"],
    "appendix_daily_activities_page": ["일별 활동", "일일 활동"],
    "appendix_interviewees_page": ["면담자", "인터뷰 대상"],
    "appendix_survey_page": ["설문조사"],
    "appendix_references_page": ["참고문헌"],
    "appendix_other_page": ["기타 첨부", "기타"],
}


def normalize_toc_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


TOC_RENDERED_PAGE_PATTERNS = [
    ("summary_ko_page", [r"^1\.\s*국문\s*요약\b"]),
    ("project_background_page", [r"^1\.\s*사업\s*추진배경\b"]),
    ("project_overview_page", [r"^2\.\s*사업개요\b", r"^2\.\s*사업\s*개요\b"]),
    ("pdm_page", [r"^3\.\s*사업설계매트릭스\s*\(PDM\)"]),
    ("evaluation_purpose_page", [r"^1\.\s*평가의\s*목적과\s*범위\b"]),
    ("evaluation_matrix_page", [r"^2\.\s*평가매트릭스\s*\(Evaluation\s*Matrix\)\s*$", r"^평가\s*매트릭스\b"]),
    ("evaluation_methods_page", [r"^3\.\s*평가\s*방법\b", r"^3\.\s*평가방법\b"]),
    ("evaluation_limitations_page", [r"^4\.\s*평가의\s*한계\b"]),
    ("evaluation_team_page", [r"^5\.\s*평가팀\s*구성\s*및\s*시행체계\b"]),
    ("achievement_page", [r"^(?:Ⅳ|IV)\.?\s*성과달성도\b", r"^성과달성도\b"]),
    ("criteria_relevance_page", [r"^1\.\s+적절성\b"]),
    ("criteria_coherence_page", [r"^2\.\s+일관성\b"]),
    ("criteria_effectiveness_page", [r"^3\.\s+효과성\b"]),
    ("criteria_efficiency_page", [r"^4\.\s+효율성\b"]),
    ("criteria_sustainability_page", [r"^5\.\s+지속가능성\b"]),
    ("criteria_crosscutting_page", [r"^6\.\s+범분야\s*이슈\b", r"^6\.\s+범분야\b"]),
    ("criteria_other_page", [r"^7\.\s+그\s*외\s*평가기준\b"]),
    ("conclusion_page", [r"^1\.\s+결론\b"]),
    ("factors_page", [r"^2\.\s*작동요인\s*및\s*비작동요인\b"]),
    ("feedback_lessons_page", [r"^3\.\s*환류과제\s*및\s*교훈\b"]),
    ("appendix_summary_en_page", [r"^1\.\s*평가결과\s*영문\s*요약\b"]),
    ("appendix_fieldwork_page", [r"^2\.\s*현지\s*\(원격\)\s*조사\s*개요\b", r"^2\.\s*현지조사\s*개요\b"]),
    ("appendix_daily_activities_page", [r"^3\.\s*일별활동내역\b", r"^3\.\s*일별\s*활동\b"]),
    ("appendix_interviewees_page", [r"^4\.\s*면담자\s*목록\b"]),
    ("appendix_survey_page", [r"^5\.\s*설문조사지\b", r"^5\.\s*설문조사\b"]),
    ("appendix_references_page", [r"^6\.\s*참고문헌\s*목록\b"]),
    ("appendix_other_page", [r"^7\.\s*그\s*외\s*첨부자료\b"]),
]


# Section 2 has a wrapper hp:p that contains the visible TOC paragraphs.
# The review manifest indexes are human-visible paragraph indexes, while
# replace_hwpx_paragraph_last_text_xml uses find_hwpx_all_tag_spans(), which
# also includes that wrapper. Keep a dedicated map so TOC numbers are written
# only to the intended original text nodes.
TOC_SECTION2_TEXT_SPAN_INDEXES = {
    "summary_ko_page": 7,
    "project_background_page": 10,
    "project_overview_page": 11,
    "pdm_page": 12,
    "evaluation_purpose_page": 15,
    "evaluation_matrix_page": 16,
    "evaluation_methods_page": 17,
    "evaluation_limitations_page": 18,
    "evaluation_team_page": 19,
    "achievement_page": 22,
    "criteria_relevance_page": 25,
    "criteria_coherence_page": 26,
    "criteria_effectiveness_page": 27,
    "criteria_efficiency_page": 28,
    "criteria_sustainability_page": 29,
    "criteria_crosscutting_page": 30,
    "criteria_other_page": 31,
    "conclusion_page": 34,
    "factors_page": 35,
    "feedback_lessons_page": 36,
    "appendix_summary_en_page": 39,
    "appendix_fieldwork_page": 40,
    "appendix_daily_activities_page": 41,
    "appendix_interviewees_page": 42,
    "appendix_survey_page": 43,
    "appendix_references_page": 44,
    "appendix_other_page": 45,
}


TOC_SECTION2_NOTICE_SPAN_INDEX = 3


def normalized_rendered_lines(text: str) -> list[str]:
    lines = []
    for line in str(text or "").splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def toc_page_map_from_page_texts(page_texts: list[tuple[int, str]]) -> dict:
    content_pages = []
    for page_number, text in page_texts:
        normalized = normalize_toc_text(text)
        if page_number <= 2:
            continue
        if normalize_toc_text("목 차") in normalized or normalize_toc_text("목차") in normalized[:20]:
            continue
        content_pages.append((page_number, normalized_rendered_lines(text)))

    page_map = {}
    min_page = 3
    from .toc_registry import TOC_ROWS, destination_title, normalized_title
    patterns_by_key = dict(TOC_RENDERED_PAGE_PATTERNS)
    all_rows = [(key, label) for key, label, _ in TOC_ROWS]
    all_rows += [(key, '') for key in patterns_by_key if key not in TOC_SECTION2_LABELS]
    for key, label in all_rows:
        patterns = patterns_by_key.get(key, [])
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        matched_page = None
        for page_number, lines in content_pages:
            if page_number < min_page:
                continue
            if any(regex.search(line) for line in lines for regex in compiled) or (
                label and any(normalized_title(line).startswith(normalized_title(destination_title(key, label))) for line in lines)):
                matched_page = page_number
                break
        if matched_page is not None:
            page_map[key] = str(matched_page)
            min_page = matched_page
    return page_map


def read_toc_page_map_from_rhwp_text(hwpx_bytes: bytes) -> dict:
    rhwp_bin = os.getenv("RHWP_BIN", "rhwp")
    if not rhwp_bin:
        return {}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="toc-rhwp-", dir=str(REPORT_DIR)) as temp_dir:
        temp_path = Path(temp_dir)
        hwpx_path = temp_path / "toc-source.hwpx"
        out_dir = temp_path / "pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        hwpx_path.write_bytes(hwpx_bytes)
        try:
            completed = subprocess.run(
                [rhwp_bin, "export-text", str(hwpx_path), "-o", str(out_dir)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except Exception:
            return {}
        if completed.returncode != 0:
            return {}
        page_texts = []
        for page_file in sorted(out_dir.glob("*.txt")):
            match = re.search(r"_(\d+)\.txt$", page_file.name)
            if not match:
                continue
            page_number = int(match.group(1))
            page_texts.append((page_number, page_file.read_text(encoding="utf-8", errors="ignore")))
        page_map = toc_page_map_from_page_texts(page_texts)
        if page_map:
            audit_path = REPORT_DIR / "toc_page_map.json"
            audit_path.write_text(
                json.dumps(
                    {
                        "source": "rhwp_export_text",
                        "generatedAt": datetime.now().isoformat(timespec="seconds"),
                        "page_numbers": page_map,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return page_map


def read_toc_page_map_from_pdf() -> dict:
    candidates = [
        REPORT_DIR / "toc_source.pdf",
        REPORT_DIR / "final_report.pdf",
        REPORT_DIR / "report.pdf",
    ]
    pdf_path = next((path for path in candidates if path.exists()), None)
    if not pdf_path:
        return {}
    try:
        from pypdf import PdfReader
    except Exception:
        return {}
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return {}
    page_texts = []
    for index, page in enumerate(reader.pages):
        if index < 2:
            continue
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        normalized = normalize_toc_text(text)
        if normalize_toc_text("목 차") in normalized or normalize_toc_text("목차") == normalized[:2]:
            continue
        page_texts.append((index + 1, normalized))
    return toc_page_map_from_page_texts(page_texts)


def read_toc_page_map() -> dict:
    page_map = {}
    candidates = [
        REPORT_DIR / "toc_page_map.json",
        REPORT_DIR / "toc_pages.json",
    ]
    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                source = data.get("page_numbers") if isinstance(data.get("page_numbers"), dict) else data
                page_map.update({key: value for key, value in source.items() if value is not None})
                return page_map
    return read_toc_page_map_from_pdf()


def build_section_manifest_values(section_number: int, context: dict, sections_by_id: dict[str, str]) -> dict:
    project = context.get("project", {})
    people = report_people_from_sections(sections_by_id)
    body_value_map = {
        11: ("eval_methods_body", "eval-methods", "평가방법"),
        12: ("eval_limitations_body", "eval-limitations", "평가의 한계"),
        13: ("eval_team_body", "eval-team", "평가팀 구성 및 시행체계"),
        14: ("achievement_body", "achievement", "성과 달성도"),
        15: ("criteria_relevance_body", "criteria-relevance", "적절성"),
        16: ("criteria_coherence_body", "criteria-coherence", "일관성"),
        17: ("criteria_effectiveness_body", "criteria-effectiveness", "효과성"),
        18: ("criteria_efficiency_body", "criteria-efficiency", "효율성"),
        19: ("criteria_sustainability_body", "criteria-sustainability", "지속가능성"),
        20: ("criteria_crosscutting_body", "criteria-crosscutting", "범분야 이슈"),
        21: ("criteria_other_body", "criteria-other", "그 외 평가기준"),
        22: ("conclusion_body", "conclusion", "결론"),
        23: ("working_factors_body", "working-factors", "작동요인"),
        24: ("nonworking_factors_body", "nonworking-factors", "비작동요인"),
        25: ("theory_body", "theory", "변화이론 분석"),
        26: ("feedback_body", "feedback", "환류과제"),
        27: ("lessons_body", "lessons", "교훈"),
    }
    if section_number == 1:
        title = str(project.get("title") or "사업명 확인 필요").strip()
        return {
            "report_title": [title],
            "date": datetime.now().strftime("%Y. %m"),
            "manager": people.get("managerLine") or "평가책임자 확인 대상",
            "institution": people.get("institutionLine") or "평가수행기관 확인 대상",
        }
    if section_number == 2:
        page_map = context.get("_toc_page_map") if isinstance(context.get("_toc_page_map"), dict) else read_toc_page_map()
        return {
            "remove_texts": {"remove_page_notice": ""},
            "page_numbers": page_map or {},
        }
    if section_number == 3:
        cover = cover_values_from_sections(context, sections_by_id)
        manager_name = re.sub(
            r"^평가책임자\s*", "", str(cover.get("manager") or "")
        ).strip() or people.get("managerName") or "등록 자료 미기재"
        institution_name = re.sub(
            r"^평가수행기관\s*", "", str(cover.get("institution") or "")
        ).strip() or people.get("institution") or "등록 자료 미기재"
        # A plan-based cover names business roles, not the evaluation team.
        # Never promote those people/institutions into notice evaluator slots.
        if str(cover.get('manager') or '').startswith('사업책임자 '):
            manager_name = '등록 자료 미기재'
        if str(cover.get('institution') or '').startswith('사업 수행기관 '):
            institution_name = '등록 자료 미기재'
        country = infer_project_country(project, {})
        country_value = f"{country} " if country else "대상국 "
        title = str(project.get("title") or "등록 사업").strip()
        completion_date = str(project.get("assessment_as_of") or datetime.now().date().isoformat()).strip()
        year_match = re.search(r"(20\d{2})", completion_date)
        citation_year = year_match.group(1) if year_match else datetime.now().strftime("%Y")
        return {
            "responsible_evaluator_name_first": manager_name,
            "country_name": country_value,
            "evaluated_project_name": f"{title} {project.get('report_label') or '평가'}",
            "commissioning_agency": str(project.get("donor") or "지원기관"),
            "implementing_agency": str(project.get("implementer") or "수행기관"),
            "report_label": str(project.get("report_label") or "평가보고서"),
            "responsible_evaluator_name_second": manager_name,
            "completion_date_value": completion_date,
            "lead_evaluator_line": f" 책 임 평 가 자 : {manager_name} ({institution_name})",
            "evaluation_expert_line": "  평 가 전 문 가 : 등록 자료 미기재",
            "sector_expert_line": "  분 야 전 문 가 : 등록 자료 미기재",
            "assistant_evaluator_line": "  평 가 보 조 원 : 등록 자료 미기재",
            "quality_review_date_value": "별도 외부심의 미실시",
            "quality_grade_value": "별도 외부심의 미실시",
            "review_chair_name": "해당 없음",
            "review_member_1_name": "해당 없음",
            "review_member_2_name": "해당 없음",
            "review_member_3_name": "해당 없음",
            "citation_lead": f"{manager_name}. {citation_year}. {project.get('donor') or '지원기관'} {title} 평가보고서. ",
        }
    if section_number == 4:
        criteria = {str(item.get("id")): item for item in criterion_grade_rows(context)}

        def criterion_score_text(criteria_id: str) -> str:
            item = criteria.get(criteria_id) or {}
            return format_score(item.get('score', 1), '점')

        def criterion_reason(criteria_id: str) -> str:
            item = criteria.get(criteria_id) or {}
            return grade_reason_sentence(item.get("reason") or "확인 필요", 65)

        def question_score(criteria_id: str, index: int) -> str:
            item = criteria.get(criteria_id) or {}
            rows = item.get("questionRows") if isinstance(item.get("questionRows"), list) else []
            if index < len(rows):
                return format_score(rows[index].get('score', 1), '점')
            return criterion_score_text(criteria_id)

        def question_reason(criteria_id: str, index: int) -> str:
            item = criteria.get(criteria_id) or {}
            rows = item.get("questionRows") if isinstance(item.get("questionRows"), list) else []
            if index < len(rows):
                return grade_question_reason(rows[index].get("reason") or rows[index].get("question") or item.get("reason") or "확인 필요")
            return criterion_reason(criteria_id)

        overall = context.get("overall") or {}
        total_score = overall.get("score")
        if total_score is None and all(item.get('score') is not None for item in criteria.values()):
            total_score = round(sum(float(item.get("score", 0) or 0) for item in criteria.values()), 1)
        return {
            # The grade sheet identifies the evaluated project by its formal
            # business name only. Period and budget belong to the overview.
            "project_label": f"ㅇ 평가대상 사업명 : {project.get('title') or '사업명 확인 필요'}",
            "relevance_policy_score": question_score("relevance", 0),
            "relevance_policy_reason": question_reason("relevance", 0),
            "relevance_adaptation_score": question_score("relevance", 1),
            "relevance_adaptation_reason": question_reason("relevance", 1),
            "relevance_total_score": criterion_score_text("relevance"),
            "relevance_total_reason": "",
            "coherence_internal_score": question_score("coherence", 0),
            "coherence_internal_reason": question_reason("coherence", 0),
            "coherence_external_score": question_score("coherence", 1),
            "coherence_external_reason": question_reason("coherence", 1),
            "coherence_total_score": criterion_score_text("coherence"),
            "coherence_total_reason": "",
            "effectiveness_output_score": question_score("effectiveness", 0),
            "effectiveness_output_reason": question_reason("effectiveness", 0),
            "effectiveness_outcome_score": question_score("effectiveness", 1),
            "effectiveness_outcome_reason": question_reason("effectiveness", 1),
            "effectiveness_equity_score": question_score("effectiveness", 2),
            "effectiveness_equity_reason": question_reason("effectiveness", 2),
            "effectiveness_total_score": criterion_score_text("effectiveness"),
            "effectiveness_total_reason": "",
            "efficiency_timeliness_score": question_score("efficiency", 0),
            "efficiency_timeliness_reason": question_reason("efficiency", 0),
            "efficiency_balance_score": question_score("efficiency", 1),
            "efficiency_balance_reason": question_reason("efficiency", 1),
            "efficiency_total_score": criterion_score_text("efficiency"),
            "efficiency_total_reason": "",
            "sustainability_capacity_score": question_score("sustainability", 0),
            "sustainability_capacity_reason": question_reason("sustainability", 0),
            "sustainability_environment_score": question_score("sustainability", 1),
            "sustainability_environment_reason": question_reason("sustainability", 1),
            "sustainability_total_score": criterion_score_text("sustainability"),
            "sustainability_total_reason": "",
            "overall_score": format_score(total_score, '/20점'),
            "government_grade": str(overall.get("governmentGrade") or "미흡"),
            "koica_grade": str(overall.get("koicaGrade") or "F"),
            "remove_texts": {
                "remove_grade_notice_1": "",
                "remove_grade_notice_2": "",
            },
        }
    if section_number == 5:
        # Section 5 is fail-closed. Its dedicated semantic adapter must
        # provide all five validated blocks; no template sample or placeholder
        # fallback is permitted at rendering time.
        return {}
    if section_number == 6:
        background_text = section_body_or_gap(sections_by_id, "project-background", "사업 추진배경")
        fallback_values = {key: "ㅇ 확인 필요" for key in SECTION6_PROJECT_BACKGROUND_SLOT_KEYS}
        fallback_values.update(
            {
                "mdg_maternal_health_context": ensure_korean_bullet(short_text(background_text, 260)),
                "government_policy_context": "ㅇ 자동 초안 생성 제약: 협력국 보건·모자보건 정책",
                "target_region_need": "ㅇ 자동 초안 생성 제약: 대상지역 보건의료 여건과 수요",
                "koica_policy_alignment": "ㅇ 자동 초안 생성 제약: KOICA 지원전략과의 부합성",
                "project_selection_rationale": "ㅇ 자동 초안 생성 제약: 사업 선정 및 추진 사유",
            }
        )
        return {
            **fallback_values,
        }
    if section_number == 7:
        title = str(project.get("title") or "사업명 확인 중").strip()
        period = str(project.get("period") or "기간 확인 중").strip()
        budget = str(project.get("budget") or "예산 확인 중").strip()
        return {
            "project_name_ko": f"▣ 국문: {title}",
            "project_name_en": "▣ 영문: Project for Improving Maternal Child Healthcare in Mugu District",
            "target_country_region": "▣ 네팔 무구군(Mugu District)",
            "project_period_budget": f"▣ 구분 : 프로젝트 / ▣ 기간 : {period} / ▣ 총 사업예산 : {budget}",
            "project_sector": "▣ 프로젝트 / 보건(모자보건)",
            "project_purpose": "▣ 무구지역 보건의료체계 개선 및 보건의료 서비스 향상 / ▣ 모자보건 개선을 위한 의료서비스 수요자 및 공급자 역량 강화",
            "pcp_feasibility_review": "󰁯 관계기관 PCP : 네팔 무구지역 모자보건환경 개선 필요성 확인 / 󰁯 수총기관 공문 : 네팔 보건의료 인프라 개선 수요 확인 / 󰁯 사전타당성조사 : 보건서비스 접근성 및 모자보건 개선 필요성 검토",
            "korean_textbook_development": "▣ 소요예산 : 사업비 내 반영 / ▪ 보건의료 인력 및 주민 보건교육 자료 개발·활용",
            "korean_equipment_support": "▣ 소요예산 : 사업비 내 반영 / ▪ 군 병원 및 보건의료시설 의료기자재 지원",
            "korean_expert_dispatch": "▣ 소요예산 : 사업비 내 반영 / ▪ 보건정책 자문, 사업관리, 모니터링 및 평가 지원",
            "korean_invitation_training": "▣ 소요예산 : 사업비 내 반영 / ▪ 보건의료 인력 역량강화 교육 및 훈련 지원",
            "partner_contribution": "▣ 네팔 보건 당국 및 지역 보건기관의 사업 협조, 병원 운영, 인력 배치 및 시설 유지관리 참여",
            "remove_texts": {
                "remove_project_overview_guide": "",
            },
        }
    if section_number == 8:
        return {
            "impact_summary": "사업대상지역 모자보건 개선",
            "impact_indicator": "1. 시설분만율 10% 증가 / 2. SBA에 의한 출산율 15% 증가 / 3. 5세 이하 아동 사망률 감소",
            "impact_mov": "종료선 조사 / 보건통계 / 사업 최종보고서",
            "impact_assumption": "무구지역 보건서비스 이용 여건과 정부 보건정책 기조가 유지됨",
            "outcome_summary": "1. 무구지역 보건의료체계 및 모성의료서비스 개선 / 2. 모자보건 관련 수요자·공급자 역량 강화",
            "outcome_indicator": "1. 산전진찰 4회 완수율 증가 / 2. 병원·보건소 외래진료 증가 / 3. 필수백신 접종률 증가 / 4. 아동 주요 질환 처치율 증가",
            "outcome_mov": "성과지표 실적표 / 종료선 조사 / HMIS 및 보건시설 자료",
            "outcome_assumption": "보건인력 배치와 시설 운영, 주민 참여가 지속됨",
            "outputs_summary": "1. 지역보건체계 거버넌스 및 경영역량 강화 / 2. 모자보건 인프라 및 서비스 개선 / 3. 마을단위 보건활동 강화 및 주민 참여 증진",
            "outputs_indicator": "1. HMIS 정기보고율 개선 / 2. 병원 병동 재건축 준공 / 3. 조산사 양성 / 4. 이동검진·사회감사·보건캠페인 실시",
            "outputs_mov": "사업 완료보고서 / 교육 이수자 명단 / 기자재·시설 점검자료 / 캠페인 실적",
            "outputs_assumption": "협력기관 간 조정과 현지 행정지원이 원활히 유지됨",
            "activities": "1. 지역보건 거버넌스 역량 강화 / 2. 보건 인프라 및 서비스 개선 / 3. 의료인력 교육·장학 지원 / 4. 주민 보건교육·사회감사·캠페인",
            "inputs": "예산: 한국측 500만 불 / 인력: PM, 전문인력, 현지인력 / 네팔측 병원 부지 및 운영 협조",
            "preconditions": "대규모 재해·분쟁·감염병 확산이 사업 수행을 중단시키지 않고, 병원·보건소 운영의 투명성이 확보됨",
        }
    if section_number == 9:
        return {
            "evaluation_purpose_scope_body": section_body_or_gap(sections_by_id, "eval-purpose", "평가의 목적과 범위"),
            "remove_texts": {
                "remove_eval_purpose_guide": "",
            },
        }
    if section_number == 10:
        return {
            "relevance_question": "사업은 네팔 보건분야 국가개발전략 및 한국의 국별협력전략(CPS), 무구지역 모자보건 수요와 적절히 부합하였는가?",
            "relevance_indicator": "정책 부합성, 수요 반영도, 사업 설계의 적절성",
            "relevance_source": "사업개요서, 사전조사 자료, CPS, 네팔 보건정책 자료",
            "relevance_method": "문헌조사, 이해관계자 면담, 설계논리 검토",
            "coherence_question": "UNICEF 등 타 공여기관 및 네팔 정부 보건사업과 중복을 피하고 상호보완적으로 연계되었는가?",
            "coherence_indicator": "타 공여기관과의 조정, 역할 분담, 범분야 이슈 반영",
            "coherence_source": "운영위원회 자료, 공여기관 관련 자료, 면담자료",
            "coherence_method": "문헌조사, 관계자 면담, 비교분석",
            "effectiveness_question": "계획된 산출물과 성과목표가 달성되었고 모자보건 서비스 개선 효과가 나타났는가?",
            "effectiveness_indicator": "산출물 달성도, 성과지표 변화, 수혜자 접근성 개선",
            "effectiveness_source": "PDM, 완료보고서, 성과자료, 종료선 조사 자료",
            "effectiveness_method": "문헌조사, 성과지표 검토, 면담 및 현장확인",
            "efficiency_question": "투입 예산, 일정, 조달·시공·운영관리 방식이 산출 달성에 효율적으로 활용되었는가?",
            "efficiency_indicator": "예산 집행률, 일정 준수, 투입 대비 산출, 운영관리 효율성",
            "efficiency_source": "예산 집행자료, 사업 일정표, 조달·시공 관련 자료",
            "efficiency_method": "문헌조사, 투입·산출 비교, 관계자 면담",
            "sustainability_question": "사업 종료 후 인력, 재정, 제도, 시설·기자재 유지관리 체계가 지속될 수 있는가?",
            "sustainability_indicator": "운영·유지관리 체계, 인력 수급, 예산 확보, 제도화 수준",
            "sustainability_source": "사후관리 자료, 기자재 관리대장, 보건시설 운영자료, 면담자료",
            "sustainability_method": "문헌조사, 운영체계 검토, 관계자 면담",
            "human_rights_question": "취약계층의 보건서비스 접근성과 참여가 사업 설계 및 성과관리 과정에서 고려되었는가?",
            "human_rights_indicator": "취약계층 접근성, 서비스 이용 형평성, 수혜자 참여",
            "human_rights_source": "수혜자 자료, 사업계획서, 현장·면담자료",
            "human_rights_method": "문헌조사, 수혜자 관점 검토, 면담",
            "gender_question": "여성의 모자보건 수요, 참여, 편익 차이가 사업 설계와 성과분석에 반영되었는가?",
            "gender_indicator": "여성 수혜 정도, 모성보건 접근성, 성별 성과 차이",
            "gender_source": "성과자료, 보건통계, 수혜자·관계자 면담자료",
            "gender_method": "문헌조사, 성별 자료 검토, 면담",
            "environment_question": "보건시설 운영, 의료폐기물, 기후·재난 위험 등 환경 요소가 사업 수행과 사후관리에 고려되었는가?",
            "environment_indicator": "환경위험 검토 여부, 의료폐기물 관리, 시설 운영관리",
            "environment_source": "사업계획서, 시설·기자재 자료, 현장확인 및 면담자료",
            "environment_method": "문헌조사, 현장확인, 관계자 면담",
            "remove_texts": {
                "remove_eval_matrix_guide_1": "",
                "remove_eval_matrix_guide_2": "",
                "remove_eval_matrix_guide_3": "",
                "remove_eval_matrix_guide_4": "",
                "remove_eval_matrix_guide_5": "",
            },
            "remove_reference_blocks": {
                "remove_oecd_dac_reference_table": ["OECD DAC 6대 평가범주", "보고서 작성 시 삭제"],
            },
        }
    if section_number in body_value_map:
        body_key, section_id, label = body_value_map[section_number]
        manifest = read_hwpx_section_manifest(section_number)
        values = {
            body_key: section_body_or_gap(sections_by_id, section_id, label),
            "remove_texts": {},
            "remove_reference_blocks": {},
        }
        for target in manifest.get("targets", []):
            replacement_type = str(target.get("replacement_type") or "")
            key = str(target.get("key") or "")
            if replacement_type in {"remove_text", "remove_paragraph"}:
                values["remove_texts"][key] = ""
            elif replacement_type == "remove_reference_block":
                required_parts = target.get("required_parts")
                if not isinstance(required_parts, list):
                    required_parts = [str(target.get("source_text") or "")]
                values["remove_reference_blocks"][key] = [str(part) for part in required_parts if str(part)]
        return values
    return {}


def patch_hwpx_section_manifest_xml(
    xml_text: str,
    section_number: int,
    context: dict,
    sections_by_id: dict[str, str],
) -> str:
    manifest = read_hwpx_section_manifest(section_number)
    if not manifest:
        return xml_text
    values = build_section_manifest_values(section_number, context, sections_by_id)
    remove_texts = values.get("remove_texts", {}) if isinstance(values.get("remove_texts"), dict) else {}
    page_numbers = values.get("page_numbers", {}) if isinstance(values.get("page_numbers"), dict) else {}
    remove_reference_blocks = values.get("remove_reference_blocks", {}) if isinstance(values.get("remove_reference_blocks"), dict) else {}
    for target in manifest.get("targets", []):
        if not isinstance(target, dict):
            continue
        key = str(target.get("key") or "")
        replacement_type = str(target.get("replacement_type") or "")
        para_index = int(target.get("paragraph_index", -1))
        if replacement_type == "paragraph_lines":
            replacement = values.get(key)
            if isinstance(replacement, list):
                xml_text, _ = set_hwpx_paragraph_lines_xml(xml_text, para_index, [str(item) for item in replacement])
        elif replacement_type == "paragraph_text":
            if key in values:
                text = normalize_hwpx_manifest_value(section_number, key, values[key])
                xml_text, _ = set_hwpx_manifest_paragraph_text_xml(
                    xml_text,
                    para_index,
                    text,
                    para_pr_id=section5_summary_paragraph_style(key) if section_number == 5 else None,
                )
        elif replacement_type in {"body_paragraph", "body_after_heading"}:
            if key in values:
                if section_number in {26, 27}:
                    continue
                lines = hwpx_report_body_lines(values[key])
                if hwpx_body_lines_present_xml(xml_text, lines):
                    continue
                source_text = str(target.get("source_text") or "")
                if source_text:
                    xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, [source_text], lines)
                    if changed:
                        continue
                heading_text = str(target.get("heading_text") or "")
                if replacement_type == "body_after_heading" and heading_text:
                    xml_text, changed = patch_hwpx_body_after_heading_xml(xml_text, heading_text, values[key])
                    if changed:
                        continue
                xml_text, changed = set_hwpx_paragraph_lines_xml(xml_text, para_index, lines)
                if changed and hwpx_body_lines_present_xml(xml_text, lines):
                    continue
                if heading_text:
                    xml_text, _ = append_hwpx_lines_to_heading_text_xml(xml_text, heading_text, values[key])
        elif replacement_type == "text":
            if key in values:
                xml_text, _ = set_hwpx_manifest_paragraph_text_xml(xml_text, para_index, values[key])
        elif replacement_type == "paragraph_text":
            if key in values:
                source_text = str(target.get("source_text") or "")
                if source_text:
                    xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, [source_text], hwpx_report_body_lines(values[key], 300))
                    if changed:
                        continue
                xml_text, _ = set_hwpx_manifest_paragraph_text_xml(xml_text, para_index, values[key])
        elif replacement_type == "grade_table_cell":
            if key in values:
                table_span = find_hwpx_grade_table_span_xml(xml_text)
                if table_span is None:
                    continue
                start, end = table_span
                table_xml, changed = set_hwpx_table_cell_text_xml(
                    xml_text[start:end],
                    int(target.get("cell_index", -1)),
                    values[key],
                )
                if changed:
                    xml_text = xml_text[:start] + table_xml + xml_text[end:]
        elif replacement_type == "table_cell":
            if key in values:
                required_parts = target.get("table_required_parts")
                if not isinstance(required_parts, list):
                    required_parts = []
                table_span = find_hwpx_table_span_by_required_parts_xml(
                    xml_text,
                    [str(part) for part in required_parts],
                )
                if table_span is None:
                    continue
                start, end = table_span
                table_xml, changed = set_hwpx_table_cell_text_xml(
                    xml_text[start:end],
                    int(target.get("cell_index", -1)),
                    values[key],
                )
                if changed:
                    xml_text = xml_text[:start] + table_xml + xml_text[end:]
        elif replacement_type in {"remove_text", "remove_paragraph"}:
            if key in remove_texts:
                source_text = str(target.get("source_text") or "")
                if source_text:
                    xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, [source_text], [])
                    if changed:
                        continue
                xml_text, _ = set_hwpx_manifest_paragraph_text_xml(xml_text, para_index, remove_texts[key])
        elif replacement_type == "page_number":
            if key in page_numbers and page_numbers[key] is not None:
                xml_text, _ = replace_hwpx_paragraph_last_text_xml(
                    xml_text,
                    para_index,
                    str(target.get("source_text") or "0"),
                    str(page_numbers[key]),
                )
        elif replacement_type == "partial_text":
            if key in values:
                xml_text, _ = set_hwpx_paragraph_run_text_xml(
                    xml_text,
                    para_index,
                    int(target.get("run_index", -1)),
                    values[key],
                )
        elif replacement_type == "remove_reference_block":
            if section_number >= 11:
                continue
            required_parts = remove_reference_blocks.get(key) or target.get("required_parts")
            if isinstance(required_parts, list):
                xml_text, _ = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, [str(part) for part in required_parts], [])
    if section_number == 5:
        xml_text, _ = normalize_hwpx_report_outline_styles_xml(xml_text)
    return xml_text


def find_hwpx_grade_table_span_xml(xml_text: str) -> tuple[int, int] | None:
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        if "평가 기준" in table_xml and "적절성 평점" in table_xml and "종합 평가 등급" in table_xml:
            return start, end
    return None


def find_hwpx_table_span_by_required_parts_xml(xml_text: str, required_parts: list[str]) -> tuple[int, int] | None:
    required = [str(part or "").strip() for part in required_parts if str(part or "").strip()]
    if not required:
        return None
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        table_text = get_hwpx_xml_scope_text(table_xml)
        if all(part in table_xml or part in table_text for part in required):
            return start, end
    return None


def set_hwpx_table_cell_text_xml(
    table_xml: str,
    cell_index: int,
    text: object,
    *,
    preserve_line_breaks: bool = False,
) -> tuple[str, bool]:
    cells = find_hwpx_tag_spans(table_xml, "hp:tc")
    if cell_index < 0 or cell_index >= len(cells):
        return table_xml, False
    start, end = cells[cell_index]
    cell_xml = table_xml[start:end]
    text_value = str(text or "")
    line_break_token = "\ue000"
    if preserve_line_breaks:
        text_value = re.sub(r"&lt;br\s*/?&gt;|<br\s*/?>", "\n", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"&lt;hp:lineBreak\s*/?&gt;|<hp:lineBreak\s*/?>", "\n", text_value, flags=re.IGNORECASE)
        text_value = line_break_token.join(
            re.sub(r"[ \t]+", " ", line).strip()
            for line in re.split(r"(?:\r?\n)+", text_value)
            if line.strip()
        )
    else:
        text_value = re.sub(r"&lt;br\s*/?&gt;|<br\s*/?>", " / ", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"&lt;hp:lineBreak\s*/?&gt;|<hp:lineBreak\s*/?>", " / ", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"\s*(?:\r?\n)+\s*", " / ", text_value)
        text_value = re.sub(r"\s*/\s*/\s*", " / ", text_value).strip()
    updated = set_hwpx_xml_scope_text(cell_xml, text_value)
    if updated == cell_xml and text_value and not get_hwpx_xml_scope_text(cell_xml).strip():
        escaped = hwpx_escape_text(text_value)
        updated, inserted = re.subn(
            r"(<hp:run\b[^>]*)/>",
            rf"\1><hp:t>{escaped}</hp:t></hp:run>",
            cell_xml,
            count=1,
        )
        if not inserted:
            updated, inserted = re.subn(
                r"(<hp:run\b[^>]*>)",
                rf"\1<hp:t>{escaped}</hp:t>",
                cell_xml,
                count=1,
            )
        if not inserted:
            updated = cell_xml
    if preserve_line_breaks and line_break_token in updated:
        updated = updated.replace(line_break_token, "<hp:lineBreak/>")
    if updated == cell_xml:
        return table_xml, False
    return table_xml[:start] + updated + table_xml[end:], True


def set_hwpx_table_cell_char_pr_xml(
    table_xml: str,
    cell_index: int,
    char_pr_id: int,
) -> str:
    cells = find_hwpx_tag_spans(table_xml, "hp:tc")
    if cell_index < 0 or cell_index >= len(cells):
        return table_xml
    start, end = cells[cell_index]
    cell_xml = table_xml[start:end]
    updated = re.sub(
        r'(<hp:run\b[^>]*\bcharPrIDRef=")\d+("[^>]*>)',
        rf"\g<1>{char_pr_id}\2",
        cell_xml,
    )
    return table_xml[:start] + updated + table_xml[end:]


def patch_hwpx_grade_section_xml(xml_text: str, context: dict) -> str:
    project = context.get("project", {})
    project_label = f"ㅇ 평가대상 사업명 : {project.get('title') or '사업명 확인 필요'}"
    xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(
        xml_text,
        ["평가대상 사업명", "사업명(사업기간/예산)"],
        [project_label],
    )
    if not changed:
        xml_text, _ = replace_hwpx_paragraph_containing_with_lines_xml(
            xml_text,
            ["평가대상 사업명", "사업명"],
            [project_label],
        )
    for notice_parts in [
        ["평가자는", "종합 평가 등급", "점수"],
        ["구간별 점수 산정", "엑셀파일"],
    ]:
        xml_text, _ = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, notice_parts, [])
    for old_text, new_text in [
        ("ㅇ 평가대상 사업명 : 사업명(사업기간/예산)", project_label),
        ("※ 평가자는 주어진 평가표에 의거하여 종합 평가 등급과 점수를 모두 제시해야 함.", ""),
        ("※ 구간별 점수 산정 참고 사항은 별도 엑셀파일 참조 요망.", ""),
    ]:
        xml_text, _ = replace_hwpx_text_xml(xml_text, old_text, new_text)

    table_span = find_hwpx_grade_table_span_xml(xml_text)
    if table_span is None:
        raise ValueError("HWPX template grade table was not found")
    start, end = table_span
    table_xml = xml_text[start:end]
    criteria = criterion_grade_rows(context)
    for item in criteria:
        cell_pairs = GRADE_SCORE_REASON_CELLS.get(str(item.get("id")), [])
        question_rows = item.get("questionRows") if isinstance(item.get("questionRows"), list) else []
        for pair_index, (score_cell, reason_cell) in enumerate(cell_pairs):
            is_average = pair_index == len(cell_pairs) - 1
            if is_average:
                score_value = item["score"]
                reason = ""
            else:
                question = question_rows[pair_index] if pair_index < len(question_rows) else {}
                score_value = question.get("score", item["score"]) if isinstance(question, dict) else item["score"]
                reason = question.get("reason") or question.get("question") or item["reason"] if isinstance(question, dict) else item["reason"]
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, score_cell, format_score(score_value, '점'))
            formatted = "" if is_average else grade_question_reason(reason, GRADE_REASON_CELL_LIMITS[reason_cell])
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, reason_cell, formatted)
    overall = context.get("overall") or {}
    table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, 74, format_score(overall.get('score'), '/20점'))
    table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, 76, str(overall.get("governmentGrade") or "미흡"))
    table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, 78, str(overall.get("koicaGrade") or "F"))
    return xml_text[:start] + table_xml + xml_text[end:]


def cover_values_from_sections(context: dict, sections_by_id: dict[str, str] | None = None) -> dict:
    project = context.get("project", {})
    section_text = str((sections_by_id or {}).get("title") or (sections_by_id or {}).get("cover") or "")
    parsed_slots = parse_section1_cover_slots(section_text, context)
    if parsed_slots:
        return {
            "title": (project.get("title") if project.get("identity_resolution") else parsed_slots.get("project_title")) or str(project.get("title") or "사업명 확인 필요"),
            "date": parsed_slots.get("report_date") or datetime.now().strftime("%Y. %m"),
            "manager": parsed_slots.get("evaluation_manager") or "평가책임자 확인 필요",
            "institution": parsed_slots.get("evaluation_institution") or "평가수행기관 확인 필요",
        }
    lines = [line.strip() for line in re.split(r"\r?\n", section_text) if line.strip()]
    title_lines = [
        line for line in lines
        if not re.search(r"\d{4}\.\s*\d{1,2}", line)
        and "평가책임자" not in line
        and "평가수행기관" not in line
        and "KOICA" not in line
        and "World Friends" not in line
        and not re.fullmatch(r"\(?1\)?\s*표지", line)
        and "종료평가 결과보고서" not in line
    ][:3]
    if title_lines:
        title = "\n".join(title_lines)
    else:
        title = str(project.get("title") or "사업명 확인 필요").strip()
    if project.get("identity_resolution"):
        title = str(project["title"])
    date_line = next((line for line in lines if re.search(r"\d{4}\.\s*\d{1,2}", line)), "")
    manager_line = next((line for line in lines if "평가책임자" in line), "")
    institution_line = next((line for line in lines if "평가수행기관" in line), "")
    people = report_people_from_sections(sections_by_id or {}) if sections_by_id else infer_report_people([])
    return {
        "title": title,
        "date": date_line or datetime.now().strftime("%Y. %m"),
        "manager": manager_line or people.get("managerLine") or "평가책임자 확인 대상",
        "institution": institution_line or people.get("institutionLine") or "평가수행기관 확인 대상",
    }


def load_text_slot_review_manifest(section_number: int) -> dict:
    section_dirs = sorted((ROOT / "hwpx_sections").glob(f"Section{section_number}_*"))
    if not section_dirs:
        raise ValueError(f"HWPX section slot directory not found: section={section_number}")
    manifest_path = section_dirs[0] / "slots.review.json"
    if not manifest_path.exists():
        raise ValueError(f"HWPX text slot review manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "text-slot-review-v1":
        raise ValueError(f"Unsupported HWPX text slot review manifest: {manifest_path}")
    return manifest


def one_line_slot_value(value: object, fallback: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text or fallback
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def ensure_slot_prefix(value: str, prefix: str, fallback: str, max_chars: int) -> str:
    text = one_line_slot_value(value, fallback, max_chars)
    if text == fallback:
        return text
    label = prefix.strip()
    if text.startswith(prefix) or (label and text.startswith(label)):
        return text[:max_chars].rstrip()
    return f"{prefix}{text}"[:max_chars].rstrip()


from .toc_registry import TOC_LABELS as TOC_SECTION2_LABELS


def normalize_hwpx_manifest_value(section_number: int, value_key: str, value: object) -> object:
    """Apply outline-safe normalization to values written into fixed slots."""
    if section_number == 4 and value_key in GRADE_QUESTION_REASON_SLOT_KEYS and isinstance(value, str):
        return readable_grade_reason(value)
    if section_number == 7 and value_key == "pcp_feasibility_review" and isinstance(value, str):
        # The legacy template's PCP list marker is a private-use font glyph.
        # Keep authored facts intact while using a portable Unicode circle in
        # the exported slot. Do not discard other private-use source characters.
        return value.replace("\U000f006f", "○")
    if section_number == 6 and value_key in SECTION6_PROJECT_BACKGROUND_SLOT_KEYS:
        return normalize_project_background_slot(value_key, value)
    if section_number != 5:
        return value
    return normalize_summary_ko_value(value_key, value)


def section5_summary_paragraph_style(value_key: str) -> int | None:
    """Return the fixed paragraph level for every Korean-summary slot."""
    slot = SUMMARY_KO_ADAPTER.slots_by_key.get(value_key)
    return slot.para_pr_id if slot else None


def section1_cover_slot_values(context: dict, sections_by_id: dict[str, str]) -> dict[str, str]:
    cover = cover_values_from_sections(context, sections_by_id)
    manager = str(cover.get('manager') or '')
    institution = str(cover.get('institution') or '')
    return {
        "project_title": one_line_slot_value(cover.get("title"), "사업명 확인 필요", 80),
        "report_date": one_line_slot_value(cover.get("date") or datetime.now().strftime("%Y. %m"), datetime.now().strftime("%Y. %m"), 20),
        "evaluation_manager": one_line_slot_value(manager, "사업책임자 확인 필요", 40) if manager.startswith('사업책임자 ') else ensure_slot_prefix(manager, "평가책임자 ", "평가책임자 확인 대상", 40),
        "evaluation_institution": ensure_slot_prefix(
            institution,
            "평가수행기관 ",
            "평가수행기관 확인 대상",
            60,
        ) if not institution.startswith('사업 수행기관 ') else one_line_slot_value(institution, "사업 수행기관 확인 필요", 60),
    }


def apply_text_slot_review_manifest_xml(xml_text: str, manifest: dict, values: dict[str, str], hwpx_path: str) -> tuple[str, int]:
    changed_count = 0
    section_number = int((manifest.get("section") or {}).get("section_number") or 0)
    notice_opening_value_keys = {
        "responsible_evaluator_name_first",
        "country_name",
        "evaluated_project_name",
        "responsible_evaluator_name_second",
    }
    table_span: tuple[int, int] | None = None
    for slot in manifest.get("slots", []):
        if not isinstance(slot, dict) or slot.get("review_decision") != "candidate":
            continue
        replacement = slot.get("replacement") if isinstance(slot.get("replacement"), dict) else {}
        if replacement.get("hwpx_path") != hwpx_path:
            continue
        replacement_type = str(replacement.get("type") or "")
        value_key = str(replacement.get("value_key") or "")
        value_group = str(replacement.get("value_group") or "")
        if section_number == 3 and value_key in notice_opening_value_keys:
            continue
        if value_group and isinstance(values.get(value_group), dict):
            text = values.get(value_group, {}).get(value_key, "")
        else:
            text = values.get(value_key, "")
        text = normalize_hwpx_manifest_value(section_number, value_key, text)
        changed = False
        if replacement_type == "hp_t_text":
            if replacement.get("transform") == "append_single_space_if_missing" and text and not str(text).endswith(" "):
                text = f"{text} "
            xml_text, changed = set_hwpx_paragraph_text_node_xml(
                xml_text,
                int(replacement.get("paragraph_index", -1)),
                int(replacement.get("text_node_index_in_paragraph", -1)),
                text,
                expected_source_text=str(replacement.get("source_text")),
            )
        elif replacement_type == "paragraph_text":
            if text not in {None, ""}:
                xml_text, changed = set_hwpx_manifest_paragraph_text_xml(
                    xml_text,
                    int(replacement.get("paragraph_index", -1)),
                    text,
                    para_pr_id=section5_summary_paragraph_style(value_key) if section_number == 5 else None,
                )
        elif replacement_type == "paragraph_last_text":
            if text not in {None, ""}:
                xml_text, changed = replace_hwpx_paragraph_last_text_xml(
                    xml_text,
                    int(replacement.get("paragraph_index", -1)),
                    str(replacement.get("source_text") or "0"),
                    str(text),
                )
        elif replacement_type == "paragraph_run_text":
            if text not in {None, ""}:
                xml_text, changed = set_hwpx_paragraph_run_text_xml(
                    xml_text,
                    int(replacement.get("paragraph_index", -1)),
                    int(replacement.get("run_index", -1)),
                    text,
                )
        elif replacement_type in {"body_paragraph", "body_after_heading"}:
            if text not in {None, ""}:
                if section_number in {26, 27}:
                    continue
                lines = hwpx_report_body_lines(text)
                source_text = str(replacement.get("source_text") or "")
                if source_text:
                    xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, [source_text], lines)
                if not changed and replacement_type == "body_after_heading":
                    heading_text = str(replacement.get("heading_text") or "")
                    if heading_text:
                        xml_text, changed = patch_hwpx_body_after_heading_xml(xml_text, heading_text, text)
                if not changed:
                    xml_text, changed = set_hwpx_manifest_paragraph_text_xml(
                        xml_text,
                        int(replacement.get("paragraph_index", -1)),
                        text,
                    )
        elif replacement_type in {"remove_paragraph_containing", "remove_paragraph", "remove_text"}:
            source_text = str(replacement.get("source_text") or "")
            if source_text:
                xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(xml_text, [source_text], [])
        elif replacement_type == "remove_reference_block":
            required_parts = (
                values.get("remove_reference_blocks", {}).get(value_key)
                if isinstance(values.get("remove_reference_blocks"), dict)
                else None
            ) or replacement.get("required_parts")
            if isinstance(required_parts, list):
                xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(
                    xml_text,
                    [str(part) for part in required_parts],
                    [],
                )
        elif replacement_type == "paragraph_containing_lines":
            source_text = str(replacement.get("source_text") or "")
            if source_text and text not in {None, ""}:
                xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(
                    xml_text,
                    [source_text],
                    hwpx_report_body_lines(text, 300),
                )
        elif replacement_type == "grade_table_cell":
            clear_grade_subtotal_reason = (
                section_number == 4 and value_key in GRADE_SUBTOTAL_REASON_SLOT_KEYS
            )
            if text not in {None, ""} or clear_grade_subtotal_reason:
                if table_span is None:
                    table_span = find_hwpx_grade_table_span_xml(xml_text)
                if table_span is not None:
                    start, end = table_span
                    table_xml, changed = set_hwpx_table_cell_text_xml(
                        xml_text[start:end],
                        int(replacement.get("cell_index", -1)),
                        text,
                    )
                    if changed:
                        xml_text = xml_text[:start] + table_xml + xml_text[end:]
                        table_span = (start, start + len(table_xml))
        elif replacement_type == "table_cell":
            if text not in {None, ""}:
                required_parts = replacement.get("table_required_parts")
                if not isinstance(required_parts, list):
                    required_parts = []
                target_span = find_hwpx_table_span_by_required_parts_xml(
                    xml_text,
                    [str(part) for part in required_parts],
                )
                if target_span is not None:
                    start, end = target_span
                    table_xml, changed = set_hwpx_table_cell_text_xml(
                        xml_text[start:end],
                        int(replacement.get("cell_index", -1)),
                        text,
                    )
                    if changed:
                        xml_text = xml_text[:start] + table_xml + xml_text[end:]
        changed_count += 1 if changed else 0
    if section_number == 4:
        # The fixed grade-table questions must describe the current project,
        # not the KOICA sample project from which the layout originated.
        changed = xml_text.count("KOICA 타 사업")
        xml_text = xml_text.replace("KOICA 타 사업", "유관 ODA 사업")
        changed_count += changed
    if section_number == 3:
        def notice_person(value: object, role: str = "평가책임자") -> str:
            text_value = str(value or "").strip()
            if not text_value or text_value == "확인 필요":
                return "등록 자료 미기재"
            return text_value

        manager_first = notice_person(values.get("responsible_evaluator_name_first"))
        manager_second = notice_person(values.get("responsible_evaluator_name_second"), "책임 평가자") or manager_first
        country = str(values.get("country_name") or "").strip() or "대상국"
        project_name = str(values.get("evaluated_project_name") or "").strip() or "사업명 평가"
        if "평가" not in project_name:
            project_name = f"{project_name} 평가"
        commissioning_agency = str(values.get("commissioning_agency") or "지원기관").strip()
        implementing_agency = str(values.get("implementing_agency") or "수행기관").strip()
        opening = (
            f"  책임 평가자({manager_first})는 {commissioning_agency}, {implementing_agency}, {country} 관계기관 등 이해관계자의 협조와 등록 자료를 바탕으로 "
            f"‘{project_name}’를 수행하였습니다. 동 보고서는 책임 평가자인 {manager_second}의 주도하에 작성되었으며, "
            "평가내용 및 편집 일체에 대한 책임은 평가자에게 있습니다."
        )
        xml_text, changed = set_hwpx_paragraph_containing_text_xml(
            xml_text,
            ["책임 평가자 ㅇㅇㅇ은", "ㅇㅇ(나라명)", "ㅇㅇ(사업명)"],
            opening,
        )
        changed_count += 1 if changed else 0
        lead_line = str(values.get("lead_evaluator_line") or "").strip()
        if not lead_line:
            lead_line = f"  책 임 평 가 자 : {manager_first}"
        xml_text, changed = set_hwpx_paragraph_containing_text_xml(
            xml_text,
            ["책 임 평 가 자", "ㅇㅇㅇ"],
            lead_line,
        )
        changed_count += 1 if changed else 0
        # The source template contains fixed KOICA stakeholder and panel
        # statements. Replace them with the actual document-review scope.
        notice_paragraphs = (
            (
                ["본 보고서의 평가결과", "한국국제협력단"],
                "본 보고서는 등록된 사업문서를 바탕으로 작성한 문헌기반 평가 결과이며, 지원기관 또는 수행기관의 공식 입장을 대신하지 않습니다. 사실관계가 다른 경우 해당 근거자료를 우선하여 확인해야 합니다.",
            ),
            (
                ["KOICA 독립평가패널", "품질 등급"],
                "별도 외부 품질심의가 수행되었다는 근거는 확인되지 않았습니다. 본 결과물은 자동 완전성·조판 검증과 평가책임자 검토 범위에서 작성되었습니다.",
            ),
        )
        for required_parts, replacement_text in notice_paragraphs:
            xml_text, changed = set_hwpx_paragraph_containing_text_xml(
                xml_text, required_parts, replacement_text,
            )
            changed_count += 1 if changed else 0
        notice_label_replacements = {
            "평가 완료일": "평가 기준일",
            "평가 품질심의 완료일": "외부 품질심의",
            "평가품질 등급": "외부 품질심의 상태",
            "평가품질 등급:": "외부 품질심의 상태:",
            "평가품질 검토위원": "외부 품질심의위원",
        }
        for old, new in notice_label_replacements.items():
            xml_text, changed = replace_hwpx_text_xml(xml_text, old, new)
            changed_count += changed
        for old, new in (("확인 필요", "평가자"), ("ㅇㅇㅇ (소속)", "해당 없음"), ("=", "")):
            xml_text, changed = replace_hwpx_text_xml(xml_text, old, new)
            changed_count += changed
        # Some template labels include punctuation in the same text run.
        # This replacement is scoped to the notice logical section.
        changed = xml_text.count("평가품질 등급:")
        xml_text = xml_text.replace("평가품질 등급:", "외부 품질심의 상태:")
        changed_count += changed
    return xml_text, changed_count


def patch_hwpx_cover_slots_only_xml(xml_text: str, context: dict, sections_by_id: dict[str, str]) -> tuple[str, int]:
    manifest = load_text_slot_review_manifest(1)
    hwpx_path = str(manifest.get("section", {}).get("hwpx_path") or "Contents/section0.xml")
    values = section1_cover_slot_values(context, sections_by_id)
    xml_text, changed_count = apply_text_slot_review_manifest_xml(xml_text, manifest, values, hwpx_path)
    report_label = str((context.get("project") or {}).get("report_label") or "평가보고서").strip()
    compact_label = re.sub(r"\s+", "", report_label)
    if len(compact_label) > 12:
        if "종료" in report_label:
            report_label = "종료평가 결과보고서"
        elif "중간" in report_label:
            report_label = "중간평가 보고서"
        elif "현재" in report_label or "현시점" in report_label or "문헌기반" in report_label:
            report_label = "현시점 평가보고서"
        else:
            report_label = "평가보고서"
    xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(
        xml_text,
        ["종료평가 결과보고서"],
        [report_label],
    )
    return xml_text, changed_count + changed


def review_values_for_section(section_number: int, context: dict, sections_by_id: dict[str, str]) -> dict:
    values = build_section_manifest_values(section_number, context, sections_by_id)
    section_id = {
        2: "toc",
        3: "notice",
        4: "grade",
        5: "summary-ko",
        6: "project-background",
        7: "project-overview",
        8: "pdm",
        9: "eval-purpose",
        10: "eval-matrix",
    }.get(section_number, "")
    if section_id:
        section_text = sections_by_id.get(section_id, "")
        if section_number == 5:
            # Do not accept the legacy free-text ``summary`` key or merge a
            # partial payload with renderer fallbacks. The semantic adapter is
            # the sole source of all five reader-facing blocks.
            return parse_summary_ko_section(section_text)
        parsed = parse_structured_section_slots(section_text, section_id)
        if parsed:
            if section_id == "toc":
                return values
            if section_id == "project-background":
                parsed = {
                    key: normalize_project_background_slot(key, value) if key in SECTION6_PROJECT_BACKGROUND_SLOT_KEYS else value
                    for key, value in parsed.items()
                }
            if section_id == "project-overview":
                parsed = {
                    key: value
                    for key, value in parsed.items()
                    if key in SECTION7_PROJECT_OVERVIEW_SLOT_KEYS
                }
            if section_id == "eval-matrix":
                parsed = {
                    key: value
                    for key, value in parsed.items()
                    if key in SECTION10_EVAL_MATRIX_SLOT_KEYS
                }
            if section_id == "grade":
                # Scores and official grades stay system-owned. The generated
                # section may improve only question-level rationales; subtotal
                # rationale cells are structurally blank by contract.
                for key in GRADE_QUESTION_REASON_SLOT_KEYS:
                    if str(parsed.get(key) or "").strip():
                        values[key] = grade_question_reason(parsed[key], 120)
                for key in GRADE_SUBTOTAL_REASON_SLOT_KEYS:
                    values[key] = ""
                return values
            values.update({key: value for key, value in parsed.items() if key not in {"page_numbers"}})
            if isinstance(parsed.get("page_numbers"), dict):
                page_numbers = dict(values.get("page_numbers", {}))
                page_numbers.update({key: value for key, value in parsed["page_numbers"].items() if value not in {None, ""}})
                values["page_numbers"] = page_numbers
    return values


def validate_section5_summary_xml(
    xml_text: str,
    context: dict,
    sections_by_id: dict[str, str],
) -> dict[str, object]:
    """Verify the five-heading draft and HWPX carry identical reader text."""
    manifest = load_text_slot_review_manifest(5)
    validate_summary_ko_manifest(manifest)
    values = review_values_for_section(5, context, sections_by_id)
    spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    errors: list[str] = []
    texts = [re.sub(r"\s+", " ", get_hwpx_xml_scope_text(xml_text[start:end])).strip() for start, end in spans]
    summary_label_index = next((index for index, text in enumerate(texts) if text == "1. 국문 요약"), -1)
    start_index = next((index for index, text in enumerate(texts) if text == "(1) 대상사업개요"), -1)
    end_index = next(
        (index for index, text in enumerate(texts) if index > start_index and re.sub(r"\s+", "", text) == "II.대상사업개요"),
        -1,
    )
    if summary_label_index < 0 or start_index < 0 or end_index <= start_index:
        raise RuntimeError("국문 요약 HWPX 적용 검증 실패: 5개 항목 본문 범위를 찾지 못했습니다.")

    expected_lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in render_summary_ko_document(values).splitlines()
        if line.strip()
    ]
    actual_paragraphs = [xml_text[start:end] for start, end in spans[start_index:end_index] if get_hwpx_xml_scope_text(xml_text[start:end]).strip()]
    actual_lines = [re.sub(r"\s+", " ", get_hwpx_xml_scope_text(paragraph)).strip() for paragraph in actual_paragraphs]
    if actual_lines != expected_lines:
        mismatch = next(
            (
                index for index, (actual, expected) in enumerate(zip(actual_lines, expected_lines))
                if actual != expected
            ),
            min(len(actual_lines), len(expected_lines)),
        )
        errors.append(
            "초안-HWPX 문단 불일치: "
            f"index={mismatch}, actual={actual_lines[mismatch:mismatch + 1]!r}, "
            f"expected={expected_lines[mismatch:mismatch + 1]!r}"
        )

    verified = 0
    for paragraph, line in zip(actual_paragraphs, actual_lines):
        if re.match(r"^\([1-5]\)\s*", line):
            expected_para, expected_char = 67, 18
        elif line.startswith("ㅇ "):
            expected_para, expected_char = 69, 28
        elif line.startswith("- "):
            expected_para, expected_char = 92, 28
        else:
            errors.append(f"허용되지 않는 국문 요약 문단 계층: {line[:100]!r}")
            continue
        para_match = re.search(r'<hp:p\b[^>]*\bparaPrIDRef="(\d+)"', paragraph)
        char_ids = re.findall(r'<hp:run\b[^>]*\bcharPrIDRef="(\d+)"', paragraph)
        if not para_match or int(para_match.group(1)) != expected_para:
            errors.append(f"국문 요약 문단 paraPr 불일치: {line[:40]} / {para_match.group(1) if para_match else '없음'}")
            continue
        expected_char_ids = (
            {18, 28}
            if line.startswith("- ") and re.match(r"^-\s+\([^()]{2,15}\)\s+\S", line)
            else {expected_char}
        )
        if not char_ids or {int(char_id) for char_id in char_ids} != expected_char_ids:
            errors.append(f"국문 요약 문단 charPr 불일치: {line[:40]} / {sorted(set(char_ids))}")
            continue
        if line == "(5) 결론":
            opening = re.search(r"<hp:p\b[^>]*>", paragraph)
            if not opening or 'pageBreak="1"' not in opening.group(0):
                errors.append("국문 요약 (5) 결론은 새 쪽에서 시작해야 합니다.")
                continue
        verified += 1

    # Layout contract: the static ``1. 국문 요약`` heading, every ``(n)``
    # block heading, and every ``ㅇ`` topic must have one empty paragraph
    # immediately above it.  Checking the physical XML paragraph sequence
    # prevents visually compressed output even when reader text is identical.
    for index in range(summary_label_index, end_index):
        line = texts[index]
        if line != "1. 국문 요약" and not re.match(r"^\([1-5]\)\s+", line) and not line.startswith("ㅇ "):
            continue
        if index == 0 or texts[index - 1] != "":
            errors.append(f"국문 요약 제목 위 한 줄 여백 누락: {line}")
    if errors:
        raise RuntimeError("국문 요약 HWPX 적용 검증 실패: " + "; ".join(errors))
    return {
        "block_count": len(SUMMARY_KO_BLOCKS),
        "paragraph_count": len(actual_lines),
        "verified_paragraphs": verified,
        "text_exact": True,
        "paragraph_styles_exact": True,
    }


NARRATIVE_SECTION_LAYOUTS: dict[int, dict[str, object]] = {
    9: {"body_key": "evaluation_purpose_scope_body", "headings": ("1. 평가의 목적과 범위",), "stops": ("2. 평가매트릭스(Evaluation Matrix)", "2. 평가매트릭스")},
    11: {"body_key": "eval_methods_body", "headings": ("3. 평가방법", "3. 평가 방법"), "stops": ("4. 평가의 한계",)},
    12: {"body_key": "eval_limitations_body", "headings": ("4. 평가의 한계",), "stops": ("5. 평가팀 구성 및 시행체계", "5. 평가팀 구성")},
    13: {"body_key": "eval_team_body", "headings": ("5. 평가팀 구성 및 시행체계", "5. 평가팀 구성"), "stops": ()},
    14: {"body_key": "achievement_body", "headings": ("IV. 성과 달성도", "IV. 성과달성도"), "stops": ()},
    15: {"body_key": "criteria_relevance_body", "headings": ("1. 적절성",), "stops": ("2. 일관성",)},
    16: {"body_key": "criteria_coherence_body", "headings": ("2. 일관성",), "stops": ("3. 효과성",)},
    17: {"body_key": "criteria_effectiveness_body", "headings": ("3. 효과성",), "stops": ()},
    18: {"body_key": "criteria_efficiency_body", "headings": ("4. 효율성",), "stops": ("5. 지속가능성",)},
    19: {"body_key": "criteria_sustainability_body", "headings": ("5. 지속가능성",), "stops": ("6. 범분야 이슈",)},
    20: {"body_key": "criteria_crosscutting_body", "headings": ("6. 범분야 이슈",), "stops": ("IV. 결론",)},
    21: {"body_key": "criteria_other_body", "headings": ("7. 그 외 평가기준",), "stops": ("IV. 결론",), "insert_before": "IV. 결론", "style_heading": "6. 범분야 이슈"},
    22: {"body_key": "conclusion_body", "headings": ("1. 결론",), "stops": ("2. 작동요인 및 비작동요인",)},
    23: {"body_key": "working_factors_body", "headings": ("(1) 작동요인",), "stops": ("(2) 비작동요인",)},
    24: {"body_key": "nonworking_factors_body", "headings": ("(2) 비작동요인",), "stops": ()},
    25: {"body_key": "theory_body", "headings": ("(3) 변화이론 분석",), "stops": ("3. 환류과제 및 교훈",)},
}


def insert_hwpx_narrative_heading_before_xml(
    xml_text: str,
    *,
    before_heading: str,
    style_heading: str,
    heading: str,
) -> tuple[str, bool]:
    """Create a missing logical heading from existing template styles."""
    spans = find_hwpx_tag_spans(xml_text, "hp:p")
    style_index = -1
    before_index = -1
    for index, (start, end) in enumerate(spans):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        text = get_hwpx_xml_scope_text(paragraph_xml).strip()
        if style_index < 0 and paragraph_text_matches_anchor(text, style_heading):
            style_index = index
        if paragraph_text_matches_anchor(text, before_heading):
            before_index = index
            break
    if style_index < 0 or before_index < 0:
        return xml_text, False

    style_start, style_end = spans[style_index]
    heading_xml = remove_hwpx_section_properties_xml(xml_text[style_start:style_end])
    heading_xml = set_hwpx_xml_scope_text(heading_xml, heading)
    heading_id = binascii.crc32(f"logical-heading|{heading}".encode("utf-8")) & 0xFFFFFFFF
    heading_xml = re.sub(r'(<hp:p\b[^>]*\bid=")\d+(")', rf"\g<1>{heading_id}\2", heading_xml, count=1)

    body_template = ""
    for index in range(style_index + 1, before_index):
        start, end = spans[index]
        candidate = xml_text[start:end]
        if any(marker in candidate for marker in ("<hp:tbl", "<hp:pic", "<hp:ole", "<hp:equation")):
            continue
        body_template = remove_hwpx_section_properties_xml(candidate)
        break
    if not body_template:
        body_template = remove_hwpx_section_properties_xml(xml_text[style_start:style_end])
    body_template = set_hwpx_xml_scope_text(body_template, "")
    body_id = binascii.crc32(f"logical-heading-body|{heading}".encode("utf-8")) & 0xFFFFFFFF
    body_template = re.sub(r'(<hp:p\b[^>]*\bid=")\d+(")', rf"\g<1>{body_id}\2", body_template, count=1)

    insert_at = spans[before_index][0]
    return xml_text[:insert_at] + heading_xml + body_template + xml_text[insert_at:], True


def patch_hwpx_narrative_section_xml(
    xml_text: str,
    section_number: int,
    body: object,
) -> tuple[str, int]:
    layout = NARRATIVE_SECTION_LAYOUTS.get(section_number)
    if not layout or not str(body or "").strip():
        return xml_text, 0
    headings = tuple(str(item) for item in layout.get("headings", ()) if str(item).strip())
    stops = tuple(str(item) for item in layout.get("stops", ()) if str(item).strip())
    if layout.get("insert_before") and headings:
        already_present = any(
            paragraph_text_matches_anchor(
                get_hwpx_xml_scope_text(xml_text[start:end]).strip(),
                headings[0],
            )
            for start, end in find_hwpx_tag_spans(xml_text, "hp:p")
            if "<hp:tbl" not in xml_text[start:end]
        )
        if not already_present:
            xml_text, inserted = insert_hwpx_narrative_heading_before_xml(
                xml_text,
                before_heading=str(layout.get("insert_before") or ""),
                style_heading=str(layout.get("style_heading") or ""),
                heading=headings[0],
            )
            if not inserted:
                return xml_text, 0
    for heading in headings:
        updated, changed = replace_hwpx_heading_block_xml(xml_text, heading, body, stops)
        if changed:
            return updated, changed
    return xml_text, 0


def _summary_document_paragraph_xml(template: str, text: str, ordinal: int) -> str:
    paragraph = remove_hwpx_section_properties_xml(template)
    stripped = text.strip()
    if re.match(r"^\([1-5]\)\s*", stripped):
        kind = "subheading"
    elif stripped.startswith("ㅇ "):
        kind = "bullet"
    elif stripped.startswith("- "):
        kind = "detail"
    else:
        kind = "body"
    # Outline styles provide the visible indentation. Canonicalize the marker
    # before writing XML so legacy drafts with leading spaces do not receive a
    # second, text-level indent on top of paraPr 92.
    visible_text = f"- {stripped[2:].lstrip()}" if kind == "detail" else text
    paragraph = set_hwpx_xml_scope_text(
        paragraph,
        visible_text,
        preserve_edge_whitespace=kind != "detail",
    )
    paragraph = apply_hwpx_report_outline_style_xml(paragraph, kind)
    paragraph = style_hwpx_detail_summary_label_xml(paragraph)
    if stripped == "(5) 결론":
        paragraph = re.sub(r'pageBreak="[01]"', 'pageBreak="1"', paragraph, count=1)
    paragraph_id = binascii.crc32(f"summary-v4|{ordinal}|{visible_text}".encode("utf-8")) & 0xFFFFFFFF
    return re.sub(
        r'(<hp:p\b[^>]*\bid=")\d+("[^>]*>)',
        rf"\g<1>{paragraph_id}\2",
        paragraph,
        count=1,
    )


def patch_hwpx_summary_ko_document_xml(xml_text: str, values: dict[str, str]) -> tuple[str, int]:
    """Replace the legacy 가~바 summary with the canonical five-heading draft."""
    document = render_summary_ko_document(values)
    spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    texts = [re.sub(r"\s+", " ", get_hwpx_xml_scope_text(xml_text[start:end])).strip() for start, end in spans]
    summary_label_index = next((index for index, text in enumerate(texts) if text == "1. 국문 요약"), -1)
    end_index = next(
        (
            index for index, text in enumerate(texts)
            if index > summary_label_index and re.sub(r"\s+", "", text) == "II.대상사업개요"
        ),
        -1,
    )
    if summary_label_index < 0 or end_index <= summary_label_index + 1:
        raise RuntimeError("국문 요약 HWPX 본문 교체 범위를 찾지 못했습니다.")

    start_index = summary_label_index + 1
    heading_template = xml_text[spans[start_index][0]:spans[start_index][1]]
    bullet_template = next(
        (
            xml_text[start:end]
            for (start, end), text in zip(spans[start_index:end_index], texts[start_index:end_index])
            if re.match(r"^ㅇ\s+", text)
        ),
        heading_template,
    )
    detail_template = next(
        (
            xml_text[start:end]
            for (start, end), text in zip(spans[start_index:end_index], texts[start_index:end_index])
            if re.match(r"^-\s+", text)
        ),
        heading_template,
    )
    blank_template = next(
        (
            xml_text[start:end]
            for (start, end), text in zip(spans[start_index:end_index], texts[start_index:end_index])
            if not text and "<hp:tbl" not in xml_text[start:end]
        ),
        heading_template,
    )

    rendered: list[str] = []
    rendered_ordinal = 0
    last_was_blank = False
    for line in document.splitlines():
        stripped = line.strip()
        if (re.match(r"^\([1-5]\)\s*", stripped) or stripped.startswith("ㅇ ")) and not last_was_blank:
            rendered.append(
                _summary_document_paragraph_xml(blank_template, "", rendered_ordinal)
            )
            rendered_ordinal += 1
            last_was_blank = True
        if not stripped:
            template = blank_template
        elif re.match(r"^\([1-5]\)\s*", stripped):
            template = heading_template
        elif stripped.startswith("ㅇ "):
            template = bullet_template
        elif stripped.startswith("- "):
            template = detail_template
        else:
            raise RuntimeError(f"국문 요약에 허용되지 않는 문단 계층이 있습니다: {line[:100]}")
        rendered.append(_summary_document_paragraph_xml(template, line, rendered_ordinal))
        rendered_ordinal += 1
        last_was_blank = not stripped

    start = spans[start_index][0]
    end = spans[end_index][0]
    prefix = xml_text[:start]
    if summary_label_index == 0 or texts[summary_label_index - 1] != "":
        summary_label_start = spans[summary_label_index][0]
        leading_blank = _summary_document_paragraph_xml(blank_template, "", -1)
        prefix = (
            xml_text[:summary_label_start]
            + leading_blank
            + xml_text[summary_label_start:start]
        )
    return prefix + "".join(rendered) + xml_text[end:], len(rendered)


def patch_hwpx_review_section_slots_xml(xml_text: str, section_number: int, context: dict, sections_by_id: dict[str, str]) -> tuple[str, int]:
    manifest = load_text_slot_review_manifest(section_number)
    if section_number == 5:
        validate_summary_ko_manifest(manifest)
    hwpx_path = str(manifest.get("section", {}).get("hwpx_path") or "")
    values = review_values_for_section(section_number, context, sections_by_id)
    if section_number == 5:
        return patch_hwpx_summary_ko_document_xml(xml_text, values)
    if section_number == 2:
        page_numbers = values.get("page_numbers") if isinstance(values.get("page_numbers"), dict) else {}
        return patch_hwpx_section2_toc_page_numbers_xml(xml_text, page_numbers)
    narrative_layout = NARRATIVE_SECTION_LAYOUTS.get(section_number)
    if narrative_layout:
        body_key = str(narrative_layout.get("body_key") or "")
        return patch_hwpx_narrative_section_xml(xml_text, section_number, values.get(body_key, ""))
    xml_text, changed_count = apply_text_slot_review_manifest_xml(xml_text, manifest, values, hwpx_path)
    if section_number == 11:
        body = section_body_or_gap(sections_by_id, "eval-methods", "평가방법")
        lines = hwpx_report_body_lines(body)
        if body and lines and not hwpx_body_lines_present_xml(xml_text, lines):
            xml_text, changed = replace_hwpx_paragraph_containing_with_lines_xml(
                xml_text,
                [
                    "KOICA 정책 문서(네팔 협력국 전략",
                    "사업관련 자료(RD, 사업개요서, PDM",
                    "성과관리 자료(성과점검 보고서 및 종료선 조사결과 보고서)",
                ],
                lines,
            )
            changed_count += changed
            if not changed:
                for heading, stops in [
                    ("3. 평가방법", ["4. 평가의 한계"]),
                    ("3. 평가 방법", ["4. 평가의 한계"]),
                    ("3. ?됯?諛⑸쾿", ["4. ?됯????쒓퀎"]),
                ]:
                    xml_text, changed = replace_hwpx_heading_block_xml(xml_text, heading, body, stops)
                    changed_count += changed
                    if changed:
                        break
    if section_number == 2:
        page_numbers = values.get("page_numbers") if isinstance(values.get("page_numbers"), dict) else {}
        toc_labels = {
            "summary_ko_page": "1. 국문 요약",
            "project_background_page": "1. 사업 추진배경",
            "project_overview_page": "2. 사업개요",
            "pdm_page": "3. 사업설계매트릭스",
            "evaluation_purpose_page": "1. 평가의 목적과 범위",
            "evaluation_matrix_page": "평가매트릭스",
            "evaluation_methods_page": "3. 평가 방법",
            "evaluation_limitations_page": "4. 평가의 한계",
            "evaluation_team_page": "5. 평가팀 구성",
            "achievement_page": "Ⅳ. 성과달성도",
            "criteria_relevance_page": "1. 적절성",
            "criteria_coherence_page": "2. 일관성",
            "criteria_effectiveness_page": "3. 효과성",
            "criteria_efficiency_page": "4. 효율성",
            "criteria_sustainability_page": "5. 지속가능성",
            "criteria_crosscutting_page": "6. 범분야 이슈",
            "criteria_other_page": "7. 그 외 평가기준",
            "conclusion_page": "1. 결론",
            "factors_page": "2. 작동요인 및 비작동요인",
            "feedback_lessons_page": "3. 환류과제 및 교훈",
            "appendix_summary_en_page": "1. 평가결과 영문 요약",
            "appendix_fieldwork_page": "2. 현지",
            "appendix_daily_activities_page": "3. 일별활동내역",
            "appendix_interviewees_page": "4. 면담자 목록",
            "appendix_survey_page": "5. 설문조사지",
            "appendix_references_page": "6. 참고문헌",
            "appendix_other_page": "7. 그 외 첨부자료",
        }
        for key, label in toc_labels.items():
            value = str(page_numbers.get(key) or "").strip()
            if not value:
                continue
            xml_text, changed = replace_hwpx_paragraph_last_text_by_label_xml(xml_text, label, "0", value)
            changed_count += 1 if changed else 0
    if section_number == 21 and changed_count == 0:
        body = section_body_or_gap(sections_by_id, "criteria-other", "그 외 평가기준")
        if body and not hwpx_body_lines_present_xml(xml_text, hwpx_report_body_lines(body)):
            lines = ["7. 그 외 평가기준", *hwpx_report_body_lines(body, 1200)]
            xml_text, changed = replace_blank_paragraph_before_heading_xml(xml_text, "IV. 결론", lines)
            if not changed:
                xml_text, changed = replace_last_paragraph_containing_before_heading_xml(
                    xml_text,
                    ["네팔 최빈곤 지역 대상"],
                    "IV. 결론",
                    lines,
                )
            changed_count += changed
    if section_number == 5:
        xml_text, hierarchy_changes = normalize_hwpx_report_outline_styles_xml(xml_text)
        changed_count += hierarchy_changes
    return xml_text, changed_count


def patch_hwpx_cover_xml(xml_text: str, context: dict, sections_by_id: dict[str, str] | None = None) -> str:
    cover = cover_values_from_sections(context, sections_by_id)
    title = cover["title"]
    year_month = datetime.now().strftime("%Y. %m")
    manager_line = cover["manager"]
    institution_line = cover["institution"]
    date_line = cover.get("date") or year_month
    xml_text, changed = replace_hwpx_paragraph_exact_with_lines_xml(
        xml_text,
        "ㅇㅇ사업 종료평가 결과보고서",
        [title, "종료평가 결과보고서"],
    )
    if not changed:
        xml_text, changed = replace_hwpx_paragraph_exact_with_lines_xml(
            xml_text,
            "ㅇㅇ사업 종료평가",
            [title, "종료평가"],
        )
    if not changed:
        xml_text, _ = replace_hwpx_paragraph_containing_with_lines_xml(
            xml_text,
            ["{사업이름}", "종료평가 결과보고서"],
            [title, "종료평가 결과보고서"],
        )
    for old_text, new_text in [
        ("{사업이름}", title),
        ("2023. 12", date_line),
        ("평가책임자 OOO", manager_line),
        ("평가수행기관 OOO(혹은 로고)", institution_line),
        ("평가책임자 확인 필요", manager_line),
        ("평가수행기관 확인 필요", institution_line),
        ("평가책임자 확인 대상", manager_line),
        ("평가수행기관 확인 대상", institution_line),
    ]:
        xml_text, _ = replace_hwpx_text_xml(xml_text, old_text, new_text)
    xml_text, _ = set_hwpx_manifest_paragraph_text_xml(xml_text, 15, manager_line)
    xml_text, _ = set_hwpx_manifest_paragraph_text_xml(xml_text, 16, institution_line)
    return xml_text


def patch_hwpx_core_body_xml(xml_text: str, sections_by_id: dict[str, str]) -> str:
    replacements = [
        ("ㅇ 보고서 주요 내용 위주로 3~5쪽 이내 요약 작성", sections_by_id.get("summary") or sections_by_id.get("summary-ko") or ""),
        ("ㅇ 평가매트릭스 상 평가질문(연번 함께 표기)에 대한 평가결과 제시", sections_by_id.get("criteria-relevance") or ""),
        ("ㅇ 결론은 평가목표와 대상 사업의 전반적인 목표에 관한 내용", sections_by_id.get("conclusion") or ""),
        ("ㅇ 평가결과를 기반으로, 사업의 성과달성에 기여한 요인과 그 원인(What worked, why) 제시", sections_by_id.get("working-factors") or ""),
        ("ㅇ 평가결과를 기반으로, 사업의 성과 달성을 저해했거나 성과 미달성의 원인(What did not work, why) 제시", sections_by_id.get("nonworking-factors") or ""),
    ]
    for old_text, new_text in replacements:
        if new_text:
            xml_text, changed = replace_hwpx_paragraph_exact_with_lines_xml(xml_text, old_text, hwpx_report_body_lines(new_text))
            if not changed:
                xml_text, _ = replace_hwpx_text_xml(xml_text, old_text, "\n".join(hwpx_report_body_lines(new_text)))
        else:
            xml_text, _ = replace_hwpx_text_xml(xml_text, old_text, "")
    return xml_text


def patch_hwpx_section_target_bodies_xml(xml_text: str, section_index: int, sections_by_id: dict[str, str]) -> str:
    block_heading_map = {
        3: [
            ("1. 국문 요약", "summary", "국문 요약", ["II. 대상사업개요"]),
            ("1. 사업 추진배경", "project-background", "사업 추진배경", ["2. 사업개요"]),
        ],
        4: [
            ("1. 평가의 목적과 범위", "eval-purpose", "평가의 목적과 범위", ["2. 평가매트릭스"]),
            ("3. 평가방법", "eval-methods", "평가방법", ["4. 평가의 한계"]),
            ("4. 평가의 한계", "eval-limitations", "평가의 한계", ["5. 평가팀 구성 및 시행체계"]),
            ("5. 평가팀 구성 및 시행체계", "eval-team", "평가팀 구성 및 시행체계", []),
        ],
        6: [
            ("1. 적절성", "criteria-relevance", "적절성", ["2. 일관성"]),
            ("2. 일관성", "criteria-coherence", "일관성", ["3. 효과성"]),
            ("3. 효과성", "criteria-effectiveness", "효과성", []),
        ],
        7: [
            ("4. 효율성", "criteria-efficiency", "효율성", ["5. 지속가능성"]),
            ("5. 지속가능성", "criteria-sustainability", "지속가능성", ["6. 범분야 이슈"]),
            ("6. 범분야 이슈", "criteria-crosscutting", "범분야 이슈", ["7. 그 외 평가기준", "IV. 결론"]),
            ("7. 그 외 평가기준", "criteria-other", "그 외 평가기준", ["IV. 결론"]),
            ("1. 결론", "conclusion", "결론", ["2. 작동요인 및 비작동요인"]),
            ("(1) 작동요인", "working-factors", "작동요인", ["(2) 비작동요인"]),
            ("(2) 비작동요인", "nonworking-factors", "비작동요인", []),
        ],
        8: [
            ("(3) 변화이론 분석", "theory", "변화이론 분석", ["3. 환류과제 및 교훈"]),
            ("(1) 환류과제", "feedback", "환류과제", ["(2) 교훈"]),
            ("(2) 교훈", "lessons", "교훈", []),
        ],
    }
    for heading, section_id, label, stop_headings in block_heading_map.get(section_index, []):
        body = sections_by_id.get(section_id)
        if section_id == "summary" and not body:
            body = sections_by_id.get("summary-ko")
        xml_text, changed = replace_hwpx_heading_block_xml(
            xml_text,
            heading,
            body or section_body_or_gap(sections_by_id, section_id, label),
            stop_headings,
        )
        if not changed:
            xml_text, changed = patch_hwpx_body_after_heading_xml(
                xml_text,
                heading,
                body or section_body_or_gap(sections_by_id, section_id, label),
            )
        if not changed:
            xml_text, _ = append_hwpx_lines_to_heading_text_xml(
                xml_text,
                heading,
                body or section_body_or_gap(sections_by_id, section_id, label),
            )
    return xml_text


def patch_hwpx_file_manifests_xml(
    xml_text: str,
    hwpx_path: str,
    context: dict,
    sections_by_id: dict[str, str],
) -> str:
    for section_number in range(1, 28):
        manifest = read_hwpx_section_manifest(section_number)
        if section_number in {1, 2, 3, 7, 14}:
            continue
        if manifest and manifest.get("hwpx_path") == hwpx_path:
            xml_text = patch_hwpx_section_manifest_xml(xml_text, section_number, context, sections_by_id)
    return xml_text


def patch_hwpx_orphan_editor_sections_xml(xml_text: str, hwpx_path: str, sections_by_id: dict[str, str]) -> str:
    """Ensure saved editor sections with missing template headings are still represented."""
    if hwpx_path == "Contents/section3.xml":
        body = sections_by_id.get("project-background")
        if body and not hwpx_body_lines_present_xml(xml_text, hwpx_report_body_lines(body)):
            xml_text = append_hwpx_section_block_xml(xml_text, "II. 대상사업개요", "1. 사업 추진배경", body)
    elif hwpx_path == "Contents/section4.xml":
        matrix_body = sections_by_id.get("eval-matrix")
        if matrix_body and not hwpx_body_lines_present_xml(xml_text, hwpx_report_body_lines(matrix_body)):
            xml_text = append_hwpx_section_block_xml(xml_text, "2. 평가매트릭스", "2. 평가매트릭스(Evaluation Matrix)", matrix_body)
        for section_id, heading in [
            ("eval-methods", "3. 평가방법"),
            ("eval-limitations", "4. 평가의 한계"),
            ("eval-team", "5. 평가팀 구성 및 시행체계"),
        ]:
            body = sections_by_id.get(section_id)
            if body and not hwpx_body_lines_present_xml(xml_text, hwpx_report_body_lines(body)):
                xml_text = append_hwpx_section_block_xml(xml_text, "2. 평가매트릭스", heading, body)
    elif hwpx_path == "Contents/section7.xml":
        body = sections_by_id.get("criteria-other")
        if body and not hwpx_body_lines_present_xml(xml_text, hwpx_report_body_lines(body)):
            xml_text = append_hwpx_section_block_xml(xml_text, "6. 범분야 이슈", "7. 그 외 평가기준", body)
    return xml_text


def cleanup_hwpx_placeholder_text_xml(xml_text: str) -> str:
    cleanup_pairs = [
        # The fixed placeholder accidentally repeats chapter IV for the
        # conclusion after IV. 성과 달성도 and V. 기준별 평가결과.
        ("IV. 결론", "VI. 결론"),
        ("placeholder", "확인 필요"),
        ("질문 작성", "평가질문 확인 필요"),
        ("평가자  작성", "확인 필요"),
        ("평가자 작성", "확인 필요"),
        ("20XX-20XX년", "사업기간 확인 필요"),
        ("XXX만불 / X,XXX백만원", "예산 확인 필요"),
        ("XX만불 (XXX백만원)", "예산 확인 필요"),
        ("000 (소속, 직함, 담당업무)", "확인 필요 (소속, 직함, 담당업무)"),
        ("000 (소속, 직함, 담당 업무)", "확인 필요 (소속, 직함, 담당업무)"),
    ]
    for old_text, new_text in cleanup_pairs:
        xml_text, _ = replace_hwpx_text_xml(xml_text, old_text, new_text)
    spans = find_hwpx_all_tag_spans(xml_text, "hp:p")
    replacements: dict[int, str] = {}
    for index, (start, end) in enumerate(spans):
        paragraph_xml = xml_text[start:end]
        if "<hp:tbl" in paragraph_xml:
            continue
        paragraph_text = get_hwpx_xml_scope_text(paragraph_xml)
        stripped_text = paragraph_text.strip()
        # Do not match these words as substrings: terms such as 교과목 개발
        # and 학생 모집 are also legitimate current-project evidence. Fixed
        # sample tables are cleared by their semantic adapters before this
        # cleanup pass; only an exact authoring token remains a placeholder.
        updated_text = "확인 필요" if stripped_text == "작성" else paragraph_text
        for old_text, new_text in cleanup_pairs:
            updated_text = updated_text.replace(old_text, new_text)
        if updated_text != paragraph_text:
            replacements[index] = set_hwpx_xml_scope_text(paragraph_xml, updated_text)
    for index in sorted(replacements.keys(), reverse=True):
        start, end = spans[index]
        xml_text = xml_text[:start] + replacements[index] + xml_text[end:]
    return xml_text


def patch_hwpx_project_overview_table_xml(xml_text: str, context: dict, sections_by_id: dict[str, str]) -> str:
    project = context.get("project") or {}
    title = str(project.get("title") or "확인 필요").strip()
    period = str(project.get("period") or "사업기간 확인 필요").strip()
    budget = str(project.get("budget") or "예산 확인 필요").strip()
    overview_body = str(sections_by_id.get("project-overview") or "").strip()

    def overview_field(labels: list[str], fallback: str) -> str:
        lines = [line.strip(" -*\t") for line in overview_body.splitlines() if line.strip()]
        for label in labels:
            pattern = re.compile(rf"^{re.escape(label)}(?:\([^)]*\))?\s*[:：]\s*(?:내\s*용\s*[:：]\s*)?(.*)$")
            for index, line in enumerate(lines):
                match = pattern.search(line)
                if not match:
                    continue
                value = match.group(1).strip()
                collected = [value] if value else []
                for next_line in lines[index + 1:index + 3]:
                    if re.match(r"^(사업명|대상국가|사업기간|총\s*사업예산|사업유형|사업분야|사업\s*목적|수원국|우리정부|PCP|사전타당성)", next_line):
                        break
                    collected.append(next_line)
                result = " ".join(item for item in collected if item).strip()
                if result:
                    return short_text(result, 260)
        return fallback

    target_table = None
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        if "사업명(국문)" in table_xml and "사업기간" in table_xml and "사업 세부내용" in table_xml:
            target_table = (start, end, table_xml)
            break
    if target_table is None:
        return xml_text
    start, end, table_xml = target_table
    cell_values = {
        4: f"▣ {title}",
        6: "▣ " + overview_field(["사업명(영문)", "영문 사업명"], "Additional information required"),
        8: "▣ " + overview_field(["대상국가", "대상국가(지역)", "대상지역"], "자동 초안 생성 제약: 대상국가 및 대상지역"),
        10: f"▣ 구분 : 신규/계속 확인 필요\n▣ 기간 : {period}\n▣ 총 사업예산 : {budget}",
        14: "▣ " + overview_field(["사업분야"], "자동 초안 생성 제약: 사업분야"),
        16: "▣ " + overview_field(["사업 목적", "사업목적"], "자동 초안 생성 제약: 사업 목적"),
        19: "󰁯 관계기관 PCP : 확인 필요\n󰁯 수총기관 공문 : 확인 필요\n󰁯 사전타당성조사 : 확인 필요",
        23: "▣ 소요예산 : 예산 확인 필요\n▪확인 필요",
        25: "▣ 소요예산 : 예산 확인 필요\n▪확인 필요",
        27: "▣ 소요예산 : 예산 확인 필요\n▪확인 필요",
        29: "▣ 소요예산 : 예산 확인 필요\n▪확인 필요",
        31: "▣ 자동 초안 생성 제약: 수원국/파트너 기관 분담사항 확인",
    }
    for cell_index, value in cell_values.items():
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, cell_index, value)
    return xml_text[:start] + table_xml + xml_text[end:]


ACHIEVEMENT_HEADER_ROWS = 3
ACHIEVEMENT_TEMPLATE_ITEM_COUNT = 5
ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM = 3
ACHIEVEMENT_FIRST_CELL_INDEX = 20
ACHIEVEMENT_CELLS_PER_ITEM = 14
ACHIEVEMENT_CELL_OFFSETS = {
    "name": 0,
    "indicator": 1,
    "baseline": 2,
    "target": 3,
    "endline": 6,
    "achievement": 7,
    "mov": 8,
    "note": 9,
}


def achievement_row_starts(item_count: int) -> tuple[int, ...]:
    return tuple(
        ACHIEVEMENT_FIRST_CELL_INDEX + ACHIEVEMENT_CELLS_PER_ITEM * index
        for index in range(max(0, item_count))
    )


def parse_achievement_items(body: object) -> list[str]:
    from .achievement_records import indexed_achievement_records
    indexed = indexed_achievement_records(body)
    if indexed:
        return indexed
    records = parse_markdown_table_records(body)
    if records:
        items: list[str] = []
        for record in records:
            name = markdown_record_value(record, ["성과달성도", "성과", "산출물", "구분"], "성과지표")
            indicator = markdown_record_value(record, ["PDM 지표명", "PDM 지표", "성과지표 (OVI)", "성과지표", "OVI"])
            baseline = markdown_record_value(record, ["기초선", "기획단계"])
            target = markdown_record_value(record, ["목표치", "목표"])
            endline = markdown_record_value(record, ["종료선", "수행단계", "최종 성과데이터", "실적"])
            achievement = markdown_record_value(record, ["달성도", "대비 결과", "달성률"])
            mov = markdown_record_value(record, ["지표입증수단", "MOV", "검증수단"])
            note = markdown_record_value(record, ["비고", "특이사항"])
            if indicator or baseline or target or endline or achievement:
                items.append(
                    "\n".join([
                        name,
                        f"성과지표: {indicator}",
                        f"기초선: {baseline}",
                        f"목표치: {target}",
                        f"종료선: {endline}",
                        f"달성도: {achievement}",
                        f"지표입증수단: {mov}",
                        f"비고: {note}",
                    ])
                )
        if items:
            return items

    text = normalize_hwpx_table_value(body, 10000)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    grouped: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^ㅇ\s+", line):
            if current:
                grouped.append("\n".join(current))
            current = [re.sub(r"^ㅇ\s+", "", line)]
        elif current and re.match(r"^-\s+", line):
            current.append(re.sub(r"^-\s+", "", line))
        elif current and re.search(r"(성과지표|기초선|목표치|종료선|달성도|지표입증수단|MOV)\s*[:：]", line):
            current.append(line)
    if current:
        grouped.append("\n".join(current))
    # A converted achievement table may be followed by reader-facing analysis
    # bullets such as ``ㅇ (차이 원인과 함의)``.  Those paragraphs often
    # mention words like "성과지표" or "달성률" in prose, but they are not
    # PDM rows.  Require an explicit labelled indicator field instead of a
    # loose keyword hit so narrative commentary cannot become a synthetic
    # table row with an empty indicator.
    indicator_labels = [
        "PDM 지표명", "PDM 지표", "성과목표 및 지표 (OVI)", "성과목표 및 지표",
        "성과지표 (OVI)", "성과 지표 명칭", "산출 지표 명칭", "지표 명칭", "성과지표",
    ]
    valid = [item for item in grouped if field_from_item(item, indicator_labels, "")]
    return valid or split_report_items(body)


def achievement_item_fields(item: str, index: int) -> dict[str, str]:
    indicator = field_from_item(
        item,
        [
            "PDM 지표명", "PDM 지표", "성과목표 및 지표 (OVI)", "성과목표 및 지표",
            "성과지표 (OVI)", "성과 지표 명칭", "산출 지표 명칭", "지표 명칭", "성과지표",
        ],
        "",
    )
    first_line = next((line.strip() for line in item.splitlines() if line.strip()), "")
    item_id_match = re.match(r"^(?:ㅇ\s+)?지표\s*ID\s*[:：]\s*(.+)$", first_line, re.IGNORECASE)
    category_match = re.match(r"^(?:구분|계층)\s*[:：]\s*(.+)$", first_line)
    if item_id_match:
        name = normalize_hwpx_table_value(item_id_match.group(1), 32)
    elif category_match:
        category = normalize_hwpx_table_value(category_match.group(1), 24)
        name = f"{category} 성과지표 {index + 1}" if category else f"성과지표 {index + 1}"
    elif first_line and not re.match(r"^(?:PDM\s*)?성과?(?:목표 및 )?지표\s*[:：]", first_line):
        name = first_line
    else:
        name = indicator or f"성과지표 {index + 1}"
    return {
        "name": name,
        "indicator": indicator or "확인 필요",
        "baseline": field_from_item(item, ["기초선 (Baselines)", "기초선", "기획단계"], "확인 필요"),
        "target": field_from_item(item, ["누적 목표치", "목표치 (Targets)", "목표치", "목표"], "확인 필요"),
        "endline": field_from_item(
            item,
            ["실적 (현재시점)", "실적 (누적/최신)", "누적 실적", "누적달성치 / 실적", "누적달성치", "실적", "수행단계", "종료선"],
            "확인 필요",
        ),
        "achievement": field_from_item(item, ["달성률(%)", "달성률 (%)", "달성률", "달성도", "대비 결과 (B-A)", "대비 결과"], "확인 필요"),
        "mov": field_from_item(item, ["검증수단(MOV)", "검증수단 (MOV)", "검증수단", "지표입증수단 (MOV)", "지표입증수단", "MOV"], "확인 필요"),
        "note": field_from_item(
            item,
            [
                "달성 여부 및 차이 원인 / 해설",
                "달성 여부 및 차이 원인",
                "달성 여부 및 원인 해설",
                "달성 여부 및 미달성 원인 / 비고",
                "달성 여부 및 미달성 원인",
                "비고",
            ],
            "",
        ),
    }


def _shift_hwpx_row_addresses(row_xml: str, delta: int) -> str:
    return re.sub(
        r'(<hp:cellAddr\b[^>]*\browAddr=")(\d+)(")',
        lambda match: f"{match.group(1)}{int(match.group(2)) + delta}{match.group(3)}",
        row_xml,
    )


def _resize_achievement_table_xml(table_xml: str, item_count: int) -> str:
    """Resize the fixed five-item template in complete three-row blocks."""
    if item_count <= 0:
        return table_xml
    row_spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    required_template_rows = ACHIEVEMENT_HEADER_ROWS + (
        ACHIEVEMENT_TEMPLATE_ITEM_COUNT * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
    )
    if len(row_spans) < required_template_rows:
        raise RuntimeError(
            f"성과달성도 원본 표 구조가 올바르지 않습니다: {len(row_spans)}행"
        )
    if item_count > ACHIEVEMENT_TEMPLATE_ITEM_COUNT:
        template_block = [
            table_xml[start:end]
            for start, end in row_spans[-ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:]
        ]
        clones: list[str] = []
        for extra_index in range(item_count - ACHIEVEMENT_TEMPLATE_ITEM_COUNT):
            delta = ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM * (extra_index + 1)
            clones.extend(_shift_hwpx_row_addresses(row_xml, delta) for row_xml in template_block)
        close_at = table_xml.rfind("</hp:tbl>")
        if close_at < 0:
            raise RuntimeError("성과달성도 원본 표 닫기 태그를 찾을 수 없습니다.")
        table_xml = table_xml[:close_at] + "".join(clones) + table_xml[close_at:]
    return trim_hwpx_table_rows_xml(
        table_xml,
        header_rows=ACHIEVEMENT_HEADER_ROWS,
        data_rows=item_count * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
    )


def patch_hwpx_achievement_table_xml(xml_text: str, sections_by_id: dict[str, str]) -> str:
    achievement_body = str(sections_by_id.get("achievement") or "").strip()
    items = parse_achievement_items(achievement_body)
    if achievement_body and not items:
        raise RuntimeError("성과달성도 본문에서 표 행을 파싱하지 못했습니다.")
    target_table = None
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        if "성과지표" in table_xml and "기초선" in table_xml and "달성도" in table_xml:
            target_table = (start, end, table_xml)
            break
    if target_table is None and items:
        raise RuntimeError("성과달성도 원본 표를 찾을 수 없습니다.")
    if target_table is None:
        return xml_text
    start, end, table_xml = target_table
    # The placeholder guidance in the first yellow header cell is longer
    # than the fixed column width and overlaps adjacent text in Hancom/rhwp.
    # Keep the semantic label but remove the authoring instruction.
    table_xml, _ = set_hwpx_table_cell_text_xml(
        table_xml,
        11,
        "주요 산출물·성과",
    )
    if not items:
        return xml_text[:start] + table_xml + xml_text[end:]

    table_xml = _resize_achievement_table_xml(table_xml, len(items))
    cells = find_hwpx_tag_spans(table_xml, "hp:tc")
    row_starts = achievement_row_starts(len(items))
    required_cell_count = row_starts[-1] + max(ACHIEVEMENT_CELL_OFFSETS.values()) + 1
    if len(cells) < required_cell_count:
        raise RuntimeError(
            f"성과달성도 표 셀이 부족합니다: 필요 {required_cell_count}개, 실제 {len(cells)}개"
        )
    for cell_index in range(20, len(cells)):
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, cell_index, "")

    cell_values: dict[int, str] = {}
    for index, item in enumerate(items):
        base = row_starts[index]
        fields = achievement_item_fields(item, index)
        cell_values.update({
            # The former fixed character budgets appended a literal ellipsis,
            # so the HWPX no longer matched the editor draft.  Pagination and
            # content-driven row sizing now own fit; the adapter preserves the
            # complete reviewed value.
            base + ACHIEVEMENT_CELL_OFFSETS["name"]: normalize_hwpx_table_value(fields["name"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["indicator"]: normalize_hwpx_table_value(fields["indicator"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["baseline"]: normalize_hwpx_table_value(fields["baseline"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["target"]: normalize_hwpx_table_value(fields["target"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["endline"]: normalize_hwpx_table_value(fields["endline"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["achievement"]: normalize_hwpx_table_value(fields["achievement"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["mov"]: normalize_hwpx_table_value(fields["mov"], 10000),
            base + ACHIEVEMENT_CELL_OFFSETS["note"]: normalize_hwpx_table_value(
                fields["note"] or fields["achievement"],
                10000,
            ),
        })
    for cell_index, value in cell_values.items():
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, cell_index, value)
    return xml_text[:start] + table_xml + xml_text[end:]


def normalize_hwpx_table_value(value: object, limit: int = 260) -> str:
    """Normalize presentation syntax without shortening stored table content.

    ``limit`` remains accepted for legacy callers, but physical row pagination
    now owns fit. A character count is not a safe bound on readable row height.
    """
    text = str(value or "").replace("\r", "\n")
    text = re.sub(r"&lt;br\s*/?&gt;|<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;hp:lineBreak\s*/?&gt;|<hp:lineBreak\s*/?>", "\n", text)
    # Markdown tables are retained until fixed HWPX tables are populated so
    # their row boundaries are not lost. Inline authoring markers, however,
    # are not reader-facing content and must never be written into a cell.
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip(" -\t\n;")


def fit_hwpx_table_value(value: object, limit: int) -> str:
    """Fit arbitrary generated prose into a fixed-layout template cell.

    The source drafts remain complete in the database.  Fixed HWPX tables are
    summaries, so line breaks and Markdown bullets are folded into a compact
    sentence and the value is cut at the last natural boundary that fits the
    reviewed cell budget.  This prevents a long new draft from expanding a
    row over adjacent rows or beyond the physical page.
    """
    text = normalize_hwpx_table_value(value, 10000)
    text = re.sub(r"\s*\n\s*", " · ", text)
    text = re.sub(r"(?:\s*·\s*){2,}", " · ", text)
    text = re.sub(r"\s+", " ", text).strip(" ·,;/")
    if limit <= 0 or len(text) <= limit:
        return text

    window = text[:limit].rstrip()
    minimum = max(8, round(limit * 0.58))
    boundary = -1
    for marker in ("?", ".", "다.", "음.", ";", "·", ",", "/", " "):
        position = window.rfind(marker)
        if position >= minimum:
            boundary = max(boundary, position + (1 if marker in {"?", ".", ";"} else 0))
    if boundary >= minimum:
        window = window[:boundary]
    return window.rstrip(" ·,;/") + "…"


def trim_hwpx_table_rows_xml(table_xml: str, header_rows: int, data_rows: int) -> str:
    """Remove unused trailing template rows and keep the declared size valid."""
    row_spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    if not row_spans:
        return table_xml
    keep_count = min(len(row_spans), max(0, header_rows) + max(1, data_rows))
    for start, end in reversed(row_spans[keep_count:]):
        table_xml = table_xml[:start] + table_xml[end:]

    kept_rows = find_hwpx_tag_spans(table_xml, "hp:tr")
    row_heights: list[int] = []
    for start, end in kept_rows:
        heights = [
            int(match.group(1))
            for match in re.finditer(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', table_xml[start:end])
        ]
        if heights:
            # A rowspan cell reports the combined height; the smallest height
            # in the row is the actual row contribution.
            row_heights.append(min(heights))
    table_xml = re.sub(
        r'(<hp:tbl\b[^>]*\browCnt=")\d+("[^>]*>)',
        rf"\g<1>{len(kept_rows)}\2",
        table_xml,
        count=1,
    )
    if row_heights:
        table_xml = re.sub(
            r'(<hp:sz\b[^>]*\bheight=")\d+("[^>]*>)',
            rf"\g<1>{sum(row_heights)}\2",
            table_xml,
            count=1,
        )
    return table_xml


def ensure_recommendation_table_rows_xml(table_xml: str, header_rows: int, data_rows: int) -> str:
    """Extend the template's last unmerged row before writing every record."""
    spans = find_hwpx_tag_spans(table_xml, "hp:tr")
    required = header_rows + max(1, data_rows)
    if len(spans) >= required or len(spans) <= header_rows:
        return table_xml
    prototype = table_xml[spans[-1][0]:spans[-1][1]]
    clones = "".join(_shift_hwpx_row_addresses(prototype, delta) for delta in range(1, required - len(spans) + 1))
    close_at = table_xml.rfind("</hp:tbl>")
    table_xml = table_xml[:close_at] + clones + table_xml[close_at:]
    return trim_hwpx_table_rows_xml(table_xml, header_rows, data_rows)


def parse_markdown_table_records(body: object) -> list[dict[str, str]]:
    """Return all Markdown table rows without flattening row boundaries."""
    lines = str(body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    records: list[dict[str, str]] = []
    index = 0
    while index < len(lines) - 1:
        header_line = lines[index].strip()
        divider_line = lines[index + 1].strip()
        if not (
            header_line.startswith("|")
            and header_line.endswith("|")
            and divider_line.startswith("|")
            and divider_line.endswith("|")
        ):
            index += 1
            continue
        headers = [normalize_hwpx_table_value(cell, 80) for cell in header_line.strip("|").split("|")]
        dividers = [cell.strip() for cell in divider_line.strip("|").split("|")]
        if not headers or not all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in dividers):
            index += 1
            continue
        index += 2
        while index < len(lines):
            row_line = lines[index].strip()
            if not (row_line.startswith("|") and row_line.endswith("|")):
                break
            cells = [normalize_hwpx_table_value(cell, 600) for cell in row_line.strip("|").split("|")]
            cells += [""] * max(0, len(headers) - len(cells))
            record = {headers[pos]: cells[pos] for pos in range(min(len(headers), len(cells))) if headers[pos]}
            if any(record.values()):
                records.append(record)
            index += 1
    return records


def markdown_record_value(record: dict[str, str], aliases: list[str], fallback: str = "") -> str:
    normalized = {re.sub(r"\s+", "", key): value for key, value in record.items()}
    for alias in aliases:
        alias_key = re.sub(r"\s+", "", alias)
        for key, value in normalized.items():
            if alias_key == key or alias_key in key:
                if str(value or "").strip():
                    return str(value).strip()
    return fallback


def split_report_items(body: object) -> list[str]:
    text = normalize_hwpx_table_value(body, 5000)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items: list[str] = []
    current = ""
    for line in lines:
        starts_item = bool(re.match(r"^(?:[-•ㅇ❍]|\d+[.)])\s+", line)) or bool(re.match(r"^[가-힣A-Za-z0-9/()·\s-]{2,35}\s*:", line))
        if starts_item and current:
            items.append(current.strip())
            current = line
        else:
            current = f"{current} {line}".strip() if current else line
    if current:
        items.append(current.strip())
    return [re.sub(r"^(?:[-•ㅇ❍]|\d+[.)])\s*", "", item).strip() for item in items if item.strip()]


def field_from_item(item: str, labels: list[str], fallback: str = "") -> str:
    stop_labels = (
        "관찰사항|환류과제|담당\\s*주체|담당주체|선정\\s*사유|선정사유|우선순위|후속\\s*확인자료|유관부서\\s*의견|"
        "완료\\s*기한|기한|점검\\s*주기|검토\\s*주기|"
        "체크리스트\\s*질문|구분|계층|PDM\\s*지표(?:명)?|성과(?:목표\\s*및\\s*)?지표(?:\\s*\\(OVI\\))?|기획단계|"
        "기초선(?:\\s*\\(Baselines\\))?|누적\\s*목표치|목표치(?:\\s*\\(Targets\\))?|목표|수행단계|종료선|"
        "누적\\s*실적|누적달성치(?:\\s*/\\s*실적)?|실적|달성률(?:\\s*\\(%\\))?|달성도|"
        "대비\\s*결과(?:\\s*\\(B-A\\))?|검증수단(?:\\s*\\(MOV\\))?|지표입증수단(?:\\s*\\(MOV\\))?|MOV|"
        "근거\\s*위치|판단|"
        "달성\\s*여부\\s*및\\s*원인\\s*해설|"
        "달성\\s*여부\\s*및\\s*차이\\s*원인(?:\\s*/\\s*해설)?|"
        "달성\\s*여부\\s*및\\s*미달성\\s*원인(?:\\s*/\\s*비고)?|비고"
    )
    for label in labels:
        label_pattern = re.sub(r"\\ ", r"\\s*", re.escape(label))
        match = re.search(
            rf"{label_pattern}\s*[:：]\s*(.*?)(?=(?:\s*;\s*|\n\s*[-•∙ㆍ·]?\s*)(?:{stop_labels})\s*[:：]|$)",
            item,
            re.DOTALL,
        )
        if match:
            return normalize_hwpx_table_value(match.group(1), 220)
    return fallback


def lesson_field_from_item(item: str, labels: list[str], fallback: str = "") -> str:
    stop_labels = (
        r"교훈\s*내용|분야/일반\s*구분|분야\s*구분|구분|"
        r"이전년도\s*교훈\s*중복\s*여부|중복\s*여부|중복여부|"
        r"M&E\s*체크리스트\s*질문|M&E\s*체크리스트|체크리스트\s*질문"
    )
    for label in labels:
        label_pattern = re.sub(r"\\ ", r"\\s*", re.escape(label))
        match = re.search(
            rf"{label_pattern}\s*[:：]\s*(.*?)(?=(?:\n\s*[-•∙ㆍ·]?\s*)(?:{stop_labels})\s*[:：]|$)",
            item,
            re.DOTALL,
        )
        if match:
            return normalize_hwpx_table_value(match.group(1), 220)
    return fallback


def recommendation_field_from_item(item: str, labels: list[str], fallback: str = "") -> str:
    stop_labels = (
        r"구분|제언|이해관계자|관찰사항|환류과제|담당\s*주체|담당주체|"
        r"선정\s*사유|선정사유|후속\s*확인자료|유관부서\s*의견|"
        r"우선순위|완료\s*기한|기한|점검\s*주기|검토\s*주기"
    )
    for label in labels:
        label_pattern = re.sub(r"\\ ", r"\\s*", re.escape(label))
        match = re.search(
            rf"{label_pattern}\s*[:：]\s*(.*?)(?=(?:\n\s*[-•∙ㆍ·]?\s*)(?:{stop_labels})\s*[:：]|$)",
            item,
            re.DOTALL,
        )
        if match:
            return normalize_hwpx_table_value(match.group(1), 260)
    return fallback


def first_report_item_line(item: str) -> str:
    for line in str(item or "").splitlines():
        cleaned = re.sub(r"^(?:[-•ㅇ❍]|\d+[.)])\s*", "", line.strip())
        if not cleaned:
            continue
        if re.match(r"^(관찰사항|담당\s*주체|선정\s*사유|우선순위|후속\s*확인자료)\s*[:：]", cleaned):
            continue
        if re.match(r"^환류과제\s*[:：]", cleaned):
            return field_from_item(cleaned, ["환류과제"], cleaned)
        return normalize_hwpx_table_value(cleaned, 220)
    return ""


def find_hwpx_table_span_by_text(xml_text: str, required_parts: list[str], min_cells: int = 1) -> tuple[int, int, str] | None:
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        if len(find_hwpx_tag_spans(table_xml, "hp:tc")) < min_cells:
            continue
        table_text = get_hwpx_xml_scope_text(table_xml)
        if all(part in table_text for part in required_parts):
            return start, end, table_xml
    return None


def pdm_segment(item: str, markers: list[str], stop_markers: list[str]) -> str:
    marker_pattern = "|".join(re.escape(marker) for marker in markers)
    if stop_markers:
        stop_pattern = "|".join(re.escape(marker) for marker in stop_markers)
        pattern = rf"(?:{marker_pattern})(?:\s*\([^)]*\))?\s*[:：]?\s*(.*?)(?=(?:{stop_pattern})(?:\s*\([^)]*\))?\s*[:：]?|$)"
    else:
        pattern = rf"(?:{marker_pattern})(?:\s*\([^)]*\))?\s*[:：]?\s*(.*)$"
    match = re.search(pattern, item, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return normalize_hwpx_table_value(match.group(1), 260)


def parse_pdm_items(body: object) -> dict[str, dict[str, str]]:
    rows = {}
    for item in split_report_items(body):
        lowered = item.lower()
        if "overall goal" in lowered or "상위목표" in item or "impact" in lowered:
            key = "impact"
            heading_markers = ["Overall Goal", "상위목표", "Impact", "영향"]
        elif "project purpose" in lowered or "사업목표" in item or "outcome" in lowered:
            key = "outcome"
            heading_markers = ["Project Purpose", "사업목표", "Outcome", "성과"]
        elif "outputs" in lowered or "산출물" in item:
            key = "outputs"
            heading_markers = ["Outputs", "산출물"]
        elif "activities" in lowered or "활동" in item:
            key = "activities"
            heading_markers = ["Activities", "활동"]
        else:
            continue
        ovi_markers = ["Objectively Verifiable Indicators", "객관적 검증지표", "OVI"]
        mov_markers = ["Means of Verification", "검증수단", "MOV"]
        assumption_markers = ["Important Assumptions", "중요가정", "Assumptions"]
        narrative = item
        for marker in [*ovi_markers, *mov_markers, *assumption_markers]:
            marker_pos = re.search(re.escape(marker), narrative, re.IGNORECASE)
            if marker_pos:
                narrative = narrative[:marker_pos.start()]
                break
        for marker in heading_markers:
            narrative = re.sub(rf"^{re.escape(marker)}(?:\s*\([^)]*\))?\s*[:：]?", "", narrative, flags=re.IGNORECASE).strip()
        rows[key] = {
            "narrative": normalize_hwpx_table_value(narrative, 10000),
            "ovi": pdm_segment(item, ovi_markers, [*mov_markers, *assumption_markers]),
            "mov": pdm_segment(item, mov_markers, assumption_markers),
            "assumption": pdm_segment(item, assumption_markers, []),
        }
    return rows


def patch_hwpx_pdm_table_xml(xml_text: str, sections_by_id: dict[str, str]) -> str:
    target = find_hwpx_table_span_by_text(xml_text, ["프로그램 요약", "객관적 검증지표", "중요가정"], 20)
    if target is None:
        return xml_text
    start, end, table_xml = target
    body = str(sections_by_id.get("pdm") or "")
    rows = parse_pdm_items(body)
    parsed_slots = parse_structured_section_slots(body, "pdm") or {}

    def row_value(row_key: str, field: str, fallback: str) -> str:
        slot_key = {
            ("impact", "narrative"): "impact_summary",
            ("impact", "ovi"): "impact_indicator",
            ("impact", "mov"): "impact_mov",
            ("impact", "assumption"): "impact_assumption",
            ("outcome", "narrative"): "outcome_summary",
            ("outcome", "ovi"): "outcome_indicator",
            ("outcome", "mov"): "outcome_mov",
            ("outcome", "assumption"): "outcome_assumption",
            ("outputs", "narrative"): "outputs_summary",
            ("outputs", "ovi"): "outputs_indicator",
            ("outputs", "mov"): "outputs_mov",
            ("outputs", "assumption"): "outputs_assumption",
            ("activities", "narrative"): "activities",
            ("activities", "assumption"): "preconditions",
        }.get((row_key, field), "")
        if slot_key and parsed_slots.get(slot_key):
            return str(parsed_slots[slot_key])
        value = (rows.get(row_key) or {}).get(field)
        return str(value or fallback)

    cell_values = {
        # The template stores the row label and narrative in two separate
        # first-column cells.  The other three columns span both rows.
        5: row_value("impact", "ovi", "시설분만율, SBA 출산율, 5세 이하 아동 사망률 등 영향 지표"),
        6: row_value("impact", "mov", "통합지역조사, HMIS, 종료선 조사"),
        7: row_value("impact", "assumption", "지진, 내전, 감염병 등 중대한 외부 충격이 사업성과를 왜곡하지 않는다는 가정"),
        8: row_value("impact", "narrative", "사업대상지역 모자보건 개선"),
        10: row_value("outcome", "ovi", "산전진찰, 외래진료, 백신 접종률, 아동 질환 처치율 등 성과 지표"),
        11: row_value("outcome", "mov", "통합지역조사, HMIS, 종료보고서"),
        12: row_value("outcome", "assumption", "병원·보건소 운영과 지역 보건서비스 제공 체계가 유지된다는 가정"),
        13: row_value("outcome", "narrative", "무구지역 보건의료체계 및 모성의료서비스 개선"),
        15: row_value("outputs", "ovi", "HMIS 정기보고, 병동 재건축, 조산사 양성, 이동검진, 사회감사, 캠페인 참가자"),
        16: row_value("outputs", "mov", "HMIS 보고서, 건축 보고서, 장학지원 보고서, 이동검진 보고서, 사회감사 보고서"),
        17: row_value("outputs", "assumption", "네팔정부 협조, 부지 확보, 보건소와 지역사회 단체의 참여"),
        18: row_value("outputs", "narrative", "지역보건체계 거버넌스 강화, 모자보건 인프라 개선, 주민 참여 증진"),
        22: row_value("activities", "narrative", "거버넌스 강화, 보건 인프라 개선, 주민 보건교육 및 사업관리 활동"),
        23: parsed_slots.get("inputs") or "예산, 인력, 장비, 교육 및 사업관리 자원",
        24: row_value("activities", "assumption", "수행기관 협조, 현지 자료 접근성, 이해관계자 참여, 데이터 품질 확보"),
    }
    for cell_index, cell_text in cell_values.items():
        table_xml, _ = set_hwpx_table_cell_text_xml(
            table_xml,
            cell_index,
            cell_text,
            preserve_line_breaks=True,
        )
        # Typography and pagination belong to the final HWPX layout stage.
        # This content patcher only maps the authoritative PDM values into
        # their semantic cells so it can also be reused by non-print outputs.
    return xml_text[:start] + table_xml + xml_text[end:]


def parse_eval_matrix_items(body: object) -> dict[str, dict[str, str]]:
    items = {}
    for item in split_report_items(body):
        label_match = re.match(r"([가-힣/·\s]+)\s*[:：]\s*(.*)$", item)
        if not label_match:
            continue
        label = label_match.group(1).strip()
        rest = label_match.group(2).strip()
        items[label] = {
            "question": field_from_item(rest, ["평가 질문", "평가질문"], rest),
            "indicator": field_from_item(rest, ["측정지표", "지표"], "평가지표 확인 필요"),
            "source": field_from_item(rest, ["자료출처", "자료 출처", "출처"], "사업개요서, PDM, 성과자료, 면담자료"),
            "method": field_from_item(rest, ["분석방법", "분석 방법", "방법"], "문헌조사, 면담, 현장확인, 기준별 채점"),
        }
    return items


def patch_hwpx_eval_matrix_table_xml(xml_text: str, context: dict, sections_by_id: dict[str, str]) -> str:
    target = find_hwpx_table_span_by_text(xml_text, ["분석방법", "평가질문", "적절성"], 40)
    if target is None:
        return xml_text
    start, end, table_xml = target
    parsed_slots = parse_structured_section_slots(sections_by_id.get("eval-matrix") or "", "eval-matrix") or {}
    if parsed_slots:
        cell_slots = {
            6: "relevance_question",
            7: "relevance_indicator",
            8: "relevance_source",
            9: "relevance_method",
            11: "coherence_question",
            12: "coherence_indicator",
            13: "coherence_source",
            14: "coherence_method",
            16: "effectiveness_question",
            17: "effectiveness_indicator",
            18: "effectiveness_source",
            19: "effectiveness_method",
            21: "efficiency_question",
            22: "efficiency_indicator",
            23: "efficiency_source",
            24: "efficiency_method",
            26: "sustainability_question",
            27: "sustainability_indicator",
            28: "sustainability_source",
            29: "sustainability_method",
            31: "human_rights_question",
            32: "human_rights_indicator",
            33: "human_rights_source",
            34: "human_rights_method",
            36: "gender_question",
            37: "gender_indicator",
            38: "gender_source",
            39: "gender_method",
            41: "environment_question",
            42: "environment_indicator",
            43: "environment_source",
            44: "environment_method",
        }
        for cell_index, key in cell_slots.items():
            value = parsed_slots.get(key)
            if value not in {None, ""}:
                table_xml, _ = set_hwpx_table_cell_text_xml(
                    table_xml,
                    cell_index,
                    normalize_hwpx_table_value(value, 10000),
                )
        return xml_text[:start] + table_xml + xml_text[end:]
    matrix_items = parse_eval_matrix_items(sections_by_id.get("eval-matrix") or "")
    score_rows = {row.get("name"): row for row in criterion_grade_rows(context)}
    row_specs = [
        ("적절성", 5, "1.적절성", "사업 설계가 수원국 정책, 수요, 환경변화에 적절히 부합하였는가?", "정책 부합성, 수요 반영도, 상황변화 대응력"),
        ("일관성", 10, "2.일관성", "국내외 전략, 타 공여기관, 범분야 이슈와 조화롭게 연계되었는가?", "타 공여기관 조화, 전략 연계성, 범분야 이슈 반영도"),
        ("효과성", 15, "3.효과성", "계획된 산출물과 성과목표가 달성되었고 수혜자에게 효과가 나타났는가?", "산출물 달성도, 성과지표 변화, 수혜자 접근성"),
        ("효율성", 20, "4.효율성", "투입, 일정, 운영방식이 산출과 성과 달성에 효율적으로 활용되었는가?", "예산 집행 효율성, 일정관리, 투입 대비 산출"),
        ("지속가능성", 25, "5.지속가능성(준비도)", "사업 종료 후 인력, 재정, 제도, 유지관리 체계가 지속될 수 있는가?", "인력·재정 자립도, 유지관리 체계, 제도화 수준"),
        ("인권/취약계층주류화", 30, "6. 인권/취약계층주류화", "취약계층 접근성과 포용성이 사업 설계 및 성과관리 과정에 반영되었는가?", "취약계층 접근성, 서비스 이용 형평성, 수혜자 참여도"),
        ("성주류화", 35, "7.성주류화", "성별 수요와 참여, 편익 차이가 사업 설계와 성과분석에 반영되었는가?", "여성 참여, 모성보건 접근성, 성별 성과 차이"),
        ("환경주류화", 40, "8.환경주류화", "환경 및 기후 위험이 사업 설계, 운영, 사후관리 과정에서 고려되었는가?", "환경위험 검토, 의료폐기물·시설 운영관리, 재난 대응"),
    ]
    for label, base, heading, fallback_question, fallback_indicator in row_specs:
        source_item = matrix_items.get(label) or {}
        score_item = score_rows.get(label) or {}
        reason = score_item.get("reason") or ""
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base, heading)
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 1, normalize_hwpx_table_value(source_item.get("question") or fallback_question, 10000))
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 2, normalize_hwpx_table_value(source_item.get("indicator") or reason or fallback_indicator, 10000))
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 3, normalize_hwpx_table_value(source_item.get("source") or "사업개요서, PDM, 성과자료, 면담자료", 10000))
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 4, normalize_hwpx_table_value(source_item.get("method") or "문헌조사, 면담, 현장확인, 기준별 채점", 10000))
    return xml_text[:start] + table_xml + xml_text[end:]


def parse_feedback_items(body: object) -> list[dict[str, str]]:
    # Current narrative authoring uses an 'ㅇ' heading with labelled detail
    # lines. Split on the record's 구분 field, never on every detail bullet.
    # Otherwise three recommendations become dozens of unrelated rows.
    source = str(body or "")
    starts = list(re.finditer(r"(?m)^\s*(?:[-•∙ㆍ·]\s*)?구분\s*[:：]", source))
    labelled_rows = []
    for i, start in enumerate(starts):
        block = source[start.start():starts[i + 1].start() if i + 1 < len(starts) else len(source)]
        fields = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(
            r"(?m)^\s*(?:[-•∙ㆍ·]\s*)?(구분|제언|이해관계자|선정 사유|우선순위|완료기한|점검주기|후속 확인자료)\s*[:：]\s*([^\n]+)", block)}
        if not fields.get("제언"):
            continue
        priority, due, cycle = (fields.get(key) or "확인 필요" for key in ("우선순위", "완료기한", "점검주기"))
        labelled_rows.append({
            "observation": fields.get("구분") or "제언", "task": fields["제언"],
            "owner": fields.get("이해관계자") or "확인 필요",
            "reason": f"우선순위: {priority} | 선정 사유: {fields.get('선정 사유') or '확인 필요'}",
            "opinion": f"완료기한: {due} | 점검주기: {cycle} | 확인자료: {fields.get('후속 확인자료') or '확인 필요'}",
            "priority": priority, "due_date": due, "review_cycle": cycle,
        })
    if labelled_rows:
        return labelled_rows
    markdown_rows = parse_markdown_table_records(body)
    parsed_markdown: list[dict[str, str]] = []
    for record in markdown_rows:
        task = markdown_record_value(record, ["제언", "환류과제", "조치사항", "후속조치", "후속 조치"])
        if not task:
            continue
        reason = markdown_record_value(record, ["선정 사유", "선정사유", "기대효과"], "평가결과 환류 및 후속 성과관리 강화 필요")
        priority = markdown_record_value(record, ["우선순위"], "중")
        due_date = markdown_record_value(record, ["완료기한", "완료 기한", "기한"], "후속 이행계획 확정 시")
        review_cycle = markdown_record_value(record, ["점검주기", "점검 주기", "검토주기"], "분기")
        evidence = markdown_record_value(record, ["후속 확인자료", "유관부서 의견", "확인자료"], "후속계획, 협의 기록, 이행 증빙")
        parsed_markdown.append({
            "observation": normalize_hwpx_table_value(
                markdown_record_value(record, ["관찰·근거", "관찰/근거", "관찰사항", "구분", "작동/비작동요인"], "제언"), 10000
            ),
            "task": normalize_hwpx_table_value(task, 10000),
            "owner": normalize_hwpx_table_value(
                markdown_record_value(record, ["이해관계자", "이행부서", "담당 주체", "담당주체", "책임주체", "책임 주체"], "사업담당부서/수행기관"), 10000
            ),
            "reason": normalize_hwpx_table_value(f"우선순위: {priority} | 선정 사유: {reason}", 10000),
            "opinion": normalize_hwpx_table_value(f"완료기한: {due_date} | 점검주기: {review_cycle} | 확인자료: {evidence}", 10000),
            "priority": normalize_hwpx_table_value(priority, 12),
            "due_date": normalize_hwpx_table_value(due_date, 30),
            "review_cycle": normalize_hwpx_table_value(review_cycle, 12),
        })
    if parsed_markdown:
        return parsed_markdown

    # Authoring cleanup may shorten/reclassify a legacy response. Export must
    # parse the stored value itself so additional rows/long fields survive.
    text = str(body or "")
    text = normalize_hwpx_table_value(text, 5000)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^\d+[.)]\s+", line) and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    if not any(re.match(r"^\d+[.)]\s+", chunk.strip()) for chunk in chunks):
        chunks = split_report_items(body)

    rows = []
    for item in chunks:
        if not re.search(r"(구분|제언|이해관계자|관찰사항|환류과제|담당\s*주체|선정\s*사유|후속\s*확인자료)\s*[:：]", item):
            continue
        recommendation = recommendation_field_from_item(item, ["제언"], "")
        stakeholder = recommendation_field_from_item(item, ["이해관계자"], "")
        category = recommendation_field_from_item(item, ["구분"], "")
        if recommendation:
            reason = recommendation_field_from_item(
                item,
                ["선정 사유", "선정사유"],
                f"{category or '제언'} 관련 평가결과 환류 및 후속사업 설계 개선 필요",
            )
            priority = recommendation_field_from_item(item, ["우선순위"], "중")
            due_date = recommendation_field_from_item(item, ["완료기한", "완료 기한", "기한"], "후속 이행계획 확정 시")
            review_cycle = recommendation_field_from_item(item, ["점검주기", "점검 주기", "검토주기"], "분기")
            evidence = recommendation_field_from_item(
                item,
                ["후속 확인자료", "유관부서 의견"],
                "후속계획, 협의 기록, 이행 증빙",
            )
            rows.append({
                "observation": normalize_hwpx_table_value(category or "제언", 10000),
                "task": normalize_hwpx_table_value(recommendation, 10000),
                "owner": normalize_hwpx_table_value(stakeholder or "사업담당부서/수행기관", 10000),
                "reason": normalize_hwpx_table_value(f"우선순위: {priority} | 선정 사유: {reason}", 10000),
                "opinion": normalize_hwpx_table_value(f"완료기한: {due_date} | 점검주기: {review_cycle} | 확인자료: {evidence}", 10000),
                "priority": normalize_hwpx_table_value(priority, 12),
                "due_date": normalize_hwpx_table_value(due_date, 30),
                "review_cycle": normalize_hwpx_table_value(review_cycle, 12),
            })
            continue
        task_fallback = first_report_item_line(item) or item
        observation_fallback = task_fallback
        observation = field_from_item(item, ["관찰사항"], observation_fallback)
        task = field_from_item(item, ["환류과제"], task_fallback)
        if normalize_toc_text(task) == normalize_toc_text(observation):
            task = feedback_task_from_observation(observation)
        reason = field_from_item(item, ["선정 사유", "선정사유"], "평가결과 환류 및 후속 성과관리 강화 필요")
        priority = field_from_item(item, ["우선순위"], "중")
        due_date = field_from_item(item, ["완료기한", "완료 기한", "기한"], "후속 이행계획 확정 시")
        review_cycle = field_from_item(item, ["점검주기", "점검 주기", "검토주기"], "분기")
        evidence = field_from_item(item, ["후속 확인자료", "유관부서 의견"], "후속계획 수립 시 유관부서 의견 반영 필요")
        rows.append({
            "observation": normalize_hwpx_table_value(observation, 10000),
            "task": normalize_hwpx_table_value(task, 10000),
            "owner": field_from_item(item, ["담당 주체", "담당주체"], "사업담당부서/수행기관"),
            "reason": normalize_hwpx_table_value(f"우선순위: {priority} | 선정 사유: {reason}", 10000),
            "opinion": normalize_hwpx_table_value(f"완료기한: {due_date} | 점검주기: {review_cycle} | 확인자료: {evidence}", 10000),
            "priority": normalize_hwpx_table_value(priority, 12),
            "due_date": normalize_hwpx_table_value(due_date, 30),
            "review_cycle": normalize_hwpx_table_value(review_cycle, 12),
        })
    return rows


def feedback_task_from_observation(observation: object) -> str:
    text = normalize_hwpx_table_value(observation, 10000)
    if not text:
        return "평가결과에 근거한 후속조치 계획을 수립하고 이행 현황을 점검한다."
    patterns = [
        (r"(.+?)\s*(?:하지\s*못하고|되지\s*못하고|못하고)\s*있음\.?$", r"\1할 수 있도록 보완계획을 수립하고 이행 현황을 정기 점검한다."),
        (r"(.+?)\s*(?:미흡함|미흡한\s*것으로\s*확인됨)\.?$", r"\1 보완을 위한 실행계획을 수립하고 담당 주체별 이행 과제를 명확화한다."),
        (r"(.+?)\s*(?:부족|미흡|제한|한계|어려움|지연|공백).*$", r"\1 보완을 위한 후속조치 계획을 수립하고 이행 책임과 일정을 명확화한다."),
        (r"(.+?)\s*(?:확인됨|나타남|있음).*$", r"\1 관련 개선 조치를 구체화하고 후속 성과관리 지표로 점검한다."),
        (r"(.+?)\s*(?:필요함|필요가 있음).*$", r"\1 실행계획을 수립하고 담당 주체별 이행 과제를 배분한다."),
    ]
    for pattern, replacement in patterns:
        candidate = re.sub(pattern, replacement, text).strip()
        if candidate and candidate != text:
            return normalize_hwpx_table_value(candidate, 10000)
    return normalize_hwpx_table_value(
        f"{text}에 대한 개선 조치를 구체화하고 후속 이행계획에 반영한다.",
        10000,
    )


def parse_lesson_items(body: object) -> list[dict[str, str]]:
    markdown_rows = parse_markdown_table_records(body)
    parsed_markdown: list[dict[str, str]] = []
    for record in markdown_rows:
        content = markdown_record_value(record, ["교훈 내용", "교훈", "일반화 원칙"])
        if not content:
            continue
        title = markdown_record_value(record, ["평가 시 관찰사항", "관찰사항", "제목", "구분"], "교훈")
        parsed_markdown.append({
            "observation": normalize_hwpx_table_value(title, 10000),
            "analysis": normalize_hwpx_table_value(content, 10000),
            "category": normalize_hwpx_table_value(markdown_record_value(record, ["분야/일반 구분", "분야 구분", "구분"], "일반"), 40),
            "duplicate": normalize_hwpx_table_value(markdown_record_value(record, ["이전년도 교훈 중복 여부", "중복 여부"], "신규"), 60),
            "lesson": normalize_hwpx_table_value(content, 10000),
            "checklist": normalize_hwpx_table_value(markdown_record_value(record, ["M&E 체크리스트 질문", "체크리스트 질문", "체크리스트"], f"후속 유사 사업에서 {title} 관련 실행 조건을 사전에 점검했는가?"), 10000),
        })
    if parsed_markdown:
        return parsed_markdown

    outlined = parse_lesson_outline(body)
    if outlined:
        return outlined

    text = normalize_hwpx_table_value(body, 7500)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = "\n".join(line for line in text.splitlines() if not re.match(r"^\(\d+\)\s+.*원칙\s*$", line.strip()))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chunks: list[str] = []
    current: list[str] = []
    started = False
    for line in lines:
        if re.match(r"^(?:Ⅵ|VI)\.?\s*결론\s*$", line, re.IGNORECASE):
            continue
        if re.match(r"^\d+[.)]\s*환류과제\s*및\s*교훈\s*$", line):
            continue
        if re.match(r"^\(?2\)?[.)]?\s*교훈(?:\s*\(Lessons\))?\s*$", line, re.IGNORECASE):
            continue
        starts_lesson = bool(
            line.startswith("❍")
            or re.match(r"^교훈\s*\d+\s*[:.)]\s*", line)
            or re.match(r"^\d+[.)]\s+(?!환류과제(?:\s*및\s*교훈)?\s*$)", line)
        )
        if starts_lesson:
            if current:
                chunks.append("\n".join(current))
            current = [line]
            started = True
        elif started:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    if not chunks:
        chunks = split_report_items(text)
    rows = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        category = lesson_field_from_item(chunk, ["분야/일반 구분", "분야 구분", "구분"], "")
        duplicate = lesson_field_from_item(chunk, ["이전년도 교훈 중복 여부", "중복 여부", "중복여부"], "")
        checklist = lesson_field_from_item(chunk, ["체크리스트 질문", "M&E 체크리스트 질문", "M&E 체크리스트"], "")
        lesson = lesson_field_from_item(chunk, ["교훈 내용", "교훈"], "")

        cleaned = re.sub(r"^❍\s*", "", chunk).strip()
        cleaned = re.sub(r"^(?:교훈\s*)?(?:\(?\d+\)?[.)])\s*", "", cleaned).strip()
        cleaned = re.sub(r"^교훈\s*\d+\s*[:.)]\s*", "", cleaned).strip()
        title = "교훈"
        title_match = re.match(r"\(([^)]+)\)\s*(.*)$", cleaned, re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
            cleaned = title_match.group(2).strip()
        else:
            first_line = cleaned.splitlines()[0] if cleaned else ""
            colon_match = re.match(r"^(.{2,40}?)\s*[:：]\s*(.*)$", first_line)
            if colon_match and "체크리스트" not in colon_match.group(1):
                title = colon_match.group(1).strip()
                cleaned = cleaned.replace(first_line, colon_match.group(2).strip(), 1).strip()

        field_label = (
            r"교훈\s*내용|분야/일반\s*구분|분야\s*구분|구분|"
            r"이전년도\s*교훈\s*중복\s*여부|중복\s*여부|중복여부|"
            r"M&E\s*체크리스트\s*질문|M&E\s*체크리스트|체크리스트\s*질문"
        )
        content_without_fields = re.sub(
            rf"(?:^|\n)\s*[-•∙ㆍ·]?\s*(?:{field_label})\s*[:：].*?(?=\n\s*[-•∙ㆍ·]?\s*(?:{field_label})\s*[:：]|$)",
            " ",
            cleaned,
            flags=re.DOTALL,
        ).strip()
        content = lesson or content_without_fields or cleaned
        if normalize_toc_text(content) in {"교훈", "환류과제및교훈"}:
            continue
        if title == "교훈" and re.match(r"^교훈\s*\(Lessons\)", content, re.IGNORECASE):
            continue
        if not category:
            category = "분야" if re.search(r"젠더|성평등|환경|기후|인권|취약계층", f"{title} {content}") else "일반"
        if not duplicate:
            duplicate = "신규"
        if not checklist:
            checklist = f"후속 유사 사업에서 {title} 관련 위험과 실행 조건을 사전에 점검했는가?"
        rows.append({
            "observation": normalize_hwpx_table_value(title, 10000),
            "analysis": normalize_hwpx_table_value(content, 10000),
            "category": normalize_hwpx_table_value(category, 40),
            "duplicate": normalize_hwpx_table_value(duplicate, 60),
            "lesson": normalize_hwpx_table_value(content, 10000),
            "checklist": normalize_hwpx_table_value(checklist, 10000),
        })
    return rows


def patch_hwpx_feedback_table_xml(xml_text: str, sections_by_id: dict[str, str]) -> str:
    """Patch only logical section 26; lesson conversion is section 27's responsibility."""
    feedback_target = find_hwpx_table_span_by_text(xml_text, ["환류과제", "이행부서"], 30)
    if feedback_target is not None:
        start, end, table_xml = feedback_target
        # The sample template mixes a red character style into one feedback
        # header.  Keep the table geometry but normalise all table text to the
        # standard black report style before inserting project content.
        table_xml = re.sub(r'charPrIDRef="38"', 'charPrIDRef="29"', table_xml)
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, 3, "선정 사유·우선순위")
        table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, 4, "완료기한·점검주기·확인자료")
        rows = parse_feedback_items(sections_by_id.get("feedback") or "")
        table_xml = ensure_recommendation_table_rows_xml(table_xml, 1, len(rows))
        for index in range(6):
            base = 5 + index * 5
            for offset in range(5):
                table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + offset, "—")
        for index, row in enumerate(rows):
            base = 5 + index * 5
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base, normalize_hwpx_table_value(row["observation"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 1, normalize_hwpx_table_value(row["task"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 2, normalize_hwpx_table_value(row["owner"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 3, normalize_hwpx_table_value(row["reason"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 4, normalize_hwpx_table_value(row["opinion"], 10000))
        table_xml = trim_hwpx_table_rows_xml(table_xml, header_rows=1, data_rows=len(rows))
        xml_text = xml_text[:start] + table_xml + xml_text[end:]

    return xml_text


def patch_hwpx_lessons_table_xml(xml_text: str, sections_by_id: dict[str, str]) -> str:
    """Patch only logical section 27 so it can be tested and changed independently."""

    lessons_target = find_hwpx_table_span_by_text(xml_text, ["평가 교훈 분석", "M&amp;E 체크리스트"], 30)
    if lessons_target is None:
        lessons_target = find_hwpx_table_span_by_text(xml_text, ["평가 교훈 분석", "체크리스트"], 30)
    if lessons_target is not None:
        start, end, table_xml = lessons_target
        rows = parse_lesson_items(sections_by_id.get("lessons") or "")
        table_xml = ensure_recommendation_table_rows_xml(table_xml, 2, len(rows))
        # The fixed template provides six data rows.  Current authoring uses
        # up to five lessons; the final unused row is explicitly neutralised
        # so sample placeholders can never leak into the report.
        for index in range(6):
            base = 6 + index * 5
            for offset in range(5):
                table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + offset, "—")
        for index, row in enumerate(rows):
            base = 6 + index * 5
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base, normalize_hwpx_table_value(row["observation"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 1, normalize_hwpx_table_value(row["category"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 2, normalize_hwpx_table_value(row["duplicate"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 3, normalize_hwpx_table_value(row["lesson"], 10000))
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, base + 4, normalize_hwpx_table_value(row["checklist"], 10000))
        table_xml = trim_hwpx_table_rows_xml(table_xml, header_rows=2, data_rows=len(rows))
        xml_text = xml_text[:start] + table_xml + xml_text[end:]
    return xml_text


def patch_hwpx_feedback_lessons_tables_xml(xml_text: str, sections_by_id: dict[str, str]) -> str:
    """Backward-compatible combined entry point for legacy callers."""
    xml_text = patch_hwpx_feedback_table_xml(xml_text, sections_by_id)
    return patch_hwpx_lessons_table_xml(xml_text, sections_by_id)


def patch_hwpx_editor_snapshot_xml(xml_text: str, section_index: int, snapshot: dict) -> str:
    if not isinstance(snapshot, dict):
        return xml_text
    for item in snapshot.get("paragraphs", []):
        if not isinstance(item, dict) or int(item.get("sec", -1)) != section_index:
            continue
        xml_text, _ = set_hwpx_paragraph_text_xml(xml_text, int(item.get("para", -1)), str(item.get("text") or ""))

    groups: dict[tuple[int, int], list[dict]] = {}
    for item in snapshot.get("cells", []):
        if not isinstance(item, dict) or int(item.get("sec", -1)) != section_index:
            continue
        cell_index = int(item.get("cellIndex", -1))
        if cell_index < 0:
            continue
        groups.setdefault((int(item.get("para", -1)), int(item.get("controlIndex", 0) or 0)), []).append(item)

    for (para_index, control_index), items in groups.items():
        table_span = find_hwpx_grade_table_span_xml(xml_text) if section_index == 2 else None
        if table_span is None and para_index >= 0:
            paragraph_spans = find_hwpx_tag_spans(xml_text, "hp:p")
            if para_index < len(paragraph_spans):
                para_start, para_end = paragraph_spans[para_index]
                paragraph_xml = xml_text[para_start:para_end]
                table_spans = find_hwpx_tag_spans(paragraph_xml, "hp:tbl")
                if 0 <= control_index < len(table_spans):
                    local_start, local_end = table_spans[control_index]
                    table_span = (para_start + local_start, para_start + local_end)
        if table_span is None:
            max_cell = max(int(item.get("cellIndex", -1)) for item in items)
            for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
                if len(find_hwpx_tag_spans(xml_text[start:end], "hp:tc")) > max_cell:
                    table_span = (start, end)
                    break
        if table_span is None:
            continue
        start, end = table_span
        table_xml = xml_text[start:end]
        for item in items:
            table_xml, _ = set_hwpx_table_cell_text_xml(table_xml, int(item.get("cellIndex", -1)), str(item.get("text") or ""))
        xml_text = xml_text[:start] + table_xml + xml_text[end:]
    return xml_text


def repack_hwpx_preserving_original_entries(modified_hwpx: bytes) -> bytes:
    """Preserve original ZIP entries and replace reviewed XML/media payloads."""
    if not SAMPLE_REPORT_HWPX_PATH.exists():
        return modified_hwpx

    def dos_time_date(info: zipfile.ZipInfo) -> tuple[int, int]:
        year, month, day, hour, minute, second = info.date_time
        return (hour << 11) | (minute << 5) | (second // 2), ((year - 1980) << 9) | (month << 5) | day

    def raw_deflate(data: bytes) -> bytes:
        compressor = zlib.compressobj(level=6, method=zlib.DEFLATED, wbits=-15)
        return compressor.compress(data) + compressor.flush()

    original_bytes = SAMPLE_REPORT_HWPX_PATH.read_bytes()
    replacements: dict[str, bytes] = {}
    with zipfile.ZipFile(SAMPLE_REPORT_HWPX_PATH, "r") as original, zipfile.ZipFile(BytesIO(modified_hwpx), "r") as modified:
        for name in [
            "Contents/header.xml",
            *[f"Contents/section{index}.xml" for index in range(9)],
            # These three reviewed frames are report-generated media:
            # Claude theory of change, DAC grade overview, and performance /
            # follow-up overview. Other template media remain byte-for-byte.
            "BinData/image1.png",
            "BinData/image2.bmp",
            "BinData/image3.bmp",
        ]:
            if name in original.namelist() and name in modified.namelist():
                new_raw = modified.read(name)
                if new_raw != original.read(name):
                    replacements[name] = new_raw
    if not replacements:
        return original_bytes

    output = bytearray()
    central_parts: list[bytes] = []
    with zipfile.ZipFile(SAMPLE_REPORT_HWPX_PATH, "r") as original:
        infos = original.infolist()
        for info in infos:
            local_offset = len(output)
            name_bytes = info.filename.encode("utf-8")
            if info.filename in replacements:
                data = replacements[info.filename]
                crc = binascii.crc32(data) & 0xFFFFFFFF
                file_size = len(data)
                compress_type = info.compress_type
                compressed = raw_deflate(data) if compress_type == zipfile.ZIP_DEFLATED else data
                compress_size = len(compressed)
                flag_bits = info.flag_bits
                mod_time, mod_date = dos_time_date(info)
                extra = info.extra or b""
                output.extend(struct.pack(
                    "<IHHHHHIIIHH",
                    0x04034B50,
                    info.extract_version,
                    flag_bits,
                    compress_type,
                    mod_time,
                    mod_date,
                    crc,
                    compress_size,
                    file_size,
                    len(name_bytes),
                    len(extra),
                ))
                output.extend(name_bytes)
                output.extend(extra)
                output.extend(compressed)
            else:
                start = info.header_offset
                (
                    signature,
                    _version,
                    flag_bits,
                    compress_type,
                    mod_time,
                    mod_date,
                    crc,
                    compress_size,
                    file_size,
                    name_len,
                    extra_len,
                ) = struct.unpack_from("<IHHHHHIIIHH", original_bytes, start)
                if signature != 0x04034B50:
                    raise ValueError(f"Invalid HWPX local header: {info.filename}")
                total_size = 30 + name_len + extra_len + info.compress_size
                output.extend(original_bytes[start:start + total_size])
            extra = info.extra or b""
            comment = info.comment or b""
            central_parts.append(struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                info.create_version,
                info.extract_version,
                flag_bits,
                compress_type,
                mod_time,
                mod_date,
                crc,
                compress_size,
                file_size,
                len(name_bytes),
                len(extra),
                len(comment),
                0,
                info.internal_attr,
                info.external_attr,
                local_offset,
            ) + name_bytes + extra + comment)
        central_offset = len(output)
        for part in central_parts:
            output.extend(part)
        central_size = len(output) - central_offset
        comment = original.comment or b""
        output.extend(struct.pack(
            "<IHHHHIIH",
            0x06054B50,
            0,
            0,
            len(infos),
            len(infos),
            central_size,
            central_offset,
            len(comment),
        ))
        output.extend(comment)
    return bytes(output)


def build_template_patched_hwpx(body: dict | None = None) -> dict:
    if not SAMPLE_REPORT_HWPX_PATH.exists():
        raise ValueError("5-1 HWPX template not found")
    if body and isinstance(body.get("sections"), list):
        saved = save_report_editor(body)
        sections = saved.get("sections", [])
    else:
        saved_state = read_report_editor_state() or {}
        sections = saved_state.get("sections") or []
    context = current_report_context()
    sections_by_id = {str(section.get("id", "")): str(section.get("body", "")) for section in sections if isinstance(section, dict)}
    editor_snapshot = body.get("editorSnapshot") if isinstance(body, dict) else None
    output = BytesIO()
    modified = {"Contents/section0.xml", "Contents/section1.xml", "Contents/section2.xml", "Contents/section3.xml", "Contents/section4.xml", "Contents/section5.xml", "Contents/section6.xml", "Contents/section7.xml", "Contents/section8.xml"}
    with zipfile.ZipFile(SAMPLE_REPORT_HWPX_PATH, "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "Contents/header.xml":
                raw = patch_hwpx_report_outline_header_xml(raw.decode("utf-8")).encode("utf-8")
            section_match = re.match(r"Contents/section(\d+)\.xml$", info.filename)
            if info.filename in modified or (section_match and editor_snapshot):
                xml_text = raw.decode("utf-8")
                if section_match and editor_snapshot:
                    xml_text = patch_hwpx_editor_snapshot_xml(xml_text, int(section_match.group(1)), editor_snapshot)
                if info.filename == "Contents/section0.xml":
                    xml_text = patch_hwpx_section_manifest_xml(xml_text, 1, context, sections_by_id)
                    xml_text = patch_hwpx_cover_xml(xml_text, context, sections_by_id)
                elif info.filename == "Contents/section1.xml":
                    xml_text = patch_hwpx_section_manifest_xml(xml_text, 2, context, sections_by_id)
                elif info.filename == "Contents/section2.xml":
                    xml_text = patch_hwpx_section_manifest_xml(xml_text, 3, context, sections_by_id)
                if not (section_match and editor_snapshot):
                    xml_text = patch_hwpx_core_body_xml(xml_text, sections_by_id)
                    if section_match:
                        xml_text = patch_hwpx_section_target_bodies_xml(xml_text, int(section_match.group(1)), sections_by_id)
                    if info.filename == "Contents/section3.xml":
                        xml_text = patch_hwpx_project_overview_table_xml(xml_text, context, sections_by_id)
                    if info.filename == "Contents/section4.xml":
                        xml_text = patch_hwpx_pdm_table_xml(xml_text, sections_by_id)
                        xml_text = patch_hwpx_eval_matrix_table_xml(xml_text, context, sections_by_id)
                    if info.filename == "Contents/section5.xml":
                        xml_text = patch_hwpx_achievement_table_xml(xml_text, sections_by_id)
                    if info.filename == "Contents/section8.xml":
                        xml_text = patch_hwpx_feedback_lessons_tables_xml(xml_text, sections_by_id)
                    xml_text = patch_hwpx_file_manifests_xml(xml_text, info.filename, context, sections_by_id)
                    if info.filename == "Contents/section4.xml":
                        xml_text = patch_hwpx_pdm_table_xml(xml_text, sections_by_id)
                        xml_text = patch_hwpx_eval_matrix_table_xml(xml_text, context, sections_by_id)
                    if info.filename == "Contents/section8.xml":
                        xml_text = patch_hwpx_feedback_lessons_tables_xml(xml_text, sections_by_id)
                    xml_text = patch_hwpx_orphan_editor_sections_xml(xml_text, info.filename, sections_by_id)
                    xml_text = cleanup_hwpx_placeholder_text_xml(xml_text)
                raw = xml_text.encode("utf-8")
            target.writestr(info, raw)
    project_name = safe_filename(str(context.get("project", {}).get("title") or "ODA_사업"))[:80]
    return validate_exported_hwpx({
        "fileName": f"{project_name}_5-1_종료평가_결과보고서.hwpx",
        "data": base64.b64encode(output.getvalue()).decode("ascii"),
    })


def build_cover_patched_hwpx() -> dict:
    if not SAMPLE_REPORT_HWPX_PATH.exists():
        raise ValueError("5-1 HWPX template not found")
    context = current_report_context()
    output = BytesIO()
    with zipfile.ZipFile(SAMPLE_REPORT_HWPX_PATH, "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "Contents/header.xml":
                raw = patch_hwpx_report_outline_header_xml(raw.decode("utf-8")).encode("utf-8")
            if info.filename == "Contents/section0.xml":
                xml_text = raw.decode("utf-8")
                xml_text = patch_hwpx_section_manifest_xml(xml_text, 1, context, {})
                xml_text = patch_hwpx_cover_xml(xml_text, context)
                xml_text = cleanup_hwpx_placeholder_text_xml(xml_text)
                raw = xml_text.encode("utf-8")
            target.writestr(info, raw)
    project_name = safe_filename(str(context.get("project", {}).get("title") or "ODA_사업"))[:80]
    return validate_exported_hwpx({
        "fileName": f"{project_name}_5-1_표지변경_종료평가_결과보고서.hwpx",
        "data": base64.b64encode(output.getvalue()).decode("ascii"),
    })


def build_cover_grade_patched_hwpx() -> dict:
    if not SAMPLE_REPORT_HWPX_PATH.exists():
        raise ValueError("5-1 HWPX template not found")
    context = current_report_context()
    output = BytesIO()
    with zipfile.ZipFile(SAMPLE_REPORT_HWPX_PATH, "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                xml_text = raw.decode("utf-8")
                xml_text = patch_hwpx_section_manifest_xml(xml_text, 1, context, {})
                raw = cleanup_hwpx_placeholder_text_xml(patch_hwpx_cover_xml(xml_text, context)).encode("utf-8")
            elif info.filename == "Contents/section1.xml":
                raw = cleanup_hwpx_placeholder_text_xml(patch_hwpx_section_manifest_xml(raw.decode("utf-8"), 2, context, {})).encode("utf-8")
            elif info.filename == "Contents/section2.xml":
                xml_text = raw.decode("utf-8")
                xml_text = patch_hwpx_section_manifest_xml(xml_text, 3, context, {})
                xml_text = patch_hwpx_section_manifest_xml(xml_text, 4, context, {})
                xml_text = patch_hwpx_file_manifests_xml(xml_text, info.filename, context, {})
                raw = cleanup_hwpx_placeholder_text_xml(xml_text).encode("utf-8")
            target.writestr(info, raw)
    project_name = safe_filename(str(context.get("project", {}).get("title") or "ODA_사업"))[:80]
    return validate_exported_hwpx({
        "fileName": f"{project_name}_5-1_표지_평가등급표변경_종료평가_결과보고서.hwpx",
        "data": base64.b64encode(output.getvalue()).decode("ascii"),
    })


def build_cover_grade_body_patched_hwpx_bytes(toc_page_map: dict | None = None) -> tuple[bytes, int]:
    if not SAMPLE_REPORT_HWPX_PATH.exists():
        raise ValueError("5-1 HWPX template not found")
    from ..reports.export_builders import current_report_context
    from ..reports.editor import read_report_editor_state

    saved_state = read_report_editor_state() or {}
    sections = saved_state.get("sections") or []
    context = current_report_context()
    if toc_page_map is not None:
        context = {**context, "_toc_page_map": dict(toc_page_map)}
    sections_by_id = {str(section.get("id", "")): str(section.get("body", "")) for section in sections if isinstance(section, dict)}
    output = BytesIO()
    changed_count = 0
    with zipfile.ZipFile(SAMPLE_REPORT_HWPX_PATH, "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "Contents/header.xml":
                raw = patch_hwpx_report_outline_header_xml(raw.decode("utf-8")).encode("utf-8")
            elif info.filename == "Contents/section0.xml":
                xml_text = raw.decode("utf-8")
                xml_text, changed = patch_hwpx_cover_slots_only_xml(xml_text, context, sections_by_id)
                changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section1.xml":
                xml_text = raw.decode("utf-8")
                xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, 2, context, sections_by_id)
                changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section2.xml":
                xml_text = raw.decode("utf-8")
                xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, 3, context, sections_by_id)
                changed_count += changed
                xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, 4, context, sections_by_id)
                changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section3.xml":
                xml_text = raw.decode("utf-8")
                for section_number in (6, 7, 5):
                    xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, section_number, context, sections_by_id)
                    changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section4.xml":
                xml_text = raw.decode("utf-8")
                for section_number in (8, 9, 10, 11, 12, 13):
                    xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, section_number, context, sections_by_id)
                    changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section5.xml":
                xml_text = raw.decode("utf-8")
                xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, 14, context, sections_by_id)
                changed_count += changed
                xml_text = patch_hwpx_achievement_table_xml(xml_text, sections_by_id)
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section6.xml":
                xml_text = raw.decode("utf-8")
                for section_number in (15, 16, 17):
                    xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, section_number, context, sections_by_id)
                    changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section7.xml":
                xml_text = raw.decode("utf-8")
                for section_number in (18, 19, 20, 21, 22, 23, 24):
                    xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, section_number, context, sections_by_id)
                    changed_count += changed
                raw = xml_text.encode("utf-8")
            elif info.filename == "Contents/section8.xml":
                xml_text = raw.decode("utf-8")
                for section_number in (25, 26, 27):
                    xml_text, changed = patch_hwpx_review_section_slots_xml(xml_text, section_number, context, sections_by_id)
                    changed_count += changed
                xml_text = patch_hwpx_feedback_lessons_tables_xml(xml_text, sections_by_id)
                raw = xml_text.encode("utf-8")
            target.writestr(info, raw)
    final_bytes = repack_hwpx_preserving_original_entries(output.getvalue())
    return final_bytes, changed_count


def build_cover_grade_body_patched_hwpx() -> dict:
    if not SAMPLE_REPORT_HWPX_PATH.exists():
        raise ValueError("5-1 HWPX template not found")
    context = current_report_context()
    first_pass_bytes, _first_changed_count = build_cover_grade_body_patched_hwpx_bytes(toc_page_map={})
    toc_page_map = read_toc_page_map_from_rhwp_text(first_pass_bytes)
    toc_source = "rhwp_export_text"
    if not toc_page_map:
        toc_page_map = read_toc_page_map()
        toc_source = "existing_toc_page_map_or_pdf"
    final_bytes, changed_count = build_cover_grade_body_patched_hwpx_bytes(toc_page_map=toc_page_map or {})
    project_name = safe_filename(str(context.get("project", {}).get("title") or "ODA_사업"))[:80]
    result = validate_exported_hwpx({
        "fileName": f"{project_name}_5-1_sections1-27_changed_final_evaluation_report.hwpx",
        "data": base64.b64encode(final_bytes).decode("ascii"),
    })
    result["changedSlots"] = changed_count
    result["scope"] = "sections1-27-reviewed-slots-only"
    result["tocPageMap"] = toc_page_map or {}
    result["tocPageMapSource"] = toc_source if toc_page_map else "unavailable"
    return result

