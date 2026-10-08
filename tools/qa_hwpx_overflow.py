"""Rebuild saved report locally without AI, changing no report/export DB rows."""
from io import BytesIO
from pathlib import Path
import json
import re
import zipfile
import xml.etree.ElementTree as ET

from kodame_intake.db import pool, tenant_context, connection
from kodame_intake import report_exporter as e
from kodame_intake.rhwp_renderer import analyze_rhwp

out = Path('/app/data/qa/hwpx-overflow-20260924')
out.mkdir(parents=True, exist_ok=True)
pool.open(wait=True)
try:
    with tenant_context(system=True), connection() as conn:
        row = conn.execute("SELECT project_id FROM report_exports WHERE status='failed' ORDER BY created_at DESC LIMIT 1").fetchone()
    with tenant_context(row['project_id']):
        context, sections, _ = e._pipeline_context()
        snapshot = e.capture_input_snapshot()
        digest = e.theory_visual_input_digest(context, sections, snapshot)
        visual = e.load_theory_artifact(digest) or e._load_cached_theory_visual_artifacts(digest)
        if not visual:
            from kodame_intake.theory_artifact_store import CACHE_ROOT
            cached = sorted((CACHE_ROOT / str(row['project_id'])).glob('*/manifest.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            if cached:
                # Layout-only QA, never a published export or cache mutation.
                visual = e.load_theory_artifact(cached[0].parent.name)
        assert visual, 'Existing cached visual required: QA never calls AI'
        output = BytesIO()
        checks = {}
        with zipfile.ZipFile(e.TEMPLATE_PATH) as source, zipfile.ZipFile(output, 'w') as target:
            for info in source.infolist():
                raw = source.read(info.filename)
                if info.filename == 'BinData/image1.png':
                    raw = visual['png']
                if info.filename == 'Contents/header.xml':
                    raw = e.finalize_report_header_layout(raw.decode('utf-8'), context['project']).xml.encode('utf-8')
                numbers = e.SECTION_GROUPS.get(info.filename, ())
                if numbers:
                    xml = raw.decode('utf-8')
                    for number in ((6, 7, 5) if info.filename == 'Contents/section3.xml' else numbers):
                        xml = e.apply_section_adapter_xml(number, xml, context, sections).xml
                    result = e.finalize_report_section_layout(info.filename, xml, context['project'], theory_png=visual['png'])
                    xml = e.cleanup_hwpx_placeholder_text_xml(result.xml)
                    xml = e._scrub_xml_reader_text(xml, context['project'], context.get('_raw_source_names', []))
                    if info.filename != 'Contents/section1.xml':
                        xml = re.sub(r'<hp:linesegarray>[\s\S]*?</hp:linesegarray>', '', xml)
                    if info.filename == 'Contents/section4.xml':
                        xml, _ = e.refresh_evaluation_matrix_split_heights_xml(xml)
                    ET.fromstring(xml)
                    checks[info.filename] = result.checks
                    raw = xml.encode('utf-8')
                target.writestr(info, raw)
        data = e.repack_hwpx_preserving_original_entries(output.getvalue())
        (out / 'candidate.hwpx').write_bytes(data)
        layout = e.validate_report_layout_contract(data)
        coverage = e._validate_semantic_coverage(data, context, sections)
        print(json.dumps({'layout': layout, 'coverage': coverage}, ensure_ascii=False), flush=True)
        assert layout['ok'] and coverage['ok']
        e._local_validate(data, context['project'], context.get('_raw_source_names', []))
        kordoc = e.analyze_hwpx(data, e.KORDOC_URL, stage='Overflow QA')
        e.toc_page_map_from_analysis(kordoc)
        e.validate_summary_page_span(kordoc, minimum_pages=4)
        print(json.dumps({'kordoc_pages': kordoc['render']['page_count']}, ensure_ascii=False), flush=True)
        rendered = analyze_rhwp(data, include_svgs=True)
        for page in rendered['page_texts']:
            svg = page.pop('svg')
            if any(code in str(page) for code in ('S1', 'M1', '상세', '기초선')):
                (out / f"detail-{page['page_number']}.svg").write_text(svg, encoding='utf-8')
        (out / 'render.json').write_text(json.dumps(rendered, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'pages': rendered['page_count']}, ensure_ascii=False), flush=True)
        from playwright.sync_api import sync_playwright
        samples = [p for p in rendered['page_texts'] if '기초선' in p.get('text', '') and '달성도' in p.get('text', '')][:2]
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            page = browser.new_page(viewport={'width': 1400, 'height': 1600})
            page.route('**/*', lambda route: route.abort())
            for sample in samples:
                path = out / f"detail-{sample['page_number']}.svg"
                page.set_content(path.read_text(encoding='utf-8'))
                page.locator('svg').screenshot(path=str(path.with_suffix('.png')))
            browser.close()
finally:
    pool.close()
