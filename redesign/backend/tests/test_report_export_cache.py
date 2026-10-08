"""Exact HWPX reuse is a read-only optimization, never a freshness bypass."""
import copy
import hashlib
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from kodame_intake import report_export_cache as cache
from kodame_intake.api import report_routes

SNAPSHOT = {'document_digest': 'documents', 'workflow_digest': 'workflow',
            'evaluation_run_id': 'old-run', 'evaluation_basis_id': 'canonical'}
RUNTIME = {'version': cache.STAMP_VERSION, 'sha256': 'runtime',
           'images': {'REPORT_API_IMAGE_REVISION': 'sha256:'+'a'*64, 'REPORT_KORDOC_IMAGE_REVISION': 'sha256:'+'b'*64}}


@pytest.fixture
def artifact(tmp_path):
    path = tmp_path / 'verified.hwpx'; path.write_bytes(b'synthetic validated hwpx')
    validation = {key: {'ok': True} for key in ('layout_contract', 'semantic_coverage',
                  'project_identity_validation', 'toc_visible_validation')}
    validation.update(export_runtime=copy.deepcopy(RUNTIME), input_snapshot=copy.deepcopy(SNAPSHOT),
                      source_sections_sha256='sections', theory_visual={'model': 'model'}, rhwp_toc_verified=True,
                      rhwp_final={'ok': True, 'geometry_validation': {'ok': True},
                                  'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'id': 'export', 'status': 'completed', 'output_path': str(path), 'validation': validation}


def reusable(row, root, **changes):
    args = dict(snapshot=SNAPSHOT, sections_digest='sections', runtime=RUNTIME, export_dir=root, model='model')
    return cache.reusable_export(row, **{**args, **changes})


def test_verified_unchanged_export_reused_after_canonical_dac_replay(artifact, tmp_path):
    assert reusable(artifact, tmp_path)
    assert reusable(artifact, tmp_path, snapshot={**SNAPSHOT, 'evaluation_run_id': 'new-verified-replay'})


@pytest.mark.parametrize('key', ['document_digest', 'workflow_digest', 'evaluation_basis_id'])
def test_each_changed_input_or_missing_identity_misses(artifact, tmp_path, key):
    assert not reusable(artifact, tmp_path, snapshot={**SNAPSHOT, key: 'changed'})
    assert not reusable(artifact, tmp_path, snapshot={**SNAPSHOT, key: None, 'evaluation_run_id': None})


@pytest.mark.parametrize('change', [dict(sections_digest='edited'), dict(model='different-model'),
                                   dict(runtime=None), dict(runtime={**RUNTIME, 'sha256': 'new-layout'})])
def test_section_model_unknown_or_changed_runtime_misses(artifact, tmp_path, change):
    assert not reusable(artifact, tmp_path, **change)


@pytest.mark.parametrize('key', ['export_runtime', 'source_sections_sha256', 'input_snapshot',
                               'layout_contract', 'semantic_coverage', 'project_identity_validation',
                               'toc_visible_validation', 'rhwp_toc_verified', 'rhwp_final'])
def test_legacy_or_incomplete_verification_never_reused(artifact, tmp_path, key):
    artifact['validation'].pop(key)
    assert not reusable(artifact, tmp_path)


def test_file_changed_missing_or_outside_export_root_misses(artifact, tmp_path):
    path = tmp_path/'verified.hwpx'
    path.write_bytes(b'altered bytes')
    assert not reusable(artifact, tmp_path)
    path.unlink()
    assert not reusable(artifact, tmp_path)
    assert not reusable(artifact, tmp_path/'different-root')


def test_failed_or_unchecked_geometry_misses(artifact, tmp_path):
    artifact['validation']['rhwp_final']['geometry_validation'] = {'ok': False}
    assert not reusable(artifact, tmp_path)
    artifact['status'] = 'failed'
    assert not reusable(artifact, tmp_path)


@pytest.mark.parametrize('key', ['input_snapshot', 'theory_visual', 'rhwp_final', 'layout_contract'])
def test_malformed_optional_cache_metadata_is_a_miss_not_an_endpoint_failure(artifact, tmp_path, key):
    artifact['validation'][key] = ['malformed legacy value']
    assert not reusable(artifact, tmp_path)


def test_sections_digest_is_identical_to_exporter_identity():
    from kodame_intake import report_exporter
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [{'part_id':'cover','content':'합성','status':'draft','updated_at':'synthetic'}]
    with patch.object(report_exporter, 'connection', return_value=nullcontext(conn)):
        assert cache.report_sections_digest(conn) == report_exporter._report_sections_digest()


def test_runtime_bytes_and_image_ids_invalidate_without_broad_cached_manifest(tmp_path, monkeypatch):
    path = tmp_path/'layout.py'; path.write_bytes(b'first layout')
    monkeypatch.setenv('REPORT_API_IMAGE_REVISION', 'sha256:'+'a'*64)
    monkeypatch.setenv('REPORT_KORDOC_IMAGE_REVISION', 'sha256:'+'b'*64)
    with patch.object(cache, '_runtime_files', return_value=[('layout',path)]) as files:
        first = cache.export_runtime_fingerprint()
        assert first == cache.export_runtime_fingerprint()
        path.write_bytes(b'next layout changed')
        assert first != cache.export_runtime_fingerprint()
        path.write_bytes(b'first layout')
        assert first == cache.export_runtime_fingerprint()
        monkeypatch.setenv('REPORT_KORDOC_IMAGE_REVISION', 'sha256:'+'c'*64)
        assert first != cache.export_runtime_fingerprint()
        monkeypatch.setenv('REPORT_API_IMAGE_REVISION', 'mutable:latest')
        assert cache.export_runtime_fingerprint() is None
        monkeypatch.delenv('REPORT_API_IMAGE_REVISION')
        assert cache.export_runtime_fingerprint() is None
        assert files.call_count == 5


def test_missing_or_unreadable_runtime_disables_cache(monkeypatch, tmp_path):
    for key, value in RUNTIME['images'].items(): monkeypatch.setenv(key, value)
    with patch.object(cache, '_runtime_files', return_value=None):
        assert cache.export_runtime_fingerprint() is None
    with patch.object(cache, '_runtime_files', return_value=[('gone',tmp_path/'missing')]):
        assert cache.export_runtime_fingerprint() is None


def test_invalid_explicit_renderer_or_profile_never_falls_back_to_default_assets(monkeypatch, tmp_path):
    monkeypatch.setenv('RHWP_ASSET_ROOT', str(tmp_path/'missing-renderer'))
    assert cache._runtime_files() is None
    monkeypatch.delenv('RHWP_ASSET_ROOT')
    monkeypatch.setenv('REPORT_QUALITY_PROFILE_PATH', str(tmp_path/'missing-profile.json'))
    assert cache._runtime_files() is None


@pytest.mark.parametrize('race', ['none', 'document', 'section', 'runtime'])
def test_find_rechecks_upload_section_and_runtime_after_file_verification(artifact, tmp_path, race):
    conn = MagicMock(); conn.execute.return_value.fetchall.return_value = [artifact]
    latest = {**SNAPSHOT, 'document_digest': 'changed'} if race == 'document' else SNAPSHOT
    digests = ['sections', 'changed' if race == 'section' else 'sections']
    stamps = [RUNTIME, None if race == 'runtime' else RUNTIME]
    with patch.object(cache, 'export_runtime_fingerprint', side_effect=stamps), \
         patch.object(cache, 'report_sections_digest', side_effect=digests), \
         patch.object(cache, 'capture_input_snapshot', return_value=latest):
        result = cache.find_reusable_export(conn, snapshot=SNAPSHOT, export_dir=tmp_path, model='model')
    assert result == (artifact if race == 'none' else None)
    assert all(call.args[0].strip().startswith('SELECT') for call in conn.execute.call_args_list)


@pytest.mark.parametrize('mode', ['hit', 'miss', 'active', 'stale', 'unready', 'other_workflow'])
def test_post_export_preserves_preflight_and_active_guards_without_queuing_a_hit(mode):
    conn = MagicMock(); conn.transaction.return_value = nullcontext()
    conn.execute.return_value.fetchone.return_value = {'id':'active'} if mode == 'active' else None
    with patch.object(report_routes, 'connection', return_value=nullcontext(conn)), \
         patch.object(report_routes, 'current_project_id', return_value='project'), \
         patch.object(report_routes, 'report_export_readiness', return_value={'ready':mode != 'unready','issues':[]}), \
         patch.object(report_routes, 'project_lifecycle', return_value={'report_current':mode != 'stale','message':'stale','input_snapshot':SNAPSHOT}), \
         patch.object(report_routes, '_reserve_project_workflow', side_effect=HTTPException(409,'active') if mode == 'other_workflow' else None), \
         patch.object(report_routes, '_request_llm_model', return_value='model'), \
         patch.object(report_routes, 'serialize_report_export', return_value={'id':'existing','status':'completed','download_url':'file'}), \
         patch.object(cache, 'find_reusable_export', return_value={'id':'existing'} if mode == 'hit' else None) as find, \
         patch.object(report_routes, 'enqueue') as enqueue:
        if mode in {'active','stale','unready','other_workflow'}:
            with pytest.raises(HTTPException) as error: report_routes.start_report_export(None,MagicMock())
            assert error.value.status_code == 409
            find.assert_not_called(); enqueue.assert_not_called()
        else:
            result=report_routes.start_report_export(None,MagicMock())
            if mode == 'hit':
                assert result == {'id':'existing','status':'completed','download_url':'file','reused':True}
                enqueue.assert_not_called()
                assert not any('INSERT' in call.args[0] for call in conn.execute.call_args_list)
            else:
                assert result['status']=='queued'; enqueue.assert_called_once()
