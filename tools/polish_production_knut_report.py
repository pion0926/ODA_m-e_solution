"""Apply reviewed factual clarifications through the production user's edit API."""
import json
from pathlib import Path
import httpx

creds=json.loads(Path('/tmp/production-knut-private.json').read_text(encoding='utf-8'))
out=Path('/app/data/qa/production-knut-20260920')
with httpx.Client(base_url='https://app.kodame.kr',timeout=120) as client:
    def call(method,path,payload=None):
        r=client.request(method,'/api/v2/'+path,json=payload);r.raise_for_status();return r
    call('POST','auth/login',{'email':creds['username'],'password':creds['password']})
    try:
        call('PUT',f"account/projects/{creds['project_id']}/select")
        client.headers.update({'X-ODAME-Account':creds['account_id'],'X-ODAME-Project':creds['project_id']})
        rows=[]
        for part in ['summary-ko','feedback']:
            section=call('GET','report/sections/'+part).json();original=section['content'];updated=original
            if part=='summary-ko':
                replacements={
                    '총사업비는 국고 25억 원과 대응자금 약 2.9억 원을 합산한 약 27.9억 원 규모로 구성되며':
                    '최초 계획의 총사업비는 국고 25억 원과 대응자금 약 2.9억 원을 합산한 약 27.9억 원이며, 5차년도 계획에는 누적 총사업비 2,732,195천원으로 기재되어 예산 변경 승인 내역의 확인이 필요함. 사업 수행은',
                    '사업 기본정보와 관련된 예산 및 기간은 공식 사업계획서와 자체평가결과보고서를 통해 교차 검증됨.':
                    '사업 기간은 계획서와 사업설계매트릭스를 대조하여 확인함. 예산은 최초 계획과 5차년도 계획의 기준 시점 및 표기 차이를 구분하여 해석해야 하며, 실집행액과 동일한 값으로 단정하지 않음.',
                    '위원회 중심의 자체평가 회의와 영역별 이행 실적 검증 절차를 거쳐 객관적인 사실에 기반한 평가적 판단을 도출함. 사업 책임자와 실무진이 참여하는 회의를 통해 각 세부 프로그램의 추진 경과를 면밀히 점검함.':
                    '기존 자체평가보고서에 기록된 위원회 회의와 영역별 실적 점검 내용을 검토함. 이번 문헌기반 평가에서는 사업 책임자·실무진과의 신규 회의 또는 독립적인 현장 검증을 수행하지 않았으며, 기존 기록에서 확인되는 범위로 판단을 제한함.',
                    '현지 현장 조사나 대면 면담이 제한된 상황에서 서면 기록을 통한 검증에 의존할 수밖에 없는 한계가 있음.':
                    '이번 평가에서 별도의 현지조사나 대면 면담을 실시하지 않았으므로, 현장 수행 여부 및 성과의 인과성은 기존 서면 기록에서 확인되는 범위로 제한함.',
                }
                for old,new in replacements.items():
                    assert old in updated,old
                    updated=updated.replace(old,new,1)
            else:
                note='- (이행계획 제안) 아래 완료기한·점검주기·우선순위는 문헌검토 결과에 따른 이행계획 제안값이며, 관계기관과의 협의를 거쳐 확정해야 함.'
                assert note not in updated
                updated=updated.replace('ㅇ 환류과제 도출 배경 및 운영 방향','ㅇ 환류과제 도출 배경 및 운영 방향\n'+note,1)
            result=call('PUT','report/sections/'+part,{'content':updated,'expected_updated_at':section['updated_at']}).json()
            assert result['status']=='draft'
            rows.append({'part':part,'before':original,'after':result['content'],'purpose':'검수: 예산 기준시점, 기존 자체평가 기록과 실제 수행범위, 제안 일정 명시'})
        (out/'editor-review.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'reviewed_edits':[r['part'] for r in rows]},ensure_ascii=False),flush=True)
    finally:call('POST','auth/logout')
