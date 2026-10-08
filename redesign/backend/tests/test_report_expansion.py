import unittest
from unittest.mock import Mock
from kodame_intake.report_expansion import expand_short_section
from report_outline import nominalize_report_sentences


class ReportExpansionTests(unittest.TestCase):
    def test_negative_and_irregular_endings_keep_meaning(self):
        self.assertEqual(nominalize_report_sentences('실패를 의미하지 않는다. 자료가 많다. 기준에 따른다.'),
                         '실패를 의미하지 않음. 자료가 많음. 기준에 따름.')
        self.assertEqual(nominalize_report_sentences('대상국은 캐나다. 평가 자료임.'), '대상국은 캐나다. 평가 자료임.')

    def test_sufficient_narrative_does_not_call_model(self):
        call = Mock()
        text = 'ㅇ 논점\n- ' + '검증된 근거임. ' * 40
        self.assertEqual(expand_short_section('conclusion',text,200,{},call,[]),text)
        call.assert_not_called()

    def test_malformed_summary_is_not_duplicated_into_five_blocks(self):
        call=Mock()
        text='형식이 아직 정해지지 않은 초안'
        self.assertEqual(expand_short_section('summary-ko',text,5200,{},call,[]),text)
        call.assert_not_called()

    def test_expansion_is_bounded_and_uses_few_shots(self):
        call=Mock(return_value={'content':'ㅇ 논점\n- 짧은 응답임.'})
        shots=[{'role':'user','content':'형식 예시'}]
        expand_short_section('conclusion','ㅇ 논점\n- 근거임.',500,{},call,shots)
        self.assertEqual(call.call_count,3)
        self.assertEqual(call.call_args.kwargs['few_shot_messages'],shots)
