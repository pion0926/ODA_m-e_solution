from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "prompts"
OUTPUT_PATH = ROOT / "docs" / "actual_prompt_inventory.md"

sys.path.insert(0, str(ROOT / "backend"))
import report_prompts  # noqa: E402


SECTION_INFO = {
    1: ("cover", "표지"),
    2: ("toc", "목차"),
    3: ("notice", "평가보고서 관련 공지"),
    4: ("grade", "평가등급 결과표"),
    5: ("summary-ko", "국문 요약"),
    6: ("project-background", "사업 추진배경"),
    7: ("project-overview", "사업개요"),
    8: ("pdm", "사업설계매트릭스(PDM)"),
    9: ("eval-purpose", "평가의 목적과 범위"),
    10: ("eval-matrix", "평가매트릭스"),
    11: ("eval-methods", "평가방법"),
    12: ("eval-limitations", "평가의 한계"),
    13: ("eval-team", "평가팀 구성 및 시행체계"),
    14: ("achievement", "성과 달성도"),
    15: ("criteria-relevance", "적절성"),
    16: ("criteria-coherence", "일관성"),
    17: ("criteria-effectiveness", "효과성"),
    18: ("criteria-efficiency", "효율성"),
    19: ("criteria-sustainability", "지속가능성"),
    20: ("criteria-crosscutting", "범분야 이슈"),
    21: ("criteria-other", "그 외 평가기준"),
    22: ("conclusion", "결론"),
    23: ("working-factors", "작동요인"),
    24: ("nonworking-factors", "비작동요인"),
    25: ("theory", "변화이론 분석"),
    26: ("feedback", "환류과제"),
    27: ("lessons", "교훈"),
}


COMMON_INPUTS = [
    ("reference_corpus", "업로드 문서, RAG 검색 결과, 샘플 보고서 등 원문 근거 묶음"),
    ("content_inputs.project", "사업명, 기간, 예산, 대상국가, 대상지역 등 프로젝트 기본정보"),
    ("content_inputs.criteria", "DAC 기준별 평가질문, 점수, 핵심 판단, 증빙 공백 및 보완 필요사항"),
    ("content_inputs.overall", "종합점수, KOICA 평가등급, 국무조정실 평가등급 등 총괄 평가정보"),
    ("grade_score_rows", "평가등급 결과표에 투입되는 기준별·질문별 시스템 산정 점수 행"),
    ("prior_analysis_sections", "앞서 생성 또는 수정된 섹션 본문. 결론·작동요인·제언·교훈의 1차 근거"),
    ("sample_reference_for_this_section", "해당 섹션과 유사한 샘플 보고서 문체·표 구조·항목 구분 참조"),
    ("previous_text", "현재 HWPX 양식 또는 기존 생성본의 해당 섹션 내용"),
    ("user_request", "사용자가 해당 섹션에 직접 입력한 수정 지시"),
]


def extract_editor_prompt(path: Path) -> str:
    module_ast = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in module_ast.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "EDITOR_PROMPT" in names:
                return str(ast.literal_eval(node.value)).strip()
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "EDITOR_PROMPT":
                return str(ast.literal_eval(node.value)).strip()
    return ""


def prompt_file(section_number: int) -> Path:
    matches = sorted(PROMPTS_DIR.glob(f"Section{section_number}_*.py"))
    if not matches:
        raise FileNotFoundError(f"Section{section_number}_*.py not found")
    return matches[0]


def block(prompt: str, header: str) -> str:
    marker = f"[{header}]"
    start = prompt.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    next_match = re.search(r"\n\[[^\]]+\]", prompt[start:])
    end = start + next_match.start() if next_match else len(prompt)
    return prompt[start:end].strip()


def one_line(value: str, max_len: int = 140) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def bullets(value: str, max_items: int = 5) -> str:
    lines = []
    for raw in value.splitlines():
        item = raw.strip()
        if not item:
            continue
        item = item.lstrip("-").strip()
        if item:
            lines.append(item)
    if len(lines) > max_items:
        shown = lines[:max_items]
        shown.append(f"외 {len(lines) - max_items}개")
        return "<br>".join(shown)
    return "<br>".join(lines)


def output_contract(prompt: str) -> str:
    for schema in re.findall(r'"schema"\s*:\s*"([^"]+)"', prompt):
        return f"JSON schema: `{schema}`"
    out = block(prompt, "출력 형식") or block(prompt, "출력")
    return one_line(out, 170)


def flatten_evidence(value: Any) -> list[str]:
    if isinstance(value, dict):
        rows: list[str] = []
        for criterion, items in value.items():
            if isinstance(items, (list, tuple)):
                rows.extend(f"{criterion}: {item}" for item in items)
            else:
                rows.append(f"{criterion}: {items}")
        return rows
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)] if value else []


def section_pipeline(part_id: str) -> dict[str, Any]:
    return report_prompts.EDITOR_PART_REFERENCE_PIPELINES.get(
        part_id,
        {"criteria": [], "evidence": {}, "notes": []},
    )


def section_rows() -> list[dict[str, Any]]:
    rows = []
    for number, (part_id, title) in SECTION_INFO.items():
        path = prompt_file(number)
        prompt = extract_editor_prompt(path)
        rows.append(
            {
                "number": number,
                "part_id": part_id,
                "title": title,
                "file": path.relative_to(ROOT).as_posix(),
                "prompt": prompt,
                "target": one_line(block(prompt, "작성 대상"), 120),
                "inputs": bullets(block(prompt, "참고할 입력"), 5),
                "rules": bullets(block(prompt, "작성 규칙"), 4),
                "detail": bullets(block(prompt, "세부 판단 기준") or block(prompt, "세부 생성 기준") or block(prompt, "세부 점수 산정 및 산정 이유 작성 기준"), 4),
                "output": output_contract(prompt),
                "pipeline": section_pipeline(part_id),
            }
        )
    return rows


def write_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        safe = [str(cell).replace("\n", "<br>").replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(safe) + " |")


def main() -> None:
    rows = section_rows()
    lines: list[str] = []

    lines.append("# 27개 섹션 실제 프롬프트 및 추가 데이터 인벤토리")
    lines.append("")
    lines.append(
        "본 문서는 `prompts/Section*.py`의 실제 `EDITOR_PROMPT` 전문과, 각 프롬프트에 주입되는 입력 데이터 및 증빙자료 목록을 한눈에 보기 위해 정리한 자료다."
    )
    lines.append("특허 출원 검토 시에는 이 문서를 기준으로 섹션별 생성 목적, 입력 데이터, 출력 계약, 판단 기준을 설명할 수 있다.")
    lines.append("")

    lines.append("## 1. 공통 추가 데이터 목록")
    lines.append("")
    write_table(lines, ["데이터 키", "역할"], COMMON_INPUTS)
    lines.append("")

    lines.append("## 2. DAC 기준별 증빙자료 슬롯")
    lines.append("")
    dac_slots = [
        ("적절성", report_prompts.RELEVANCE_SLOTS),
        ("일관성", report_prompts.COHERENCE_SLOTS),
        ("효과성", report_prompts.EFFECTIVENESS_SLOTS),
        ("효율성", report_prompts.EFFICIENCY_SLOTS),
        ("지속가능성", report_prompts.SUSTAINABILITY_SLOTS),
    ]
    for label, slots in dac_slots:
        lines.append(f"### {label}")
        for item in slots:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 3. 섹션별 프롬프트 한눈에 보기")
    lines.append("")
    overview_rows = []
    for row in rows:
        evidence = flatten_evidence(row["pipeline"].get("evidence", {}))
        notes = row["pipeline"].get("notes", [])
        overview_rows.append(
            [
                row["number"],
                row["title"],
                f"`{row['part_id']}`",
                f"`{row['file']}`",
                row["target"],
                row["inputs"],
                "<br>".join(evidence[:6]) + (f"<br>외 {len(evidence) - 6}개" if len(evidence) > 6 else ""),
                "<br>".join(notes),
                row["output"],
            ]
        )
    write_table(
        lines,
        ["No", "섹션", "파트 ID", "파일", "작성 대상", "프롬프트 입력", "추가 증빙 데이터", "파이프라인 메모", "출력 계약"],
        overview_rows,
    )
    lines.append("")

    lines.append("## 4. 섹션별 요약 및 실제 프롬프트 전문")
    lines.append("")
    for row in rows:
        evidence = flatten_evidence(row["pipeline"].get("evidence", {}))
        criteria = row["pipeline"].get("criteria", [])
        notes = row["pipeline"].get("notes", [])
        lines.append(f"### {row['number']}. {row['title']} ({row['part_id']})")
        lines.append("")
        lines.append(f"- 원본 파일: `{row['file']}`")
        lines.append(f"- 작성 대상: {row['target']}")
        lines.append(f"- 출력 계약: {row['output']}")
        if criteria:
            lines.append(f"- 참조 평가기준: {', '.join(criteria)}")
        if row["detail"]:
            lines.append(f"- 세부 판단/생성 기준 요약: {row['detail']}")
        if notes:
            lines.append("- 파이프라인 메모:")
            for item in notes:
                lines.append(f"  - {item}")
        if evidence:
            lines.append("- 추가 증빙 데이터:")
            for item in evidence:
                lines.append(f"  - {item}")
        lines.append("")
        lines.append("<details>")
        lines.append(f"<summary>실제 EDITOR_PROMPT 전문 보기: {row['title']}</summary>")
        lines.append("")
        lines.append("````text")
        lines.append(row["prompt"])
        lines.append("````")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(OUTPUT_PATH)
    print(f"sections={len(rows)}")


if __name__ == "__main__":
    main()
