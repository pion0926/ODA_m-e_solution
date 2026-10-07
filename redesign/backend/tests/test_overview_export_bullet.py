"""Portable rendering of the template's known PCP bullet without losing facts."""
from backend.oda_me.hwpx.patchers import normalize_hwpx_manifest_value


def test_pcp_legacy_bullet_becomes_visible_without_changing_text():
    source = "\U000f006f PCP: 검토 완료 / \U000f006f 공문: 확인 필요 / \U000f006f 사전조사: 2024년"
    actual = normalize_hwpx_manifest_value(7, "pcp_feasibility_review", source)
    assert actual == "○ PCP: 검토 완료 / ○ 공문: 확인 필요 / ○ 사전조사: 2024년"
    assert normalize_hwpx_manifest_value(7, "pcp_feasibility_review", actual) == actual


def test_other_source_symbols_and_fields_are_preserved():
    source = "\ue001 원문 기호 / \U000f006f 알려진 목록 기호"
    assert normalize_hwpx_manifest_value(7, "pcp_feasibility_review", source) == "\ue001 원문 기호 / ○ 알려진 목록 기호"
    assert normalize_hwpx_manifest_value(7, "project_purpose", source) == source
    assert normalize_hwpx_manifest_value(8, "pcp_feasibility_review", source) == source
    assert normalize_hwpx_manifest_value(7, "pcp_feasibility_review", None) is None
