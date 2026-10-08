"""Build an evidence-backed token report for the single development Flash run.

Read-only database access. Does not submit any AI, evaluation, or export jobs.
Run beside qa_gemini_flash_e2e.py inside the development API container.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path

from kodame_intake.db import connection, pool, tenant_context
from qa_gemini_flash_e2e import MODEL, save, snapshot, usage


def build(state_path: Path, output: Path):
    state = json.loads(state_path.read_text(encoding='utf-8'))
    data = snapshot(state)
    pid = state['project_id']
    with tenant_context(pid), connection() as conn, conn.transaction():
        conn.execute('SET TRANSACTION READ ONLY')
        files = conn.execute('SELECT sha256 FROM intake_documents').fetchall()
        runs = {table: conn.execute(f'SELECT count(*) AS count FROM {table}').fetchone()['count']
                for table in ('evaluation_runs','report_generation_runs','report_exports')}
    source_hashes = Counter(d['sha256'].strip() for d in state['sources'])
    copied_hashes = Counter(d['sha256'].strip() for d in files)
    totals = usage(pid)
    events = data['token_events']
    checks = {
        'all_original_files_match': source_hashes == copied_hashes,
        'all_documents_completed': sum(x['count'] for x in data['documents'] if x['status']=='completed') == len(files),
        'only_requested_model_recorded': all(x['model']==MODEL for x in events),
        'ledger_matches_totals': sum(x['total_tokens'] for x in events)==totals['total_tokens'],
        'input_plus_output_equals_total': totals['input_tokens']+totals['output_tokens']==totals['total_tokens'],
        'evaluation_completed': (data['evaluation'] or {}).get('status')=='completed',
        'all_27_sections_have_content': len(data['sections'])==27 and all(x['content_chars'] for x in data['sections']),
        'hwpx_completed': (data['export'] or {}).get('status')=='completed',
    }
    checkpoints = state.get('checkpoints',[])
    last = {'calls':0,'input_tokens':0,'output_tokens':0,'total_tokens':0,'last_event_id':0}
    phases = []
    labels = {
        'document_intake_finished':f'문서 {len(files)}개 적재·분석 및 자동 갱신',
        'pdm_dac_evaluation_finished':'PDM·DAC 종합 평가',
        'report_sections_finished':'27개 보고서 섹션 생성·내부 검증',
        'hwpx_export_finished':'HWPX 저장·변화이론 생성·최종 쪽수 검증',
    }
    for point in checkpoints:
        if point['label']=='start':
            last = point
            continue
        phases.append({'label':labels.get(point['label'],point['label']), 'completed_at':point['at'],
            **{k:int(point[k])-int(last[k]) for k in ('calls','input_tokens','output_tokens','total_tokens')},
            'first_event_id_exclusive':int(last['last_event_id']),'last_event_id_inclusive':int(point['last_event_id'])})
        last = point
    if totals['last_event_id']>int(last['last_event_id']):
        phase_name = {'document_intake':'문서 적재·분석','pdm_dac_evaluation':'PDM·DAC 종합 평가',
                      'report_sections':'27개 보고서 섹션 생성','hwpx_export':'HWPX 저장'}.get(state.get('phase'),'후속 작업')
        phases.append({'label':phase_name + (' (오류 중단)' if state.get('error') else ' (진행 중)'),
            **{k:int(totals[k])-int(last[k]) for k in ('calls','input_tokens','output_tokens','total_tokens')}})
    data.update({'checks':checks,'job_counts':runs,'phase_usage':phases,'usage':totals})
    output.mkdir(parents=True,exist_ok=True)
    save(data,output/'gemini-flash-full-run-token-usage.json')
    complete = state.get('phase')=='completed' and all(checks.values())
    lines = [
        '# Gemini Flash 신규 프로젝트 전체 보고서 생성 토큰 실측', '',
        f'- 상태: {"완료" if complete else "오류 중단 · 최종 보고서 미생성" if state.get("error") else "진행 중 또는 검토 필요"}',
        f'- 프로젝트: {state["project_name"]}',
        f'- 프로젝트 ID: `{pid}`', f'- 계정: `{state["username"]}`',
        f'- 모델: `{MODEL}`',
        f'- 원본: {state["source_name"]} — {len(files)}개, {data["source_bytes"]:,}바이트',
        '- 개발 서버: http://127.0.0.1:8002 (운영 서버와 분리)',
        '- 기존 AI 분석·평가·보고서를 복제하지 않고 원본 파일을 빈 프로젝트에 다시 업로드함.',
        '', '## 실제 사용량', '',
        '| 구간 | API 응답 기록 수 | 입력 토큰 | 출력 토큰 | 합계 |',
        '|---|---:|---:|---:|---:|',
    ]
    lines += [f'| {p["label"]} | {p["calls"]:,} | {p["input_tokens"]:,} | {p["output_tokens"]:,} | {p["total_tokens"]:,} |' for p in phases]
    lines += [f'| **총합** | **{totals["calls"]:,}** | **{totals["input_tokens"]:,}** | **{totals["output_tokens"]:,}** | **{totals["total_tokens"]:,}** |', '',
        '프로젝트별 `token_usage_events`에 저장된 API 응답 사용량을 합산함. 입력/출력 추정치가 아니며, 내부 재시도와 검증 호출 중 사용량이 반환된 응답도 포함함. 사용량이 반환되지 않은 HTTP 오류의 과금 여부는 이 원장만으로 확인할 수 없음.', '',
        '구간별 수치는 단계 완료 시점 누계의 차이임. 문서 처리 완료 직후의 비동기 사업개요/PDM 갱신 일부는 다음 평가 구간에 포함될 수 있으나 전체 합계에는 영향을 주지 않음. 과금액과 토큰 수는 별개이며 캐시·추론·공급자 과금의 세부 내역은 이 원장에 저장하지 않음.', '',
        '## 검증', '',
    ]
    lines += [f'- {key}: {"PASS" if value else "확인 필요"}' for key,value in checks.items()]
    lines += ['', '## 실행 횟수', '', *[f'- {name}: {count}회' for name,count in runs.items()], '']
    if state.get('error'):
        lines += ['## 중단 원인', '', f'- 기록된 오류: `{state["error"]}`',
                  '- 오류가 발생한 실행의 토큰도 전부 포함함. 최종 보고서가 생성될 때까지의 총량으로 해석하면 안 됨.',
                  '- 자료 적재 결과와 완료된 문헌 검토 캐시는 보존함. 추가 수정·재시도는 별도 승인을 받은 뒤 수행함.', '']
    if data['export']:
        export = data['export']
        lines += ['## 최종 산출물', '', f'- 내보내기 ID: `{export["id"]}`',
                  f'- 파일명: {export["file_name"]}', f'- 상태: {export["status"]}', '']
    (output/'gemini-flash-full-run-token-usage.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'complete':complete,'checks':checks,'usage':totals,'output':str(output)},ensure_ascii=False,default=str))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get('SESSION_COOKIE_NAME')!='kodame_session':
        raise SystemExit('Development server only.')
    pool.open(wait=True)
    try:
        build(args.state,args.output)
    finally:
        pool.close()
