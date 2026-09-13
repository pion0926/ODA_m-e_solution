"""Read supplied PDF reference decks; retain page text and visual review sheets."""
import json
from pathlib import Path
import pdfplumber
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("brief15", Path("C:/Users/aimne/Downloads/남아공 DEEP 종료평가 결과보고 발표자료(1223).pdf")),
    ("detailed30", Path("C:/Users/aimne/Downloads/모잠비크 켈리만 중앙병원 건립사업 사후평가 용역_최종보고회 발표자료_최종 (1).pdf")),
]
out = ROOT / "tmp/presentation-samples-20260906"
out.mkdir(parents=True, exist_ok=True)
for key, path in SOURCES:
    with pdfplumber.open(path) as pdf:
        rows = []
        thumbnails = []
        for i, page in enumerate(pdf.pages, 1):
            rows.append({"page": i, "text": page.extract_text(), "width": page.width, "height": page.height})
            im = page.to_image(resolution=90).original.convert("RGB")
            im.save(out / f"{key}-{i:02d}.png")
            im.thumbnail((520, 390))
            thumb = Image.new("RGB", (540, 420), "#dddddd")
            thumb.paste(im, (10, 20))
            ImageDraw.Draw(thumb).text((10, 4), f"{key} / {i}", fill="black")
            thumbnails.append(thumb)
        for start in range(0, len(thumbnails), 6):
            sheet = Image.new("RGB", (1620, 840), "white")
            for j, thumb in enumerate(thumbnails[start:start+6]):
                sheet.paste(thumb, ((j % 3)*540, (j // 3)*420))
            sheet.save(out / f"{key}-sheet-{start//6+1}.png")
        (out / f"{key}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(key, len(rows), "pages", out)
