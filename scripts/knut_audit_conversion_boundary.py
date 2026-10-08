"""Offline KNUT stored draft -> fixed HWPX slot preservation audit.

No database access, external service calls, deployment, or source modification.
Writes only the requested diagnostic JSON (not a submission-ready HWPX).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import zipfile
import xml.etree.ElementTree as ET

from backend.oda_me.hwpx.patchers import get_hwpx_xml_scope_text, parse_lesson_items
from kodame_intake.hwpx_adapters.registry import ADAPTER_BY_PART
from kodame_intake.hwpx_pipeline import normalize_section_text


def audit(snapshot: Path, template: Path) -> dict:
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    sections = {item["part_id"]: item["content"] for item in data["report/sections"]["body"]["items"]}
    result = {"scope": "offline semantic input and XML only; no browser/native-Hancom claims", "snapshot": str(snapshot), "sections": [], "warnings": []}
    elapsed_ms = []
    with zipfile.ZipFile(template) as archive:
        for part in ("project-background", "eval-matrix", "lessons"):
            adapter = ADAPTER_BY_PART[part]
            source = sections[part]
            began = time.perf_counter()
            normalized, report = normalize_section_text(part, source)
            prepared = adapter.prepare({"project": {}}, sections, {part: normalized}, [])
            xml = adapter.patch_xml(archive.read(adapter.spec.hwpx_path).decode("utf-8"), {"project": {}}, {part: prepared}).xml
            ET.fromstring(xml)
            elapsed_ms.append((time.perf_counter() - began) * 1000)
            visible = get_hwpx_xml_scope_text(xml)
            if part == "lessons":
                rows = parse_lesson_items(source)
                expected = [row[field] for row in rows for field in ("observation", "lesson", "category", "duplicate", "checklist")]
                entry = {"part_id": part, "record_count": len(rows), "field_count": len(expected), "all_fields_in_xml": all(value in visible for value in expected)}
                assert entry["all_fields_in_xml"], entry
            else:
                original = json.loads(source)["slots"]
                actual = json.loads(prepared)["slots"]
                expected = [value.split(") ", 1)[1] if part == "project-background" and ") " in value else value for value in original.values()]
                canonical = json.dumps(original, ensure_ascii=False, sort_keys=True)
                entry = {"part_id": part, "slot_count": len(original), "all_values_equal": original == actual, "all_full_bodies_in_xml": all(value in visible for value in expected), "input_values_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "technical_schema_visible": "section6_project_background_slots_v1" in visible or "section10_eval_matrix_slots_v1" in visible}
                assert entry["all_values_equal"] and entry["all_full_bodies_in_xml"] and not entry["technical_schema_visible"], entry
            entry["source_chars"] = len(source)
            entry["xml_sha256"] = hashlib.sha256(xml.encode()).hexdigest()
            result["sections"].append(entry)
            result["warnings"].extend(report["warnings"])
    # This is local conversion latency, explicitly not LLM response latency.
    durations = []
    for _ in range(100):
        began = time.perf_counter()
        normalize_section_text("project-background", sections["project-background"])
        durations.append((time.perf_counter() - began) * 1000)
    result["performance"] = {"scope": "local draft normalization only, excludes LLM/render/network", "samples": len(durations), "median_ms": round(statistics.median(durations), 3), "p95_ms": round(sorted(durations)[94], 3), "three_section_xml_conversion_ms": round(sum(elapsed_ms), 3)}
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=root / "output/knut-e2e-20260911/recovered.json")
    parser.add_argument("--output", type=Path, default=root / "output/knut-e2e-20260911/conversion-boundary-audit.json")
    args = parser.parse_args()
    report = audit(args.snapshot, root / "samples/5-1. 종료평가 결과보고서 placeholder.hwpx")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
