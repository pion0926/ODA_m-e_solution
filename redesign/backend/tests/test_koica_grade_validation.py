import unittest
from kodame_intake.evaluation_criteria import grade, KOICA_GRADES
from kodame_intake.report_generator import _validate_reader_content, _ensure_official_grade_statement


class KoicaGradeValidationTests(unittest.TestCase):
    def issues(self, content, part='conclusion'):
        return _validate_reader_content(part,content,'우즈베키스탄',{'commissioning_agency':'교육부'})

    def test_all_six_grade_labels_pass_in_conclusion_and_grade(self):
        for part in ('conclusion','grade'):
            for label in KOICA_GRADES:
                for name in ('KOICA','코이카'):
                    with self.subTest(part=part,label=label,name=name):
                        self.assertFalse(any('KOICA·코이카' in i for i in self.issues(f'{name} 등급 {label}, 국무조정실 등급 참고임.',part)))

    def test_boundaries_match_guide(self):
        for score,expected in ((20,'A'),(18,'A'),(17.9,'B'),(16,'B'),(15.9,'C'),(14,'C'),
                               (13.9,'D'),(12,'D'),(11.9,'E'),(10,'E'),(10.5,'E'),(9.9,'F')):
            self.assertEqual(grade(score)[0],expected)

    def test_invalid_labels_and_unsubstantiated_institution_claims_remain_blocked(self):
        for content in ('KOICA 등급 G','KOICA 등급 EF','KOICA 등급 E+',
                        'KOICA 등급 E, KOICA가 사업을 지원함.', 'KOICA가 사업을 수행함.'):
            with self.subTest(content=content):
                self.assertTrue(any('KOICA·코이카' in i for i in self.issues(content)))

    def test_server_generated_e_and_f_statements_do_not_fail_its_validator(self):
        for score,label in ((2.1,'E'),(1.5,'F')):
            evaluations=[{'criterion_id':key,'score':score} for key in
                         ('relevance','coherence','effectiveness','efficiency','sustainability')]
            content=_ensure_official_grade_statement('conclusion','근거에 따른 종합판단임.',evaluations)
            self.assertIn('KOICA 등급 '+label,content)
            self.assertFalse(any('KOICA·코이카' in i for i in self.issues(content)))
