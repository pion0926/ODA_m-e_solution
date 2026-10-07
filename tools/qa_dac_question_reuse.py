"""Transactional DAC checkpoint/RLS smoke test for the isolated QA database.

No AI requests, credentials, uploaded files, or production data. All synthetic
rows are rolled back after checking actual PostgreSQL JSONB storage and scope.
"""
import copy
import json
import os
import uuid
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

assert os.getenv('KODAME_QA') == '1'
assert 'qa-local-only@postgres' in os.environ['DATABASE_URL']
assert not os.getenv('OPENROUTER_API_KEY')

from kodame_intake import evaluation_recovery as recovery
from kodame_intake.workflow_models import bind_claimed_model


class RollbackFixture(Exception):
    pass


def verify_repeated_runner(conn, owner, shared_connection):
    """Run normal runner SQL/validation with only synthetic AI responses.

    The first repeat takes the actual whole-run replay path; the next bypasses
    that optimization to prove the per-question fallback remains idempotent.
    All rows stay inside the caller's rollback transaction and tenant scope.
    """
    from kodame_intake import dac_assessor, dac_pdm, dac_replay, dac_review
    from kodame_intake import evaluation_runner, project_lifecycle
    from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
    from kodame_intake.llm_models import llm_model_context

    project, document = uuid.uuid4(), uuid.uuid4()
    conn.execute("SELECT set_config('kodame.system_access','on',true)")
    conn.execute('INSERT INTO projects(id,owner_account_id,name) VALUES (%s,%s,%s)',
                 (project, owner, '합성 DAC 정상 반복 실행 검증'))
    conn.execute("SELECT set_config('kodame.project_id',%s,true),set_config('kodame.system_access','off',true)", (str(project),))
    text = '사업 대상 지역의 관계 기관들이 회의에 참석하여 수행 활동을 검토했다.'
    conn.execute("""INSERT INTO intake_documents
        (id,original_name,stored_path,extension,size_bytes,sha256,status,summary)
        VALUES (%s,'synthetic.txt','','txt',0,%s,'completed','합성 검토 자료')""", (document, 'a' * 64))
    pdm = {'performance_indicators': [{'id': 'synthetic-p1', 'indicator': '합성 활동 횟수',
                                      'target': 10, 'actual': 6, 'status': 'under'}]}
    conn.execute("INSERT INTO pdm_models(id,source_document_id,source_file_name,model) VALUES (%s,%s,'synthetic.txt',%s)",
                 (uuid.uuid4(), document, Jsonb(pdm)))
    question_ids = [q['id'] for c in EVALUATION_CRITERIA.values() for q in c['questions']]
    scopes = {qid: {str(document): {'mode': 'focused', 'ranges': [[0, len(text)]]}} for qid in question_ids}
    overview = {'period': {'text': '2025.01.01 ~ 2026.12.31'}}
    calls = []

    def generate_overview(run_id):
        conn.execute('''INSERT INTO project_overviews
            (id,run_id,model,document_count,overview,source_document_ids,conflicts)
            VALUES (%s,%s,'synthetic',1,%s,%s,%s)''',
            (uuid.uuid4(), run_id, Jsonb(overview), Jsonb([str(document)]), Jsonb([])))

    def prepare_documents(documents, **kwargs):
        for doc in documents:
            doc['review_source_text'] = text
            doc['fulltext_review'] = {'status': 'completed', 'character_count': len(text),
                'reviewed_criteria': list(EVALUATION_CRITERIA), 'chunks': [{'start': 0, 'end': len(text),
                'reviewed_questions': question_ids, 'evidence': [{'question_id': qid, 'kind': 'positive',
                    'quote': text, 'finding': '관계 기관이 실제 검토 활동을 수행한 기록입니다.'} for qid in question_ids]}]}

    def answer(system, prompt, title, **kwargs):
        data = json.JSONDecoder().raw_decode(prompt)[0]
        qid = data['questions'][0]['question_id']
        calls.append(qid)
        criterion = EVALUATION_CRITERIA[qid.rsplit('-q', 1)[0]]
        raw = dac_assessor.template({**criterion, 'questions': [q for q in criterion['questions'] if q['id'] == qid]})
        raw['question_assessments'][0]['finding'] = '합성 원문은 활동을 설명하지만 해당 성과를 확정할 근거는 부족합니다.'
        return raw, 'synthetic'

    def enqueue():
        run_id = uuid.uuid4()
        snapshot = project_lifecycle.capture_input_snapshot(conn)
        plan = {'version': dac_review.VERSION, 'revision': str(uuid.uuid4()), 'scopes': copy.deepcopy(scopes),
                'input_snapshot': snapshot, 'documents': [{'id': str(document),
                    'text_digest': dac_review.digest(text), 'artifact': False}]}
        conn.execute("INSERT INTO evaluation_runs(id,status,model,document_count,input_snapshot) VALUES (%s,'queued',%s,1,%s)",
                     (run_id, 'openai/gpt-5.6-luna', Jsonb({'review_plan': plan})))
        return run_id

    def saved(run_id):
        row = conn.execute('SELECT status,input_snapshot FROM evaluation_runs WHERE id=%s', (run_id,)).fetchone()
        assert row['status'] == 'completed'
        assert conn.execute('SELECT count(*) AS n FROM criterion_evaluations WHERE run_id=%s', (run_id,)).fetchone()['n'] == 5
        assert set(row['input_snapshot']['question_checkpoints']) == set(question_ids)
        return row['input_snapshot']

    with ExitStack() as stack:
        for module in (recovery, evaluation_runner, project_lifecycle, dac_replay, dac_pdm):
            stack.enter_context(patch.object(module, 'connection', shared_connection))
        stack.enter_context(patch.object(evaluation_runner, 'open_pool'))
        stack.enter_context(patch.object(evaluation_runner, 'generate_project_overview', side_effect=generate_overview))
        stack.enter_context(patch.object(evaluation_runner, 'prepare_documents', side_effect=prepare_documents))
        stack.enter_context(patch.object(dac_review, 'text_for', return_value=text))
        stack.enter_context(patch.object(dac_assessor, '_request_json', side_effect=answer))
        stack.enter_context(llm_model_context('openai/gpt-5.6-luna'))
        first = enqueue()
        evaluation_runner._run_all(first)
        original = saved(first)
        assert len(calls) == len(question_ids) == 11

        calls.clear()
        second = enqueue()
        evaluation_runner._run_all(second)
        repeated = saved(second)
        assert repeated['evaluation_run_id'] == str(first)
        assert repeated['review_plan']['revision'] != original['review_plan']['revision']
        assert repeated['reused_from_run_id'] == str(first)
        assert not calls and len(repeated['question_reuse']) == 11
        assert repeated['question_checkpoints'] == original['question_checkpoints']

        # Identical PDM content gets a new persistence identity/timestamp; only
        # the semantic model/source and assessment timing govern reuse.
        conn.execute("""INSERT INTO pdm_models(id,source_document_id,source_file_name,model,created_at)
            VALUES (%s,%s,'synthetic.txt',%s,now()+interval '1 second')""", (uuid.uuid4(), document, Jsonb(pdm)))
        third = enqueue()
        with patch.object(evaluation_runner, 'replay_if_identical', return_value=False):
            evaluation_runner._run_all(third)
        fallback = saved(third)
        assert fallback['pdm_context']['snapshot_id'] != original['pdm_context']['snapshot_id']
        assert not calls and len(fallback['question_reuse']) == 11
        assert fallback['question_checkpoints'] == original['question_checkpoints']
    return ['normal repeat replays all 11 questions despite prior-run metadata changes',
            'normal runner fallback revalidates/reuses all 11 checkpoints after equivalent PDM save']


checks = []
with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as conn:
    try:
        with conn.transaction():
            conn.execute("SELECT set_config('kodame.system_access','on',true)")
            owner = conn.execute('SELECT id FROM accounts WHERE is_admin LIMIT 1').fetchone()['id']
            project, other_project = uuid.uuid4(), uuid.uuid4()
            for ident in (project, other_project):
                conn.execute('INSERT INTO projects(id,owner_account_id,name) VALUES (%s,%s,%s)',
                             (ident, owner, '합성 DAC 체크포인트 검증'))
            previous, current, foreign = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            raw = {'question_assessments': [{'question_id': 'relevance-q1', 'finding': '합성 원문 검증 판정'}]}
            for ident, tenant, status, snapshot in (
                    (previous, project, 'completed', {'question_checkpoints': {'q1': {'digest': 'ours', 'raw': raw}}}),
                    (current, project, 'running', {'question_checkpoints': {}}),
                    (foreign, other_project, 'failed', {'question_checkpoints': {'q1': {'digest': 'foreign', 'raw': raw}}})):
                conn.execute('INSERT INTO evaluation_runs(id,project_id,status,model,document_count,input_snapshot) VALUES (%s,%s,%s,%s,0,%s)',
                             (ident, tenant, status, 'synthetic', Jsonb(snapshot)))

            @contextmanager
            def shared_connection():
                yield conn

            with patch.object(recovery, 'connection', shared_connection):
                # Even with maintenance privileges, the explicit project join
                # cannot return another project's checkpoint candidates.
                candidates, _ = recovery.load_question_candidates(current)
                assert candidates['q1'][0]['digest'] == 'ours'
                assert len(candidates['q1']) == 1
                checks.append('candidate query is explicitly project-scoped')

                conn.execute("SELECT set_config('kodame.project_id',%s,true),set_config('kodame.system_access','off',true)", (str(project),))
                recovery.save_question(current, 'q1', 'new-digest', raw)
                recovery.record_question_reuse(current, 'q1', str(previous))
                saved = conn.execute('SELECT input_snapshot FROM evaluation_runs WHERE id=%s', (current,)).fetchone()['input_snapshot']
                assert saved['question_checkpoints']['q1'] == {'digest': 'new-digest', 'raw': raw}
                assert saved['question_reuse']['q1'] == {'reused': True, 'source_run_id': str(previous)}
                checks.append('reused judgment and provenance persist in JSONB')
                assert conn.execute('SELECT id FROM evaluation_runs WHERE id=%s', (foreign,)).fetchone() is None
                checks.append('RLS excludes other project runs')
                # Exercise the model binding against real task/receipt rows in
                # the same rollback-only fixture, without claiming other jobs.
                conn.execute("UPDATE evaluation_runs SET status='completed' WHERE id=%s", (current,))
                queued, task_id = uuid.uuid4(), uuid.uuid4()
                old_model, new_model = 'google/gemini-3.5-flash-lite', 'openai/gpt-5.6-luna'
                conn.execute('UPDATE projects SET llm_model=%s WHERE id=%s', (new_model, project))
                conn.execute("INSERT INTO evaluation_runs(id,project_id,status,model,document_count) VALUES (%s,%s,'queued',%s,0)",
                             (queued, project, old_model))
                task = conn.execute("""INSERT INTO workflow_tasks(id,project_id,kind,queue,arguments,model,status)
                    VALUES (%s,%s,'dac','analysis',%s,%s,'running') RETURNING *""",
                    (task_id, project, Jsonb([str(queued), str(project), old_model]), old_model)).fetchone()
                claimed = bind_claimed_model(conn, task)
                stored = conn.execute('SELECT model,arguments FROM workflow_tasks WHERE id=%s', (task_id,)).fetchone()
                receipt = conn.execute('SELECT model FROM evaluation_runs WHERE id=%s', (queued,)).fetchone()
                assert claimed['model'] == stored['model'] == receipt['model'] == new_model
                assert stored['arguments'][2] == new_model
                checks.append('queued model binds task arguments and receipt atomically')
            checks.extend(verify_repeated_runner(conn, owner, shared_connection))
            raise RollbackFixture()
    except RollbackFixture:
        pass
print(json.dumps({'status': 'passed', 'checks': checks, 'fixture': 'rolled_back'}))
