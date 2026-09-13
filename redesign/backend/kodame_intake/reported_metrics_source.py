"""Find performance sheets by their table schema, never a client/year filename."""
from pathlib import Path
import re


def is_metrics_header(line: str) -> bool:
    cells = [re.sub(r"\s+", "", c) for c in line.split("|")]
    return len(cells) >= 7 and cells[0] in {"프로그램", "성과구분", "사업", "구분"} and cells[1] in {
        "성과지표", "성과지표명", "지표명", "객관적검증지표", "객관적검증지표(OVI)"
    } and cells[2] in {"목표", "목표값", "목표치"} and cells[3] in {"실적", "실적값", "실적치"}


def select_reported_metrics_source(documents: list[dict]) -> tuple[dict | None, str]:
    # _documents() supplies newest first. Unrecognized shapes are not guessed.
    for source in documents:
        if not source.get("extracted_path"):
            continue
        if Path(source.get("original_name", "")).suffix.lower() not in {".xlsx", ".xls", ".csv", ".tsv"}:
            continue
        try:
            text = Path(source["extracted_path"]).read_text(encoding="utf-8")
        except OSError:
            continue
        if any(is_metrics_header(line) for line in text.splitlines()):
            return source, text
    return None, ""
