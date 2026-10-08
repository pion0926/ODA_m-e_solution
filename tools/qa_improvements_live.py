"""Explicit paid, synthetic-only gold set. No customer text or DB mutations."""
import json, os, time
from pathlib import Path
from kodame_intake.db import pool
from kodame_intake.llm_models import llm_model_context
from kodame_intake.foundation_facts import extract_plan_facts
from kodame_intake.pdm_evidence import _request_measurements, measurement_schema, MEASUREMENT_PROMPT
from kodame_intake.measurement_recheck import suspicious_negatives
from kodame_intake.ai.job_budget import job_budget

assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
pool.open(wait=True)
start=time.monotonic()
results={'plan_fields':[], 'measurements':[], 'version':'synthetic-gold-v1'}
sectors=[('보건','지역사회 강사','명'),('교육','직업교육 수료생','명'),('농업','시범농장 수확량','톤'),('인프라','포장도로 연장','km')]
with llm_model_context(os.getenv('OPENROUTER_MODEL')),job_budget('gold-set-'+str(time.time())):
    for sector, indicator, unit in sectors:
        plan=f'''[PDF 페이지 1]
사업명: 합성 {sector} 역량강화 사업
대상국: 가상국. 지역: 가상시.
사업기간: 2025년 1월~2026년 12월. 총예산: 3억원.
공여기관: 가상개발기금. 수행기관: 가상대학. 협력기관: 가상시청.
배경: 지역 서비스 접근성 부족. 목표: 서비스 접근성 개선.
수혜자: 지역 주민 100명. 활동: {indicator} 확대 사업.
산출물: 사업 운영 매뉴얼 1종. 기대성과: 서비스 이용률 개선.
이해관계자: 가상시청은 운영을 담당한다.
일정: 2025년 준비, 2026년 운영. 확인 필요 정보: 유지관리 예산.
'''
        facts=extract_plan_facts(plan)
        present={f['field'] for f in facts['facts']}
        from kodame_intake.foundation_facts import FIELDS
        results['plan_fields'].append({'sector':sector,'expected':len(FIELDS),'found':len(present),'missing':sorted(set(FIELDS)-present),
            'grounded':all(f.get('source_location') for f in facts['facts'])})
        roster=[{'id':'outputs-1','indicator':indicator+f' ({unit})','evidence':'실적 보고서'}]
        cases=[('positive',f'2026년 6월 최종 실적\n항목 | 목표 | 실적\n{indicator} | 30{unit} | 54{unit}',54),
               ('negative',f'{indicator} 확대를 계획하였다. 아직 측정한 실적은 없다.',None),
               ('baseline',f'2025년 기초선 10{unit}. 2026년 목표 30{unit}. {indicator}의 2026년 실적은 54{unit}이다.',54)]
        for label,text,expected in cases:
            payload,_=_request_measurements(MEASUREMENT_PROMPT,json.dumps({'indicators':roster,'text':text},ensure_ascii=False),
                'KODAME Gold Measurement',response_schema=measurement_schema(roster))
            recheck=False
            suspects=suspicious_negatives(roster,text,payload)
            if suspects:
                recheck=True
                payload,_=_request_measurements(MEASUREMENT_PROMPT+'\n원문 표·동등 표현을 독립적으로 재검토한다.',
                    json.dumps({'indicators':roster,'text':text},ensure_ascii=False),'KODAME Gold Independent Review',response_schema=measurement_schema(roster))
            observations=[o for o in payload['observations'] if o['kind']=='actual' and ''.join(o['quote'].split()) in ''.join(text.split())]
            okay=not observations if expected is None else any(str(expected) in o['value'] for o in observations)
            results['measurements'].append({'sector':sector,'case':label,'expected':expected,'pass':okay,'recheck':recheck,'observations':observations})
positive=[r for r in results['measurements'] if r['expected'] is not None]
negative=[r for r in results['measurements'] if r['expected'] is None]
results.update(elapsed_seconds=round(time.monotonic()-start,2),positive_recall=sum(r['pass'] for r in positive)/len(positive),
               negative_specificity=sum(r['pass'] for r in negative)/len(negative),
               plan_omission_rate=sum(len(r['missing']) for r in results['plan_fields'])/sum(r['expected'] for r in results['plan_fields']))
Path('/qa/gold-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in results.items() if k not in ('plan_fields','measurements')},ensure_ascii=False))
pool.close()
assert results['positive_recall']==1 and results['negative_specificity']==1 and results['plan_omission_rate']==0, 'Gold acceptance failed; inspect saved cases'
