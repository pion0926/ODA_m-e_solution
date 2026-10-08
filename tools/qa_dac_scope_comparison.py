"""Paid synthetic-only focused/expanded versus full-source DAC comparison.

Uses the production extractor and assessor; only document-cache writes are mocked.
No customer files or evaluation results are read or modified.
"""
import copy
import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from kodame_intake.db import pool
from kodame_intake.llm_models import llm_model_context
from kodame_intake.ai.job_budget import job_budget
from kodame_intake.dac_evidence import analyze_document
from kodame_intake.dac_scope_policy import escalation_questions, expand_documents
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
from kodame_intake.evaluation_runner import _corpus
from kodame_intake.dac_assessor import assess_criterion
from kodame_intake.assessment_context import assessment_scope

assert os.getenv('KODAME_QA') == '1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
assert os.getenv('OPENROUTER_API_KEY')
qid = 'relevance-q1'
criterion = {**EVALUATION_CRITERIA['relevance'], 'questions': [
    q for q in EVALUATION_CRITERIA['relevance']['questions'] if q['id'] == qid]}
positive = '2026년 가상국 농업부 공식 정책 대조표는 이 사업의 관개시설 개선 목표가 국가개발계획의 농업용수 접근성 개선 우선순위와 직접 일치함을 확인하였다.'
negative = '2026년 가상국 농업부 최종 현장검토서는 사업 대상 3개 마을 중 2개 마을이 국가개발계획 우선지원지역에서 제외되어 대상지역 선정이 국가 우선순위와 상충한다고 확인하였다.'
cases = [
    ('missing', '문서 표지와 배포 목록만 기록한다.', positive, ['positive']),
    ('conflict', positive + '\n' + negative, '부록에는 검토 참석기관 목록이 기록되어 있다.', ['positive', 'limitation']),
    ('sufficient', positive, '부록에는 문서 배포 일자만 기록되어 있다.', ['positive']),
]
start = time.monotonic()
results = []
pool.open(wait=True)
try:
    with llm_model_context(os.getenv('OPENROUTER_MODEL')), job_budget('dac-scope-comparison-' + str(time.time())):
        for label, head, tail, expected_kinds in cases:
            text = head + '\n' + tail
            path = Path('/qa') / ('dac-scope-' + label + '.txt')
            path.write_text(text, encoding='utf-8')
            base = {'id': str(uuid.uuid4()), 'ref': 'D001', 'name': '합성 공식정책 대조표.txt',
                'summary': '', 'document_type': 'official_record', 'period': '2026', 'organizations': [],
                'quality_flags': [], 'assigned_criteria': ['relevance'], 'extracted_path': str(path),
                'scope_text': text, 'review_all': False,
                'question_scopes': {qid: {'mode': 'focused', 'ranges': [[0, len(head)]]}}}
            def review(doc):
                # Keep all real AI parsing/validation/coverage code and its budget DB;
                # suppress only the document cache UPDATE for this synthetic UUID.
                with patch('kodame_intake.dac_evidence.connection', return_value=MagicMock()), \
                     patch('kodame_intake.intake_control.check'):
                    doc['fulltext_review'] = analyze_document(doc)
                return doc
            focused = review(copy.deepcopy(base))
            escalated = escalation_questions([focused], [qid])
            if escalated:
                focused = review(expand_documents([base], [focused], escalated)[0])
            full = copy.deepcopy(base)
            full['question_scopes'][qid]['ranges'] = [[0, len(text)]]
            full = review(full)
            def kinds(doc):
                return sorted({e['kind'] for c in doc['fulltext_review']['chunks'] for e in c['evidence']})
            scores = []
            for doc in (focused, full):
                corpus, _ = _corpus('relevance', [doc])
                assessment = assess_criterion('relevance', criterion, corpus,
                    assessment_scope({'period': {'text': '2025년 1월~2026년 6월'}}),
                    {'status': 'not_available', 'model': {'performance_indicators': []}})
                scores.append(assessment['score'])
            result = {'case': label, 'escalated': bool(escalated), 'expected_kinds': expected_kinds,
                'focused_kinds': kinds(focused), 'full_kinds': kinds(full), 'scores': scores,
                'score_equal': scores[0] == scores[1],
                'grounded': all(e['quote'] in text for doc in (focused, full)
                    for c in doc['fulltext_review']['chunks'] for e in c['evidence'])}
            result['pass'] = (set(expected_kinds) <= set(result['focused_kinds'])
                and set(expected_kinds) <= set(result['full_kinds']) and result['grounded']
                and result['score_equal'] and (bool(escalated) == (label != 'sufficient')))
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
finally:
    pool.close()
output = {'cases': results, 'elapsed_seconds': round(time.monotonic() - start, 2),
    'status': 'passed' if all(r['pass'] for r in results) else 'failed',
    'limitation': 'Three synthetic cases for one DAC question; not a corpus-wide accuracy guarantee.'}
Path('/qa/dac-scope-comparison.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
assert output['status'] == 'passed', output
