import copy
import unittest

from kodame_intake.dac_tables import paired_rows
from kodame_intake.dac_evidence import _quote_matches
from kodame_intake.dac_assessor import template, validate
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA


class DacTableTests(unittest.TestCase):
    def test_explicit_columns_preserve_each_numeric_row_and_reset_on_new_sheet(self):
        text='''[시트: 실적]
A1=성과지표 | B1=목표 | C1=실적 | D1=목표대비실적(%)
A2=교육 | B2=연 6회 | C2=29회 | D2=483.3
A3=졸업 | B3=8명 | C3=-
A4=평가 | B4=80~90점 | C4=97점
[시트: 다른 표]
A2=교육 | B2=6회 | C2=29회'''
        rows=paired_rows(text)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['target'],rows[0]['actual']),(6,29))
        self.assertTrue(_quote_matches(rows[0]['quote'],text))

    def test_activity_and_survey_counts_are_not_outcome_measurements(self):
        rows=paired_rows('''[시트: 성과]
A1=성과지표 | B1=목표 | C1=실적
A2=만족도 조사 80점 이상 | B2=5회 | C2=3회
A3=도입 완료된 기자재 | B3=87건 | C3=188건
A4=취업률 | B4=70% | C4=80%''')
        self.assertEqual([r['measurement_level'] for r in rows],['activity_output','activity_output','requires_review'])

    def test_output_rows_cannot_inflate_outcome_score(self):
        criterion,raw,evidence=self.fixture()
        criterion['questions']=EVALUATION_CRITERIA['effectiveness']['questions'][1:2]
        raw=template(criterion)
        evidence['E1'].update(question_id='effectiveness-q2',measurement_level='activity_output',status_text='완료')
        q=raw['question_assessments'][0]
        q['finding']='교육 횟수가 목표를 초과하여 사업의 성과가 달성된 것으로 판단했습니다.'
        q['table_row_reviews']=[{'evidence_id':'E1','decision':'included','reason':'교육 시행 횟수가 목표를 초과하므로 성과로 반영합니다.'}]
        result=validate(criterion,raw,evidence,{'status':'unavailable','model':{}})['question_assessments'][0]
        self.assertEqual(result['table_row_reviews'][0]['decision'],'excluded')
        self.assertEqual(result['scoring_trace']['checks'][0]['state'],'unverified')
        self.assertEqual(result['scoring_trace']['checks'][0]['measurements'],[])
        self.assertIn('계산하지 않고',result['finding'])

    def fixture(self):
        criterion=copy.deepcopy(EVALUATION_CRITERIA['effectiveness'])
        criterion['questions']=criterion['questions'][:1]
        raw=template(criterion)
        q=raw['question_assessments'][0]
        q['finding']='현재 시점 확인된 비교 자료가 부족하여 성과를 확정할 수 없습니다.'
        source={'question_id':'effectiveness-q1','document_id':'d1','document_ref':'D001',
            'source_sha256':'sha','file_name':'성과.xlsx','quote':'목표 6회 실적 29회',
            'metric':'교육','target':6,'actual':29,'table_row_candidate':True,'locator':{'row':'2'}}
        return criterion,raw,{'E1':source}

    def test_candidate_cannot_be_silently_omitted_and_exclusion_is_visible(self):
        criterion,raw,evidence=self.fixture()
        pdm={'status':'unavailable','model':{}}
        with self.assertRaisesRegex(ValueError,'모든 후보 행'):
            validate(criterion,raw,evidence,pdm)
        q=raw['question_assessments'][0]
        q['table_row_reviews']=[{'evidence_id':'E1','decision':'excluded','reason':'최종 성과가 아닌 별도 활동 횟수이므로 제외합니다.'}]
        q['positive_evidence']=['E1','원문에 없는 허위 성과 999건']
        result=validate(criterion,raw,evidence,pdm)['question_assessments'][0]
        self.assertEqual(result['table_row_reviews'][0]['row'],'2')
        self.assertEqual(result['positive_evidence'],[])
        q['table_row_reviews'][0]['decision']='included'
        with self.assertRaisesRegex(ValueError,'단위·기간'):
            validate(criterion,raw,evidence,pdm)

    def test_included_row_cannot_change_source_values(self):
        criterion,raw,evidence=self.fixture()
        q=raw['question_assessments'][0]
        q['table_row_reviews']=[{'evidence_id':'E1','decision':'included','reason':'교육 산출물 실적을 원문과 비교하기 위해 포함합니다.',
            'unit':'회','period':'2026년','population':'교육 대상자','direction':'higher','comparable':True,'due':True}]
        q['indicators'][0]['measurements']=[{'table_row_id':'E1','target':6,'actual':99,
            'target_evidence_ids':['E1'],'actual_evidence_ids':['E1']}]
        result=validate(criterion,raw,evidence,{'status':'unavailable','model':{}})['question_assessments'][0]
        measurement=result['scoring_trace']['checks'][0]['measurements'][0]
        self.assertEqual((measurement['target'],measurement['actual']),(6,29))
        self.assertFalse(measurement['due'])
        self.assertIsNone(measurement['ratio'])
        self.assertEqual(len(result['scoring_trace']['checks'][0]['measurements']),1)
        for status,due in [('미완료',False),('완료 예정',False),('진행 중(9월 완료 예정)',False),('완료(9월 추가 추진 예정)',True)]:
            evidence['E1']['status_text']=status
            again=validate(criterion,raw,evidence,{'status':'unavailable','model':{}})['question_assessments'][0]
            self.assertEqual(again['scoring_trace']['checks'][0]['measurements'][0]['due'],due)

    def test_original_quote_and_generated_row_cannot_double_count_the_same_measurement(self):
        criterion,raw,evidence=self.fixture()
        evidence['E2']={**evidence['E1'],'table_row_candidate':False}
        q=raw['question_assessments'][0]
        q['table_row_reviews']=[{'evidence_id':'E1','decision':'included','reason':'원문의 모든 비교 행을 검토하여 교육 실적을 포함합니다.',
            'unit':'회','period':'2026년','population':'교육 대상자','direction':'higher','comparable':True,'due':True}]
        q['indicators'][0]['measurements']=[{'table_row_id':'','metric':'교육','target':6,'actual':29,
            'unit':'회','period':'2026년','population':'교육 대상자','direction':'higher','comparable':True,'due':True,
            'target_evidence_ids':['E2'],'actual_evidence_ids':['E2']}]
        result=validate(criterion,raw,evidence,{'status':'unavailable','model':{}})['question_assessments'][0]
        self.assertEqual(len(result['scoring_trace']['checks'][0]['measurements']),1)
        self.assertIsNone(result['scoring_trace']['checks'][0]['measurements'][0]['ratio'])
