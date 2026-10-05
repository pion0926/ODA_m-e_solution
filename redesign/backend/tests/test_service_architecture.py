"""Behavioral checks for durable tasks and bounded provider requests (no paid API)."""
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import pytest
from kodame_intake import workflow_queue as queue
from kodame_intake.ai import request_limits
from kodame_intake.ai.prompt_registry import load_prompt, prompt_manifest
from kodame_intake.db import tenant_context


def task(kind='pdm'):
    return {'id':uuid.uuid4(),'project_id':uuid.uuid4(),'account_id':uuid.uuid4(),
            'kind':kind,'arguments':[str(uuid.uuid4())],'model':'google/gemini-3.5-flash-lite'}


def test_outbox_binds_project_actor_model_and_serializable_arguments():
    job = task(); conn=MagicMock()
    with tenant_context(job['project_id'],account_id=job['account_id']):
        queue.enqueue(conn,job['kind'],[job['id']],job['model'])
    args=conn.execute.call_args.args[1]
    assert args[1:5] == (job['project_id'],job['account_id'],'pdm','analysis')
    assert args[5].obj == [str(job['id'])]
    assert args[6] == job['model']
    conn.commit.assert_not_called()  # receipt + task share caller's transaction


@pytest.mark.parametrize('domain,expected', [('failed','failed'),('partial','partial'),
    ('completed_with_errors','partial'),('cancelled','cancelled'),('draft','completed'),('completed','completed')])
def test_task_uses_actual_handler_result_even_without_exception(domain,expected):
    conn=MagicMock(); conn.execute.return_value.fetchone.return_value={'status':domain,'error_message':None}
    assert queue.finish_task(conn,task()) == expected
    assert conn.execute.call_args.args[1][0] == expected


def test_handler_returning_without_saving_cannot_leave_receipt_running():
    conn=MagicMock(); conn.execute.return_value.fetchone.return_value={'status':'running','error_message':None}
    assert queue.finish_task(conn,task()) == 'failed'
    assert any('UPDATE pdm_refresh_runs' in c.args[0] for c in conn.execute.call_args_list)


def test_provider_slot_is_released_after_failure_and_is_bounded(monkeypatch):
    monkeypatch.setattr(request_limits,'_slots',threading.BoundedSemaphore(1))
    with pytest.raises(ValueError), request_limits.request_slot():
        raise ValueError('failed request')
    with request_limits.request_slot():
        assert not request_limits._slots.acquire(blocking=False)
    assert request_limits._slots.acquire(blocking=False)
    request_limits._slots.release()


def test_cancellation_prevents_provider_slot_use():
    from kodame_intake.report_cancellation import ReportCancelled
    with patch('kodame_intake.report_cancellation.check_cancelled',side_effect=ReportCancelled()):
        with pytest.raises(ReportCancelled), request_limits.request_slot():
            pytest.fail('request must not be sent')


def test_prompts_have_reproducible_identity_and_block_path_traversal():
    manifest = prompt_manifest()
    assert set(manifest) >= {'document_intake','foundation_pdm','performance_measurements'}
    assert all(len(v)==64 for v in manifest.values())
    with pytest.raises(ValueError):
        load_prompt('../settings')


def test_frontend_entry_loads_separate_assets_in_dependency_order():
    root=Path(__file__).resolve().parents[3]
    html=(root/'frontend/index.html').read_text(encoding='utf-8')
    assert 'assets/app-styles.css' in html
    assert html.index('assets/app-shell.js') < html.index('assets/app-controller.js')
    assert '<style>' not in html
    # The single inline bootstrap must survive a failed download of app-shell.
    # All actual application modules remain external and ordered.
    import re
    inline = re.findall(r'<script>(.*?)</script>', html, re.S)
    assert len(inline) == 1
    assert 'window.reportModuleUnavailable = function' in inline[0]
    assert 'KODAME_MODULE_FAILED = true' in inline[0]
    assert 'fetch(' not in inline[0]


def test_short_authoritative_pdm_does_not_require_invented_length():
    from kodame_intake.report_generator import _validate_reader_content, _deterministic_quality_cap
    text='지역사회 CPCR 강사 수: 목표 6명. 검증수단: 수료증 및 서명 명부.'
    issues=_validate_reader_content('pdm',text,'',{})
    assert not any('최소 분량' in issue for issue in issues)
    _,warnings=_deterministic_quality_cap('pdm',text,{},False)
    assert not any('최소 분량' in issue for issue in warnings)


def test_runtime_diagnostics_rejects_project_user_before_querying_global_counts():
    from fastapi import HTTPException
    from kodame_intake.api.operations_routes import runtime_status
    request=MagicMock()
    request.state.auth={'is_admin':False}
    with patch('kodame_intake.api.operations_routes.connection') as connect:
        with pytest.raises(HTTPException) as error:
            runtime_status(request)
    assert error.value.status_code==403
    connect.assert_not_called()


def test_normalized_narrative_never_inserts_a_forbidden_template_heading():
    from report_outline import (NARRATIVE_OUTLINE_DEFAULT_LABELS,
        is_redundant_narrative_outer_heading,canonical_narrative_outline_text,narrative_outline_issues)
    for part,label in NARRATIVE_OUTLINE_DEFAULT_LABELS.items():
        assert not is_redundant_narrative_outer_heading(part,label),part
    content=canonical_narrative_outline_text('eval-purpose','- 등록 문서를 기준으로 목표와 실적의 차이를 검토함.')
    assert canonical_narrative_outline_text('eval-purpose',content)==content
    assert not narrative_outline_issues('eval-purpose',content)
