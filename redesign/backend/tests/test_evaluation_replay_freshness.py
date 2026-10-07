"""Report freshness follows only proven whole-run copies, never similar scores."""
import copy
from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pytest

from kodame_intake.dac_replay import fingerprint, replay_if_identical
from kodame_intake.evaluation_versions import canonical_evaluation_id, whole_run_replay_basis
from kodame_intake.project_lifecycle import evaluate_freshness, snapshots_match


ROOT = '10000000-0000-0000-0000-000000000001'
REPLAY = '10000000-0000-0000-0000-000000000002'
NEXT = '10000000-0000-0000-0000-000000000003'
PROJECT = '20000000-0000-0000-0000-000000000001'
INPUTS = {'document_digest': 'documents', 'workflow_digest': 'workflow', 'assessment_fingerprint': 'fingerprint'}


def original():
    return {'id': ROOT, 'project_id': PROJECT, 'model': 'model-a', 'status': 'completed',
            'input_snapshot': {**INPUTS}}


def verified_copy():
    old = original()
    proof = whole_run_replay_basis(Mock(), old, REPLAY, INPUTS['assessment_fingerprint'], INPUTS)
    return {**old, 'id': REPLAY, 'input_snapshot': {**INPUTS, 'reused_from_run_id': ROOT, 'replay_basis': proof}}


def root_connection(row=None):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = original() if row is None else row
    return conn


def test_identical_whole_run_replay_keeps_legacy_report_snapshot_current():
    conn = root_connection()
    run = verified_copy()
    basis = canonical_evaluation_id(conn, run)
    before = {**INPUTS, 'evaluation_run_id': ROOT}
    after = {**INPUTS, 'evaluation_run_id': REPLAY, 'evaluation_basis_id': basis,
             'document_count': 1, 'completed_document_count': 1}
    assert basis == ROOT and after['evaluation_run_id'] == REPLAY
    assert snapshots_match(before, after)
    section = {'part_id': 'summary', 'status': 'draft', 'content': 'verified report',
               'generation_metadata': {'input_snapshot': before}}
    assert evaluate_freshness(after, run, [section])['report_current']
    assert str(conn.execute.call_args.args[1][0]) == ROOT
    assert conn.execute.call_args.args[1][1] == PROJECT


def test_repeated_copy_keeps_canonical_root_and_immediate_source_audit():
    conn = root_connection()
    proof = whole_run_replay_basis(conn, verified_copy(), NEXT, INPUTS['assessment_fingerprint'], INPUTS)
    assert proof['canonical_run_id'] == ROOT
    assert proof['source_run_id'] == REPLAY
    assert proof['run_id'] == NEXT


@pytest.mark.parametrize('field', ['assessment_fingerprint', 'document_digest', 'workflow_digest'])
def test_changed_or_missing_input_never_receives_basis_proof(field):
    for value in ('changed', ''):
        current = {**INPUTS, field: value}
        assert whole_run_replay_basis(Mock(), original(), REPLAY, current['assessment_fingerprint'], current) is None


@pytest.mark.parametrize('field,value', [('version', 'old-version'), ('run_id', ROOT),
    ('project_id', 'foreign-project'), ('source_run_id', NEXT), ('canonical_run_id', 'not-a-run-id'),
    ('canonical_run_id', REPLAY), ('model', 'model-b'), ('document_digest', 'changed'),
    ('workflow_digest', 'changed'), ('assessment_fingerprint', 'changed')])
def test_copied_forged_or_stale_proof_cannot_preserve_report(field, value):
    run = verified_copy()
    run['input_snapshot']['replay_basis'][field] = value
    assert canonical_evaluation_id(root_connection(), run) == REPLAY


@pytest.mark.parametrize('change', [{'project_id': 'other-project'}, {'model': 'model-b'},
                                  {'input_snapshot': {**INPUTS, 'workflow_digest': 'old-policy'}},
                                  {'input_snapshot': {**INPUTS, 'assessment_fingerprint': 'different-input'}}])
def test_unrelated_canonical_root_is_rejected(change):
    assert canonical_evaluation_id(root_connection({**original(), **change}), verified_copy()) == REPLAY


def test_missing_root_and_non_replay_partial_question_reuse_keep_new_identity():
    conn = root_connection()
    conn.execute.return_value.fetchone.return_value = None
    assert canonical_evaluation_id(conn, verified_copy()) == REPLAY
    partial = {**original(), 'id': REPLAY, 'input_snapshot': {**INPUTS, 'question_reuse': {'q1': {'reused': True}}}}
    assert canonical_evaluation_id(Mock(), partial) == REPLAY
    assert not snapshots_match({**INPUTS, 'evaluation_run_id': ROOT},
                               {**INPUTS, 'evaluation_run_id': REPLAY, 'evaluation_basis_id': REPLAY})


def test_actual_document_or_policy_change_still_invalidates_shared_basis():
    before = {**INPUTS, 'evaluation_run_id': ROOT}
    for field in ('document_digest', 'workflow_digest'):
        after = {**INPUTS, field: 'changed', 'evaluation_run_id': REPLAY, 'evaluation_basis_id': ROOT}
        assert not snapshots_match(before, after)
    assert snapshots_match(before, {**INPUTS, 'evaluation_run_id': REPLAY}, include_evaluation=False)


def test_assessment_date_model_and_rules_change_the_replay_fingerprint():
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = None
    with patch('kodame_intake.dac_replay.connection') as connection, \
         patch('kodame_intake.dac_replay.assessment_date', return_value=date(2026, 10, 8)) as day:
        connection.return_value.__enter__.return_value = conn
        baseline = fingerprint([], 'model-a')
        assert fingerprint([], 'model-b') != baseline
        day.return_value = date(2026, 10, 9)
        assert fingerprint([], 'model-a') != baseline
        day.return_value = date(2026, 10, 8)
        with patch('kodame_intake.dac_replay.PROMPT_VERSION', 'different-prompt'):
            assert fingerprint([], 'model-a') != baseline
        with patch('kodame_intake.dac_replay.RULE_DIGEST', 'different-rubric'):
            assert fingerprint([], 'model-a') != baseline


def test_whole_copy_issues_server_proof_and_preserves_run_and_source_ids():
    conn = MagicMock()
    old = original()
    before = copy.deepcopy(old)
    conn.execute.return_value.fetchone.side_effect = [old, {'n': 5}]
    with patch('kodame_intake.dac_replay.connection') as connection:
        connection.return_value.__enter__.return_value = conn
        assert replay_if_identical(REPLAY, INPUTS['assessment_fingerprint'], INPUTS)
    saved, new_id = conn.execute.call_args.args[1]
    assert new_id == REPLAY
    assert saved.obj['reused_from_run_id'] == ROOT
    assert saved.obj['replay_basis']['canonical_run_id'] == ROOT
    assert saved.obj['replay_basis']['run_id'] == REPLAY
    assert old == before


def test_unfinished_source_cannot_issue_a_whole_run_proof():
    assert whole_run_replay_basis(Mock(), {**original(), 'status': 'failed'}, REPLAY,
                                 INPUTS['assessment_fingerprint'], INPUTS) is None


def test_theory_visual_digest_reuses_only_the_verified_evaluation_basis():
    from kodame_intake.theory_visual import theory_visual_input_digest
    before = {**INPUTS, 'evaluation_run_id': ROOT}
    replay = {**INPUTS, 'evaluation_run_id': REPLAY, 'evaluation_basis_id': ROOT}
    genuine_new_evaluation = {**INPUTS, 'evaluation_run_id': REPLAY, 'evaluation_basis_id': REPLAY}
    digest = theory_visual_input_digest({}, {'theory': 'verified content'}, before)
    assert theory_visual_input_digest({}, {'theory': 'verified content'}, replay) == digest
    assert theory_visual_input_digest({}, {'theory': 'verified content'}, genuine_new_evaluation) != digest
