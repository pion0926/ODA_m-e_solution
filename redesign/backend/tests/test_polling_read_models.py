"""Polling retains visible data without decoding unrelated analysis caches."""
import copy
import json
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from kodame_intake.api.dependencies import serialize_document
from kodame_intake.api.read_projections import INTAKE_LIST_COLUMNS, PDM_DOCUMENT_COLUMNS, public_monitoring
from kodame_intake.evaluation_versions import has_current_approval
from kodame_intake.pdm_mapping_policy import VERSION, decision


def test_public_monitoring_omits_internal_pair_bodies_without_mutating_ledger():
    monitoring = {'pair_results': {'old': {'observations': ['private quote']}},
                  'evidence_analysis': {'observation_count': 2}, 'reviewed_mappings': {'i': ['d']}}
    before = copy.deepcopy(monitoring)
    assert public_monitoring(monitoring) == {
        'evidence_analysis': {'observation_count': 2}, 'reviewed_mappings': {'i': ['d']}}
    assert monitoring == before
    assert public_monitoring(None) == {}


def test_no_approval_skips_expensive_bundle_construction():
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = None
    with patch('kodame_intake.evaluation_versions.current_bundle') as bundle:
        assert has_current_approval(conn) is False
        bundle.assert_not_called()


@pytest.mark.parametrize('matched', [None, {'exists': 1}])
def test_existing_approval_still_compares_exact_current_revision(matched):
    conn = Mock()
    conn.execute.return_value.fetchone.side_effect = [{'exists': 1}, matched]
    with patch('kodame_intake.evaluation_versions.current_bundle', return_value={'revision': 'current'}) as bundle:
        assert has_current_approval(conn) is bool(matched)
        bundle.assert_called_once_with(conn)
    assert conn.execute.call_args.args[1] == ('current',)


@pytest.fixture
def sql_connection():
    if os.getenv('KODAME_POLLING_SQL_TEST') != '1':
        pytest.skip('Enable only in isolated QA to exercise PostgreSQL read projections')
    import psycopg
    from psycopg.rows import dict_row
    # Synthetic records only: not even the QA document table is read or changed.
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        yield conn


def synthetic_document(analysis):
    now = datetime(2026, 10, 8, tzinfo=timezone.utc).isoformat()
    return {'id': '00000000-0000-0000-0000-000000000001', 'original_name': 'synthetic.pdf',
            'size_bytes': 100, 'sha256': 'a' * 64, 'upload_role': 'evidence',
            'evaluation_excluded': False, 'evaluation_scope': {'decision': 'include'},
            'extracted_path': '/synthetic.txt', 'status': 'completed', 'stage': 'completed',
            'progress': 100, 'cancel_requested': False, 'analysis_model': 'synthetic-model',
            'intake_mode': 'auto', 'triage': {'reason': 'synthetic'}, 'queue_position': 1,
            'summary': 'synthetic summary', 'uploaded_at': now, 'updated_at': now, 'analysis': analysis}


def sql_row(conn, columns, document):
    from psycopg.types.json import Jsonb
    return conn.execute(f'SELECT {columns} FROM jsonb_populate_record(NULL::intake_documents,%s)',
                        (Jsonb(document),)).fetchone()


@pytest.mark.parametrize('analysis', [None, {}, {
    'intake_mode': 'artifact', 'registration': {'limitation': 'submission only', 'deeper_review_suggested': True},
    'quality_flags': ['synthetic warning'], 'registration_facts': {'facts': [{'fact': 'a'}, {'fact': 'b'}]},
    'evidence_matches': {'document_profiles': [{'role': 'interview'}],
                         'pdm': [{'indicator_id': 'i', 'rationale': 'record', 'evidence_quote': 'hidden'}]},
    'dac_fulltext': {'chunks': ['large-source-cache' * 1000]},
    'pdm_measurements': {'measurements': ['large-measurement-cache' * 1000]},
}])
def test_sql_list_projection_preserves_all_public_fields(sql_connection, analysis):
    document = synthetic_document(analysis)
    full = sql_row(sql_connection, '*', document)
    projected = sql_row(sql_connection, INTAKE_LIST_COLUMNS, document)
    assert serialize_document(projected) == serialize_document(full)
    assert 'dac_fulltext' not in projected['analysis']
    assert 'pdm_measurements' not in projected['analysis']
    assert 'registration_facts' not in projected['analysis']
    if analysis:
        assert len(json.dumps(projected, default=str)) < len(json.dumps(full, default=str)) / 10


@pytest.mark.parametrize('override', [None, {'version': 3, 'source_document_id': 'source', 'included': ['manual'], 'excluded': ['i']},
                                     {'version': 1, 'source_document_id': 'source', 'included': ['manual', 'i']}])
def test_sql_pdm_projection_preserves_automatic_and_manual_purpose_decisions(sql_connection, override):
    match = {'indicator_id': 'i', 'evidence_kind': 'direct_record', 'measurement_relation': 'reported_result',
             'subject_match': True, 'activity_match': True, 'scope_match': True,
             'proves': 'completed', 'evidence_quote': 'completed', 'confidence': .9}
    document = synthetic_document({'evidence_matches': {'version': VERSION, 'sources': {'pdm': {'id': 'source'}}, 'pdm': [match]},
                                   'pdm_mapping_overrides': override, 'dac_fulltext': {'chunks': ['large cache' * 1000]}})
    full = sql_row(sql_connection, '*', document)
    projected = sql_row(sql_connection, PDM_DOCUMENT_COLUMNS, document)
    for indicator_id in ('i', 'manual', 'unmapped'):
        assert decision(projected, indicator_id, 'source') == decision(full, indicator_id, 'source')
    assert 'dac_fulltext' not in projected['analysis']


def test_sql_pdm_projection_handles_unanalyzed_documents(sql_connection):
    row = sql_row(sql_connection, PDM_DOCUMENT_COLUMNS, synthetic_document(None))
    assert decision(row, 'i', 'source') is None
