"""Render exported document bytes offline; no account, API or DB access."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from kodame_intake.rhwp_renderer import analyze_rhwp

source, destination = map(Path, sys.argv[1:3])
destination.mkdir(parents=True, exist_ok=True)
result = analyze_rhwp(source.read_bytes(), include_svgs=True)
with sync_playwright() as runtime:
    browser = runtime.chromium.launch()
    page = browser.new_page(viewport={'width': 1200, 'height': 1600})
    page.route('**/*', lambda route: route.abort())
    for item in result['page_texts']:
        svg = item.pop('svg')
        if item['page_number'] not in (1, 3):
            continue
        path = destination / f"page-{item['page_number']:03}"
        path.with_suffix('.svg').write_text(svg, encoding='utf-8')
        page.set_content('<style>body{margin:0;background:white}body>svg{display:block;width:900px;height:auto}</style>' + svg)
        page.evaluate('document.fonts.ready')
        page.locator('body>svg').screenshot(path=str(path.with_suffix('.png')))
    browser.close()
(destination / 'render.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'pages': result['page_count'], 'sha256': result['source_sha256']}))
