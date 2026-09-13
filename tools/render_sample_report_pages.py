from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


SAMPLE_DIR = Path("/app/samples")
OUTPUT_DIR = Path("/tmp/sample-report-pages")

REPORTS = [
    ("paraguay", "13. 파라과이", {"toc": 8, "matrix": 29, "feedback": 92, "references": 97}),
    ("ghana", "4. 가나", {"toc": 7, "matrix": 31, "feedback": 83, "references": 88}),
    ("bangladesh", "방글라데시", {"toc": 7, "matrix": 35, "feedback": 118, "references": 123}),
    ("uganda", "우간다", {"toc": 7, "matrix": 28, "feedback": 70, "references": 73}),
    ("cambodia", "캄보디아", {"toc": 6, "matrix": 47, "feedback": 96, "references": 100}),
]


def find_pdf(prefix: str) -> Path:
    matches = list(SAMPLE_DIR.glob(f"{prefix}*.pdf"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one PDF for {prefix!r}, got {len(matches)}")
    return matches[0]


def render_page(pdf_path: Path, page: int, output_path: Path) -> None:
    prefix = output_path.with_suffix("")
    subprocess.run(
        [
            "pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
            "-r", "120", "-png", str(pdf_path), str(prefix),
        ],
        check=True,
    )


def contact_sheet(kind: str, items: list[tuple[str, int, Path]]) -> None:
    thumb_width, thumb_height, label_height = 330, 470, 36
    sheet = Image.new("RGB", (thumb_width * len(items), thumb_height + label_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, page, image_path) in enumerate(items):
        with Image.open(image_path) as source:
            source = source.convert("RGB")
            source.thumbnail((thumb_width - 10, thumb_height - 10))
            x = index * thumb_width + (thumb_width - source.width) // 2
            y = label_height + (thumb_height - source.height) // 2
            sheet.paste(source, (x, y))
        draw.text((index * thumb_width + 8, 10), f"{label} p.{page}", fill="black")
    sheet.save(OUTPUT_DIR / f"sheet-{kind}.png")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sheets: dict[str, list[tuple[str, int, Path]]] = {}
    for label, prefix, pages in REPORTS:
        pdf_path = find_pdf(prefix)
        for kind, page in pages.items():
            output_path = OUTPUT_DIR / f"{label}-{kind}-p{page}.png"
            render_page(pdf_path, page, output_path)
            sheets.setdefault(kind, []).append((label, page, output_path))
    for kind, items in sheets.items():
        contact_sheet(kind, items)
        print(f"rendered {kind}: {len(items)} pages", flush=True)


if __name__ == "__main__":
    main()
