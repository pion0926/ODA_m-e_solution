"""Prompt and deterministic quality gate for forward-looking PDM advice."""
from pathlib import Path
import re

_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "prompts/performance_risk_policy.md").is_file())
RISK_SYSTEM_PROMPT = (_ROOT / "prompts/performance_risk_policy.md").read_text(encoding="utf-8")
_CALENDAR_DEADLINE = re.compile(r"(?:20\d{2}\s*년|20\d{2}[-./]\d|\d{1,2}\s*월\s*\d{1,2}\s*일)")
_UNFOUNDED = re.compile(r"(?:관리|성과\s*관리|모니터링)(?:가|이|는)?\s*(?:이루어지지\s*않|부재|되지\s*않)|기한이?\s*(?:도과|경과)")


def validate_risk_result(result: dict, candidates: list[dict]) -> None:
    items = result.get("items")
    if not isinstance(items, list) or len(items) != len(candidates):
        raise ValueError("모든 입력 지표의 상세 리스크 항목이 필요합니다.")
    by_id = {item["id"]: item for item in candidates}
    seen = set()
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in by_id or item["id"] in seen:
            raise ValueError("리스크 지표 ID가 누락·중복되거나 유효하지 않습니다.")
        seen.add(item["id"])
        for key in ("risk_title", "risk_analysis", "forecast"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"구체적인 {key} 설명이 필요합니다.")
        for key in ("root_causes", "recommendations", "evidence_needed"):
            values = item.get(key)
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"구체적인 {key} 목록이 필요합니다.")
        for advice in item["recommendations"]:
            if _CALENDAR_DEADLINE.search(advice):
                raise ValueError("권고에는 달력 날짜 대신 검토 착수/자료 확보 후의 상대기한을 사용하십시오.")
        if by_id[item["id"]].get("status") == "unset":
            if _UNFOUNDED.search(item["risk_analysis"]):
                raise ValueError("실적 미확인을 실제 관리 부재나 기한 경과로 단정할 수 없습니다.")
