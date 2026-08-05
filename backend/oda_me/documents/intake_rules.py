from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = ROOT / "data" / "document_intake_rules.json"

DEFAULT_RULES = {
    "version": 1,
    "updatedBy": "system",
    "metadataFields": [
        {"key": "documentType", "label": "자료 유형", "description": "보고서, 조사자료, 회의록, 행정자료, 계약·계획서 등", "required": True, "examples": "기초선 조사, 월간 모니터링 보고서"},
        {"key": "title", "label": "자료명", "description": "문서 표지 또는 본문에서 확인되는 공식 명칭", "required": True, "examples": "파푸아 모자보건 기초선 조사보고서"},
        {"key": "period", "label": "대상 기간", "description": "자료가 설명하는 기준일 또는 시작·종료 기간", "required": False, "examples": "2025-01~2025-03"},
        {"key": "region", "label": "지역", "description": "파푸아 7개 사업지역 또는 전체", "required": False, "examples": "Jayapura, Biak Numfor, 전체"},
        {"key": "organization", "label": "생산·책임기관", "description": "자료를 생산하거나 승인한 기관", "required": False, "examples": "UNICEF, 지방보건국"},
        {"key": "dataLevel", "label": "자료 수준", "description": "개인·시설·지역·사업 전체 등 집계 수준", "required": False, "examples": "보건시설, 군/시, 사업 전체"},
        {"key": "disaggregation", "label": "분리 기준", "description": "성별, 연령, 지역, 취약집단 등 포함된 분리 통계", "required": False, "examples": "성별·연령·지역"},
        {"key": "indicators", "label": "관련 지표", "description": "문서에서 측정하거나 언급한 성과지표", "required": False, "examples": "시설분만율, 산전관리 4회 이상"},
        {"key": "summary", "label": "핵심 내용", "description": "평가자가 빠르게 검토할 수 있는 사실 중심 요약", "required": True, "examples": "3~5문장"},
        {"key": "qualityFlags", "label": "품질 주의사항", "description": "결측, 중복, 불일치, 출처·산식 부재 등", "required": False, "examples": "지역 코드 12건 누락"},
        {"key": "language", "label": "언어", "description": "문서의 주 사용 언어", "required": False, "examples": "한국어, 영어, 인도네시아어"},
        {"key": "confidentiality", "label": "민감도", "description": "개인정보·민감정보 포함 가능성", "required": False, "examples": "일반, 내부, 개인정보 포함"},
    ],
    "allocationPolicy": {
        "autoAssignThreshold": 0.82,
        "reviewThreshold": 0.45,
        "minimumMargin": 0.12,
        "llmRequired": True,
        "allowMultipleSlots": True,
        "maxSlots": 4,
        "instructions": "자료의 실제 내용과 평가 활용 목적을 우선한다. 파일명만으로 확정하지 않으며, 여러 DAC 기준의 근거가 되면 복수 슬롯을 제안한다. 근거가 약하거나 상위 후보 간 점수 차가 작으면 반드시 전문가 확인으로 보낸다."
    },
    "slotRules": [],
}


def rules_with_slots(candidates: list[dict]) -> dict:
    config = load_rules()
    saved = {(item.get("criterionId"), item.get("evidenceName")): item for item in config.get("slotRules", [])}
    slot_rules = []
    for candidate in candidates:
        key = (candidate.get("criterionId"), candidate.get("evidenceName"))
        current = saved.get(key, {})
        slot_rules.append({
            "criterionId": candidate.get("criterionId"),
            "criterionName": candidate.get("criterionName"),
            "evidenceName": candidate.get("evidenceName"),
            "category": candidate.get("category", ""),
            "enabled": current.get("enabled", True),
            "priority": current.get("priority", 3),
            "assignmentGuidance": current.get("assignmentGuidance") or f"문서의 핵심 내용과 평가 활용 목적이 '{candidate.get('evidenceName', '')}'에 해당하고, {candidate.get('category', '해당 증빙 범주')}의 판단 근거로 직접 사용할 수 있을 때 배정한다.",
            "rejectionGuidance": current.get("rejectionGuidance") or "단순 언급, 참고문헌 수록, 유사 사업의 외부 사례처럼 현재 사업의 직접 증빙이 아닌 경우에는 배정하지 않는다.",
            "examples": current.get("examples", []),
            "expertNote": current.get("expertNote", ""),
        })
    config["slotRules"] = slot_rules
    return config


def load_rules() -> dict:
    if not RULES_PATH.exists():
        return deepcopy(DEFAULT_RULES)
    try:
        saved = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return deepcopy(DEFAULT_RULES)
    merged = deepcopy(DEFAULT_RULES)
    merged.update(saved if isinstance(saved, dict) else {})
    merged["allocationPolicy"] = {**DEFAULT_RULES["allocationPolicy"], **merged.get("allocationPolicy", {})}
    return merged


def validate_and_save_rules(payload: dict, candidates: list[dict]) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("규칙 설정은 JSON 객체여야 합니다.")
    fields = payload.get("metadataFields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("분석 메타데이터 항목을 한 개 이상 설정하세요.")
    keys = [str(item.get("key", "")).strip() for item in fields if isinstance(item, dict)]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("메타데이터 key는 비어 있거나 중복될 수 없습니다.")
    valid_slots = {(item["criterionId"], item["evidenceName"]) for item in candidates}
    cleaned_rules = []
    for item in payload.get("slotRules", []):
        if not isinstance(item, dict) or (item.get("criterionId"), item.get("evidenceName")) not in valid_slots:
            continue
        cleaned_rules.append({**item, "priority": max(1, min(5, int(item.get("priority", 3) or 3)))})
    saved = rules_with_slots(candidates)
    saved.update(payload)
    saved["slotRules"] = cleaned_rules
    saved["version"] = int(saved.get("version", 0) or 0) + 1
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return rules_with_slots(candidates)
