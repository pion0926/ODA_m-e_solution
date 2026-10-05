"""Shared reservations across API/intake/analysis/report processes.

Unknown transport outcomes keep their worst-case reservation. Missing provider
costs never count as free. Live catalog prices bound normal text requests;
provider routing is constrained to those prices to avoid a dearer fallback.
"""
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from .job_budget import current_job, BudgetExceeded


def enabled():
    return os.getenv('AI_GLOBAL_BUDGET_ENABLED', 'false').lower() == 'true'


def usage_limits_enabled():
    return os.getenv('AI_USAGE_LIMITS_ENABLED', 'true').lower() == 'true'


def estimate(payload):
    from ..model_catalog import get_model_catalog
    model = payload.get('model', '')
    row = next((m for m in get_model_catalog()['models'] if m['id'] == model), None)
    if not row or row.get('input') is None or row.get('output') is None:
        raise BudgetExceeded('모델 가격을 확인하지 못해 비용 제한을 적용할 수 없습니다. 잠시 후 다시 실행해 주세요.')
    # Bytes overestimate normal tokenizer input. Images have an additional
    # reservation and must remain within the model's selected token bound.
    prompt = len(json.dumps(payload.get('messages', []), ensure_ascii=False).encode())
    output = min(int(payload.get('max_tokens') or payload.get('max_completion_tokens') or 24000), 24000)
    payload['max_tokens'] = output
    payload.setdefault('provider', {})['max_price'] = {'prompt': row['input'], 'completion': row['output']}
    return prompt + output, (prompt*row['input']+output*row['output'])/1_000_000


def reserve(key_hash, task, model, tokens, cost):
    from ..db import connection, current_account_id, current_project_id
    with connection() as conn, conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('ai-budget:'+key_hash,))
        stats = conn.execute('''SELECT count(*) AS requests,coalesce(sum(tokens),0) AS tokens,
            coalesce(sum(cost_usd),0) AS cost,
            count(*) FILTER(WHERE finished_at IS NULL AND lease_until>now()) AS active,
            count(*) FILTER(WHERE task_id=%s) AS job_requests,
            coalesce(sum(cost_usd) FILTER(WHERE task_id=%s),0) AS job_cost,
            coalesce(sum(cost_usd) FILTER(WHERE account_id IS NOT DISTINCT FROM %s),0) AS account_cost
            FROM ai_request_reservations WHERE key_hash=%s AND created_at>now()-interval '24 hours' ''',
            (task,task,current_account_id(),key_hash)).fetchone()
        limits = [('requests', 1, int(os.getenv('AI_DAILY_REQUESTS','3000'))),
                  ('tokens', tokens, int(os.getenv('AI_DAILY_TOKENS','30000000'))),
                  ('cost', cost, float(os.getenv('AI_DAILY_USD','100'))),
                  ('account_cost', cost, float(os.getenv('AI_ACCOUNT_DAILY_USD','60'))),
                  ('job_requests', 1, int(os.getenv('AI_JOB_REQUESTS','600'))),
                  ('job_cost', cost, float(os.getenv('AI_JOB_USD','30')))]
        if usage_limits_enabled():
            for key, added, limit in limits:
                if float(stats[key])+added > limit:
                    raise BudgetExceeded(f'AI 사용 한도({key})에 도달했습니다. 완료 결과를 보존하고 작업을 중지합니다.')
        if stats['active'] >= int(os.getenv('AI_GLOBAL_IN_FLIGHT','4')):
            return None
        ident = uuid.uuid4()
        conn.execute('''INSERT INTO ai_request_reservations(id,key_hash,account_id,project_id,task_id,model,tokens,cost_usd,lease_until)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now()+interval '10 minutes')''',
            (ident,key_hash,current_account_id(),current_project_id(),task,model,tokens,cost))
        return ident


def settle(ident, body):
    if not ident or not isinstance(body, dict):
        return
    from ..db import connection
    usage = body.get('usage') or {}
    cost, tokens = usage.get('cost'), usage.get('total_tokens')
    if not isinstance(cost, (int,float)) or cost < 0 or not isinstance(tokens, int) or tokens <= 0:
        return
    with connection() as conn:
        conn.execute('UPDATE ai_request_reservations SET tokens=%s,cost_usd=%s,usage_confirmed=true WHERE id=%s', (tokens,cost,ident))


@contextmanager
def global_slot(payload):
    current_job()
    if not enabled():
        yield None
        return
    from ..settings import OPENROUTER_API_KEY
    from ..db import connection
    from ..intake_control import check
    from ..report_cancellation import check_cancelled
    tokens, cost = estimate(payload)
    key_hash = hashlib.sha256(OPENROUTER_API_KEY.encode()).hexdigest()
    task, deadline = current_job(), time.monotonic()+300
    ident = None
    while ident is None:
        check(); check_cancelled(); current_job()
        ident = reserve(key_hash, task, payload.get('model',''), tokens, cost)
        if ident is None:
            if time.monotonic() >= deadline:
                raise BudgetExceeded('AI 전역 요청 슬롯 대기 한도를 초과했습니다.')
            time.sleep(.5)
    try:
        yield ident
    finally:
        with connection() as conn:
            conn.execute('UPDATE ai_request_reservations SET finished_at=now() WHERE id=%s', (ident,))
