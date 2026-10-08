"""Privacy filtering must preserve the cells used to verify performance."""
import pytest

from kodame_intake.ai_gateway import redact_for_external_analysis


@pytest.mark.parametrize('text', [
    '목표치 20 40 60 80 100',
    '연도 2026 2027 2028 2029',
    '학생 수 1000 2000 3000',
    '누적 달성치 50 75 100',
    '기준일 2026-06-30 실적 6명 목표 10명',
])
def test_numeric_cells_are_not_generic_identifiers(text):
    assert redact_for_external_analysis(text) == (text, [])


@pytest.mark.parametrize('text, secret', [
    ('연락처 010 1234 5678', '010 1234 5678'),
    ('주민등록번호 900101 1234567', '900101 1234567'),
    ('계좌번호: 123 456 7890', '123 456 7890'),
    ('Account number: 123 456 7890', '123 456 7890'),
    ('사업자등록번호 123 45 67890', '123 45 67890'),
    ('계좌 123-456-7890', '123-456-7890'),
    ('수신처 person@example.com', 'person@example.com'),
])
def test_identifying_values_still_redacted(text, secret):
    result, flags = redact_for_external_analysis(text)
    assert secret not in result
    assert flags


def test_private_header_does_not_hide_next_table_row():
    text = '계좌번호 123 456 7890\n목표치 20 40 60\n2026 2027 2028'
    result, _ = redact_for_external_analysis(text)
    assert '123 456 7890' not in result
    assert '20 40 60' in result
    assert '2026 2027 2028' in result
