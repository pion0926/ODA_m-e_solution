"""Bind queued project workflows to the model policy at the claim boundary."""
from psycopg.types.json import Jsonb
from .llm_models import DEFAULT_MODEL, validate_model

# Presentation export intentionally has a separately configured dedicated model.
# There is no per-request model override for the project workflow endpoints.
PROJECT_POLICY_KINDS = {'pdm', 'dac', 'report_section', 'report_all', 'report_export', 'translation'}
MODEL_ARGUMENTS = {'dac': 2, 'report_all': 2, 'report_section': 3}
MODEL_RECEIPTS = {'pdm': 'pdm_refresh_runs', 'dac': 'evaluation_runs',
                  'report_all': 'report_generation_runs'}


def bind_claimed_model(conn, task):
    """Called only inside the transaction that changes queued -> running.

    FOR SHARE serializes the boundary with administrative model changes. Once
    committed the task, handler arguments, and receipt retain that model through
    execution; later policy changes affect the next claim only.
    """
    if task['kind'] not in PROJECT_POLICY_KINDS:
        return task
    project = conn.execute("SELECT llm_model,status FROM projects WHERE id=%s FOR SHARE",
                           (task['project_id'],)).fetchone()
    if not project or project['status'] != 'active':
        raise ValueError('AI 작업을 실행할 활성 프로젝트가 없습니다.')
    model = validate_model(project.get('llm_model') or DEFAULT_MODEL)
    arguments = list(task['arguments'])
    index = MODEL_ARGUMENTS.get(task['kind'])
    if index is not None:
        if len(arguments) <= index:
            raise ValueError('대기 작업의 AI 모델 인자가 올바르지 않습니다. 작업을 다시 요청해 주세요.')
        arguments[index] = model
    conn.execute("UPDATE workflow_tasks SET model=%s,arguments=%s WHERE id=%s AND status='running'",
                 (model, Jsonb(arguments), task['id']))
    table = MODEL_RECEIPTS.get(task['kind'])
    if table:
        conn.execute(f"UPDATE {table} SET model=%s WHERE project_id=%s AND id=%s AND status='queued'",
                     (model, task['project_id'], arguments[0]))
    # report_sections.generation_model describes its existing content until new
    # content is saved. Do not relabel that historical draft at claim time.
    return {**task, 'model': model, 'arguments': arguments}
