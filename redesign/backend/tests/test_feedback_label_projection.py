"""Feedback field labels are projected once without changing source facts."""
from pathlib import Path
import zipfile

import pytest

from backend.oda_me.hwpx.patchers import (
    get_hwpx_xml_scope_text,
    patch_hwpx_feedback_lessons_tables_xml,
)
from kodame_intake.hwpx_layout.recommendations import (
    _feedback_label_projection,
    _project_feedback_table_labels,
    style_recommendation_tables_xml,
)


LABELS = ("우선순위", "선정 사유", "완료기한", "점검주기", "확인자료")


@pytest.mark.parametrize(("value", "expected"), [
    ("우선순위: 우선순위: 상 | 선정 사유: 선정 사유: 12건 확인",
     "우선순위: 상 | 선정 사유: 12건 확인"),
    ("완료기한: 완료기한: 2028-06-30 | 점검주기: 점검주기: 분기 | 확인자료: 확인자료: 대장 5건",
     "완료기한: 2028-06-30 | 점검주기: 분기 | 확인자료: 대장 5건"),
    ("우선순위： 우선순위： 우선순위： 상", "우선순위： 상"),
    ("완료기한: 2028-06-30 | 점검주기: 분기", "완료기한: 2028-06-30 | 점검주기: 분기"),
    ("설명에서 완료기한: 완료기한: 이라고 반복함", "설명에서 완료기한: 완료기한: 이라고 반복함"),
    ("우선순위: 상이며 우선순위: 우선순위: 라는 인용을 남김",
     "우선순위: 상이며 우선순위: 우선순위: 라는 인용을 남김"),
    ("확인자료: 후속 확인자료: 20,000천원 대장", "확인자료: 후속 확인자료: 20,000천원 대장"),
    ("책임자: 책임자: 사업단", "책임자: 책임자: 사업단"),
])
def test_exact_field_prefix_projection_preserves_values_and_is_idempotent(value, expected):
    assert _feedback_label_projection(value, LABELS) == expected
    assert _feedback_label_projection(expected, LABELS) == expected


def test_only_feedback_body_reason_and_management_cells_change():
    def cell(text):
        return '<hp:tc><hp:p><hp:run><hp:t>' + text + '</hp:t></hp:run></hp:p></hp:tc>'
    header = '<hp:tr>' + cell('우선순위: 우선순위: 머리') * 5 + '</hp:tr>'
    other = '완료기한: 완료기한: 과제 원문 &amp; 5건'
    row = '<hp:tr>' + cell(other) * 3 + cell('우선순위: 우선순위: 상') + cell('완료기한: 완료기한: 2028-06-30 | 점검주기: 점검주기: 분기') + '</hp:tr>'
    source = '<hp:tbl>' + header + row + '</hp:tbl>'
    expected = source.replace(cell('우선순위: 우선순위: 상'), cell('우선순위: 상')).replace(
        cell('완료기한: 완료기한: 2028-06-30 | 점검주기: 점검주기: 분기'),
        cell('완료기한: 2028-06-30 | 점검주기: 분기'),
    )
    assert _project_feedback_table_labels(source) == expected
    assert source.count(other) == 3


def test_real_feedback_layout_projects_labels_and_preserves_body_and_lessons():
    template = Path(__file__).resolve().parents[3] / 'samples' / '5-1. 종료평가 결과보고서 placeholder.hwpx'
    with zipfile.ZipFile(template) as archive:
        xml = archive.read('Contents/section8.xml').decode('utf-8')
    sections = {
        'feedback': '\n'.join([
            '| 구분 | 제언 | 이해관계자 | 선정 사유 | 우선순위 | 완료기한 | 점검주기 | 후속 확인자료 |',
            '|---|---|---|---|---|---|---|---|',
            '| 운영 | 12건 및 20,000천원 대장 점검 | 사업단 | 점검 누락 | 우선순위: 상 | 완료기한: 2028-06-30 | 점검주기: 분기 | 대장 |',
        ]),
        'lessons': '교훈 1. (관리)\n- 교훈 내용: 우선순위: 우선순위: 라는 원문은 보존함.\n- 분야/일반 구분: 일반\n- 이전년도 교훈 중복 여부: 신규\n- 체크리스트 질문: 대장을 점검했는가?',
    }
    original = dict(sections)
    populated = patch_hwpx_feedback_lessons_tables_xml(xml, sections)
    assert '우선순위: 우선순위: 상' in get_hwpx_xml_scope_text(populated)
    styled, checks = style_recommendation_tables_xml(populated)
    visible = get_hwpx_xml_scope_text(styled)
    assert '우선순위: 상' in visible
    assert '완료기한: 2028-06-30 | 점검주기: 분기 | 확인자료: 대장' in visible
    assert '12건 및 20,000천원 대장 점검' in visible
    assert '우선순위: 우선순위: 라는 원문은 보존함' in visible
    assert sections == original
    assert checks['feedback_table_pages'] == 1
