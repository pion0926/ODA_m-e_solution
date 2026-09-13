from __future__ import annotations

import argparse
import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "redesign" / "backend"), str(ROOT)]

from report_few_shot import EXPECTED_PART_IDS, FORMAT_ONLY_DEMOS  # noqa: E402
from report_outline import NARRATIVE_OUTLINE_PART_IDS  # noqa: E402
from report_prompts import EDITOR_PART_REFERENCE_PIPELINES, EDITOR_REPORT_PARTS  # noqa: E402
from kodame_intake.hwpx_pipeline import SECTION_PIPELINES, hwpx_authoring_contract  # noqa: E402


BAD_MARKERS = ("자료 업로드 전", "Gemini", "Traceback", "{{CURRENT_")
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
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def load_section_contents(path: str) -> dict[str, str]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        rows = payload["items"]
    elif isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        return {str(key): str(value or "") for key, value in payload.items()}
    else:
        raise ValueError("섹션 JSON은 items 배열, 배열, 또는 part_id-content 객체여야 합니다.")
    return {
        str(row.get("part_id") or row.get("partId") or row.get("id")): str(row.get("content") or "")
        for row in rows
        if isinstance(row, dict)
    }


def fetch_section_contents(base_url: str, email: str, password: str) -> dict[str, str]:
    if not base_url:
        return {}
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    login_request = Request(
        base_url.rstrip("/") + "/api/v2/auth/login",
        data=json.dumps({"email": email, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(login_request, timeout=15) as response:
        if response.status >= 400:
            raise RuntimeError(f"프롬프트 감사 로그인 실패: HTTP {response.status}")
    with opener.open(base_url.rstrip("/") + "/api/v2/report/sections", timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        str(row.get("part_id") or row.get("id")): str(row.get("content") or "")
        for row in payload.get("items", [])
        if isinstance(row, dict)
    }


def detail_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("-")]


def audit_part(index: int, part: dict, content: str | None) -> dict:
    part_id = str(part.get("id") or "")
    prompt = str(part.get("prompt") or "").strip()
    required_inputs = [str(item) for item in (part.get("requiredInputs") or [])]
    route = EDITOR_PART_REFERENCE_PIPELINES.get(part_id) or {}
    evidence = route.get("evidence") or {}
    demo = str(FORMAT_ONLY_DEMOS.get(part_id) or "")
    pipeline = next((item for item in SECTION_PIPELINES if item.part_id == part_id), None)
    contract = hwpx_authoring_contract(part_id) if pipeline else {}
    prompt_source = str(part.get("promptSourceFile") or "").replace("\\", "/")
    adapter_source = str(contract.get("source_module") or "")
    issues: list[str] = []

    if len(prompt) < 60:
        issues.append("프롬프트가 짧아 산출 범위와 판단 기준이 불명확함")
    if part_id not in {"toc", "notice"} and not required_inputs:
        issues.append("필수 입력 목록이 비어 있음")
    if part_id not in {"toc", "notice"} and not route.get("criteria"):
        issues.append("평가기준·증빙 라우팅이 없음")
    if part_id not in {"toc", "notice"} and not evidence:
        issues.append("증빙 슬롯 라우팅이 없음")
    if not demo or "{{CURRENT_" not in demo:
        issues.append("현재 사업 값으로 치환되는 형식 전용 few-shot 예시가 없음")
    if pipeline is None or not contract.get("adapter"):
        issues.append("독립 HWPX 어댑터 계약이 없음")
    if not prompt_source.startswith("prompts/Section"):
        issues.append("독립 생성 프롬프트 원본 파일이 없음")
    if ".hwpx_adapters.sections.section" not in adapter_source:
        issues.append("독립 HWPX 변환 소스 모듈이 없음")
    if contract and "report_sections.content" not in str(contract.get("source_of_truth") or ""):
        issues.append("초안과 HWPX가 동일한 저장 원문을 사용하지 않음")

    if part_id in NARRATIVE_OUTLINE_PART_IDS or part_id == "summary-ko":
        lines = detail_lines(demo)
        if not lines:
            issues.append("few-shot에 세부 논거 '-' 문단이 없음")
        if part_id in NARRATIVE_OUTLINE_PART_IDS:
            for marker in ("[전 서술형 섹션 공통 문단 양식]", "(핵심어 요약)", "~함", "약 360자 이내"):
                if marker not in prompt:
                    issues.append(f"공통 서술형 제약 누락: {marker}")

    content_length = None
    content_preview = ""
    if content is not None:
        content = str(content)
        content_length = len(content.strip())
        content_preview = clean_line(content, 450)
        if content_length < MIN_CONTENT_LENGTH.get(part_id, 160):
            issues.append(f"저장된 실제 응답이 짧음({content_length}자)")
        for marker in BAD_MARKERS:
            if marker in content:
                issues.append(f"저장된 실제 응답에 내부·임시 문구 포함: {marker}")

    return {
        "index": index,
        "id": part_id,
        "title": str(part.get("title") or ""),
        "status": "수정 필요" if issues else "정상",
        "prompt_length": len(prompt),
        "required_inputs": required_inputs,
        "reference_criteria": list(route.get("criteria") or []),
        "evidence_slot_count": sum(len(items) for items in evidence.values()) if isinstance(evidence, dict) else 0,
        "adapter": str(contract.get("adapter") or ""),
        "prompt_source": prompt_source,
        "adapter_source": adapter_source,
        "authoring_shape": str(contract.get("authoring_shape") or ""),
        "content_length": content_length,
        "content_preview": content_preview,
        "issues": issues,
    }


def write_markdown(audits: list[dict], output_path: Path, live_content: bool) -> None:
    ok_count = sum(item["status"] == "정상" for item in audits)
    lines = [
        "# 평가보고서 27개 섹션 프롬프트·HWPX 계약 점검 결과",
        "",
        f"- 총 섹션: {len(audits)}개",
        f"- 정상: {ok_count}개",
        f"- 수정 필요: {len(audits) - ok_count}개",
        f"- 저장 응답 포함 점검: {'예' if live_content else '아니오(프롬프트·few-shot·어댑터 계약만 점검)'}",
        "",
    ]
    for item in audits:
        lines.extend([
            f"## 섹션 {item['index']}. {item['title']} (`{item['id']}`)",
            "",
            f"- 상태: {item['status']}",
            f"- 프롬프트: {item['prompt_length']}자 / 형식 전용 few-shot 있음",
            f"- 프롬프트 원본: `{item['prompt_source']}`",
            f"- 증빙 라우팅: {', '.join(item['reference_criteria']) or '양식 소유 섹션'} / {item['evidence_slot_count']}개 슬롯",
            f"- HWPX 어댑터: `{item['adapter']}`",
            f"- HWPX 변환 원본: `{item['adapter_source']}`",
            f"- 작성 형상: {item['authoring_shape']}",
        ])
        if item["content_length"] is not None:
            lines.append(f"- 저장 응답: {item['content_length']}자")
        if item["issues"]:
            lines.append("- 발견 이슈: " + " / ".join(item["issues"]))
        if item["content_preview"]:
            lines.extend(["", "> 실제 응답 미리보기: " + item["content_preview"]])
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sections-json", default="", help="선택: /api/v2/report/sections 응답 JSON")
    parser.add_argument("--api-base-url", default="", help="선택: 실행 중인 ODAME 웹 주소")
    parser.add_argument("--email", default="", help="API 점검 계정")
    parser.add_argument("--password", default="", help="API 점검 비밀번호")
    parser.add_argument("--output", default=str(ROOT / "data" / "reports" / "report_prompt_audit.md"))
    parser.add_argument("--json-output", default=str(ROOT / "data" / "reports" / "report_prompt_audit.json"))
    args = parser.parse_args()

    if args.sections_json:
        contents = load_section_contents(args.sections_json)
    elif args.api_base_url:
        if not args.email or not args.password:
            raise RuntimeError("API 점검에는 --email과 --password가 필요합니다.")
        contents = fetch_section_contents(args.api_base_url, args.email, args.password)
    else:
        contents = {}
    part_ids = tuple(str(part.get("id")) for part in EDITOR_REPORT_PARTS)
    if part_ids != EXPECTED_PART_IDS:
        raise RuntimeError("27개 프롬프트 순서가 표준 섹션 순서와 다릅니다.")
    audits = [
        audit_part(index, part, contents.get(str(part.get("id"))) if contents else None)
        for index, part in enumerate(EDITOR_REPORT_PARTS, 1)
    ]
    prompt_sources = [item["prompt_source"] for item in audits]
    adapter_sources = [item["adapter_source"] for item in audits]
    if len(set(prompt_sources)) != 27 or len(set(adapter_sources)) != 27:
        raise RuntimeError("27개 프롬프트·HWPX 변환 소스가 각각 독립 파일이 아닙니다.")
    output_path = Path(args.output)
    json_path = Path(args.json_output)
    write_markdown(audits, output_path, bool(contents))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"audits": audits}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item for item in audits if item["status"] != "정상"]
    print(f"prompt audit written: {output_path}")
    print(f"json audit written: {json_path}")
    print(f"sections={len(audits)} ok={len(audits) - len(failed)} needs_fix={len(failed)}")
    for item in failed:
        print(f"- section {item['index']} {item['id']}: {'; '.join(item['issues'])}")


if __name__ == "__main__":
    main()
