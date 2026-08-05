from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app  # noqa: E402
from report_prompts import EDITOR_REPORT_PARTS  # noqa: E402


BAD_MARKERS = ["자료 업로드 전", "Gemini", "백엔드", "평가 초안", "Cannot", "Traceback"]
MIN_CONTENT_LENGTH = {
    "cover": 20,
    "toc": 30,
    "notice": 80,
    "grade": 120,
    "project-overview": 120,
    "eval-matrix": 220,
    "feedback": 220,
    "lessons": 180,
}


def clean_line(value: object, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def part_section_id(part: dict) -> str:
    return str(part.get("sectionId") or part.get("id") or "")


def generated_content_by_part(generate: bool) -> tuple[dict[str, str], dict]:
    if generate:
        result = app.generate_report_editor_auto_draft({"force": True})
        return {
            str(item.get("partId") or item.get("sectionId")): str(item.get("content") or "")
            for item in result.get("results", [])
        }, result

    payload = app.report_editor_payload()
    section_map = {str(section.get("id")): str(section.get("body") or "") for section in payload.get("sections", [])}
    contents = {}
    for part in EDITOR_REPORT_PARTS:
        contents[str(part.get("id"))] = section_map.get(part_section_id(part), "")
    return contents, {"ok": True, "generated": 0, "skipped": len(EDITOR_REPORT_PARTS), "total": len(EDITOR_REPORT_PARTS)}


def audit_part(index: int, part: dict, content: str, context: dict) -> dict:
    part_id = str(part.get("id") or "")
    references = app.part_reference_documents(part)
    uploaded = references.get("uploadedDocuments", [])
    missing = references.get("missingEvidence", [])
    required_inputs = part.get("requiredInputs") or part.get("required_inputs") or []
    prompt = str(part.get("prompt") or "")
    contract = app.editor_part_output_contract(part_id)
    issues: list[str] = []

    if len(prompt.strip()) < 60:
        issues.append("프롬프트가 짧아 산출 범위와 판단 기준이 불명확함")
    if len(contract.strip()) < 50:
        issues.append("출력 계약이 구체적이지 않음")
    if part_id not in {"toc", "notice"} and not required_inputs:
        issues.append("필수 입력 목록이 비어 있음")
    if part_id not in {"toc", "notice"} and not references.get("criteria"):
        issues.append("참고 평가기준 매핑이 없음")

    min_length = MIN_CONTENT_LENGTH.get(part_id, 160)
    if len(content.strip()) < min_length:
        issues.append(f"실제 생성 응답이 짧음({len(content.strip())}자)")
    for marker in BAD_MARKERS:
        if marker in content:
            issues.append(f"생성 응답에 내부/임시 문구 포함: {marker}")

    if part_id == "grade":
        score_rows = app.criterion_grade_rows(context)
        expected_total = f"{context['overall']['score']}/{context['overall']['maxScore']}점"
        if expected_total not in content:
            issues.append(f"평가등급표 응답에 종합점수 {expected_total} 미반영")
        for row in score_rows:
            if f"{row['score']}점" not in content:
                issues.append(f"{row['name']} {row['score']}점 미반영 가능성")
        if len({row["score"] for row in score_rows}) > 1 and content.count("1점") >= len(score_rows):
            issues.append("점수가 모두 1점처럼 보이는 패턴 감지")

    if part_id.startswith("criteria-"):
        related = references.get("criteria") or []
        for criterion in context.get("criteria", []):
            if criterion.get("id") in related and f"{criterion.get('score')}점" not in content:
                issues.append(f"{criterion.get('name')} 점수 {criterion.get('score')}점이 본문에 명시되지 않음")

    if uploaded and len(missing) > len(uploaded) + 3:
        issues.append("등록 문서 대비 누락 항목이 과도함. 참고문서 매핑을 더 넓게 볼 필요가 있음")

    status = "수정 필요" if issues else "정상"
    return {
        "index": index,
        "id": part_id,
        "sectionId": part_section_id(part),
        "title": part.get("title", ""),
        "status": status,
        "promptLength": len(prompt),
        "requiredInputs": required_inputs,
        "referenceCriteria": references.get("criteria", []),
        "uploadedCount": len(uploaded),
        "directCount": len([item for item in uploaded if item.get("match") == "direct"]),
        "supportingCount": len([item for item in uploaded if item.get("match") == "supporting"]),
        "missingCount": len(missing),
        "missingSamples": missing[:5],
        "contentLength": len(content.strip()),
        "contentPreview": clean_line(content, 450),
        "issues": issues,
    }


def write_markdown(audits: list[dict], generation_result: dict, output_path: Path) -> None:
    ok_count = len([item for item in audits if item["status"] == "정상"])
    lines = [
        "# 평가보고서 27개 섹션 프롬프트 점검 결과",
        "",
        f"- 생성 버전: `{app.REPORT_GENERATOR_VERSION}`",
        f"- 총 섹션: {len(audits)}개",
        f"- 정상: {ok_count}개",
        f"- 수정 필요: {len(audits) - ok_count}개",
        f"- 실제 생성 호출: 갱신 {generation_result.get('generated', 0)}개 / 재사용 {generation_result.get('skipped', 0)}개 / 실패 {generation_result.get('failed', 0)}개",
        "",
    ]
    for item in audits:
        lines.extend(
            [
                f"## 프롬프트 {item['index']}. {item['title']} (`{item['id']}`)",
                "",
                f"- 상태: {item['status']}",
                f"- 섹션 ID: `{item['sectionId']}`",
                f"- 프롬프트 길이: {item['promptLength']}자",
                f"- 실제 응답 길이: {item['contentLength']}자",
                f"- 참고 기준: {', '.join(item['referenceCriteria']) or '없음'}",
                f"- 사용 문서: 직접 {item['directCount']}건, 보조 {item['supportingCount']}건, 총 {item['uploadedCount']}건",
                f"- 보완 필요로 남은 핵심 증빙: {item['missingCount']}건",
                f"- 필수 입력: {', '.join(clean_line(value, 70) for value in item['requiredInputs']) or '없음'}",
            ]
        )
        if item["missingSamples"]:
            lines.append("- 보완 필요 샘플: " + " / ".join(clean_line(sample.get("evidenceName"), 80) for sample in item["missingSamples"]))
        if item["issues"]:
            lines.append("- 발견 이슈: " + " / ".join(item["issues"]))
        lines.extend(["", "> 실제 응답 미리보기: " + (item["contentPreview"] or "(비어 있음)"), ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", help="Call the LLM-backed 27-part auto draft before auditing.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "reports" / "report_prompt_audit.md"),
        help="Markdown audit output path.",
    )
    parser.add_argument(
        "--json-output",
        default=str(ROOT / "data" / "reports" / "report_prompt_audit.json"),
        help="JSON audit output path.",
    )
    args = parser.parse_args()

    app.attach_uploaded_documents()
    app.apply_persisted_evaluations()
    context = app.current_report_context()
    contents, generation_result = generated_content_by_part(args.generate)
    audits = [
        audit_part(index, part, contents.get(str(part.get("id")), ""), context)
        for index, part in enumerate(EDITOR_REPORT_PARTS, start=1)
    ]

    output_path = Path(args.output)
    json_path = Path(args.json_output)
    write_markdown(audits, generation_result, output_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"generation": generation_result, "audits": audits}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failed = [item for item in audits if item["status"] != "정상"]
    print(f"prompt audit written: {output_path}")
    print(f"json audit written: {json_path}")
    print(f"sections={len(audits)} ok={len(audits) - len(failed)} needs_fix={len(failed)}")
    if failed:
        for item in failed:
            print(f"- prompt {item['index']} {item['id']}: {'; '.join(item['issues'])}")


if __name__ == "__main__":
    main()
