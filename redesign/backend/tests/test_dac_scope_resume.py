from unittest.mock import patch
from kodame_intake.evaluation_runner import prepare_review


def test_resume_restores_expanded_scope_before_any_document_requests():
    narrow = [{'id': 'doc', 'question_scopes': {'q': {'ranges': [[0, 50]]}}}]
    expanded = [{'id': 'doc', 'question_scopes': {'q': {'ranges': [[0, 500]]}}}]
    saved = {'scope_escalation': {'q': '근거 부족'}}
    with patch('kodame_intake.evaluation_runner.apply_plan', return_value=narrow), \
         patch('kodame_intake.evaluation_runner.set_stage'), \
         patch('kodame_intake.dac_scope_policy.expand_documents', return_value=expanded) as expand, \
         patch('kodame_intake.dac_scope_policy.escalation_questions') as decide, \
         patch('kodame_intake.evaluation_runner.prepare_documents') as prepare:
        assert prepare_review('run', ['source'], {'scopes': {}}, saved) == expanded
        expand.assert_called_once_with(['source'], narrow, saved['scope_escalation'])
        prepare.assert_called_once_with(expanded, allow_partial=True)
        decide.assert_not_called()


def test_new_expansion_is_saved_before_a_provider_failure():
    events = []
    with patch('kodame_intake.evaluation_runner.apply_plan', return_value=['narrow']), \
         patch('kodame_intake.evaluation_runner.set_stage', side_effect=lambda *a, **k: events.append((a, k))), \
         patch('kodame_intake.dac_scope_policy.expand_documents', return_value=['expanded']), \
         patch('kodame_intake.dac_scope_policy.escalation_questions', return_value={'q': '근거 부족'}), \
         patch('kodame_intake.evaluation_runner.prepare_documents', side_effect=lambda docs, **k: events.append(docs)):
        prepare_review('run', ['source'], {'scopes': {}})
    assert events[-2] == (('run', 'expanded_evidence'), {'scope_escalation': {'q': '근거 부족'}})
    assert events[-1] == ['expanded']
