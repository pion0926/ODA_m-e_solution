"""Editable question checks and validated scoring trace; never invent legacy traces."""
from __future__ import annotations

import json
from pathlib import Path

from .report_text import sanitize_report_text

_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config/dac_scoring_checks.json").is_file())
_CONFIG = json.loads((_ROOT / "config/dac_scoring_checks.json").read_text(encoding="utf-8"))
RUBRIC_VERSION = _CONFIG["version"]


def scoring_definition(question: dict) -> dict:
    return {
        "version": RUBRIC_VERSION, "label": _CONFIG["label"], "notice": _CONFIG["notice"],
        "question_id": question["id"], "levels": question["levels"],
        "checks": [{"id": f"{question['id']}-c{index}", "criterion": text}
                   for index, text in enumerate(_CONFIG["questions"][question["id"]], 1)],
    }


def validate_scoring_trace(definition: dict, item: dict, id_by_ref: dict) -> dict:
    score = item.get("score")
    if type(score) is not int or score not in (1, 2, 3, 4):
        raise ValueError("질문 점수는 정수 1~4점이어야 합니다.")
    if item.get("question_id") != definition["id"]:
        raise ValueError("평가 질문 ID 또는 순서가 일치하지 않습니다.")
    trace = item.get("scoring_trace")
    if not isinstance(trace, dict):
        raise ValueError("질문별 scoring_trace 적용 내역이 필요합니다.")
    rule = scoring_definition(definition)
    checks = trace.get("checks")
    if not isinstance(checks, list) or len(checks) != len(rule["checks"]):
        expected_ids = [check["id"] for check in rule["checks"]]
        actual_ids = [check.get("check_id") for check in checks if isinstance(check, dict)] if isinstance(checks, list) else []
        raise ValueError(f"{definition['id']}: checks에 정확히 {len(expected_ids)}개 항목이 필요합니다. 필수 ID={expected_ids}, 받은 ID={actual_ids}. 하나의 예시 항목으로 축약하지 마십시오.")
    cleaned = []
    for expected, actual in zip(rule["checks"], checks):
        if not isinstance(actual, dict) or actual.get("check_id") != expected["id"]:
            raise ValueError("내부 평가 확인 항목 ID가 일치하지 않습니다.")
        state = actual.get("status")
        if state not in {"met", "partial", "not_met", "unverified"}:
            raise ValueError("확인 항목은 충족/일부 충족/미충족/미확인으로 구분해야 합니다.")
        refs = actual.get("evidence_document_refs", [])
        if not isinstance(refs, list) or any(ref not in id_by_ref for ref in refs):
            raise ValueError("확인 항목의 근거 문서 참조가 유효하지 않습니다.")
        explanation = sanitize_report_text(actual.get("finding", ""))
        if len(explanation.strip()) < 12:
            raise ValueError("확인 항목별 구체적인 근거 설명이 필요합니다.")
        if state != "unverified" and not refs:
            raise ValueError("충족 또는 미충족 판단에는 검토한 문서 근거가 필요합니다.")
        cleaned.append({**expected, "status": state, "finding": explanation[:2000],
                        "evidence_document_refs": refs,
                        "evidence_document_ids": list(dict.fromkeys(id_by_ref[ref] for ref in refs))})
    reason = sanitize_report_text(trace.get("selected_level_reason", ""))
    gap = sanitize_report_text(trace.get("next_level_gap", ""))
    if len(reason.strip()) < 20 or len(gap.strip()) < 12:
        raise ValueError("선택 점수 및 상위 점수 경계의 구체적 설명이 필요합니다.")
    uncertain = any(check["status"] == "unverified" for check in cleaned)
    if score == 4 and any(check["status"] != "met" for check in cleaned):
        raise ValueError("4점은 모든 내부 확인 항목 충족과 해당 질문의 4점 요건 증명이 필요합니다.")
    return {**rule, "selected_score": score, "selected_level": definition["levels"][score],
            "selected_level_reason": reason[:3000], "next_level_gap": gap[:2000],
            "status": "provisional" if uncertain else "assessed", "checks": cleaned}
