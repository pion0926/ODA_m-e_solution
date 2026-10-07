"""Queued exports cannot publish stale report sections after a new upload."""
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kodame_intake import report_exporter as exporter, workflow_queue


SNAPSHOT={'document_digest':'documents','workflow_digest':'workflow','evaluation_run_id':'evaluation'}


def context(*,current=True,snapshot=None,ready=True,after=None):
    stack=ExitStack()
    stack.enter_context(patch.object(exporter,'connection',return_value=nullcontext(MagicMock())))
    stack.enter_context(patch('kodame_intake.project_lifecycle.project_lifecycle',return_value={
        'report_current':current,'input_snapshot':snapshot or SNAPSHOT}))
    readiness=stack.enter_context(patch('kodame_intake.report_generator.report_export_readiness',return_value={
        'ready':ready,'issues':[] if ready else [{'message':'한 섹션이 실패 상태'}]}))
    stack.enter_context(patch('kodame_intake.db.current_project_id',return_value='synthetic-project'))
    stack.enter_context(patch.object(exporter,'capture_input_snapshot',return_value=after or snapshot or SNAPSHOT))
    return stack,readiness


def test_same_snapshot_and_legacy_jobs_validate_readiness_in_project_scope():
    stack,readiness=context()
    with stack:
        assert exporter._validate_export_start(SNAPSHOT)==SNAPSHOT
        assert exporter._validate_export_start()==SNAPSHOT
    assert all(call.args==('synthetic-project',) for call in readiness.call_args_list)


@pytest.mark.parametrize('change',[{'document_digest':'new-documents'},{'evaluation_run_id':'new-evaluation'},
                                   {'workflow_digest':'new-mappings'}])
def test_changed_receipt_snapshot_rejected_even_if_current_report_available(change):
    stack,readiness=context(snapshot={**SNAPSHOT,**change})
    with stack,pytest.raises(RuntimeError,match='접수 이후'):
        exporter._validate_export_start(SNAPSHOT)
    readiness.assert_not_called()


def test_failed_section_and_racing_preflight_change_rejected():
    stack,_=context(ready=False)
    with stack,pytest.raises(RuntimeError,match='본문 재점검'):
        exporter._validate_export_start(SNAPSHOT)
    stack,_=context(after={**SNAPSHOT,'document_digest':'upload-during-preflight'})
    with stack,pytest.raises(RuntimeError,match='사전 점검 중'):
        exporter._validate_export_start(SNAPSHOT)


def test_stale_27_sections_never_enter_render_or_complete_and_old_export_is_preserved(tmp_path):
    previous=tmp_path/'previous-completed.hwpx';previous.write_bytes(b'previous validated bytes')
    conn=MagicMock()
    with patch.object(exporter,'connection',return_value=nullcontext(conn)), \
         patch.object(exporter,'_update'), \
         patch('kodame_intake.project_lifecycle.project_lifecycle',return_value={
             'report_current':False,'input_snapshot':{**SNAPSHOT,'document_digest':'new-documents'}}), \
         patch.object(exporter,'_pipeline_context') as content, \
         patch.object(exporter,'build_theory_visual_artifacts') as ai, \
         patch.object(exporter,'EXPORT_DIR',tmp_path):
        exporter._run_report_export('new-export',SNAPSHOT)
    content.assert_not_called();ai.assert_not_called()
    statements=[call.args[0] for call in conn.execute.call_args_list]
    assert any("status='failed'" in sql for sql in statements)
    assert not any("status='completed'" in sql for sql in statements)
    assert previous.read_bytes()==b'previous validated bytes'
    assert list(tmp_path.iterdir())==[previous]


@pytest.mark.parametrize('arguments',[['export','project'],['export','project',SNAPSHOT]])
def test_dispatcher_forwards_legacy_and_snapshot_arguments_unchanged(arguments):
    task={'id':'task','kind':'report_export','project_id':'project','account_id':'account',
          'model':'openai/gpt-5.6-luna','arguments':arguments}
    with patch('kodame_intake.db.tenant_context',return_value=nullcontext()), \
         patch('kodame_intake.llm_models.llm_model_context',return_value=nullcontext()), \
         patch('kodame_intake.ai.job_budget.job_budget',return_value=nullcontext()), \
         patch.object(exporter,'run_report_export') as export:
        workflow_queue.dispatch(task)
    export.assert_called_once_with(*arguments)


def test_wrapper_preserves_optional_snapshot_and_project_scope():
    with patch.object(exporter,'tenant_context',return_value=nullcontext()) as scope, \
         patch.object(exporter,'_run_report_export') as run:
        exporter.run_report_export('export','project',SNAPSHOT)
    scope.assert_called_once_with('project',system=False)
    run.assert_called_once_with('export',SNAPSHOT)
