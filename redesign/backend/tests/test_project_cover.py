import json
from unittest.mock import patch

from kodame_intake.project_cover import plan_business_roles, cover_text
from kodame_intake.project_identity import project_title_overview, project_title_section
from kodame_intake.hwpx_adapters.sections.section01_cover import prepare
from backend.oda_me.hwpx.patchers import section1_cover_slot_values, build_section_manifest_values
from kodame_intake import report_generator, report_sections


PLAN = '''[PDF 페이지 2]
협력대학 사업책임자
성 명 현지담당
국내 주관대학
기 관 명 테스트대학교 등 록 번 호 1234
사업(PM)책임자 : 김 사 업 (인)
[PDF 페이지 5]
주관대학
(사업책임자)
/공동대학
테스트대학교(김사업)
'''


def identity():
    return {'title': '현재 사업명', 'source': 'registered_project', 'document_id': 'plan',
            'business_roles': plan_business_roles(PLAN)}


def test_plan_roles_are_grounded_and_exclude_local_contacts():
    roles = plan_business_roles(PLAN)
    assert roles['project_manager']['text'] == '김사업'
    assert roles['lead_implementer']['text'] == '테스트대학교'
    for item in roles.values():
        loc = item['source_location']
        assert PLAN[loc['start']:loc['end']] == item['quote']


def test_conflicting_roles_are_not_silently_selected():
    roles = plan_business_roles(PLAN + '\n사업책임자: 다른사람\n')
    assert roles['project_manager']['text'] == '확인 필요'
    assert plan_business_roles('과거 평가책임자: 외부인')['project_manager']['text'] == '확인 필요'


def test_profile_preview_and_hwpx_share_business_roles_and_no_evaluator_prefix():
    overview = project_title_overview({}, identity())
    text = cover_text(overview)
    projected = project_title_section('cover', '이전 표지\n평가책임자 과거인\n평가수행기관 과거기관', identity())
    assert projected == text
    context = {'project': {'title': '현재 사업명', 'identity_resolution': identity()}}
    prepared = prepare(context, {'cover': '평가책임자 과거인'}, {}, [])
    slots = section1_cover_slot_values(context, {'cover': prepared})
    assert slots['evaluation_manager'] == '사업책임자 김사업'
    assert slots['evaluation_institution'] == '사업 수행기관 테스트대학교'
    assert '평가책임자' not in text and '과거인' not in prepared
    assert json.loads(prepared)['slots']['evaluation_manager'] == slots['evaluation_manager']
    notice = build_section_manifest_values(3, context, {'cover': prepared})
    assert '김사업' not in notice['lead_evaluator_line']
    assert '테스트대학교' not in notice['lead_evaluator_line']


def test_cover_context_does_not_load_dac_or_document_evidence():
    with patch('kodame_intake.project_overview.latest_plan_overview', return_value={'overview': {'project_name': {'text': 'Plan'}}}), \
            patch.object(report_generator, 'connection') as connection:
        overview, evaluations, dependencies = report_generator._context_for('cover', 1)
        assert overview['project_name']['text'] == 'Plan'
        assert evaluations == dependencies == []
        connection.return_value.__enter__.return_value.execute.assert_not_called()


def test_cover_connected_documents_use_only_current_overview_plan():
    with patch('kodame_intake.project_overview.latest_plan_overview', return_value={'source_document_ids': ['plan']}), \
            patch.object(report_sections, 'connection') as connection:
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [{'id': 'plan', 'extracted_path': '/private/path'}]
        docs = report_sections.section_documents('cover')
        sql, args = conn.execute.call_args.args
        assert "upload_role='project_plan'" in sql and 'active_intake_documents' in sql
        assert args == (['plan'],)
        assert docs[0]['matched_via'] == 'project-basic-info'
        assert 'extracted_path' not in docs[0]


def test_cover_generation_never_calls_external_ai_or_evaluator_lookup():
    overview = project_title_overview({}, identity())
    with patch.object(report_generator, 'connection') as connection, \
            patch('kodame_intake.project_lifecycle.capture_input_snapshot', return_value={}), \
            patch.object(report_generator, '_context_for', return_value=(overview, [], [])), \
            patch.object(report_generator, 'section_documents', return_value=[{'id': 'plan'}]), \
            patch.object(report_generator, 'check_cancelled'), \
            patch.object(report_generator, '_verified_execution_scope', side_effect=AssertionError('Evaluator lookup forbidden')), \
            patch.object(report_generator.httpx, 'Client', side_effect=AssertionError('External AI forbidden')):
        conn = connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = {'section_number': 1}
        result = report_generator._generate_report_section('cover', '기본정보로 갱신')
        assert result['status'] == 'draft'
        saved = conn.execute.call_args.args[1]
        assert '사업책임자 김사업' in saved[0]
        assert saved[1].obj['source_policy'] == 'project-basic-info-only-v1'
        assert saved[3].obj == ['plan']
