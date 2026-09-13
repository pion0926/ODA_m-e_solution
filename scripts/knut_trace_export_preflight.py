"""Read-only export preparation diagnostic; refuses external model calls."""
from unittest.mock import patch
from kodame_intake.db import open_pool, tenant_context
from kodame_intake.report_exporter import _pipeline_context, _load_cached_theory_visual_artifacts
from kodame_intake.theory_visual import request_theory_visual_plan

open_pool()
with tenant_context('ee8b8006-96eb-4f69-9778-233c42f6f009'):
    context, sections, report = _pipeline_context()
    print('context prepared', flush=True)
    import zipfile
    from kodame_intake.report_exporter import TEMPLATE_PATH, apply_section_adapter_xml, finalize_report_section_layout
    from kodame_intake.hwpx_layout.spacing import _top_level_paragraphs, _visible_text
    print('achievement headings', [line for line in sections['achievement'].splitlines() if '종합' in line], flush=True)
    with zipfile.ZipFile(TEMPLATE_PATH) as archive:
        xml = archive.read('Contents/section5.xml').decode('utf-8')
    xml = apply_section_adapter_xml(14, xml, context, sections).xml
    xml = finalize_report_section_layout('Contents/section5.xml', xml, context['project']).xml
    for _, _, paragraph in _top_level_paragraphs(xml):
        if '<hp:tbl' not in paragraph:
            print(paragraph[:160], _visible_text(paragraph)[:150], flush=True)
    print('cache present', bool(_load_cached_theory_visual_artifacts()), flush=True)
    with patch('httpx.Client.post', side_effect=RuntimeError('PREFLIGHT_OK: external call intentionally stopped')):
        request_theory_visual_plan(context, sections)
