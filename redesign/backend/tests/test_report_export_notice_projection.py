"""Reader projection must preserve a single fixed assessment disclaimer."""
import pytest

from kodame_intake.report_evaluation_context import PROVISIONAL_NOTICE, qualify_report_text
from kodame_intake.report_exporter import _project_reader_text


EVALUATIONS = [{'criterion_id': 'coherence', 'score': 3,
                'assessment_basis': 'provisional_document_review'}]


@pytest.mark.parametrize('part', ['summary-ko', 'criteria-coherence', 'conclusion'])
@pytest.mark.parametrize('donor', ['교육부', 'KOICA'])
def test_saved_notice_survives_export_once_without_changing_scores(part, donor):
    saved = '일관성은 3점으로 평가함. 확인된 교육 6회와 계약금액 71,000,000원을 검토함.\n- ' + PROVISIONAL_NOTICE
    exported = qualify_report_text(part, _project_reader_text(saved, donor), EVALUATIONS)
    assert exported == saved
    assert exported.count(PROVISIONAL_NOTICE) == 1
    assert '지원기관·국무조정실의 공식 확정평가' not in exported
    assert qualify_report_text(part, _project_reader_text(exported, donor), EVALUATIONS) == exported
    assert saved.endswith(PROVISIONAL_NOTICE)


def test_export_adds_missing_notice_once_and_retains_real_grade_labels():
    saved = 'KOICA 등급 D, KOICA 평가등급 D는 참고 환산등급임. KOICA의 사업 지원을 검토함.'
    projected = _project_reader_text(saved, '교육부')
    assert projected == 'KOICA 등급 D, KOICA 평가등급 D는 참고 환산등급임. 지원기관의 사업 지원을 검토함.'
    result = qualify_report_text('conclusion', projected, EVALUATIONS)
    assert result.count(PROVISIONAL_NOTICE) == 1
    assert qualify_report_text('conclusion', _project_reader_text(result, '교육부'), EVALUATIONS) == result
    assert '__' not in result
    assert saved.endswith('KOICA의 사업 지원을 검토함.')


def test_similar_disclaimer_does_not_protect_a_false_institution_claim():
    altered = PROVISIONAL_NOTICE.replace('공식 확정평가를 의미하지 않음', '공식 확정평가를 의미함')
    saved = altered + '\nKOICA의 공식 승인으로 4점 확정.'
    projected = _project_reader_text(saved, '교육부')
    assert 'KOICA' not in projected
    assert '지원기관·국무조정실의 공식 확정평가를 의미함' in projected
    assert '지원기관의 공식 승인으로 4점 확정.' in projected


def test_unrelated_text_and_literal_marker_like_text_are_not_replaced_as_tokens():
    saved = '__ODAME_ASSESSMENT_NOTICE__ / 2027년 목표 8회, 현재 실적 6회.'
    assert _project_reader_text(saved, '교육부') == saved
