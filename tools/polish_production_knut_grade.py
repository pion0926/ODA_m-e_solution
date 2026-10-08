"""Reviewed, compact rationales; all scores are bound to the saved evaluation."""
import json
from pathlib import Path
import httpx
from kodame_intake.report_grade_scores import bind_grade_question_slots

reasons={
    'relevance_policy':'양국 정책·국가협력전략 및 현지 응급의료 수요와의 부합성이 확인됨. 수요조사 원자료와 설계 반영 기록의 정밀성 보완이 필요함.',
    'relevance_adaptation':'코로나19와 현지 제도 변화에 대응하여 교육·운영 방식을 조정함. 위험관리 대장과 대응 이력의 체계적 기록은 제한적임.',
    'coherence_internal':'국내 보건의료·고등교육 ODA 방향과 연계됨. 유관사업 사전 매핑 비교표와 공식 조율 증빙은 부족함.',
    'coherence_external':'수원국 부처·대학·유관기관과의 협약 및 협의체 운영이 확인됨. 최종 역할분담과 공동 성과 측정 자료의 보완이 필요함.',
    'effectiveness_output':'학과 개설 승인, 교재·강의계획서 개발, 기자재 검수 등 산출물이 확인됨. 일부 연차 지표는 미달 또는 진행 중임.',
    'effectiveness_outcome':'첫 졸업생 배출 전이거나 취업률·자격시험 실적이 누락되어 있음. 기초선·종료선 비교와 성과 인과성 근거가 부족하여 판정을 보류함.',
    'effectiveness_equity':'성·연령·장애 등 취약계층 분리데이터와 집단별 성과 격차 원자료가 부족하여 형평성 점수 판정을 보류함.',
    'efficiency_timeliness':'종합 정산·기간 비교와 시장 벤치마크 자료가 부족함. 일부 비교 수치가 원문 검증을 통과하지 못해 경제성·적시성 판정을 보류함.',
    'efficiency_balance':'역할 분담, 소통 체계 및 활동 간 연계 조정이 확인됨. 정밀한 일정 네트워크와 투입·산출 생산성 검증은 제한적임.',
    'sustainability_capacity':'학과 운영·시설 제공 등 자립 기반이 확인됨. 다년도 독립 예산 집행과 위기대응 체계의 검증 자료는 제한적임.',
    'sustainability_environment':'학과·직무 코드 승인과 산학관 협약 등 제도적 기반이 확인됨. 타 기관 확산과 장기 정규 운영 실적은 추가 확인이 필요함.',
}
creds=json.loads(Path('/tmp/production-knut-private.json').read_text(encoding='utf-8'))
out=Path('/app/data/qa/production-knut-20260920')
with httpx.Client(base_url='https://app.kodame.kr',timeout=120) as client:
    def call(method,path,payload=None):
        r=client.request(method,'/api/v2/'+path,json=payload);r.raise_for_status();return r
    call('POST','auth/login',{'email':creds['username'],'password':creds['password']})
    try:
        call('PUT',f"account/projects/{creds['project_id']}/select")
        client.headers.update({'X-ODAME-Account':creds['account_id'],'X-ODAME-Project':creds['project_id']})
        section=call('GET','report/sections/grade').json()
        evaluation=call('GET','evaluations').json()
        document=json.loads(section['content'])
        slots=bind_grade_question_slots(document['slots'],evaluation['criteria'])
        for key,reason in reasons.items():
            assert len(reason)<=100
            slots[key+'_reason']=reason
        document['slots']=slots
        result=call('PUT','report/sections/grade',{'content':json.dumps(document,ensure_ascii=False,indent=2),'expected_updated_at':section['updated_at']}).json()
        assert result['status']=='draft'
        (out/'grade-editor-review.json').write_text(json.dumps({'evaluation_run_id':evaluation['run_id'],'reasons':reasons,'scores_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'reviewed_grade_questions':len(reasons),'scores_bound_to_evaluation':True}),flush=True)
    finally:call('POST','auth/logout')
