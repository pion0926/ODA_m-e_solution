"""Technical diagnostics stay in saved data; report grade cells keep meaning."""
import pytest

from backend.oda_me.hwpx.grade_reasons import (
    readable_grade_reason, READER_MEASUREMENT_LIMITATION,
)
from backend.oda_me.hwpx.patchers import (
    grade_question_reason, normalize_hwpx_manifest_value,
)


@pytest.mark.parametrize('formal',[False,True])
def test_known_repeated_numeric_diagnostics_become_one_reader_limitation(formal):
    lead='일부 정량 비교 수치가 원문 검증을 통과하지 못해 해당 항목을 미확인으로 처리했습니다'
    hold='정량 비교 수치를 지정된 원문에서 검증하지 못해 이 항목의 판정을 '
    hold+='보류합니다.' if formal else '보류함'
    diagnostic='없습니다.' if formal else '없음'
    block=lead+('. ' if formal else ' ')+hold+' '+ ' '.join(
        f'측정값 {value}를 지정한 원문에서 확인할 수 {diagnostic}'
        for value in ('71000000','26000000','1.4e8','-2.5','80,000'))
    before='확인된 계약금액 71,000,000원과 실적 6회는 별도 기록임. '
    after=' 납품기간 2024년 3월~8월의 조기 검수를 확인했으나 전체 비교에는 한계가 있음.'
    saved=before+block+after
    expected=before+READER_MEASUREMENT_LIMITATION+' '+after.lstrip()
    assert readable_grade_reason(saved)==expected
    assert normalize_hwpx_manifest_value(4,'efficiency_timeliness_reason',saved)==expected
    assert grade_question_reason(saved,10000)==expected
    assert grade_question_reason(saved,90)==expected
    assert saved==before+block+after
    assert readable_grade_reason(expected)==expected
    assert '일부 정량 비교는 원문 근거가 충분히 확인되지 않아 계산에서 제외함.' in expected
    assert '판정을 보류' not in expected


@pytest.mark.parametrize('text',[
    '측정값 71000000를 지정한 원문에서 확인할 수 없습니다. 실제 지출은 500원임.',
    '정량 비교 수치를 지정된 원문에서 검증하지 못해 이 항목의 판정을 보류함 알 수 없는 공급자 진단 42.',
    '정량 비교 수치를 지정된 원문에서 검증하지 못해 이 항목의 판정을 보류함 측정값 미상을 지정한 원문에서 확인할 수 없음',
    '정량 실적 6회와 2026년 목표 4회를 확인함. 예산은 71,000,000원임.',
    '  정량 실적 6회 확인함.  ',
    '미확인 취업률은 판정을 보류함. 별도 질문에서 확인된 산출은 2점으로 평가함.',
])
def test_unknown_diagnostics_and_legitimate_numbers_are_preserved(text):
    assert readable_grade_reason(text)==text


def test_projection_is_scoped_to_grade_question_reason_slots():
    raw='정량 비교 수치를 지정된 원문에서 검증하지 못해 이 항목의 판정을 보류합니다. 측정값 71000000를 지정한 원문에서 확인할 수 없습니다.'
    assert normalize_hwpx_manifest_value(4,'efficiency_timeliness_reason',raw)==READER_MEASUREMENT_LIMITATION
    assert normalize_hwpx_manifest_value(18,'criteria_efficiency_body',raw)==raw
    assert normalize_hwpx_manifest_value(4,'efficiency_total_score',raw)==raw


def test_existing_saved_reader_prefix_is_upgraded_without_regenerating_draft():
    old = '정량 비교 근거가 충분히 확인되지 않아 해당 항목의 판정을 보류함.'
    facts = ' 교육은 6회 완료됨. 계약금액 71,000,000원, 기한 2027년 3월보다 11일 빠른 검수를 확인함.'
    saved = old + facts
    expected = READER_MEASUREMENT_LIMITATION + facts
    assert readable_grade_reason(saved) == expected
    assert normalize_hwpx_manifest_value(4, 'efficiency_timeliness_reason', saved) == expected
    assert grade_question_reason(saved, 90) == expected
    assert readable_grade_reason(expected) == expected
    assert saved == old + facts
    assert normalize_hwpx_manifest_value(4, 'efficiency_total_score', saved) == saved
    assert normalize_hwpx_manifest_value(18, 'criteria_efficiency_body', saved) == saved
    assert readable_grade_reason('원문 인용: "' + saved + '"') == '원문 인용: "' + saved + '"'
