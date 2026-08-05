from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from oda_me.core import CRITERIA  # noqa: E402
from oda_me.documents.evidence_store import attach_uploaded_documents  # noqa: E402
from oda_me.evaluations.engine import (  # noqa: E402
    fallback_generic_evaluation,
    structured_evaluation_from_llm,
)
from oda_me.utils.common import find_criterion  # noqa: E402
from oda_me.documents.evidence_store import intake_rules_payload  # noqa: E402
from oda_me.reports.section_settings import section_settings_payload  # noqa: E402


def assert_clean_criteria() -> None:
    criteria = [item for item in CRITERIA if item.get("id") != "impact"]
    assert len(criteria) == 5, f"expected 5 scored DAC criteria, got {len(criteria)}"
    for criterion in criteria:
        assert criterion.get("name"), f"{criterion.get('id')} has no name"
        assert "?" not in criterion["name"], f"mojibake in criterion name: {criterion['name']}"
        assert criterion.get("scoringRubric"), f"{criterion['id']} has no scoring rubric"
        assert criterion.get("evidence"), f"{criterion['id']} has no required evidence"


def assert_structured_llm_parse() -> None:
    criterion = find_criterion("effectiveness")
    assert criterion
    assessments = [
        {
            "questionId": f"q{index + 1}",
            "question": rubric["question"],
            "score": 2,
            "finding": "성과 변화는 일부 확인되나 시점별 비교 근거가 부족함.",
            "evidenceUsed": ["성과지표 실적표"],
            "evidenceGaps": ["기초선·종료선 비교자료"],
            "actionItems": ["지역별 분리 통계를 추가 수집"],
        }
        for index, rubric in enumerate(criterion["scoringRubric"])
    ]
    response = {
        "score": 2,
        "summary": "성과는 일부 확인되나 핵심 증빙 보완이 필요함.",
        "questionAssessments": assessments,
        "improvementNeeds": ["기초선·종료선 비교자료 보완"],
        "scoreReason": "질문별 평가와 증빙공백을 고려하여 2점으로 산정함.",
    }
    parsed = structured_evaluation_from_llm(
        "effectiveness", None, {"ok": True, "content": json.dumps(response, ensure_ascii=False)}
    )
    assert parsed and parsed["score"] == 2
    assert len(parsed["sections"]) == len(criterion["scoringRubric"])
    assert parsed["improvementNeeds"]


def assert_fallback_is_actionable() -> None:
    result = fallback_generic_evaluation("efficiency")
    assert result["status"] == "fallback"
    assert result["sections"], "fallback should build question sections"
    assert result.get("improvementNeeds"), "fallback should expose improvement actions"


def assert_document_intake_rules() -> None:
    rules = intake_rules_payload()
    assert len(rules["metadataFields"]) >= 10, "document metadata schema is incomplete"
    assert rules["slotRules"], "slot allocation rules should be generated from evidence slots"
    first = rules["slotRules"][0]
    assert first.get("assignmentGuidance"), "each slot needs semantic assignment guidance"
    assert first.get("rejectionGuidance"), "each slot needs semantic rejection guidance"
    assert "includeKeywords" not in first and "excludeKeywords" not in first, "keyword rules must not drive allocation"


def assert_report_section_settings() -> None:
    payload = section_settings_payload()
    assert len(payload["editorParts"]) == 27, "all 27 report sections must be configurable"
    for part in payload["editorParts"]:
        assert part.get("id") and part.get("title")
        assert "prompt" in part and "description" in part
        assert isinstance(part.get("customReferenceDocumentIds", []), list)


def main() -> None:
    attach_uploaded_documents()
    assert_clean_criteria()
    assert_structured_llm_parse()
    assert_fallback_is_actionable()
    assert_document_intake_rules()
    assert_report_section_settings()
    print("evaluation quality checks passed")


if __name__ == "__main__":
    main()
