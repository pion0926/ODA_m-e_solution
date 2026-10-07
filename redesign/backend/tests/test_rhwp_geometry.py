"""Synthetic SVG geometry checks; no user reports, network or AI requests."""
import pytest

from kodame_intake.rhwp_geometry import GEOMETRY_VERSION, PAGE_LABEL_VERSION, SVG_GEOMETRY_SCRIPT, validate_rendered_geometry


@pytest.fixture(scope='module')
def page():
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        except api.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip('Chromium is not installed in this test environment')
            raise
        try:
            current = browser.new_page()
            current.route('**/*', lambda route: route.abort())
            current.set_content('<!doctype html><html><body></body></html>')
            yield current
        finally:
            browser.close()


def svg(content, *, rect='x="10" y="20" width="180" height="180"', transform=''):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300" viewBox="0 0 200 300">
      <defs><clipPath id="cell-clip-1"><rect {rect}/></clipPath></defs>
      <text x="20" y="14" font-size="12">Header</text>
      <g clip-path="url(#cell-clip-1)" {transform}>{content}</g>
      <text x="98" y="287" font-size="12">7</text></svg>'''


def kinds(result):
    return {error['kind'] for error in result['errors']}


def test_normal_header_footer_and_transformed_table_are_visible(page):
    result = page.evaluate(SVG_GEOMETRY_SCRIPT,
        svg('<text x="20" y="40" font-size="12">Value</text>', transform='transform="translate(1,2) scale(.9)"'))
    assert result['ok'] is True and result['footer_detected'] is True
    assert result['cell_count'] == 1


def test_text_present_in_svg_but_clipped_by_small_cell_is_rejected(page):
    result = page.evaluate(SVG_GEOMETRY_SCRIPT,
        svg('<text x="20" y="65" font-size="12">Hidden below cell</text>', rect='x="10" y="20" width="180" height="25"'))
    assert 'text_outside_cell' in kinds(result)


def test_long_table_row_outside_page_is_rejected_even_with_intact_text(page):
    result = page.evaluate(SVG_GEOMETRY_SCRIPT,
        svg('<text x="20" y="310" font-size="12">Overflow</text>', rect='x="10" y="20" width="180" height="310"'))
    assert {'cell_outside_page', 'text_outside_page', 'table_text_in_footer'} <= kinds(result)


def test_table_text_over_footer_fails_before_leaving_page(page):
    result = page.evaluate(SVG_GEOMETRY_SCRIPT,
        svg('<text x="20" y="285" font-size="12">Over footer</text>', rect='x="10" y="20" width="180" height="275"'))
    assert kinds(result) == {'table_text_in_footer'}


@pytest.mark.parametrize('hidden', ['fill-opacity="0"', 'visibility="hidden"', 'style="display:none"'])
def test_invisible_text_proxies_and_empty_cells_do_not_cause_false_overflow(page, hidden):
    result = page.evaluate(SVG_GEOMETRY_SCRIPT,
        svg(f'<text x="20" y="330" {hidden}>invisible proxy</text>', rect='x="10" y="20" width="180" height="340"'))
    assert result['ok'] is True and result['cell_count'] == 0


def test_visible_plain_text_outside_page_fails_without_any_table(page):
    source = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300"><text x="-30" y="40">Outside</text></svg>'
    result = page.evaluate(SVG_GEOMETRY_SCRIPT, source)
    assert kinds(result) == {'text_outside_page'}


def test_final_geometry_contract_rejects_missing_or_failed_proof():
    for geometry in ({}, {'version': GEOMETRY_VERSION, 'ok': False, 'errors': [{'kind': 'text_outside_cell'}]}):
        with pytest.raises(RuntimeError, match='잘린 보고서'):
            validate_rendered_geometry({'page_count': 1, 'page_texts': [{'page_number': 1, 'geometry': geometry}]})
    assert validate_rendered_geometry({'page_count': 1, 'page_texts': [{'page_number': 1,
        'geometry': {'version': GEOMETRY_VERSION, 'ok': True}}]})['ok'] is True


def printed_svg(body):
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300">'+body+'</svg>'


def footer_digits(y=287, *, hidden='', transform=''):
    # rHWP emits individual glyphs; their page label is 18, not 1 or 8.
    return f'<g {hidden} {transform}>'+''.join(
        f'<text x="{x}" y="{y}" font-size="12">{value}</text>'
        for x,value in ((80,'-'),(90,'1'),(98,'8'),(110,'-')))+'</g>'


@pytest.mark.parametrize('transform',['','transform="translate(2,-2)"'])
def test_printed_page_label_joins_split_glyphs_in_page_coordinates(page, transform):
    result=page.evaluate(SVG_GEOMETRY_SCRIPT,printed_svg(footer_digits(transform=transform)))
    assert result['page_label_version']==PAGE_LABEL_VERSION
    assert result['printed_page_label']=='18'
    assert result['printed_page_label_candidates']==1


@pytest.mark.parametrize('body',[
    footer_digits(hidden='style="display:none"'),
    footer_digits(y=140),
    '<defs><clipPath id="cell-clip-1"><rect x="0" y="0" width="200" height="300"/></clipPath></defs>'
        '<g clip-path="url(#cell-clip-1)">'+footer_digits()+'</g>',
    '<text x="95" y="287">18</text>',  # no configured page-number delimiters
])
def test_hidden_body_or_table_numbers_are_not_guessed_as_printed_labels(page,body):
    result=page.evaluate(SVG_GEOMETRY_SCRIPT,printed_svg(body))
    assert result['printed_page_label'] is None
    assert result['printed_page_label_candidates']==0


def test_multiple_printed_footer_candidates_fail_closed(page):
    result=page.evaluate(SVG_GEOMETRY_SCRIPT,printed_svg(footer_digits(287)+footer_digits(299)))
    assert result['printed_page_label'] is None
    assert result['printed_page_label_candidates']==2


@pytest.mark.parametrize('total,numbers', [
    (None, [1]), (True, [1]), (0, []), (201, list(range(1, 202))),
    (2, [1]), (1, [1, 2]), (2, [1, 1]), (2, [2, 1]),
    (2, [1, 3]), (1, [0]), (1, ['1']), (1, [True]),
])
def test_geometry_proof_requires_every_declared_page_exactly_once(total, numbers):
    rows = [{'page_number': number, 'geometry': {'version': GEOMETRY_VERSION, 'ok': True}}
            for number in numbers]
    with pytest.raises(RuntimeError, match='누락·중복'):
        validate_rendered_geometry({'page_count': total, 'page_texts': rows})


@pytest.mark.parametrize('pages', [None, {}, [None], ['page']])
def test_malformed_page_rows_are_not_accepted_as_geometry_proof(pages):
    with pytest.raises(RuntimeError, match='누락·중복'):
        validate_rendered_geometry({'page_count': 1, 'page_texts': pages})
