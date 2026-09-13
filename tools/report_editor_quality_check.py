from __future__ import annotations

import base64
import re
import sys
import zipfile
from html import unescape
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from oda_me import runtime as app  # noqa: E402
from oda_me.hwpx.patchers import (  # noqa: E402
    apply_text_slot_review_manifest_xml,
    find_hwpx_all_tag_spans,
    get_hwpx_xml_scope_text,
    hwpx_report_body_lines,
    load_text_slot_review_manifest,
    normalize_hwpx_manifest_value,
    replace_hwpx_heading_block_xml,
)


def hwpx_section_text(hwpx_bytes: bytes, section_name: str) -> str:
    with zipfile.ZipFile(BytesIO(hwpx_bytes), "r") as archive:
        xml = archive.read(section_name).decode("utf-8")
    xml = re.sub(r"<hp:lineBreak\b[^>]*/>", "\n", xml)
    text_nodes = re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", xml, re.DOTALL)
    return unescape(re.sub(r"<[^>]+>", "", "".join(text_nodes)))


def assert_report_cover_title() -> None:
    context, blueprint = app.current_report_context_and_blueprint()
    sections = app.complete_report_sections(context, blueprint, use_saved=False)
    project_title = context["project"].get("title") or ""
    cover = next((section for section in sections if section.get("id") == "title"), None)
    assert cover, "cover/title section is missing"
    body = str(cover.get("body") or "")
    assert project_title and project_title in body, f"cover does not include project title: {project_title!r}"
    assert "종료평가 결과보고서" in body, "cover does not include report title"
    assert "?" not in project_title, f"project title looks corrupted: {project_title}"
    assert "占" not in body, "cover body contains replacement characters"


def assert_editor_payload_uses_current_version() -> None:
    payload = app.report_editor_payload()
    assert payload.get("generatorVersion") == app.REPORT_GENERATOR_VERSION
    sections = payload.get("sections", [])
    cover = next((section for section in sections if section.get("id") == "title"), None)
    summary = next((section for section in sections if section.get("id") == "summary"), None)
    assert cover, "editor payload cover/title section is missing"
    assert payload["project"]["title"] in cover.get("body", ""), "editor payload cover is not using current project title"
    assert len(sections) == 27, f"editor payload should contain 27 report sections, got {len(sections)}"
    all_body = "\n\n".join(str(section.get("body") or "") for section in sections)
    assert "|" not in all_body, "editor payload still contains markdown table pipes"
    assert "쪽수는" not in all_body, "editor payload still contains page-number placeholder wording"
    assert "참고문헌 목록" not in all_body, "editor payload still uses the old references label"
    assert "B(매우 성공적)" not in all_body, "editor payload still contains stale overall grade wording"
    assert "2013~2021" not in all_body, "editor payload still contains stale project period"
    assert "540만" not in all_body, "editor payload still contains stale project budget"
    assert "평가책임자 추가" not in all_body, "editor payload inferred a placeholder as the manager name"
    assert "추가은" not in all_body, "editor payload contains malformed manager wording"
    assert not re.search(r"확인이 제한됨\)", all_body), "editor payload contains malformed parenthetical limitation text"
    assert summary, "editor payload summary section is missing"
    summary_body = str(summary.get("body") or "")
    overall = app.current_report_context().get("overall") or {}
    expected_score = f"{overall.get('score')}/{overall.get('maxScore', 20)}점"
    assert expected_score in summary_body, f"summary does not include current overall score {expected_score}"
    assert str(overall.get("governmentGrade") or "") in summary_body, "summary does not include current government grade"
    assert str(overall.get("koicaGrade") or "") in summary_body, "summary does not include current KOICA grade"


def assert_generated_hwpx_uses_current_context() -> None:
    context = app.current_report_context()
    result = app.build_cover_grade_body_patched_hwpx()
    hwpx_bytes = base64.b64decode(result["data"])
    project_title = str(context.get("project", {}).get("title") or "").strip()
    overall = context.get("overall") or {}
    expected_score = f"{overall.get('score')}/{overall.get('maxScore', 20)}점"
    expected_criterion_scores = {
        item.get("name"): f"{item.get('score')}점"
        for item in context.get("criteria", [])
        if item.get("id") in {"relevance", "coherence", "effectiveness", "efficiency", "sustainability"}
    }

    cover_text = hwpx_section_text(hwpx_bytes, "Contents/section0.xml")
    grade_text = hwpx_section_text(hwpx_bytes, "Contents/section2.xml")

    assert project_title and project_title in cover_text, "generated HWPX cover does not include current project title"
    assert "종료평가 결과보고서" in cover_text, "generated HWPX cover does not include report title"
    assert "ㅇㅇ사업" not in cover_text, "generated HWPX cover still contains template project placeholder"
    assert "2023. 12" not in cover_text, "generated HWPX cover still contains template date"
    assert "평가책임자 추가" not in cover_text, "generated HWPX cover inferred a placeholder as the manager name"

    assert project_title in grade_text, "generated HWPX grade page does not include current project title"
    assert "사업명(사업기간/예산)" not in grade_text, "generated HWPX grade page still contains project placeholder"
    assert "구간별 점수 산정 참고" not in grade_text, "generated HWPX grade page still contains template scoring notice"
    assert expected_score in grade_text, f"generated HWPX grade page does not include overall score {expected_score}"
    assert str(overall.get("governmentGrade") or "") in grade_text, "generated HWPX grade page does not include government grade"
    assert str(overall.get("koicaGrade") or "") in grade_text, "generated HWPX grade page does not include KOICA grade"
    for criterion_name, score_text in expected_criterion_scores.items():
        assert score_text in grade_text, f"generated HWPX grade page does not include {criterion_name} score {score_text}"
    assert "적절성 근거 미흡 보완 필요" not in grade_text, "generated HWPX grade page is still using fallback grade reasons"


def assert_hwpx_outline_hierarchy() -> None:
    lines = hwpx_report_body_lines(
        "ㅇ 추진배경\n- (추진배경) 중복 없이 남아야 하는 본문\n"
        "ㅇ 평가의 목적과 범위\n- (평가목적) 서로 다른 하위 라벨은 유지"
    )
    assert lines[1] == "- 중복 없이 남아야 하는 본문", "repeated parent label was not removed"
    assert lines[3].startswith("- (평가목적)"), "meaningful child label was removed"
    assert normalize_hwpx_manifest_value(5, "business_background", "- (추진배경) 본문") == "- 본문"
    assert normalize_hwpx_manifest_value(5, "business_overview", "(사업개요) 본문") == "- 본문"
    assert normalize_hwpx_manifest_value(5, "relevance_summary", "ㅇ 적절성: 판단 본문") == "- 판단 본문"

    summary_xml = (ROOT / "hwpx_sections" / "Section5_국문_요약" / "original.xml").read_text(encoding="utf-8")
    summary_manifest = load_text_slot_review_manifest(5)
    summary_xml, changed = apply_text_slot_review_manifest_xml(
        summary_xml,
        summary_manifest,
        {
            "business_background": "- (추진배경) 배경 본문",
            "business_overview": "- (사업개요) 개요 본문",
        },
        "Contents/section3.xml",
    )
    assert changed == 2, f"expected two summary slots to change, got {changed}"
    summary_paragraphs = find_hwpx_all_tag_spans(summary_xml, "hp:p")
    for paragraph_index, expected_text in [(6, "- 배경 본문"), (9, "- 개요 본문")]:
        start, end = summary_paragraphs[paragraph_index]
        paragraph_xml = summary_xml[start:end]
        assert get_hwpx_xml_scope_text(paragraph_xml).strip() == expected_text
        assert 'paraPrIDRef="91"' in paragraph_xml, "summary child paragraph is not indented below its parent"

    narrative_xml = (ROOT / "hwpx_sections" / "Section15_적절성" / "original.xml").read_text(encoding="utf-8")
    narrative_xml, changed = replace_hwpx_heading_block_xml(
        narrative_xml,
        "1. 적절성",
        "ㅇ 상위 항목\n- 하위 항목",
        ["2. 일관성"],
    )
    assert changed == 1, "narrative outline test block was not replaced"
    paragraphs = [
        narrative_xml[start:end]
        for start, end in find_hwpx_all_tag_spans(narrative_xml, "hp:p")
    ]
    bullet = next(item for item in paragraphs if get_hwpx_xml_scope_text(item).strip() == "ㅇ 상위 항목")
    detail = next(item for item in paragraphs if get_hwpx_xml_scope_text(item).strip() == "- 하위 항목")
    assert 'paraPrIDRef="69"' in bullet, "first-level bullet style was not applied"
    assert 'paraPrIDRef="92"' in detail, "second-level detail style was not applied"


def main() -> None:
    app.attach_uploaded_documents()
    app.apply_persisted_evaluations()
    assert_report_cover_title()
    assert_editor_payload_uses_current_version()
    assert_hwpx_outline_hierarchy()
    assert_generated_hwpx_uses_current_context()
    print("report editor quality checks passed")


if __name__ == "__main__":
    main()
