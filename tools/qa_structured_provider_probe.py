"""Three-provider smoke test using synthetic data only; no project writes."""
import json
import sys
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_overview import request_overview

prompt = '''테스트용 가상 사업개요를 JSON으로 작성하세요.
[D001] 검증용 문서: 사업명은 합성 테스트 교육사업, 국가는 가상국,
위치는 테스트시, 기간은 2025~2027년, 예산은 100만원이다.
공여기관은 테스트 공여기관, 수행기관은 테스트 수행기관, 협력기관은 테스트 대학이다.
교육 접근 부족으로 학생 10명을 대상으로 교육을 시행할 계획이며, 목표는 교육 접근성 개선이다.
활동은 교육 2회 실시, 산출은 교육자료 1종, 기대성과는 학습역량 개선이다.
공여기관은 예산, 수행기관은 운영, 대학은 참여자 모집을 담당한다.
2025년 준비, 2026년 실시, 2027년 검토 예정이다. 실제 성과 자료는 없다.
각 필드의 사실은 D001을 참조하고, conflicts는 빈 배열로 반환한다.
다른 사실을 만들어내지 않는다.'''
rows=[]
for model in (sys.argv[1:] or ['google/gemini-3.5-flash-lite','openai/gpt-5.6-luna','anthropic/claude-haiku-4.5']):
    try:
        with llm_model_context(model):
            result=request_overview(prompt,{'D001'})
        row={'model':model,'status':'passed','fields':len(result)}
    except Exception as exc:
        row={'model':model,'status':'failed','error':str(exc)[:300]}
    rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
assert all(r['status']=='passed' for r in rows), 'One or more provider probes failed'
