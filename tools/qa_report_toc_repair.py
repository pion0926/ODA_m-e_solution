"""Offline regression against an existing exported file; no DB/AI access."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from kodame_intake.rhwp_renderer import analyze_rhwp, finalize_toc_with_rhwp
from kodame_intake.hwpx_layout.rendering import analyze_hwpx, toc_page_map_from_analysis

source, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
data, metadata = finalize_toc_with_rhwp(source.read_bytes())
(out/'toc-repaired.hwpx').write_bytes(data)
(out/'toc-validation.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
rendered = analyze_rhwp(data, include_svgs=True)
analysis = analyze_hwpx(data, 'http://kodame-kordoc:8200', stage='목차 개발 검증')
assert len(toc_page_map_from_analysis(analysis)) == 26
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1300, 'height': 1800})
    page.route('**/*', lambda route: route.abort())
    svg = rendered['page_texts'][1]['svg']
    page.set_content('<style>body{margin:0;background:white}body>svg{display:block;width:900px;height:auto}</style>'+svg)
    page.evaluate('document.fonts.ready')
    page.locator('body>svg').screenshot(path=str(out/'toc.png'))
    browser.close()
print(json.dumps({'pages': rendered['page_count'], 'checked_toc_entries': len(metadata['page_map']),
                  'visible_validation': metadata['visible_validation']}, ensure_ascii=False), flush=True)
