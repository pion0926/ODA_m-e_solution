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


def main() -> None:
    app.attach_uploaded_documents()
    app.apply_persisted_evaluations()
    assert_report_cover_title()
    assert_editor_payload_uses_current_version()
    assert_generated_hwpx_uses_current_context()
    print("report editor quality checks passed")


if __name__ == "__main__":
    main()
