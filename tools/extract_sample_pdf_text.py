from __future__ import annotations

from pathlib import Path
import subprocess

from pypdf import PdfReader


SAMPLE_DIR = Path("/app/samples")
OUTPUT_DIR = Path("/app/tmp/sample-report-text")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_path in sorted(SAMPLE_DIR.glob("*.pdf")):
        output_path = OUTPUT_DIR / f"{pdf_path.stem}.txt"
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(output_path)],
            check=True,
        )
        reader = PdfReader(pdf_path)
        chars = len(output_path.read_text(encoding="utf-8", errors="replace"))
        print(f"{pdf_path.name}\tpages={len(reader.pages)}\tchars={chars}", flush=True)


if __name__ == "__main__":
    main()
