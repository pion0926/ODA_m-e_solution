from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SECTIONS_PATH = ROOT / "data" / "sample_analysis" / "nepal_mugu_27_sections.json"

SECTION_TO_PART_ID = {
    "title": "cover",
}


def _short_text(value: str, limit: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def good_example_for(section_id: str, limit: int = 3500) -> dict:
    if not SAMPLE_SECTIONS_PATH.exists():
        return {
            "available": False,
            "message": "Run tools/build_sample_report_examples.py to create section examples.",
        }
    try:
        payload = json.loads(SAMPLE_SECTIONS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"Could not read sample examples: {exc}"}
    part_id = SECTION_TO_PART_ID.get(str(section_id), str(section_id))
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    section = next((item for item in sections if str(item.get("partId")) == part_id), None)
    if not section:
        return {"available": False, "part_id": part_id, "message": "No matching sample section."}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return {
        "available": True,
        "source_file": source.get("fileName", ""),
        "part_id": part_id,
        "section_id": section_id,
        "title": section.get("title", ""),
        "status": section.get("status", ""),
        "usage_rule": (
            "잘 작성된 실제 보고서 예시다. 구조, 논리 전개, 문체, 근거 밀도만 참고하고 "
            "문장/표현을 복사하거나 가깝게 패러프레이즈하지 않는다."
        ),
        "example_text": _short_text(section.get("exampleText", ""), limit),
    }
