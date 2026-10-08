import unittest
from report_outline import format_narrative_detail, canonical_narrative_outline_text, narrative_outline_issues


class OptionalDetailLabelTests(unittest.TestCase):
    def test_long_authored_label_does_not_get_parent_fallback(self):
        value = '(실제 응급 현장 적용 효과 검증) 교육 이후 현장 적용 효과를 추가 검증할 필요가 있음.'
        self.assertEqual(format_narrative_detail(value, '지역사회 확산 및 지속가능성 제고 요인', 2), value)

    def test_legacy_stacked_label_is_repaired_without_body_loss(self):
        body = '교육 이후 현장 적용 효과를 추가 검증할 필요가 있음.'
        self.assertEqual(format_narrative_detail('(운영 자립) (실제 응급 현장 적용 효과 검증) ' + body), '(실제 응급 현장 적용 효과 검증) ' + body)

    def test_unlabelled_paragraph_remains_unlabelled(self):
        body = '운영체계의 추가 검증이 필요함.'
        self.assertEqual(format_narrative_detail(body, '지속가능성', 2), body)

    def test_other_legacy_automatic_prefixes_do_not_survive_stacked_labels(self):
        for outer, inner in [('포용적 설계', '인구통계학적 특성 분리 통계 보완'), ('역할 분담', '재정 자립 예산 집행 증빙 강화')]:
            self.assertEqual(format_narrative_detail(f'({outer}) ({inner}) 검증이 필요함.'), f'({inner}) 검증이 필요함.')

    def test_duplicate_optional_label_is_omitted_not_invented(self):
        self.assertEqual(format_narrative_detail('(교육 운영) 설명을 보완함.', used_labels=['교육 운영']), '설명을 보완함.')

    def test_acronym_and_numeric_parentheses_are_not_headings(self):
        for text in ('(교육기관) (ASMI) 현황을 설명함.', '(예산) (2026년 기준) 계획을 설명함.'):
            self.assertEqual(format_narrative_detail(text), text)

    def test_normalization_is_idempotent(self):
        raw = 'ㅇ 지속가능성\n- **(운영 자립)** (실제 응급 현장 적용 효과 검증) 검증이 필요함.\n- 본문을 보존함.'
        first = canonical_narrative_outline_text('working-factors', raw)
        self.assertEqual(first, canonical_narrative_outline_text('working-factors', first))
        self.assertNotIn('운영 자립', first)
        self.assertFalse(narrative_outline_issues('working-factors', first))

    def test_prompt_has_format_only_examples(self):
        import runpy
        from pathlib import Path
        import sys
        folder = Path(__file__).resolve().parents[3] / 'prompts'
        sys.path.insert(0, str(folder))
        try:
            prompt = runpy.run_path(str(folder / 'Section23_작동요인.py'))['EDITOR_PROMPT']
        finally:
            sys.path.pop(0)
        self.assertIn('Few-shot', prompt)
        self.assertIn('최대', __import__('report_writing_policy').report_writing_policy_prompt())
        self.assertIn('괄호 뒤 괄호 구조를 금지', prompt)


if __name__ == '__main__':
    unittest.main()
