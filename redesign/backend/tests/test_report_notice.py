from kodame_intake.report_generator import _deterministic_safe_section, _validate_reader_content


def test_default_notice_is_readable_and_does_not_claim_external_review():
    content = _deterministic_safe_section('notice', {}, {})
    assert len(content) >= 250
    assert '문헌기반 평가 초안' in content
    assert '확인된 성과의 점수와 증빙 신뢰도를 구분함' in content
    assert '근거가 부족하거나 상충하는 평가 질문은 판정보류' not in content
    assert 'schema' not in content and 'slots' not in content
    assert not _validate_reader_content('notice', content, '우즈베키스탄', {})


def test_legacy_notice_json_is_blocked_before_export():
    content = '{"schema":"section3 notice slots v1","slots":{"country name":"우즈베키스탄"}}'
    assert any('JSON' in issue for issue in _validate_reader_content('notice', content, '우즈베키스탄', {}))
