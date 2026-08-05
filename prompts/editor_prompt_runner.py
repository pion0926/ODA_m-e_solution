from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib import error, request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3.1-flash-lite")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

SAMPLE_REFERENCE_USAGE_PROMPT = """

[좋은 샘플 활용 규칙]
- sample_reference_for_this_section은 사용자가 제공한 잘 작성된 실제 보고서 예시다.
- 샘플의 구조, 항목 분리 방식, 논리 전개, 공적 보고서 문체, 근거 밀도를 우선 참고한다.
- 샘플의 사업명, 고유 사실, 수치, 평가 판단, 문장을 복사하거나 현재 사업 사실처럼 쓰지 않는다.
- 현재 섹션의 자료가 충분하면 샘플 수준의 완성된 본문으로 작성하고, 단순 점수 메모나 표 원문 요약으로 끝내지 않는다.
""".strip()


DETAILED_EVIDENCE_WRITING_PART_IDS = {
    "summary-ko",
    "project-background",
    "eval-purpose",
    "eval-methods",
    "eval-limitations",
    "eval-team",
    "achievement",
    "criteria-relevance",
    "criteria-coherence",
    "criteria-effectiveness",
    "criteria-efficiency",
    "criteria-sustainability",
    "criteria-crosscutting",
    "criteria-other",
    "conclusion",
    "working-factors",
    "nonworking-factors",
    "theory",
    "feedback",
    "lessons",
}


DETAILED_EVIDENCE_WRITING_PROMPT = """

[자료 기반 상세 서술 및 인용 지침]
- 이 파트는 단순 빈칸 채우기가 아니라 최종 보고서 본문이다. reference_corpus.documents, content_inputs.references, content_inputs.criteria, prior_analysis_sections, sample_reference_for_this_section를 먼저 확인한 뒤 자료에 근거해 충분히 상세하게 작성한다.
- 주요 주장마다 가능한 경우 근거 문서명 또는 evidenceName을 문장 안에 자연스럽게 언급한다.
- 직접 인용은 짧게만 사용하고, 대부분은 자료 내용을 해석·종합해 보고서 문체로 재작성한다.
- 자료가 제한적이면 현재 보유 자료에서 확인되는 사실, 합리적 해석, 판단의 한계를 한 문단 안에 함께 설명하고 "추가 정보 필요" 같은 표식을 쓰지 않는다.
""".strip()


def prompt_with_sample_reference_usage(prompt: object) -> str:
    base = str(prompt or "").strip()
    if SAMPLE_REFERENCE_USAGE_PROMPT in base:
        return base
    return (base + "\n\n" + SAMPLE_REFERENCE_USAGE_PROMPT).strip()


def prompt_with_detailed_evidence_usage(prompt: object, part_id: str) -> str:
    base = str(prompt or "").strip()
    if part_id not in DETAILED_EVIDENCE_WRITING_PART_IDS:
        return base
    if "[자료 기반 상세 서술 및 인용 지침]" in base:
        return base
    return (base + "\n\n" + DETAILED_EVIDENCE_WRITING_PROMPT).strip()

PART_ID_BY_SECTION_NUMBER = {
    1: "cover",
    2: "toc",
    3: "notice",
    4: "grade",
    5: "summary-ko",
    6: "project-background",
    7: "project-overview",
    8: "pdm",
    9: "eval-purpose",
    10: "eval-matrix",
    11: "eval-methods",
    12: "eval-limitations",
    13: "eval-team",
    14: "achievement",
    15: "criteria-relevance",
    16: "criteria-coherence",
    17: "criteria-effectiveness",
    18: "criteria-efficiency",
    19: "criteria-sustainability",
    20: "criteria-crosscutting",
    21: "criteria-other",
    22: "conclusion",
    23: "working-factors",
    24: "nonworking-factors",
    25: "theory",
    26: "feedback",
    27: "lessons",
}

EDITOR_SECTION_ID_BY_PART_ID = {
    "cover": "title",
    "summary-ko": "summary",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def openrouter_api_key() -> str:
    if os.getenv("OPENROUTER_API_KEY"):
        return os.getenv("OPENROUTER_API_KEY", "")
    compose_path = ROOT / "docker-compose.yml"
    if not compose_path.exists():
        return ""
    match = re.search(
        r"OPENROUTER_API_KEY:\s*\$\{OPENROUTER_API_KEY:-([^}]+)\}",
        compose_path.read_text(encoding="utf-8"),
    )
    return match.group(1).strip() if match else ""


def project_input() -> dict:
    overview = read_json(ROOT / "data" / "project_overview" / "current.json")
    return {
        "title": overview.get("projectTitle") or "사업명 확인 중",
        "period": overview.get("projectPeriod") or "기간 확인 중",
        "budget": overview.get("projectBudget") or "예산 확인 중",
        "overview_file": overview.get("name") or "",
    }


def current_section_text(section_id: str) -> str:
    state = read_json(ROOT / "data" / "reports" / "report_editor_state.json")
    for section in state.get("sections", []):
        if str(section.get("id")) == section_id:
            return str(section.get("body") or "")
    return ""


def editor_part_config(part_id: str) -> dict:
    backend_dir = ROOT / "backend"
    backend_path = str(backend_dir)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    try:
        from report_prompts import EDITOR_REPORT_PARTS

        return next((part for part in EDITOR_REPORT_PARTS if str(part.get("id")) == part_id), {})
    except Exception:
        return {}


def app_like_reference_context(part_id: str) -> dict:
    backend_dir = ROOT / "backend"
    backend_path = str(backend_dir)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    part = editor_part_config(part_id)
    try:
        from oda_me import runtime as oda_runtime

        context = oda_runtime.current_report_context()
        references = oda_runtime.part_reference_documents(part)
        criteria_ids = set(references.get("criteria") or [])
        return {
            "context": context,
            "reference_plan": {
                "criteria": part.get("referenceCriteria", []),
                "evidence": part.get("referenceEvidence", {}),
                "notes": part.get("referenceNotes", []),
            },
            "content_inputs": {
                "project": context.get("project") or project_input(),
                "criteria": [
                    item for item in context.get("criteria", [])
                    if item.get("id") in criteria_ids
                ],
                "references": references,
            },
            "reference_corpus": oda_runtime.build_full_reference_corpus(part),
            "sample_reference_for_this_section": oda_runtime.sample_reference_for_editor_part(part),
        }
    except Exception as exc:
        return {
            "context": {"project": project_input()},
            "reference_plan": {
                "criteria": part.get("referenceCriteria", []),
                "evidence": part.get("referenceEvidence", {}),
                "notes": part.get("referenceNotes", []),
            },
            "content_inputs": {
                "project": project_input(),
                "reference_load_error": str(exc),
            },
            "reference_corpus": {"enabled": False, "reason": str(exc)},
            "sample_reference_for_this_section": "",
        }


def prompt_file_manifest(script_file: str | Path) -> tuple[Path, dict]:
    script_path = Path(script_file).resolve()
    manifest_path = ROOT / "hwpx_sections" / script_path.stem / "manifest.json"
    return manifest_path, read_json(manifest_path)


def build_prompt_input(script_file: str | Path, editor_prompt: str) -> dict:
    manifest_path, manifest = prompt_file_manifest(script_file)
    section_number_match = re.match(r"Section(\d+)_", Path(script_file).name)
    section_number = int(section_number_match.group(1)) if section_number_match else 0
    part_id = PART_ID_BY_SECTION_NUMBER.get(section_number) or str(manifest.get("section_id") or Path(script_file).stem)
    editor_section_id = EDITOR_SECTION_ID_BY_PART_ID.get(part_id, str(manifest.get("section_id") or part_id))
    reference_context = app_like_reference_context(part_id)
    project = (reference_context.get("context") or {}).get("project") or project_input()
    writing_prompt = prompt_with_detailed_evidence_usage(
        prompt_with_sample_reference_usage(editor_prompt),
        part_id,
    )
    content_request = {
        "report_context": {
            "report_type": "KOICA 5-1 종료평가 결과보고서",
            "project": project,
            "draft_date": datetime.now().strftime("%Y. %m"),
        },
        "section_to_write": {
            "part_id": part_id,
            "section_id": editor_section_id,
            "section_name": manifest.get("section_name") or Path(script_file).stem,
            "writing_prompt": writing_prompt,
        },
        "reference_plan": reference_context.get("reference_plan", {}),
        "previous_text": current_section_text(editor_section_id),
        "user_request": "기본 생성 요청: 현재 섹션의 기존 텍스트와 참고자료를 바탕으로 제출 가능한 초안을 작성한다.",
        "content_inputs": reference_context.get("content_inputs") or {"project": project},
        "reference_corpus": reference_context.get("reference_corpus", {}),
        "sample_reference_for_this_section": reference_context.get("sample_reference_for_this_section") or "",
        "response_requirements": "반환값은 이 섹션에 들어갈 최종 텍스트만 작성한다. 설명, markdown fence, 파일 경로, XML 정보는 쓰지 않는다.",
    }
    messages = [
        {
            "role": "system",
            "content": (
                "너는 KOICA 종료평가 결과보고서의 선택 섹션을 작성하는 보고서 편집자다. "
                "문서 파일 경로나 XML 구조가 아니라, 기존 텍스트와 참고자료를 근거로 최종 섹션 내용을 작성한다. "
                "sample_reference_for_this_section은 좋은 샘플의 구조와 문체를 참고하기 위한 자료이며 문장과 고유 사실은 복사하지 않는다."
            ),
        },
        {"role": "user", "content": json.dumps(content_request, ensure_ascii=False)},
    ]
    return {
        "model": MODEL,
        "routing_metadata": {
            "prompt_file": str(Path(script_file).resolve().relative_to(ROOT)),
            "manifest_path": str(manifest_path.relative_to(ROOT)) if manifest_path.exists() else "",
            "section_id": part_id,
            "editor_section_id": editor_section_id,
            "hwpx_path": manifest.get("hwpx_path", ""),
        },
        "section_prompt": writing_prompt,
        "input": content_request,
        "output_format": "final_section_text",
        "messages": messages,
        "temperature": 0.2,
    }


def model_request_payload(payload: dict) -> dict:
    return {
        "model": payload["model"],
        "messages": payload["messages"],
        "temperature": payload["temperature"],
    }


def prompt_debug_payload(payload: dict) -> dict:
    return {
        "model": payload["model"],
        "routing_metadata": payload["routing_metadata"],
        "section_prompt": payload["section_prompt"],
        "input": payload["input"],
        "output_format": payload["output_format"],
        "temperature": payload["temperature"],
    }


def request_model(payload: dict) -> dict:
    api_key = openrouter_api_key()
    if not api_key:
        return {"ok": False, "error": "OPENROUTER_API_KEY is not configured"}
    req = request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(model_request_payload(payload), ensure_ascii=False).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://127.0.0.1:8001",
            "X-Title": "ODA ImpactOps Section Prompt Check",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {
            "ok": True,
            "content": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
            "raw": data,
        }
    except error.URLError as exc:
        return {"ok": False, "error": str(exc)}


def main(build_prompt_input_func, request_model_func=request_model) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-model", action="store_true")
    args = parser.parse_args()
    payload = build_prompt_input_func()
    print("=== PROMPT DEBUG (ROUTING METADATA IS NOT SENT AS PROMPT) ===")
    print(json.dumps(prompt_debug_payload(payload), ensure_ascii=False, indent=2))
    print("\n=== ACTUAL LLM REQUEST PAYLOAD ===")
    print(json.dumps(model_request_payload(payload), ensure_ascii=False, indent=2))
    if args.no_model:
        return
    print("\n=== MODEL OUTPUT ===")
    print(json.dumps(request_model_func(payload), ensure_ascii=False, indent=2))
