from __future__ import annotations

import html
import hashlib
import logging
import json
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from psycopg.types.json import Jsonb
from .report_policy import REPORT_TITLE
from .project_lifecycle import capture_input_snapshot, snapshots_match
from .project_identity import current_project_identity, project_title_overview, project_title_section

from backend.oda_me.hwpx.patchers import (
    ACHIEVEMENT_CELL_OFFSETS,
    ACHIEVEMENT_HEADER_ROWS,
    ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM,
    cleanup_hwpx_placeholder_text_xml,
    find_hwpx_tag_spans,
    get_hwpx_xml_scope_text,
    achievement_item_fields,
    achievement_row_starts,
    parse_achievement_items,
    parse_feedback_items,
    parse_lesson_items,
    review_values_for_section,
    repack_hwpx_preserving_original_entries,
    validate_section5_summary_xml,
)
from backend.oda_me.reports.context import parse_structured_section_slots, structured_slots_to_json

from .assessment_context import assessment_scope
from .db import connection, tenant_context
from .evaluation_criteria import grade
from .hwpx_adapters import apply_section_adapter_xml
from .hwpx_pipeline import prepare_hwpx_sections
from .hwpx_layout.cover import (
    adapt_cover_title_font_xml as _adapt_cover_title_font_xml,
    split_cover_title as _split_cover_title,
    wrap_cover_title_xml as _wrap_cover_title_xml,
)
from .hwpx_layout.headings import patch_orphan_heading_page_breaks
from .hwpx_layout.pipeline import finalize_report_header_layout, finalize_report_section_layout
from .hwpx_layout.overflow import resolve_detail_text
from .hwpx_layout.spacing import report_heading_gap_violations_xml
from .hwpx_layout.rendering import (
    REQUIRED_TOC_KEYS,
    analyze_hwpx,
    orphan_heading_adjustments_from_analysis,
    toc_page_map_from_analysis,
    validate_render_result,
    validate_summary_page_span,
)
from .hwpx_layout.tables import (
    achievement_page_groups,
    EVALUATION_MATRIX_TABLE_PAGE_ROW_GROUPS,
    PDM_TABLE_PAGE_ROW_GROUPS,
    detach_evaluation_matrix_table_xml as _detach_evaluation_matrix_table_xml,
    refresh_evaluation_matrix_split_heights_xml,
)
from .hwpx_layout.theory import (
    attach_feedback_headings_to_table_xml as _attach_feedback_headings_to_table_xml,
    force_lessons_page_break_xml as _force_lessons_page_break_xml,
    replace_stale_theory_pictures_xml as _replace_stale_theory_pictures_xml,
)
from .hwpx_layout.validation import (
    validate_orphan_heading_page_breaks,
    validate_report_layout_contract,
)
from .hwpx_layout.toc import (
    clean_toc_annotations_xml as _clean_toc_annotations_xml,
    patch_toc_page_numbers as _patch_toc_page_numbers,
    validate_toc_page_numbers,
)
from .document_classification import pdm_slots
from .quality_profile import toc_project_overrides
from .report_sources import (
    normalize_source_mentions,
    source_artifact_issues,
    strip_inline_source_citations,
)
from .report_text import sanitize_report_text
from .report_evaluation_context import is_provisional, qualify_report_text, PROVISIONAL_BASIS, PROVISIONAL_NOTICE
from .theory_visual import THEORY_VISUAL_DESIGN_VERSION, build_theory_visual_artifacts, theory_visual_input_digest
from .theory_artifact_store import load_theory_artifact, save_theory_artifact
from .report_visuals import build_supplemental_report_visuals


TEMPLATE_PATH = Path("/app/samples/5-1. 종료평가 결과보고서 placeholder.hwpx")
TEMPLATE_SHA256 = "0653d926b1b096015dc355bfc3b6eee6971342706102c7cb1cb91f64dce97b7c"
EXPORT_DIR = Path("/app/data/report_exports")
KORDOC_URL = "http://kodame-kordoc:8200"
SECTION_GROUPS = {
    "Contents/section0.xml": (1,),
    "Contents/section1.xml": (2,),
    "Contents/section2.xml": (3, 4),
    "Contents/section3.xml": (5, 6, 7),
    "Contents/section4.xml": (8, 9, 10, 11, 12, 13),
    "Contents/section5.xml": (14,),
    "Contents/section6.xml": (15, 16, 17),
    "Contents/section7.xml": (18, 19, 20, 21, 22, 23, 24),
    "Contents/section8.xml": (25, 26, 27),
}

NARRATIVE_VALIDATION_KEYS = {
    3: ("notice_body", "notice"),
    9: ("evaluation_purpose_scope_body", "eval-purpose"),
    11: ("eval_methods_body", "eval-methods"),
    12: ("eval_limitations_body", "eval-limitations"),
    13: ("eval_team_body", "eval-team"),
    14: ("achievement_body", "achievement"),
    15: ("criteria_relevance_body", "criteria-relevance"),
    16: ("criteria_coherence_body", "criteria-coherence"),
    17: ("criteria_effectiveness_body", "criteria-effectiveness"),
    18: ("criteria_efficiency_body", "criteria-efficiency"),
    19: ("criteria_sustainability_body", "criteria-sustainability"),
    20: ("criteria_crosscutting_body", "criteria-crosscutting"),
    21: ("criteria_other_body", "criteria-other"),
    22: ("conclusion_body", "conclusion"),
    23: ("working_factors_body", "working-factors"),
    24: ("nonworking_factors_body", "nonworking-factors"),
    25: ("theory_body", "theory"),
}


def _report_sections_digest() -> str:
    with connection() as conn:
        rows = conn.execute("SELECT part_id,content,status,updated_at FROM report_sections ORDER BY part_id").fetchall()
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _load_cached_theory_visual_artifacts(input_digest: str) -> dict | None:
    """Reuse a visual only when project input, model and design match."""

    with connection() as conn:
        rows = conn.execute(
            """SELECT id,validation FROM report_exports
                 WHERE status='completed' ORDER BY completed_at DESC LIMIT 12"""
        ).fetchall()
    for row in rows:
        png_path = EXPORT_DIR / f"{row['id']}-theory.png"
        pptx_path = EXPORT_DIR / f"{row['id']}-theory.pptx"
        if not png_path.is_file() or not pptx_path.is_file():
            continue
        validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        metadata = validation.get("theory_visual") if isinstance(validation.get("theory_visual"), dict) else {}
        if metadata.get("design_version") != THEORY_VISUAL_DESIGN_VERSION:
            continue
        if metadata.get("input_digest") != input_digest:
            continue
        return {
            "png": png_path.read_bytes(),
            "pptx": pptx_path.read_bytes(),
            "model": str(metadata.get("model") or "unknown"),
            "plan": {
                "design_version": THEORY_VISUAL_DESIGN_VERSION,
                "column_count": int(metadata.get("column_count") or 6),
            },
            "design_version": THEORY_VISUAL_DESIGN_VERSION,
            "render_source": str(metadata.get("render_source") or "cached_pptx_render"),
            "source": "project_cached_artifact",
            "input_digest": input_digest,
        }
    return None


def _coverage_text(value: object) -> str:
    decoded = html.unescape(str(value or ""))
    decoded = re.sub(r"<[^>]+>", "", decoded)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", decoded).lower()


def validate_report_identity(data: bytes, project: dict) -> dict:
    """Do not publish a cover/grade/overview whose identity was truncated or stale."""
    expected = _coverage_text(project.get('title'))
    missing = []
    with zipfile.ZipFile(BytesIO(data)) as archive:
        for label, path in (('표지', 'Contents/section0.xml'), ('평가등급표', 'Contents/section2.xml'),
                            ('사업개요', 'Contents/section3.xml')):
            visible = _coverage_text(get_hwpx_xml_scope_text(archive.read(path).decode('utf-8')))
            if not expected or expected not in visible:
                missing.append(label)
    if missing:
        raise ValueError('보고서 사업명 일치 검증 실패: ' + ', '.join(missing))
    return {'ok': True, 'title': project['title'], 'checked': ['cover', 'grade', 'project-overview']}


def _body_probes(value: object, limit: int = 2) -> list[str]:
    probes: list[str] = []
    for line in str(value or "").splitlines():
        normalized = _coverage_text(line)
        if len(normalized) < 14:
            continue
        probes.append(normalized[:42])
        if len(probes) >= limit:
            break
    if not probes:
        normalized = _coverage_text(value)
        if normalized:
            probes.append(normalized[:42])
    return probes


def _narrative_body_probes(part_id: str, value: object) -> list[str]:
    if part_id == "achievement":
        from backend.oda_me.hwpx.achievement_records import ACHIEVEMENT_RECORD_RE
        # Structured records are mapped to cells and independently checked
        # field-by-field below. Their literal slash/field-label representation
        # is intentionally absent from the reader-facing narrative.
        value = "\n".join(line for line in str(value or "").splitlines()
                          if not ACHIEVEMENT_RECORD_RE.match(line))
    return _body_probes(value)


def _table_xml_by_text(xml_text: str, required_parts: tuple[str, ...], min_cells: int) -> str:
    for start, end in find_hwpx_tag_spans(xml_text, "hp:tbl"):
        table_xml = xml_text[start:end]
        cell_count = len(find_hwpx_tag_spans(table_xml, "hp:tc"))
        table_text = html.unescape(get_hwpx_xml_scope_text(table_xml))
        if cell_count >= min_cells and all(part in table_text for part in required_parts):
            return table_xml
    return ""


def _table_cell_texts(table_xml: str) -> list[str]:
    return [
        html.unescape(get_hwpx_xml_scope_text(table_xml[start:end])).strip()
        for start, end in find_hwpx_tag_spans(table_xml, "hp:tc")
    ]


def _evaluation_matrix_cell_texts(section_xml: str) -> list[str]:
    """Reconstruct the logical 9x5 matrix, joining continuation cells losslessly."""

    tables: list[str] = []
    for start, end in find_hwpx_tag_spans(section_xml, "hp:tbl"):
        table = section_xml[start:end]
        table_text = html.unescape(get_hwpx_xml_scope_text(table))
        if all(part in table_text for part in ("평가기준", "평가질문", "분석방법")):
            tables.append(table)
    if not tables:
        return []
    cells = _table_cell_texts(tables[0])[:5]
    logical = []
    for table in tables:
        physical = [html.unescape(get_hwpx_xml_scope_text(table[a:b]))
                    for a, b in find_hwpx_tag_spans(table, "hp:tc")][5:]
        for offset in range(0, len(physical), 5):
            row = physical[offset:offset + 5]
            if len(row) != 5:
                raise ValueError("평가매트릭스 열 구성 오류")
            if row[0].endswith(" (계속)"):
                if not logical or logical[-1][0] != row[0][:-5]:
                    raise ValueError("평가매트릭스 계속 행 연결 오류")
                for index in range(1, 5): logical[-1][index] += row[index]
            else: logical.append(row)
    for row in logical: cells.extend(row)
    return cells


def _table_declared_rows(table_xml: str) -> int:
    match = re.search(r'<hp:tbl\b[^>]*\browCnt="(\d+)"', table_xml)
    return int(match.group(1)) if match else 0


def _validate_semantic_coverage(data: bytes, context: dict, sections_by_id: dict[str, str]) -> dict:
    # Coverage must compare the same reader projection that is written to the
    # package.  Verification-only citations are intentionally absent from the
    # HWPX and therefore must not be treated as required cell content.
    sections_by_id = {
        part_id: strip_inline_source_citations(content)
        for part_id, content in sections_by_id.items()
    }
    with zipfile.ZipFile(BytesIO(data), "r") as archive:
        xml_by_path = {
            path: archive.read(path).decode("utf-8")
            for path in SECTION_GROUPS
            if path in archive.namelist()
        }
    visible_by_path = {
        path: _coverage_text(get_hwpx_xml_scope_text(xml))
        for path, xml in xml_by_path.items()
    }
    failures: list[str] = []
    section_results: list[dict] = []

    for section_number, (body_key, part_id) in NARRATIVE_VALIDATION_KEYS.items():
        path = next((name for name, numbers in SECTION_GROUPS.items() if section_number in numbers), "")
        values = review_values_for_section(section_number, context, sections_by_id)
        body = values.get(body_key) or sections_by_id.get(part_id) or ""
        probes = _narrative_body_probes(part_id, body)
        missing = [probe for probe in probes if probe not in visible_by_path.get(path, "")]
        ok = bool(probes) and not missing
        section_results.append({"section": section_number, "part_id": part_id, "ok": ok, "probe_count": len(probes)})
        if not ok:
            failures.append(f"{section_number}:{part_id} 본문 앵커 누락")

    section4_xml = xml_by_path.get("Contents/section4.xml", "")
    pdm_tables = [
        section4_xml[start:end]
        for start, end in find_hwpx_tag_spans(section4_xml, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(section4_xml[start:end])
            for token in ("프로그램 요약", "객관적 검증지표", "중요가정")
        )
    ]
    if len(pdm_tables) != len(PDM_TABLE_PAGE_ROW_GROUPS):
        failures.append(
            f"8:pdm 결과수준별 분할 오류: {len(pdm_tables)}/{len(PDM_TABLE_PAGE_ROW_GROUPS)}"
        )
    pdm_visible = _coverage_text(" ".join(get_hwpx_xml_scope_text(table) for table in pdm_tables))
    pdm_slots = parse_structured_section_slots(sections_by_id.get("pdm") or "", "pdm") or {}
    pdm_slot_keys = (
        "impact_indicator", "impact_mov", "impact_assumption", "impact_summary",
        "outcome_indicator", "outcome_mov", "outcome_assumption", "outcome_summary",
        "outputs_indicator", "outputs_mov", "outputs_assumption", "outputs_summary",
        "activities", "inputs", "preconditions",
    )
    for slot_key in pdm_slot_keys:
        expected = _coverage_text(pdm_slots.get(slot_key))[:16]
        if expected and expected not in pdm_visible:
            failures.append(f"8:pdm {slot_key} 셀 매핑 오류")

    matrix_cells = _evaluation_matrix_cell_texts(section4_xml)
    matrix_slots = parse_structured_section_slots(sections_by_id.get("eval-matrix") or "", "eval-matrix") or {}
    matrix_cell_slots = {
        6: "relevance_question", 7: "relevance_indicator", 8: "relevance_source", 9: "relevance_method",
        11: "coherence_question", 12: "coherence_indicator", 13: "coherence_source", 14: "coherence_method",
        16: "effectiveness_question", 17: "effectiveness_indicator", 18: "effectiveness_source", 19: "effectiveness_method",
        21: "efficiency_question", 22: "efficiency_indicator", 23: "efficiency_source", 24: "efficiency_method",
        26: "sustainability_question", 27: "sustainability_indicator", 28: "sustainability_source", 29: "sustainability_method",
        31: "human_rights_question", 32: "human_rights_indicator", 33: "human_rights_source", 34: "human_rights_method",
        36: "gender_question", 37: "gender_indicator", 38: "gender_source", 39: "gender_method",
        41: "environment_question", 42: "environment_indicator", 43: "environment_source", 44: "environment_method",
    }
    for cell_index, slot_key in matrix_cell_slots.items():
        probe_length = 32 if slot_key.endswith("_question") else 10
        expected = _coverage_text(matrix_slots.get(slot_key))[:probe_length]
        actual = _coverage_text(resolve_detail_text(section4_xml, matrix_cells[cell_index])) if cell_index < len(matrix_cells) else ""
        if expected and expected not in actual:
            failures.append(f"10:eval-matrix {slot_key} 셀 매핑 오류")

    achievement_rows = parse_achievement_items(sections_by_id.get("achievement") or "")
    achievement_section = xml_by_path.get("Contents/section5.xml", "")
    achievement_tables = [
        achievement_section[start:end]
        for start, end in find_hwpx_tag_spans(achievement_section, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(achievement_section[start:end])
            for token in ("성과지표", "기초선", "달성도")
        )
    ]
    # Pagination is content-driven. Semantic validation walks every actual
    # indicator in order; the separate layout contract validates page heights.
    expected_achievement_groups = []
    next_item = 0
    for table in achievement_tables:
        physical_rows = len(find_hwpx_tag_spans(table, 'hp:tr')) - ACHIEVEMENT_HEADER_ROWS
        if physical_rows <= 0 or physical_rows % ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM:
            failures.append('14:achievement 지표별 물리행 구조 오류')
        count = max(0, physical_rows) // ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
        expected_achievement_groups.append(tuple(range(next_item,next_item+count)))
        next_item += count
    if not achievement_rows:
        failures.append("14:achievement 지표 데이터 누락")
    if next_item != len(achievement_rows):
        failures.append(
            f"14:achievement 전체 지표 수 불일치: "
            f"{next_item}/{len(achievement_rows)}"
        )
    for part_index, (achievement_table, item_indexes) in enumerate(
        zip(achievement_tables, expected_achievement_groups),
        start=1,
    ):
        achievement_cells = _table_cell_texts(achievement_table)
        row_starts = achievement_row_starts(len(item_indexes))
        for local_index, item_index in enumerate(item_indexes):
            if item_index >= len(achievement_rows):
                failures.append(f"14:achievement 표 {part_index}쪽 지표 데이터 누락")
                continue
            item = achievement_rows[item_index]
            base = row_starts[local_index]
            fields = achievement_item_fields(item, item_index)
            if not fields["indicator"] or fields["indicator"] == "확인 필요":
                failures.append(f"14:achievement 표 {item_index + 1}행 PDM 지표명 누락")
            for field_key in ("name", "indicator", "baseline", "target", "endline", "achievement", "mov", "note"):
                expected_value = fields[field_key] or fields["achievement"]
                probe_length = 18 if field_key in {"name", "indicator"} else 10
                expected = _coverage_text(expected_value)[:probe_length]
                cell_index = base + ACHIEVEMENT_CELL_OFFSETS[field_key]
                actual = _coverage_text(resolve_detail_text(achievement_section, achievement_cells[cell_index])) if cell_index < len(achievement_cells) else ""
                if expected and expected not in actual:
                    failures.append(
                        f"14:achievement 표 {item_index + 1}행 {field_key} 셀 매핑 오류"
                        f"(기대={expected[:18]}, 실제={actual[:18]})"
                    )
        expected_part_rows = ACHIEVEMENT_HEADER_ROWS + (
            len(item_indexes) * ACHIEVEMENT_PHYSICAL_ROWS_PER_ITEM
        )
        if _table_declared_rows(achievement_table) != expected_part_rows:
            failures.append(f"14:achievement 표 {part_index}쪽 행 확장·정리 오류")

    section8_xml = xml_by_path.get("Contents/section8.xml", "")
    feedback_tables = [
        section8_xml[start:end]
        for start, end in find_hwpx_tag_spans(section8_xml, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(section8_xml[start:end])
            for token in ("환류과제", "이행부서")
        )
    ]
    feedback_visible = _coverage_text(
        " ".join(get_hwpx_xml_scope_text(table) for table in feedback_tables)
    )
    feedback_rows = parse_feedback_items(sections_by_id.get("feedback") or "")[:6]
    for index, row in enumerate(feedback_rows):
        expected = _coverage_text(row.get("task"))[:36]
        if expected and expected not in feedback_visible:
            failures.append(f"26:feedback 표 {index + 1}행 누락")
    if feedback_visible.count("우선순위") < len(feedback_rows):
        failures.append("26:feedback 우선순위 필드 누락")
    if feedback_visible.count("완료기한") < len(feedback_rows) or feedback_visible.count("점검주기") < len(feedback_rows):
        failures.append("26:feedback 완료기한·점검주기 필드 누락")
    actual_feedback_rows = sum(max(0, _table_declared_rows(table) - 1) for table in feedback_tables)
    if actual_feedback_rows != len(feedback_rows):
        failures.append(f"26:feedback 분할 표 행 정리 오류: {actual_feedback_rows}/{len(feedback_rows)}")

    lesson_rows = parse_lesson_items(sections_by_id.get("lessons") or "")[:5]
    lessons_tables = [
        section8_xml[start:end]
        for start, end in find_hwpx_tag_spans(section8_xml, "hp:tbl")
        if all(
            token in get_hwpx_xml_scope_text(section8_xml[start:end])
            for token in ("평가 교훈 분석", "체크리스트")
        )
    ]
    lessons_visible = _coverage_text(
        " ".join(get_hwpx_xml_scope_text(table) for table in lessons_tables)
    )
    for index, row in enumerate(lesson_rows):
        expected = _coverage_text(row.get("lesson"))[:36]
        if expected and expected not in lessons_visible:
            failures.append(f"27:lessons 표 {index + 1}행 누락")
    actual_lesson_rows = sum(max(0, _table_declared_rows(table) - 2) for table in lessons_tables)
    if actual_lesson_rows != len(lesson_rows):
        failures.append(f"27:lessons 분할 표 행 정리 오류: {actual_lesson_rows}/{len(lesson_rows)}")

    for path in ("Contents/section5.xml", "Contents/section6.xml", "Contents/section7.xml", "Contents/section8.xml"):
        visible = html.unescape(get_hwpx_xml_scope_text(xml_by_path.get(path, "")))
        # '확인 필요' is a valid, deliberate evidence-gap statement. Only
        # reject unmistakable sample-template placeholders here.
        stale_placeholders = [token for token in ("{사업이름}", "평가책임자 OOO", "샘플 입력", "작성 예시") if token in visible]
        if stale_placeholders:
            failures.append(f"{path} 미치환 템플릿 문구 잔존: {', '.join(stale_placeholders)}")

    if failures:
        raise RuntimeError("HWPX 섹션 완전성 검증 실패: " + "; ".join(failures[:20]))
    return {
        "ok": True,
        "narrative_sections": section_results,
        "pdm_slots": len(pdm_slot_keys),
        "matrix_slots": len(matrix_cell_slots),
        "achievement_rows": len(achievement_rows),
        "feedback_rows": len(feedback_rows),
        "lesson_rows": len(lesson_rows),
    }


def _update(export_id: uuid.UUID, progress: int, stage: str, message: str) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            """UPDATE report_exports SET status='running',progress=%s,stage=%s,message=%s,
               started_at=COALESCE(started_at,now()),updated_at=now() WHERE id=%s""",
            (progress, stage, message, export_id),
        )


def _source_project_metadata(document_rows: list[dict]) -> dict[str, str]:
    """Read source-declared overview metadata without relying on LLM prose."""
    result: dict[str, str] = {}
    for row in document_rows:
        path = Path(str(row.get("extracted_path") or ""))
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")[:300_000]
        except (OSError, UnicodeError):
            continue
        if "sector" not in result:
            sector_match = re.search(r"사업\s*분야\s*▣\s*[①-⑳]?\s*([가-힣·/]+)", text)
            if sector_match:
                result["sector"] = sector_match.group(1).strip(" ·/")
        if "title_en" not in result:
            candidates: list[str] = []
            for line in text.splitlines():
                if "|" not in line or "Paramedicine" not in line:
                    continue
                for cell in (item.strip() for item in line.split("|")):
                    if (
                        35 <= len(cell) <= 320
                        and re.search(r"\b(?:Establish|Establishment|International Cooperation)\b", cell)
                        and sum(character.isascii() for character in cell) / max(1, len(cell)) > 0.92
                    ):
                        candidates.append(re.sub(r"\s+", " ", cell).strip())
            if candidates:
                candidates.sort(key=lambda value: (not value.startswith("Establish the Department"), len(value)))
                result["title_en"] = candidates[0]
        if "sector" in result and "title_en" in result:
            break
    return result


def _project_reader_text(value: object, donor: str) -> str:
    """Remove source-template vocabulary that does not describe this project."""
    text = sanitize_report_text(value)
    text = text.replace("삼각검증", "자료 간 교차대조")
    text = text.replace("영향(Outcome)", "성과(Outcome)")
    text = text.replace("KOICA 타 사업", "유관 ODA 사업")
    text = text.replace("향후 고용 연계 실적 확인 필요", "향후 고용 연계 실적을 후속 확인해야 함")
    tone_replacements = {
        "높은 정합성": "정합성",
        "견고한 제도적 성과": "확인된 제도적 성과",
        "성공적으로 이루어졌다": "이루어졌다",
        "성공적으로 구축": "구축",
        "선도적 교육 인프라": "교육 인프라",
        "극대화될 수": "높일 수",
        "극대화": "제고",
        "성공적으로": "확인된 근거 범위에서",
        "실시간 3각 소통 매트릭스": "세 기관 간 실시간 소통 체계",
    }
    for old, new in tone_replacements.items():
        text = text.replace(old, new)
    if "KOICA" not in donor.upper():
        protected = {
            "__KOICA_EVAL_GRADE__": "KOICA 평가등급",
            "__KOICA_GRADE__": "KOICA 등급",
        }
        for token, phrase in protected.items():
            text = text.replace(phrase, token)
        text = text.replace("대한민국 정부 및 KOICA의", "대한민국 정부 및 지원기관의")
        text = text.replace("KOICA의", "지원기관의")
        text = text.replace("KOICA", "지원기관")
        for token, phrase in protected.items():
            text = text.replace(token, phrase)
    return text


def _context() -> tuple[dict, dict[str, str]]:
    with connection() as conn:
        identity = current_project_identity(conn)
        sections = conn.execute("SELECT part_id,content FROM report_sections ORDER BY section_number").fetchall()
        overview_row = conn.execute("SELECT overview FROM project_overviews ORDER BY created_at DESC LIMIT 1").fetchone()
        run = conn.execute("SELECT id FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1").fetchone()
        evaluations = conn.execute(
            "SELECT * FROM criterion_evaluations WHERE run_id=%s ORDER BY id", (run["id"],)
        ).fetchall() if run else []
    overview = project_title_overview(overview_row["overview"] if overview_row else {}, identity)
    value = lambda key, fallback="확인 필요": str((overview.get(key) or {}).get("text") or fallback)
    criteria = []
    for row in evaluations:
        assessments = [{
            "questionId": item.get("question_id", ""),
            "question": item.get("question", ""),
            "score": item.get("score", 1),
            "finding": sanitize_report_text(item.get("finding", "")),
        } for item in row["question_assessments"]]
        criteria.append({
            "id": row["criterion_id"], "name": row["criterion_name"], "currentScore4": (float(row["score"]) if row["score"] is not None else None),
            "evaluationResult": {
                "score": (float(row["score"]) if row["score"] is not None else None), "summary": sanitize_report_text(row["summary"]),
                "rationale": sanitize_report_text(row["score_reason"]), "questionAssessments": assessments,
            },
        })
    total = round(sum(item["currentScore4"] for item in criteria), 1) if len(criteria) == 5 and all(item["currentScore4"] is not None for item in criteria) else None
    koica, government = grade(total) if total is not None else ("판정보류", "판정보류")
    if total is not None and is_provisional(evaluations):
        koica, government = f"{koica} (잠정)", f"{government} (잠정)"
    context = {
        "project": {
            "title": value("project_name"), "period": value("period"), "budget": value("budget"),
            "identity_resolution": identity,
            "country": value("country"), "location": value("location"),
        },
        "criteria": criteria,
        "overall": {"score": total, "maxScore": 20, "koicaGrade": koica, "governmentGrade": government},
        "_toc_page_map": {},
    }
    section_text = {row["part_id"]: sanitize_report_text(row["content"]) for row in sections}
    background = value("background", "등록 자료에서 확인되는 사업 추진배경을 기준으로 분석하였다.")
    objective = value("objective", "사업 목표는 등록 자료의 사업계획과 성과체계를 기준으로 확인한다.")
    activities = value("activities", "주요 활동은 등록 자료의 수행실적을 기준으로 확인한다.")
    outputs = value("outputs", "산출물은 등록 자료의 성과자료를 기준으로 확인한다.")
    outcomes = value("outcomes", "성과는 등록 자료의 성과자료를 기준으로 확인한다.")
    evidence_gaps = value("evidence_gaps", "장기 성과는 후속 추적자료로 보완할 필요가 있다.")
    criterion_by_id = {item["id"]: item for item in criteria}

    def criterion_summary(criterion_id: str) -> str:
        item = criterion_by_id.get(criterion_id)
        if not item:
            return "현재 등록 자료 범위에서 추가 검토가 필요하다."
        result = item["evaluationResult"]
        value = f"{item['currentScore4']:.1f}/4" if item['currentScore4'] is not None else '판정보류'
        return sanitize_report_text(f"{value}. {result['summary']}")

    # ``summary-ko`` is intentionally not rebuilt here. The saved five-heading
    # draft is the canonical source, and the HWPX adapter may only apply layout
    # to that exact text. Legacy/free-text drafts are migrated once by the
    # summary adapter instead of being silently replaced by unrelated sections.
    section_text["project-background"] = structured_slots_to_json("project-background", {
        "mdg_maternal_health_context": background,
        "government_policy_context": f"수원국 정책 및 제도와의 연계는 등록된 정책·사업 문서를 기준으로 검토하였다. {objective}",
        "target_region_need": f"대상지역의 수요와 문제상황은 등록된 사전조사 및 사업자료를 기준으로 확인하였다. {background}",
        "koica_policy_alignment": "KOICA 정책 및 국가협력전략과의 정합성은 관련 사업계획과 평가근거를 통해 검토하였다.",
        "project_selection_rationale": f"사업 선정 논리는 확인된 문제, 목표, 활동과 기대성과의 연결성을 중심으로 검토하였다. {objective}",
    })
    section_text["project-overview"] = structured_slots_to_json("project-overview", {
        "project_name_ko": value("project_name"), "project_name_en": value("project_name_en", "영문 사업명은 원 사업문서 확인 필요"),
        "target_country_region": f"{value('country')} · {value('location')}",
        "project_period_budget": f"{value('period')} / {value('budget')}",
        "project_sector": value("sector", "사업분야는 원 사업문서 확인 필요"),
        "project_purpose": objective, "pcp_feasibility_review": background,
        "korean_textbook_development": activities, "korean_equipment_support": outputs,
        "korean_expert_dispatch": activities, "korean_invitation_training": activities,
        "partner_contribution": f"수행기관: {value('implementer')} / 협력기관: {value('partner')}",
    })
    section_text["pdm"] = structured_slots_to_json("pdm", {
        "impact_summary": objective, "impact_indicator": "상위목표 지표는 최신 PDM을 기준으로 확정한다.",
        "impact_mov": "PDM 및 종료·후속 성과자료", "impact_assumption": evidence_gaps,
        "outcome_summary": outcomes, "outcome_indicator": "성과지표는 최신 PDM과 성과자료를 대조한다.",
        "outcome_mov": "연차별 성과자료 및 종료평가 근거", "outcome_assumption": evidence_gaps,
        "outputs_summary": outputs, "outputs_indicator": "산출지표는 계획 대비 실적으로 확인한다.",
        "outputs_mov": "수행실적, 검수·교육·제도화 자료", "outputs_assumption": evidence_gaps,
        "activities": activities, "inputs": f"총사업비 {value('budget')}; 수행기관 {value('implementer')}",
        "preconditions": "수원기관의 제도적 협력과 운영인력·예산 확보",
    })
    section_text["eval-purpose"] = structured_slots_to_json("eval-purpose", {
        "evaluation_purpose_scope_body": section_text.get("eval-purpose") or f"{value('project_name')}의 계획 대비 성과와 OECD DAC 평가기준을 분석하고 후속 개선과제를 도출한다."
    })
    matrix_slots = {}
    for criterion_id, label in (("relevance", "relevance"), ("coherence", "coherence"), ("effectiveness", "effectiveness"), ("efficiency", "efficiency"), ("sustainability", "sustainability")):
        item = criterion_by_id.get(criterion_id)
        questions = " / ".join(q.get("question", "") for q in (item or {}).get("evaluationResult", {}).get("questionAssessments", []))
        matrix_slots[f"{label}_question"] = questions or f"{criterion_id} 평가질문은 평가기준 탭의 정의를 적용한다."
        matrix_slots[f"{label}_indicator"] = "질문별 1~4점 루브릭과 확인된 정성·정량 근거"
        matrix_slots[f"{label}_source"] = "등록 사업문서 및 연결된 평가근거"
        matrix_slots[f"{label}_method"] = "문헌검토·자료 간 교차검증"
    for label, question in (("human_rights", "인권과 취약계층 접근성이 고려되었는가?"), ("gender", "성평등 관점과 성별분리 자료가 반영되었는가?"), ("environment", "환경·기후 위험과 완화조치가 고려되었는가?")):
        matrix_slots[f"{label}_question"] = question
        matrix_slots[f"{label}_indicator"] = "설계 반영 여부, 이행 근거 및 분리통계"
        matrix_slots[f"{label}_source"] = "사업계획, 수행실적 및 성과자료"
        matrix_slots[f"{label}_method"] = "문헌검토·교차검증"
    section_text["eval-matrix"] = structured_slots_to_json("eval-matrix", matrix_slots)
    return context, {part: qualify_report_text(part, text, evaluations) for part, text in section_text.items()}


def _pipeline_context(content_overrides: dict[str, str] | None = None, *, preview_part: str | None = None) -> tuple[dict, dict[str, str], dict]:
    """Build the export context without replacing expert-authored section drafts."""
    with connection() as conn:
        identity = current_project_identity(conn)
        section_rows = conn.execute(
            "SELECT part_id,content FROM report_sections ORDER BY section_number"
        ).fetchall()
        overview_row = conn.execute(
            "SELECT overview FROM project_overviews ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        run = conn.execute(
            "SELECT id FROM evaluation_runs WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        evaluation_rows = conn.execute(
            "SELECT * FROM criterion_evaluations WHERE run_id=%s ORDER BY id", (run["id"],)
        ).fetchall() if run else []
        pdm_source_row = conn.execute(
            """SELECT d.original_name,d.analysis,p.model
                 FROM pdm_models p JOIN evaluation_intake_documents d ON d.id=p.source_document_id
                WHERE d.status='completed' AND d.upload_role='pdm'
                ORDER BY p.created_at DESC LIMIT 1"""
        ).fetchone()
        metadata_rows = conn.execute(
            """SELECT original_name,extracted_path
                 FROM evaluation_intake_documents
                WHERE status='completed' AND extracted_path IS NOT NULL
                ORDER BY completed_at DESC NULLS LAST, uploaded_at DESC"""
        ).fetchall()
        source_name_rows = conn.execute(
            """SELECT original_name
                 FROM evaluation_intake_documents
                WHERE status='completed'
                ORDER BY uploaded_at DESC"""
        ).fetchall()

    overview = project_title_overview(overview_row["overview"] if overview_row else {}, identity)

    def overview_value(key: str, fallback: str = "확인 필요") -> str:
        return str((overview.get(key) or {}).get("text") or fallback).strip()

    donor = overview_value("donor")
    criteria: list[dict] = []
    for row in evaluation_rows:
        assessments = [{
            "questionId": item.get("question_id", ""),
            "question": _project_reader_text(item.get("question", ""), donor),
            "score": item.get("score", 1),
            "finding": _project_reader_text(item.get("finding", ""), donor),
            "limitations": item.get("limitations", []),
            "evidenceGaps": item.get("evidence_gaps", []),
        } for item in row["question_assessments"]]
        criteria.append({
            "id": row["criterion_id"],
            "name": row["criterion_name"],
            "currentScore4": (float(row["score"]) if row["score"] is not None else None),
            "evaluationResult": {
                "score": (float(row["score"]) if row["score"] is not None else None),
                "summary": _project_reader_text(row["summary"], donor),
                "rationale": _project_reader_text(row["score_reason"], donor),
                "questionAssessments": assessments,
            },
        })

    total = round(sum(item["currentScore4"] for item in criteria), 1) if len(criteria) == 5 and all(item["currentScore4"] is not None for item in criteria) else None
    koica_grade, government_grade = grade(total) if total is not None else ("판정보류", "판정보류")
    provisional = is_provisional(evaluation_rows)
    if total is not None and provisional:
        koica_grade, government_grade = f"{koica_grade} (잠정)", f"{government_grade} (잠정)"
    period = overview_value("period")
    scope = assessment_scope(overview)
    project_status = scope["project_status"]
    report_label = REPORT_TITLE
    project = {
        "title": overview_value("project_name"),
        "identity_resolution": identity,
        "title_en": overview_value("project_name_en", ""),
        "period": period,
        "budget": overview_value("budget"),
        "country": overview_value("country"),
        "location": overview_value("location"),
        "sector": overview_value("sector", ""),
        "donor": donor,
        "implementer": overview_value("implementer"),
        "project_manager": overview_value("project_manager"),
        "lead_implementer": overview_value("lead_implementer"),
        "partner": overview_value("partner"),
        "beneficiaries": overview_value("beneficiaries"),
        "stakeholders": overview_value("stakeholders"),
        "background": overview_value("background"),
        "objective": overview_value("objective"),
        "activities": overview_value("activities"),
        "outputs": overview_value("outputs"),
        "outcomes": overview_value("outcomes"),
        "evidence_gaps": overview_value("evidence_gaps"),
        "status": project_status,
        "report_label": report_label,
        "assessment_as_of": scope["assessment_as_of"],
    }
    source_metadata = _source_project_metadata(metadata_rows)
    for key in ("title_en", "sector"):
        current = str(project.get(key) or "").strip()
        if (not current or "확인 필요" in current or "미기재" in current) and source_metadata.get(key):
            project[key] = source_metadata[key]
    context = {
        "project": project,
        "criteria": criteria,
        "overall": {
            "score": total,
            "maxScore": 20,
            "koicaGrade": koica_grade,
            "governmentGrade": government_grade,
            "assessmentBasis": PROVISIONAL_BASIS if provisional else "stored_evaluation",
            "assessmentNotice": PROVISIONAL_NOTICE if provisional else "",
        },
        "_toc_page_map": {},
        "_raw_source_names": [str(row["original_name"] or "") for row in source_name_rows],
    }
    if pdm_source_row:
        pdm_source_slots = pdm_slots(pdm_source_row.get("analysis")) or (pdm_source_row.get("model") or {}).get("source_cells", {})
        if pdm_source_slots:
            context["_pdm_source_slots"] = pdm_source_slots
            context["_pdm_source_name"] = pdm_source_row["original_name"]
    raw_sections = {}
    for row in section_rows:
        part_id = row["part_id"]
        reader_text = normalize_source_mentions(
            _project_reader_text((content_overrides or {}).get(part_id, row["content"]), donor),
            context["_raw_source_names"],
        )
        reader_text = strip_inline_source_citations(reader_text)
        if part_id == "achievement":
            reader_text = reader_text.replace(
                "영향, 성과, 산출물의 계층별 지표 전체",
                "성과(Outcome)와 산출물(Output)의 지표 전체",
            )
        reader_text = re.sub(
            r"(?m)^\s*확인 필요\s*$",
            "현재 등록 근거 범위에서 확인된 실적은 다음과 같다.",
            reader_text,
        )
        raw_sections[part_id] = qualify_report_text(
            part_id, project_title_section(part_id, reader_text, identity), evaluation_rows)
    prepared_sections, conversion_report = prepare_hwpx_sections(
        context, raw_sections, criteria,
        selected_parts={preview_part} if preview_part else None,
    )
    prepared_sections = {part: project_title_section(part, body, identity) for part, body in prepared_sections.items()}
    return context, prepared_sections, conversion_report


def _scrub_xml_reader_text(xml: str, project: dict, source_names: list[str] | None = None) -> str:
    """Remove template-only project prose and corpus IDs without altering HWPX markup."""
    project_identity = " ".join(str(project.get(key) or "") for key in ("title", "country", "location", "sector"))
    forbidden = []
    if "네팔" not in project_identity:
        forbidden.extend(("네팔", "무구", "UNICEF Nepal"))
    # Exact phrases from the fixed sample report.  They are narrow enough not
    # to remove legitimate generic ODA terminology from a future project.
    forbidden.extend((
        "KOICA의 2010년 대 개발도상국 지원전략",
        "보건의료분야 중장기 전략(2008~2010)",
        "네팔 티까품지역 보건의료개선사업",
        "종료평가 시점에서 병원건축 상태",
        "COIVD-19",
    ))
    paragraph_pattern = re.compile(r"<hp:p\b[\s\S]*?</hp:p>")
    text_pattern = re.compile(r"(<hp:t\b[^>]*>)([\s\S]*?)(</hp:t>)")

    def paragraph_replacement(match: re.Match[str]) -> str:
        paragraph = match.group(0)
        visible = html.unescape(re.sub(r"<[^>]+>", "", paragraph))
        if forbidden and any(term in visible for term in forbidden):
            return text_pattern.sub(lambda item: item.group(1) + "" + item.group(3), paragraph)

        def text_replacement(item: re.Match[str]) -> str:
            raw = item.group(2)
            # hp:t may legitimately contain inline layout controls.  Reader
            # sanitization treats every XML-looking token as authoring markup,
            # which previously removed TOC tab leaders and concatenated the
            # title with its page number (for example ``국문 요약5``).
            inline_controls: dict[str, str] = {}

            def shield_inline_control(control: re.Match[str]) -> str:
                token = f"HWPXINLINECONTROL{len(inline_controls):04d}TOKEN"
                inline_controls[token] = control.group(0)
                return token

            raw = re.sub(
                r"<hp:(?:lineBreak|tab)\b[^>]*/?>",
                shield_inline_control,
                raw,
            )
            unescaped = html.unescape(raw)
            leading_space = re.match(r"^\s*", unescaped).group(0)
            trailing_space = re.search(r"\s*$", unescaped).group(0)
            cleaned = sanitize_report_text(unescaped)
            # Fixed-table adapters preserve Markdown until row parsing. Keep
            # a final package-level guard as well so a future adapter cannot
            # leak authoring markers into reader-visible HWPX text.
            cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
            cleaned = normalize_source_mentions(cleaned, source_names or [])
            cleaned = strip_inline_source_citations(cleaned)
            # HWPX uses separate text runs for mixed character styles.  The
            # boundary spaces in runs such as ``'- '`` and ``' 본문'`` are
            # semantic; stripping them concatenates ``-(요약어)본문`` after
            # the bold summary label is introduced.
            if cleaned:
                if leading_space and not cleaned[:1].isspace():
                    cleaned = leading_space + cleaned
                if trailing_space and not cleaned[-1:].isspace():
                    cleaned = cleaned + trailing_space
            elif unescaped and unescaped.isspace():
                cleaned = unescaped
            escaped = html.escape(cleaned, quote=False)
            for token, control in inline_controls.items():
                escaped = escaped.replace(token, control)
            return item.group(1) + escaped + item.group(3)

        return text_pattern.sub(text_replacement, paragraph)

    scrubbed = paragraph_pattern.sub(paragraph_replacement, xml)
    if "평가보고서 관련 공지" in scrubbed:
        # Final physical-section guard: section 3 and the grade table share
        # section2.xml, and legacy cleanup can otherwise reintroduce these
        # two notice-only placeholders after slot patching.
        scrubbed = re.sub(
            r"(<hp:t\b[^>]*>)\s*확인 필요\s*(</hp:t>)",
            r"\1평가자\2",
            scrubbed,
            count=1,
        )
        scrubbed = scrubbed.replace("평가품질 등급:", "외부 품질심의 상태:")
    return scrubbed


def _local_validate(
    data: bytes,
    project: dict | None = None,
    source_names: list[str] | None = None,
) -> dict:
    project = project or {}
    current_country = str(project.get("country") or "")
    with zipfile.ZipFile(BytesIO(data), "r") as archive:
        names = set(archive.namelist())
        required = {"mimetype", "META-INF/container.xml", "Contents/content.hpf", "Contents/header.xml"}
        missing = sorted(required - names)
        section_names = sorted(name for name in names if name.startswith("Contents/section") and name.endswith(".xml"))
        xml_text = "\n".join(archive.read(name).decode("utf-8") for name in section_names)
        visible_text = html.unescape("\n".join(re.findall(r"<hp:t\b[^>]*>([\s\S]*?)</hp:t>", xml_text)))
    if missing or not section_names:
        raise RuntimeError(f"HWPX 필수 구성요소 누락: {', '.join(missing) or 'section XML'}")
    internal_refs = sorted(set(re.findall(r"(?<![A-Za-z0-9])[DS]\d{2,3}(?![A-Za-z0-9])", xml_text)))
    escaped_controls = sorted(set(re.findall(r"&lt;hp:(?:tab|lineBreak)\b", xml_text, re.IGNORECASE)))
    unresolved_reader_placeholders = sorted(set(
        html.unescape(match.group(1)).strip()
        for match in re.finditer(
            r"<hp:t\b[^>]*>\s*(ㅇㅇㅇ\s*\(소속\)|평가품질\s*등급:|평가책임자\s*OOO|샘플\s*입력|작성\s*예시)\s*</hp:t>",
            xml_text,
        )
    ))
    source_artifacts = source_artifact_issues(visible_text, source_names or [])
    if re.search(r'"schema"\s*:\s*"section\d+[ _]', visible_text):
        source_artifacts.append('독자용 본문에 내부 JSON 슬롯 구조가 노출됨')
    project_identity = " ".join(str(project.get(key) or "") for key in ("title", "country", "location", "sector"))
    forbidden_samples = [
        "KOICA의 2010년 대 개발도상국 지원전략",
        "보건의료분야 중장기 전략(2008~2010)",
        "네팔 티까품지역 보건의료개선사업",
        "종료평가 시점에서 병원건축 상태",
        "COIVD-19",
    ]
    if "네팔" not in project_identity:
        forbidden_samples.extend(("네팔", "무구", "UNICEF Nepal"))
    sample_terms = [term for term in forbidden_samples if term in visible_text]
    markdown_artifacts = sorted(set(
        match.group(0) for pattern in (
            r"(?m)^\s*#{1,6}\s+",
            r"\*\*|__",
            r"(?m)^\s*\|?\s*:?-{3,}\s*\|",
            r"\((?:criteria-crosscutting|working-factors|nonworking-factors|criteria-other)\)",
        ) for match in re.finditer(pattern, visible_text, re.IGNORECASE)
    ))
    if internal_refs or sample_terms or escaped_controls or markdown_artifacts or unresolved_reader_placeholders or source_artifacts:
        raise RuntimeError(
            "HWPX 품질검사 실패: "
            + (f"내부 참조번호 {', '.join(internal_refs[:10])} " if internal_refs else "")
            + (f"다른 사업 샘플 문구 {', '.join(sample_terms)}" if sample_terms else "")
            + (" 이스케이프된 HWPX 제어태그" if escaped_controls else "")
            + (f" 마크다운/내부 작업표시 {', '.join(markdown_artifacts[:5])}" if markdown_artifacts else "")
            + (f" 미치환 독자표시 {', '.join(unresolved_reader_placeholders)}" if unresolved_reader_placeholders else "")
            + (f" 원본 파일명/관리정보 노출 {', '.join(source_artifacts[:5])}" if source_artifacts else "")
        )
    return {
        "zip_ok": True,
        "section_count": len(section_names),
        "missing": missing,
        "internal_refs": [],
        "sample_terms": [],
        "escaped_controls": [],
        "markdown_artifacts": [],
        "source_artifacts": [],
        "visible_chars": len(visible_text),
        "lineseg_cache_count": len(re.findall(r"<hp:linesegarray\b", xml_text)),
    }


def _validate_embedded_report_visuals(
    data: bytes,
    theory_visual: dict,
    _supplemental_visuals: dict,
) -> dict[str, object]:
    """Prove that the sole reader-facing frame is the current theory visual."""

    expected = {
        "BinData/image1.png": theory_visual["png"],
    }
    mismatches: list[str] = []
    digests: dict[str, str] = {}
    with zipfile.ZipFile(BytesIO(data), "r") as archive:
        for name, payload in expected.items():
            if name not in archive.namelist():
                mismatches.append(f"{name}: 누락")
                continue
            actual = archive.read(name)
            if actual != payload:
                mismatches.append(f"{name}: 생성 결과와 패키지 바이트 불일치")
            digests[name] = hashlib.sha256(actual).hexdigest()
        theory_section = archive.read("Contents/section8.xml").decode("utf-8")
        if theory_section.count("<hp:pic") != 1:
            mismatches.append("Contents/section8.xml: 변화이론 외 그림 문단 잔존")
        references = re.findall(r'binaryItemIDRef="([^"]+)"', theory_section)
        if references != ["image1"]:
            mismatches.append(f"Contents/section8.xml: 그림 참조 불일치 {references}")
    if mismatches:
        raise RuntimeError("보고서 시각자료 패키지 검증 실패: " + "; ".join(mismatches))
    return {"ok": True, "count": len(expected), "sha256": digests}


def run_report_export(export_id: uuid.UUID, project_id: uuid.UUID | None = None,
                      queued_snapshot: dict | None = None) -> None:
    with tenant_context(project_id, system=project_id is None):
        _run_report_export(export_id, queued_snapshot)


def _validate_export_start(queued_snapshot=None):
    """Recheck queued exports before any AI/render work; keep old files intact."""
    from .db import current_project_id
    from .project_lifecycle import project_lifecycle
    from .report_generator import report_export_readiness
    with connection() as conn:
        lifecycle = project_lifecycle(conn)
    if not lifecycle['report_current']:
        raise RuntimeError('내보내기 대기 중 자료·평가·보고서 상태가 변경되었습니다. 최신 평가와 27개 본문을 확인한 뒤 다시 내보내 주세요.')
    snapshot = lifecycle['input_snapshot']
    if queued_snapshot is not None and not snapshots_match(queued_snapshot, snapshot):
        raise RuntimeError('내보내기 접수 이후 자료 또는 평가가 변경되었습니다. 최신 보고서로 다시 내보내 주세요.')
    readiness = report_export_readiness(current_project_id())
    if not readiness['ready']:
        raise RuntimeError('HWPX 생성 전 본문 재점검이 필요합니다: ' + ' / '.join(
            item['message'] for item in readiness.get('issues', [])[:3]))
    if not snapshots_match(snapshot, capture_input_snapshot()):
        raise RuntimeError('내보내기 사전 점검 중 자료 또는 평가가 변경되었습니다. 다시 내보내 주세요.')
    return snapshot


def _run_report_export(export_id: uuid.UUID, queued_snapshot: dict | None = None) -> None:
    try:
        _update(export_id, 5, "preparing", "저장된 27개 섹션과 최신 평가결과를 불러오는 중")
        input_snapshot = _validate_export_start(queued_snapshot)
        if not TEMPLATE_PATH.exists():
            raise RuntimeError("원본 HWPX 양식을 찾을 수 없습니다.")
        template_digest = hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()
        if template_digest != TEMPLATE_SHA256:
            raise RuntimeError("고정 원본 HWPX 양식이 변경되었습니다. 레이아웃 프로파일을 다시 생성해야 합니다.")
        source_sections_digest = _report_sections_digest()
        context, sections_by_id, conversion_report = _pipeline_context()
        from .report_response import normalize_achievement_structure
        sections_by_id['achievement'] = normalize_achievement_structure(sections_by_id.get('achievement', ''))
        if len(sections_by_id) != 27:
            raise RuntimeError(f"보고서 섹션이 27개가 아닙니다: {len(sections_by_id)}개")

        visual_digest = theory_visual_input_digest(context, sections_by_id, input_snapshot)
        theory_visual = load_theory_artifact(visual_digest) or _load_cached_theory_visual_artifacts(visual_digest)
        if theory_visual:
            _update(export_id, 10, "theory_visual", "검증된 기존 변화이론 PPT·이미지를 재사용하는 중")
        else:
            _update(export_id, 10, "theory_visual", "Claude로 변화이론 성과경로를 구성하고 PPT·이미지를 생성하는 중")
            theory_visual = build_theory_visual_artifacts(context, sections_by_id)
            theory_visual["source"] = "claude_generated"
        theory_visual["input_digest"] = visual_digest
        save_theory_artifact(visual_digest, theory_visual)
        supplemental_visuals = build_supplemental_report_visuals(context, sections_by_id)

        _update(export_id, 15, "mapping", "원본 양식의 문단·표 슬롯과 섹션을 매핑하는 중")
        output = BytesIO()
        changed_slots = 0
        section_changes: dict[str, int] = {}
        layout_checks: dict[str, dict[str, bool | int]] = {}
        completed_sections = 0
        cover_font_height = 4800
        with zipfile.ZipFile(TEMPLATE_PATH, "r") as source, zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                raw = source.read(info.filename)
                if info.filename == "BinData/image1.png":
                    raw = theory_visual["png"]
                elif info.filename == "BinData/image2.bmp" and supplemental_visuals.get("enabled"):
                    raw = supplemental_visuals["grade_bmp"]
                elif info.filename == "BinData/image3.bmp" and supplemental_visuals.get("enabled"):
                    raw = supplemental_visuals["performance_bmp"]
                if info.filename == "Contents/header.xml":
                    header_layout = finalize_report_header_layout(raw.decode("utf-8"), context["project"])
                    cover_font_height = header_layout.cover_font_height
                    raw = header_layout.xml.encode("utf-8")
                section_numbers = SECTION_GROUPS.get(info.filename, ())
                if section_numbers:
                    xml = raw.decode("utf-8")
                    # Section 5 replaces a variable-length summary block. Apply
                    # the following fixed-address sections first so their
                    # paragraph indices cannot shift underneath them.
                    ordered_numbers = (6, 7, 5) if info.filename == "Contents/section3.xml" else section_numbers
                    for number in ordered_numbers:
                        patch_result = apply_section_adapter_xml(
                            number,
                            xml,
                            context,
                            sections_by_id,
                        )
                        xml = patch_result.xml
                        changed = patch_result.changed
                        if number == 1:
                            title_wraps = int(patch_result.metrics.get("title_wraps") or 0)
                            if len(re.sub(r"\s+", "", context["project"].get("title") or "")) > 22 and title_wraps != 1:
                                raise RuntimeError("긴 표지 사업명을 안전하게 줄바꿈하지 못했습니다.")
                        changed_slots += changed
                        section_changes[str(number)] = changed
                        completed_sections += 1
                        progress = 15 + round(completed_sections / 27 * 55)
                        _update(export_id, progress, "writing", f"원본 양식에 {completed_sections}/27 섹션 반영 중")
                    section_layout = finalize_report_section_layout(
                        info.filename,
                        xml,
                        context["project"],
                        theory_png=theory_visual["png"],
                    )
                    xml = section_layout.xml
                    layout_checks[info.filename] = section_layout.checks
                    if info.filename not in {"Contents/section0.xml", "Contents/section1.xml"}:
                        heading_gap_violations = report_heading_gap_violations_xml(xml)
                        layout_checks[info.filename]["heading_gap_violations"] = heading_gap_violations
                        if heading_gap_violations:
                            raise RuntimeError(
                                "제목 역할 기반 한 줄 여백을 적용하지 못했습니다: "
                                + ", ".join(heading_gap_violations)
                            )
                    if info.filename == "Contents/section2.xml" and not section_layout.checks.get("grade_split_layout"):
                        raise RuntimeError("평가등급 결과표의 읽기 안전 페이지 분할 조판을 적용하지 못했습니다.")
                    if info.filename == "Contents/section3.xml" and section_layout.checks.get("project_background_subheadings") != 5:
                        raise RuntimeError("사업 추진배경 ㅇ 소제목·본문 줄바꿈 문단 5개를 적용하지 못했습니다.")
                    if info.filename == "Contents/section3.xml" and not section_layout.checks.get("project_overview_opening"):
                        raise RuntimeError("사업개요 작성 메모·상단 공백을 제거하지 못했습니다.")
                    if info.filename == "Contents/section3.xml" and not section_layout.checks.get("project_overview_table_compacted"):
                        raise RuntimeError("사업개요 표의 과도한 상하 셀 여백을 축소하지 못했습니다.")
                    if info.filename == "Contents/section4.xml" and not all(
                        section_layout.checks.get(key)
                        for key in (
                            "pdm_typography",
                            "evaluation_matrix_header",
                            "evaluation_matrix_detached",
                            "evaluation_matrix_heading_spacing",
                            "evaluation_matrix_layout",
                        )
                    ):
                        raise RuntimeError("PDM·평가매트릭스 조판 단계를 완료하지 못했습니다.")
                    if info.filename == "Contents/section5.xml" and not section_layout.checks.get("achievement_typography"):
                        raise RuntimeError("성과달성도 표 최소 글자 크기를 적용하지 못했습니다.")
                    if info.filename == "Contents/section8.xml":
                        if (
                            section_layout.checks.get("theory_picture_kept") != 1
                            or section_layout.checks.get("theory_picture_removed") != 2
                        ):
                            raise RuntimeError("변화이론만 유지하고 후속 요약 그림 2개를 제거하지 못했습니다.")
                        if not section_layout.checks.get("feedback_headings_attached"):
                            raise RuntimeError("환류과제 제목과 표를 같은 쪽에 묶지 못했습니다.")
                        if not section_layout.checks.get("lessons_page_break"):
                            raise RuntimeError("교훈 표의 새 쪽 시작점을 구성하지 못했습니다.")
                        if (
                            int(section_layout.checks.get("feedback_table_pages") or 0) < 1
                            or int(section_layout.checks.get("lessons_table_pages") or 0) < 1
                            or not section_layout.checks.get("recommendation_full_text")
                        ):
                            raise RuntimeError("환류과제·교훈 표를 전체 텍스트가 보이는 읽기 안전 페이지로 구성하지 못했습니다.")
                    xml = cleanup_hwpx_placeholder_text_xml(xml)
                    xml = _scrub_xml_reader_text(
                        xml,
                        context["project"],
                        context.get("_raw_source_names", []),
                    )
                    if info.filename == "Contents/section3.xml":
                        summary_validation = validate_section5_summary_xml(
                            xml,
                            context,
                            sections_by_id,
                        )
                        layout_checks[info.filename] = {
                            **layout_checks.get(info.filename, {}),
                            **{f"summary_{key}": value for key, value in summary_validation.items()},
                        }
                    # A physical section cannot safely mix old cached line
                    # coordinates with newly cloned/reflowable paragraphs.
                    # Once any logical section in it changes, discard that
                    # section's layout cache and let Hancom/kordoc/rhwp lay out
                    # the complete section consistently from its styles.
                    # The TOC uses fixed tab/leader coordinates. Its cached
                    # line geometry is still valid because only page-number
                    # text changes, and removing it collapses every entry in
                    # rhwp. Narrative sections are reflowed as before.
                    if info.filename != "Contents/section1.xml":
                        xml = re.sub(r"<hp:linesegarray>[\s\S]*?</hp:linesegarray>", "", xml)
                    if info.filename == "Contents/section4.xml":
                        xml, refreshed_matrix_tables = refresh_evaluation_matrix_split_heights_xml(xml)
                        layout_checks[info.filename]["evaluation_matrix_height_refresh"] = (
                            refreshed_matrix_tables > 0
                        )
                        if refreshed_matrix_tables == 0:
                            raise RuntimeError(
                                "최종 텍스트 기준 평가매트릭스 분할 표의 행 높이를 모두 갱신하지 못했습니다."
                            )
                    raw = xml.encode("utf-8")
                target.writestr(info, raw)

        _update(export_id, 75, "packaging", "원본 ZIP 엔트리와 서식을 보존하여 HWPX를 패키징하는 중")
        final_bytes = repack_hwpx_preserving_original_entries(output.getvalue())
        layout_validation = validate_report_layout_contract(final_bytes)
        if not layout_validation.get("ok"):
            raise RuntimeError("HWPX 조판 계약 검증 실패: " + "; ".join(layout_validation.get("errors") or []))
        local_validation = _local_validate(
            final_bytes,
            context["project"],
            context.get("_raw_source_names", []),
        )
        semantic_validation = _validate_semantic_coverage(final_bytes, context, sections_by_id)

        _update(export_id, 82, "validating", "kordoc 1차 조판에서 실제 목차 쪽수를 계산하는 중")
        first_kordoc_validation = analyze_hwpx(final_bytes, KORDOC_URL, stage="kordoc 1차 검증")
        summary_page_span = validate_summary_page_span(first_kordoc_validation, minimum_pages=4)
        toc_page_map = toc_page_map_from_analysis(first_kordoc_validation)
        orphan_headings, toc_corrections, orphan_evidence = orphan_heading_adjustments_from_analysis(
            first_kordoc_validation
        )
        toc_page_map.update(toc_corrections)
        # A project title is not a layout version. Historical page numbers
        # must never overwrite destinations measured for this document.
        configured_toc_overrides = {}
        unknown_toc_keys = sorted(set(configured_toc_overrides) - set(REQUIRED_TOC_KEYS))
        if unknown_toc_keys:
            raise RuntimeError(
                "rHWP 목차 보정 프로필에 알 수 없는 키가 있습니다: "
                + ", ".join(unknown_toc_keys)
            )
        toc_page_map.update(configured_toc_overrides)
        final_bytes, orphan_breaks_changed = patch_orphan_heading_page_breaks(
            final_bytes, orphan_headings
        )
        # A criterion heading can already carry the mandatory hard break from
        # the section-layout pass.  In that case the orphan pass correctly
        # makes zero mutations; the contract is decided by validation below,
        # not by the mutation count.
        orphan_break_validation = validate_orphan_heading_page_breaks(final_bytes, orphan_headings)
        if not orphan_break_validation.get("ok"):
            raise RuntimeError(
                "고립 제목 페이지 나눔 검증 실패: "
                + "; ".join(orphan_break_validation.get("errors") or [])
            )
        final_bytes, toc_changed = _patch_toc_page_numbers(final_bytes, toc_page_map)
        # The source template stores the exceptional IV entry in two rows.
        # Its first merge removes that legacy row and can shift the final
        # feedback entry once. Reapply on the stabilized label topology and
        # verify every visible label/value pair before the second render.
        final_bytes, toc_stabilized_changes = _patch_toc_page_numbers(final_bytes, toc_page_map)
        toc_changed += toc_stabilized_changes
        toc_validation = validate_toc_page_numbers(final_bytes, toc_page_map)
        if not toc_validation.get("ok"):
            raise RuntimeError(
                "HWPX 목차 표시값 검증 실패: "
                + "; ".join(toc_validation.get("mismatches") or [])
            )
        if toc_changed < len(REQUIRED_TOC_KEYS):
            raise RuntimeError(f"HWPX 목차 쪽수 반영 실패: {toc_changed}/{len(REQUIRED_TOC_KEYS)}개")
        changed_slots += toc_changed

        visual_validation = _validate_embedded_report_visuals(
            final_bytes,
            theory_visual,
            supplemental_visuals,
        )

        _update(export_id, 88, "validating", "목차 쪽수를 반영한 HWPX를 2차 조판·검증하는 중")
        layout_validation = validate_report_layout_contract(final_bytes)
        if not layout_validation.get("ok"):
            raise RuntimeError("최종 HWPX 조판 계약 검증 실패: " + "; ".join(layout_validation.get("errors") or []))
        local_validation = _local_validate(
            final_bytes,
            context["project"],
            context.get("_raw_source_names", []),
        )
        semantic_validation = _validate_semantic_coverage(final_bytes, context, sections_by_id)
        kordoc_validation = analyze_hwpx(final_bytes, KORDOC_URL, stage="kordoc 2차 검증")
        for toc_pass in range(3):
            measured_map = toc_page_map_from_analysis(kordoc_validation)
            if measured_map == toc_page_map:
                break
            toc_page_map = measured_map
            final_bytes, _ = _patch_toc_page_numbers(final_bytes, toc_page_map)
            kordoc_validation = analyze_hwpx(
                final_bytes, KORDOC_URL, stage=f"목차 수렴 검증 {toc_pass + 1}"
            )
        if toc_page_map_from_analysis(kordoc_validation) != toc_page_map:
            raise RuntimeError("목차 쪽수가 최종 조판 결과에 수렴하지 않았습니다.")
        toc_validation = validate_toc_page_numbers(final_bytes, toc_page_map)
        if not toc_validation.get("ok"):
            raise RuntimeError("최종 조판 목차 쪽수 불일치")
        summary_page_span = validate_summary_page_span(kordoc_validation, minimum_pages=4)
        page_count, table_count = validate_render_result(kordoc_validation)

        # The browser preview is the final pagination authority. All body,
        # images and tables are frozen before the TOC is measured and patched.
        from .rhwp_renderer import finalize_toc_with_rhwp
        _update(export_id, 92, "toc_final", "완성된 문서를 rHWP로 조판하고 목차 쪽수를 최종 확정하는 중")
        final_bytes, rhwp_final = finalize_toc_with_rhwp(final_bytes)
        identity_validation = validate_report_identity(final_bytes, context['project'])
        toc_page_map = rhwp_final["page_map"]
        toc_validation = rhwp_final["visible_validation"]
        layout_validation = validate_report_layout_contract(final_bytes)
        if not layout_validation.get("ok"):
            raise RuntimeError("최종 rHWP 목차 반영 후 조판 계약 불일치: " + "; ".join(layout_validation.get("errors") or []))

        _update(export_id, 95, "saving", "검증된 HWPX 다운로드 파일을 저장하는 중")
        if not snapshots_match(input_snapshot, capture_input_snapshot()) or source_sections_digest != _report_sections_digest():
            raise RuntimeError("생성 중 원본 자료·평가·초안이 변경되었습니다. 기존 파일은 보존되며 최신 데이터로 다시 내보내야 합니다.")
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        project_name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", context["project"]["title"]).strip("._")[:70] or "ODA_사업"
        report_label = str(context["project"].get("report_label") or "평가보고서")
        safe_label = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", report_label).strip("._")
        file_name = f"{project_name}_{safe_label}.hwpx"
        output_path = EXPORT_DIR / f"{export_id}.hwpx"
        output_path.write_bytes(final_bytes)
        theory_pptx_path = EXPORT_DIR / f"{export_id}-theory.pptx"
        theory_png_path = EXPORT_DIR / f"{export_id}-theory.png"
        theory_pptx_path.write_bytes(theory_visual["pptx"])
        theory_png_path.write_bytes(theory_visual["png"])
        validation = {
            "local": local_validation,
            "input_snapshot": input_snapshot,
            "source_sections_sha256": source_sections_digest,
            "project_identity": context['project'].get('identity_resolution'),
            "project_identity_validation": identity_validation,
            "kordoc": kordoc_validation,
            "conversion": conversion_report,
            "semantic_coverage": semantic_validation,
            "layout_contract": layout_validation,
            "layout_stages": layout_checks,
            "orphan_heading_breaks": {
                **orphan_break_validation,
                "changed": orphan_breaks_changed,
                "evidence": orphan_evidence,
                "toc_corrections": toc_corrections,
            },
            "template_sha256": template_digest,
            "changed_slots": changed_slots,
            "section_changes": section_changes,
            "cover_title_font_pt": cover_font_height / 100,
            "toc_page_map": toc_page_map,
            "toc_page_slots_changed": toc_changed,
            "toc_visible_validation": toc_validation,
            "toc_source": "rhwp_final_render",
            "rhwp_final": rhwp_final,
            "rhwp_toc_verified": True,
            "rhwp_page_count": rhwp_final["page_count"],
            "summary_page_span": summary_page_span,
            "embedded_report_visuals": visual_validation,
            "theory_visual": {
                "model": theory_visual["model"],
                "source": theory_visual.get("source") or "project_model_generated",
                "pptx_path": str(theory_pptx_path),
                "png_path": str(theory_png_path),
                "design_version": theory_visual.get("design_version") or THEORY_VISUAL_DESIGN_VERSION,
                "render_source": theory_visual.get("render_source") or "unknown",
                "column_count": 6,
                "input_digest": visual_digest,
                "raster_dpi": 300 if theory_visual.get("render_source") == "libreoffice_pptx" else None,
                "embedded_image": "BinData/image1.png",
            },
        }
        with connection() as conn, conn.transaction():
            conn.execute(
                """UPDATE report_exports SET status='completed',progress=100,stage='completed',
                   message='HWPX 생성 및 검증 완료',output_path=%s,file_name=%s,validation=%s,
                   error_message=NULL,completed_at=now(),updated_at=now() WHERE id=%s""",
                (str(output_path), file_name, Jsonb(validation), export_id),
            )
    except Exception as exc:
        logging.getLogger(__name__).error("Report export failed: export_id=%s error_type=%s", export_id, type(exc).__name__)
        diagnostic = {}
        # Keep a non-published candidate for a reproducible layout diagnosis.
        # The download endpoint still requires status=completed. Never replace
        # the user's last valid export with a file that failed verification.
        if isinstance(locals().get("final_bytes"), bytes):
            try:
                diagnostic_dir = EXPORT_DIR / "diagnostics" / str(export_id)
                diagnostic_dir.mkdir(parents=True, exist_ok=True)
                candidate_path = diagnostic_dir / "candidate.hwpx"
                candidate_path.write_bytes(final_bytes)
                analysis = locals().get("kordoc_validation") or locals().get("first_kordoc_validation") or {}
                (diagnostic_dir / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, default=str), encoding="utf-8")
                diagnostic = {"candidate_path": str(candidate_path), "published": False,
                              "source_sha256": hashlib.sha256(final_bytes).hexdigest()}
            except OSError:
                logging.getLogger(__name__).warning("Could not retain failed export diagnostic", exc_info=True)
        with connection() as conn, conn.transaction():
            conn.execute(
                """UPDATE report_exports SET status='failed',stage='failed',message='HWPX 생성 실패',
                   error_message=%s,validation=validation || %s,completed_at=now(),updated_at=now() WHERE id=%s""",
                (f"{type(exc).__name__}: {exc}"[:2000], Jsonb({"diagnostic": diagnostic}), export_id),
            )
