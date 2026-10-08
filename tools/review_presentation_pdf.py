"""Render app-produced PDFs to review images (does not author a deck)."""
import sys
from pathlib import Path
import pdfplumber
from PIL import Image, ImageDraw

for argument in sys.argv[1:]:
    path = Path(argument)
    target = path.parent / path.stem
    target.mkdir(parents=True, exist_ok=True)
    thumbs = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            image = page.to_image(resolution=130).original.convert('RGB')
            image.save(target/f'page-{i:02d}.png')
            image.thumbnail((570,425))
            thumb = Image.new('RGB',(590,455),'#dddddd')
            thumb.paste(image,(10,24))
            ImageDraw.Draw(thumb).text((10,6),f'{path.stem} / {i}',fill='black')
            thumbs.append(thumb)
        for start in range(0,len(thumbs),6):
            sheet = Image.new('RGB',(1770,910),'white')
            for j,thumb in enumerate(thumbs[start:start+6]):
                sheet.paste(thumb,((j%3)*590,(j//3)*455))
            sheet.save(target/f'sheet-{start//6+1}.png')
    print(path, len(thumbs), 'pages', flush=True)
