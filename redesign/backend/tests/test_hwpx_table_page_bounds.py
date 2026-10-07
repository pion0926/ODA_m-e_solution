"""Long rationale cells and landscape headings must fit without dropping text."""
from pathlib import Path
import re
import zipfile

import pytest
from backend.oda_me.hwpx.patchers import (
    find_hwpx_grade_table_span_xml, find_hwpx_tag_spans, get_hwpx_xml_scope_text,
    set_hwpx_table_cell_text_xml, GRADE_QUESTION_REASON_CELLS,
)
from kodame_intake.hwpx_layout.grade_table import (
    style_grade_table_xml, grade_question_row_height, GRADE_QUESTION_LINE_HEIGHT,
)
from kodame_intake.hwpx_layout.overflow import resolve_detail_text
from kodame_intake.hwpx_layout.recommendations import (
    recommendation_page_budget, _split_table_xml,
)


def grade_template():
    path=Path(__file__).resolve().parents[3]/'samples'/'5-1. 종료평가 결과보고서 placeholder.hwpx'
    with zipfile.ZipFile(path) as z:return z.read('Contents/section2.xml').decode()


@pytest.mark.parametrize('length',[800,5000])
def test_grade_long_reason_is_measured_and_preserved_on_bounded_pages(length):
    xml=grade_template();a,b=find_hwpx_grade_table_span_xml(xml)
    original=('긴 평가 근거와 검토 한계를 원문 그대로 보존함. '*250)[:length]
    table,_=set_hwpx_table_cell_text_xml(xml[a:b],GRADE_QUESTION_REASON_CELLS[7],original)
    # The content measurement must exceed the former nine-line clamp.
    row=next(table[c:d] for c,d in find_hwpx_tag_spans(table,'hp:tr') if original.strip() in get_hwpx_xml_scope_text(table[c:d]))
    assert grade_question_row_height(row)>GRADE_QUESTION_LINE_HEIGHT*9+200
    styled,_=style_grade_table_xml(xml[:a]+table+xml[b:])
    tables=[styled[c:d] for c,d in find_hwpx_tag_spans(styled,'hp:tbl')
            if '핵심 질문' in get_hwpx_xml_scope_text(styled[c:d])]
    for page,t in enumerate(tables):
        height=int(re.search(r'<hp:sz\b[^>]*height="(\d+)"',t)[1])
        assert height<=(58000 if page==0 else 65000)
    visible=''.join(get_hwpx_xml_scope_text(t) for t in tables)
    if original.strip() not in visible:
        references=[get_hwpx_xml_scope_text(t[c:d]) for t in tables for c,d in find_hwpx_tag_spans(t,'hp:tc')
                    if re.search(r'\[G\d+ 상세\]',get_hwpx_xml_scope_text(t[c:d]))]
        assert original.strip() in [resolve_detail_text(styled,text).strip() for text in references]


def test_landscape_table_budget_leaves_room_for_visible_headings():
    xml='<hp:pagePr landscape="NARROWLY" width="59528" height="84188"><hp:margin top="5669" bottom="5669" header="0" footer="0"/></hp:pagePr>'
    budget=recommendation_page_budget(xml)
    assert budget==42190
    assert recommendation_page_budget(xml,42000)==42000
    assert recommendation_page_budget(xml.replace('NARROWLY','WIDELY'))==60000


def test_landscape_first_feedback_table_does_not_push_headings_to_empty_page():
    # Same physical pattern as the production defect: a 12209 header and
    # three individually safe rows total 46739, leaving no heading room.
    heights=[12209,13070,10730,10730]
    characters=[0,*[((h-200)//1170)*4 for h in heights[1:]]]
    rows=''.join(f'<hp:tr><hp:tc><hp:cellAddr rowAddr="{i}" colAddr="0"/><hp:cellSpan rowSpan="1" colSpan="1"/><hp:cellSz width="72511" height="{h}"/><hp:p><hp:run><hp:t>{"가"*characters[i] if i else "머리"}</hp:t></hp:run></hp:p></hp:tc></hp:tr>' for i,h in enumerate(heights))
    # Use actual measured narrow cells to fill two body rows on the first
    # page, with enough text to trigger the height-based (not row-count) split.
    rows=rows.replace('width="72511"','width="1200"')
    table='<hp:tbl id="1" rowCnt="4"><hp:sz height="46739"/>'+rows+'</hp:tbl>'
    result,pages=_split_table_xml(table,header_rows=1,rows_per_page=3,max_table_height=42190)
    assert pages>=2
    for a,b in find_hwpx_tag_spans(result,'hp:tbl'):
        assert int(re.search(r'<hp:sz\b[^>]*height="(\d+)"',result[a:b])[1])<=42190
    assert get_hwpx_xml_scope_text(result).count('가')==sum(characters)
