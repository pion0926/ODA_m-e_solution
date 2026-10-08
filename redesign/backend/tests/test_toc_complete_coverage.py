from io import BytesIO
from pathlib import Path
import zipfile

from backend.oda_me.hwpx.patchers import _toc_labeled_numeric_target
from backend.oda_me.hwpx.toc_registry import TOC_ROWS, TOC_LABELS
from kodame_intake.hwpx_layout.toc import patch_toc_page_numbers, validate_toc_page_numbers
from kodame_intake.hwpx_layout.rendering import REQUIRED_TOC_KEYS, toc_page_map_from_analysis
from kodame_intake.report_rhwp_verification import rhwp_page_map


def test_all_26_rows_share_both_renderers_and_validator():
    rows = [{'page_number': i+3, 'text': label} for i, (_, label, _) in enumerate(TOC_ROWS)]
    payload = {'page_count': 28, 'page_texts': [{'page_number': 1, 'text': '표지'}, {'page_number': 2, 'text': '목차'}, *rows]}
    pages = rhwp_page_map(payload)
    assert set(pages) == REQUIRED_TOC_KEYS == set(TOC_LABELS)
    assert toc_page_map_from_analysis({'render': payload}) == pages
    template = next((Path(__file__).resolve().parents[3]/'samples').glob('*placeholder.hwpx')).read_bytes()
    output, _ = patch_toc_page_numbers(template, pages)
    output, _ = patch_toc_page_numbers(output, pages)
    verified = validate_toc_page_numbers(output, pages)
    assert verified['ok'], verified
    assert verified['required_count'] == verified['checked_count'] == 26
    # Missing previously-unchecked grade/chapter rows must fail the gate.
    del pages['grade_page']
    assert not validate_toc_page_numbers(output, pages)['ok']


def test_missing_heading_number_never_uses_neighbour_number():
    xml = '<hp:p><hp:run><hp:p><hp:run><hp:t>Ⅰ. 평가결과 요약</hp:t></hp:run></hp:p><hp:p><hp:run><hp:t>1. 국문 요약</hp:t><hp:t>7</hp:t></hp:run></hp:p></hp:run></hp:p>'
    assert _toc_labeled_numeric_target(xml, 'Ⅰ. 평가결과 요약') is None
    assert _toc_labeled_numeric_target(xml, '1. 국문 요약')[3][2] == '7'


def test_missing_six_major_rows_rejected_in_old_export_shape():
    template = next((Path(__file__).resolve().parents[3]/'samples').glob('*placeholder.hwpx')).read_bytes()
    pages = {key: str(i+3) for i, (key, _, _) in enumerate(TOC_ROWS)}
    old_pages = {key: value for key, value in pages.items() if key != 'grade_page' and '_chapter_' not in key}
    output, _ = patch_toc_page_numbers(template, old_pages)
    check = validate_toc_page_numbers(output, pages)
    assert not check['ok']
    assert len(check['mismatches']) >= 6
