"""The server's assessment disclaimer must not become a false donor claim."""
import pytest

from kodame_intake.report_evaluation_context import (
    PROVISIONAL_BASIS, PROVISIONAL_NOTICE, qualify_report_text,
)
from kodame_intake.report_generator import _validate_reader_content


SCOPE = {"commissioning_agency": "교육부", "project_status": "completed"}


def institution_issues(part_id, content):
    return [issue for issue in _validate_reader_content(part_id, content, "합성국", SCOPE)
            if "KOICA·코이카 정보" in issue]


@pytest.mark.parametrize("part_id", [
    "criteria-relevance", "criteria-coherence", "criteria-effectiveness",
    "criteria-efficiency", "criteria-sustainability", "summary-ko", "conclusion",
])
def test_server_notice_is_preserved_but_is_not_a_commissioning_claim(part_id):
    content = qualify_report_text(part_id, "- 현재 등록 자료에서 확인한 잠정 판단임.",
                                  [{"assessment_basis": PROVISIONAL_BASIS}])
    assert PROVISIONAL_NOTICE in content
    assert institution_issues(part_id, content) == []
    assert PROVISIONAL_NOTICE in content  # Validation never mutates export input.


@pytest.mark.parametrize("claim", [
    "KOICA가 이 사업의 소관기관임.",
    "코이카가 사업을 지원하고 인력을 파견하였음.",
    "KOICA 정책과 운영체계를 적용하였음.",
])
def test_real_institution_claim_remains_blocked_next_to_the_exact_notice(claim):
    assert institution_issues("criteria-relevance", f"- {claim}\n\n- {PROVISIONAL_NOTICE}")


@pytest.mark.parametrize("claim", [
    "현재 등록 자료의 내부 잠정 진단이며 KOICA 공식 평가를 의미하지 않음.",
    "KOICA가 이 사업을 지원했다는 공식 확정평가를 의미하지 않음.",
    "현재 등록 자료 기준의 내부 잠정 진단이며, KOICA·국무조정실의 공식 확정평가를 의미하지 않음.",
    PROVISIONAL_NOTICE.replace("공식 확정평가를 의미하지 않음", "사업 소관기관임"),
])
def test_generic_or_altered_disclaimer_is_not_a_factual_validation_bypass(claim):
    assert institution_issues("criteria-relevance", "- " + claim)
