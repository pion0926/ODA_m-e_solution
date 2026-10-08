from report_writing_policy import report_writing_policy_issues


def test_multicell_indicator_record_is_not_one_narrative_paragraph():
    record='- [outputs-1-1-1]: 성과지표: 인증 교원 수 / 목표치: 확인 필요 / 비고: '+('인증 자료의 대상과 기간을 구분함. '*50)
    assert not any('시각 예산' in issue for issue in report_writing_policy_issues(record))


def test_actual_long_narrative_still_requires_meaningful_paragraphs():
    paragraph='- (자료 한계) '+('인증 자료의 대상과 기간을 구분함. '*50)
    assert any('시각 예산' in issue for issue in report_writing_policy_issues(paragraph))


def test_fake_record_prefix_does_not_bypass_prose_validation():
    paragraph='- [메모] '+('긴 설명을 반복함. '*80)
    assert any('시각 예산' in issue for issue in report_writing_policy_issues(paragraph))
