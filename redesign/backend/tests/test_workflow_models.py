"""Queued model changes are bound atomically before a workflow starts."""
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

from kodame_intake import workflow_queue
from kodame_intake.workflow_models import bind_claimed_model
from kodame_intake.llm_models import current_llm_model

OLD = 'google/gemini-3.5-flash-lite'
NEW = 'openai/gpt-5.6-luna'


def task(kind='dac'):
    args = {'dac': ['run', 'project', OLD], 'pdm': ['run'],
            'report_all': ['run', 'project', OLD],
            'report_section': ['section', '사용자 수정 요청', 'project', OLD, '기존 초안'],
            'report_export': ['export', 'project'], 'translation': ['job'],
            'presentation': ['export', 'project', 15]}[kind]
    return {'id': 'task', 'kind': kind, 'project_id': 'project', 'account_id': None,
            'status': 'running', 'model': OLD, 'arguments': args}


@pytest.mark.parametrize('kind', ['dac', 'pdm', 'report_all', 'report_section', 'report_export', 'translation'])
def test_claim_binds_latest_policy_and_handler_arguments(kind):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {'status': 'active', 'llm_model': NEW}
    old = task(kind)
    result = bind_claimed_model(conn, old)
    assert result['model'] == NEW and old['model'] == OLD
    assert 'FOR SHARE' in conn.execute.call_args_list[0].args[0]
    if kind in ('dac', 'report_all'):
        assert result['arguments'] == ['run', 'project', NEW]
    elif kind == 'report_section':
        assert result['arguments'] == ['section', '사용자 수정 요청', 'project', NEW, '기존 초안']
        assert not any('UPDATE report_sections' in call.args[0] for call in conn.execute.call_args_list)
    else:
        assert result['arguments'] == old['arguments']
    if kind in ('dac', 'pdm', 'report_all'):
        assert conn.execute.call_args.args[1] == (NEW, 'project', 'run')
        assert "status='queued'" in conn.execute.call_args.args[0]


def test_dedicated_presentation_model_is_not_silently_changed():
    conn = MagicMock()
    original = task('presentation')
    assert bind_claimed_model(conn, original) == original
    conn.execute.assert_not_called()


@pytest.mark.parametrize('project', [None, {'status': 'paused', 'llm_model': NEW},
                                    {'status': 'active', 'llm_model': 'unknown/provider'}])
def test_invalid_model_or_inactive_project_never_falls_back(project):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = project
    with pytest.raises(ValueError):
        bind_claimed_model(conn, task())
    assert not any(call.args[0].startswith('UPDATE') for call in conn.execute.call_args_list)


def test_failed_policy_marks_only_claimed_task_failed_without_worker_crash():
    conn = MagicMock()
    conn.execute.return_value.fetchone.side_effect = [task(), {'status': 'active', 'llm_model': 'unknown/provider'}]
    result = workflow_queue.claim_task(conn, 'worker', 0, 'analysis')
    assert result['status'] == 'failed'
    assert any('UPDATE evaluation_runs' in call.args[0] for call in conn.execute.call_args_list)
    assert any("status='failed'" in call.args[0] for call in conn.execute.call_args_list)


def test_empty_queue_never_resolves_or_modifies_model():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    assert workflow_queue.claim_task(conn, 'worker', 0, 'analysis') is None
    assert not any('FROM projects' in call.args[0] for call in conn.execute.call_args_list)


def test_running_task_keeps_claimed_model_when_policy_changes_again():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {'status': 'active', 'llm_model': NEW}
    claimed = bind_claimed_model(conn, task())
    seen = []
    with patch('kodame_intake.evaluation_runner.run_all', side_effect=lambda *args: seen.append((args, current_llm_model()))), \
         patch('kodame_intake.ai.job_budget.job_budget', return_value=nullcontext()), \
         patch('kodame_intake.project_ai.get_project_model', return_value=OLD) as resolve:
        workflow_queue.dispatch(claimed)
    resolve.assert_not_called()
    assert seen == [(('run', 'project', NEW), NEW)]
