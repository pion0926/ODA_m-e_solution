"""Offline visual inspection of exact exported HWPX bytes; no AI or DB writes."""
import json,sys
from pathlib import Path
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
from kodame_intake.rhwp_renderer import analyze_rhwp
from kodame_intake.hwpx_layout.rendering import analyze_hwpx

source=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
data=source.read_bytes()
analysis=analyze_hwpx(data,'http://kodame-kordoc:8200',stage='QA')
(out/'kordoc.json').write_text(json.dumps(analysis,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'kordoc_pages':analysis['render']['page_count'],'overlap_risks':analysis['render']['line_overlap_risks']},ensure_ascii=False),flush=True)
render=analyze_rhwp(data,include_svgs=True)
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':1300,'height':1800})
    page.route('**/*',lambda route:route.abort())
    for row in render['page_texts']:
        svg=row.pop('svg');number=row['page_number']
        (out/f'page-{number:03}.svg').write_text(svg,encoding='utf-8')
        page.set_content('<style>body{margin:0;background:white}body>svg{display:block;width:900px;height:auto}</style>'+svg)
        page.evaluate('document.fonts.ready')
        page.locator('body>svg').screenshot(path=str(out/f'page-{number:03}.png'))
    browser.close()
(out/'rhwp.json').write_text(json.dumps(render,ensure_ascii=False,indent=2),encoding='utf-8')
paths=sorted(out.glob('page-*.png'))
for start in range(0,len(paths),9):
    sheet=Image.new('RGB',(1200,1770),'#dce3eb');draw=ImageDraw.Draw(sheet)
    for i,path in enumerate(paths[start:start+9]):
        im=Image.open(path).convert('RGB');im.thumbnail((386,546))
        x=(i%3)*400+(400-im.width)//2;y=(i//3)*590+30
        sheet.paste(im,(x,y));draw.text(((i%3)*400+12,(i//3)*590+8),path.stem,fill='black')
    sheet.save(out/f'contact-{start//9+1:02}.jpg',quality=90)
print(json.dumps({'rhwp_pages':render['page_count'],'sha256':render['source_sha256'],'output':str(out)}),flush=True)
