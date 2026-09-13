from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"
DEFAULT_OUTPUT = ROOT / "hwpx_sections" / "template.layout-profile.json"

NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
}


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//hp:t", NS)).strip()


def attrs(element: ET.Element | None) -> dict[str, str]:
    return dict(element.attrib) if element is not None else {}


def common(counter: Counter[str], limit: int = 8) -> list[dict[str, object]]:
    return [{"id": key, "count": count} for key, count in counter.most_common(limit)]


def header_profile(xml: bytes) -> dict:
    root = ET.fromstring(xml)
    hangul_fonts: dict[str, str] = {}
    for face in root.findall(".//hh:fontface", NS):
        if face.get("lang") != "HANGUL":
            continue
        for font in face.findall("hh:font", NS):
            hangul_fonts[str(font.get("id"))] = str(font.get("face") or "")

    char_properties = {}
    for item in root.findall(".//hh:charPr", NS):
        font_ref = item.find("hh:fontRef", NS)
        hangul_ref = font_ref.get("hangul") if font_ref is not None else None
        char_properties[str(item.get("id"))] = {
            "height_hwpunit": item.get("height"),
            "height_pt": round(int(item.get("height") or 0) / 100, 2),
            "text_color": item.get("textColor"),
            "shade_color": item.get("shadeColor"),
            "hangul_font_ref": hangul_ref,
            "hangul_font": hangul_fonts.get(str(hangul_ref), ""),
            "bold": item.find("hh:bold", NS) is not None,
            "italic": item.find("hh:italic", NS) is not None,
        }

    paragraph_properties = {}
    for item in root.findall(".//hh:paraPr", NS):
        align = item.find("hh:align", NS)
        line_spacing = item.find(".//hh:lineSpacing", NS)
        margin = item.find(".//hh:margin", NS)
        paragraph_properties[str(item.get("id"))] = {
            "align": align.get("horizontal") if align is not None else None,
            "vertical_align": align.get("vertical") if align is not None else None,
            "line_spacing_type": line_spacing.get("type") if line_spacing is not None else None,
            "line_spacing": line_spacing.get("value") if line_spacing is not None else None,
            "margin": {
                child.tag.rsplit("}", 1)[-1]: child.get("value")
                for child in (list(margin) if margin is not None else [])
            },
            "keep_with_next": (
                item.find("hh:breakSetting", NS).get("keepWithNext")
                if item.find("hh:breakSetting", NS) is not None else None
            ),
            "keep_lines": (
                item.find("hh:breakSetting", NS).get("keepLines")
                if item.find("hh:breakSetting", NS) is not None else None
            ),
        }

    styles = {}
    for item in root.findall(".//hh:style", NS):
        styles[str(item.get("id"))] = {
            "name": item.get("name"),
            "type": item.get("type"),
            "para_pr_id": item.get("paraPrIDRef"),
            "char_pr_id": item.get("charPrIDRef"),
        }
    return {
        "hangul_fonts": hangul_fonts,
        "char_properties": char_properties,
        "paragraph_properties": paragraph_properties,
        "styles": styles,
    }


def paragraph_profile(paragraph: ET.Element) -> dict:
    run = paragraph.find("hp:run", NS)
    return {
        "style_id": paragraph.get("styleIDRef"),
        "para_pr_id": paragraph.get("paraPrIDRef"),
        "char_pr_id": run.get("charPrIDRef") if run is not None else None,
        "text_preview": text_of(paragraph)[:120],
        "has_lineseg_cache": paragraph.find(".//hp:linesegarray", NS) is not None,
    }


def section_profile(xml: bytes) -> dict:
    root = ET.fromstring(xml)
    paragraphs = root.findall(".//hp:p", NS)
    tables = root.findall(".//hp:tbl", NS)
    cells = root.findall(".//hp:tc", NS)
    para_pr = Counter(str(item.get("paraPrIDRef") or "") for item in paragraphs)
    style_ids = Counter(str(item.get("styleIDRef") or "") for item in paragraphs)
    char_pr = Counter(
        str(run.get("charPrIDRef") or "")
        for paragraph in paragraphs
        for run in paragraph.findall("hp:run", NS)
    )
    table_profiles = []
    for index, table in enumerate(tables):
        table_cells = table.findall(".//hp:tc", NS)
        table_profiles.append({
            "index": index,
            "rows": int(table.get("rowCnt") or 0),
            "cols": int(table.get("colCnt") or 0),
            "cell_count": len(table_cells),
            "anchor": re.sub(r"\s+", "", text_of(table))[:80],
            "width_hwpunit": table.get("width"),
        })
    page_pr = root.find(".//hp:pagePr", NS)
    page_margin = page_pr.find("hp:margin", NS) if page_pr is not None else None
    return {
        "paragraph_count": len(paragraphs),
        "table_count": len(tables),
        "cell_count": len(cells),
        "image_count": len(root.findall(".//hp:pic", NS)),
        "lineseg_cache_count": len(root.findall(".//hp:linesegarray", NS)),
        "common_style_ids": common(style_ids),
        "common_para_pr_ids": common(para_pr),
        "common_char_pr_ids": common(char_pr),
        "tables": table_profiles,
        "page": {
            "width_hwpunit": page_pr.get("width") if page_pr is not None else None,
            "height_hwpunit": page_pr.get("height") if page_pr is not None else None,
            "landscape": page_pr.get("landscape") if page_pr is not None else None,
            "margin": attrs(page_margin),
        },
    }


def slot_style_profile(xml: bytes, manifest: dict) -> list[dict]:
    root = ET.fromstring(xml)
    paragraphs = root.findall(".//hp:p", NS)
    tables = root.findall(".//hp:tbl", NS)
    result = []
    for slot in manifest.get("slots", []):
        replacement = slot.get("replacement") or {}
        replacement_type = str(replacement.get("type") or "")
        item = {
            "slot_id": slot.get("slot_id"),
            "value_key": replacement.get("value_key"),
            "type": replacement_type,
            "enabled": bool((slot.get("llm_generation") or {}).get("enabled")),
        }
        paragraph_index = replacement.get("paragraph_index")
        if isinstance(paragraph_index, int) and 0 <= paragraph_index < len(paragraphs):
            item["paragraph_style"] = paragraph_profile(paragraphs[paragraph_index])
        if replacement_type in {"table_cell", "grade_table_cell"}:
            cell_index = int(replacement.get("cell_index") or -1)
            required = [str(value) for value in replacement.get("table_required_parts") or []]
            target = None
            for table in tables:
                if required and not all(value in text_of(table) for value in required):
                    continue
                cells = table.findall(".//hp:tc", NS)
                if 0 <= cell_index < len(cells):
                    target = cells[cell_index]
                    break
            if target is None:
                for table in tables:
                    cells = table.findall(".//hp:tc", NS)
                    if 0 <= cell_index < len(cells):
                        target = cells[cell_index]
                        break
            if target is not None:
                paragraph = target.find(".//hp:p", NS)
                cell_size = target.find("hp:cellSz", NS)
                item["cell_style"] = {
                    "cell_index": cell_index,
                    "width_hwpunit": cell_size.get("width") if cell_size is not None else None,
                    "height_hwpunit": cell_size.get("height") if cell_size is not None else None,
                    "paragraph": paragraph_profile(paragraph) if paragraph is not None else {},
                }
        result.append(item)
    return result


def build_profile(template: Path) -> dict:
    template_bytes = template.read_bytes()
    with zipfile.ZipFile(template, "r") as archive:
        names = archive.namelist()
        header = header_profile(archive.read("Contents/header.xml"))
        section_paths = sorted(
            name for name in names if re.fullmatch(r"Contents/section\d+\.xml", name)
        )
        physical_sections = {
            path: section_profile(archive.read(path)) for path in section_paths
        }

        logical_sections = []
        for folder in sorted((ROOT / "hwpx_sections").glob("Section*_*")):
            manifest_path = folder / "slots.review.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            section = manifest.get("section") or {}
            hwpx_path = str(section.get("hwpx_path") or "")
            logical_sections.append({
                "section_number": section.get("section_number"),
                "part_id": section.get("section_id"),
                "name": section.get("section_name"),
                "hwpx_path": hwpx_path,
                "slot_count": len(manifest.get("slots") or []),
                "enabled_slot_count": sum(
                    1 for slot in manifest.get("slots") or []
                    if (slot.get("llm_generation") or {}).get("enabled")
                ),
                "replacement_types": dict(Counter(
                    str((slot.get("replacement") or {}).get("type") or "")
                    for slot in manifest.get("slots") or []
                )),
                "slots": slot_style_profile(archive.read(hwpx_path), manifest),
            })
    logical_sections.sort(key=lambda item: int(item.get("section_number") or 0))
    return {
        "schema_version": "kodame-hwpx-layout-profile-v1",
        "template": {
            "file_name": template.name,
            "sha256": hashlib.sha256(template_bytes).hexdigest(),
            "size_bytes": len(template_bytes),
            "zip_entry_count": len(names),
            "physical_section_count": len(physical_sections),
        },
        "format_policy": {
            "font_policy": "inherit existing template charPr/style; never introduce a new font",
            "body_policy": "one semantic block per cloned template paragraph; no manual visual-width wrapping",
            "table_policy": "edit reviewed cells only; compact text before insertion; preserve widths, merges, borders, shading",
            "line_cache_policy": "drop all linesegarray in a changed physical section; mixed old/new caches are forbidden",
            "package_policy": "preserve every untouched ZIP entry byte-for-byte",
        },
        "header": header,
        "physical_sections": physical_sections,
        "logical_sections": logical_sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    template = Path(args.template).resolve()
    output = Path(args.output).resolve()
    profile = build_profile(template)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "sha256": profile["template"]["sha256"],
        "logical_sections": len(profile["logical_sections"]),
        "physical_sections": len(profile["physical_sections"]),
        "fonts": list(profile["header"]["hangul_fonts"].values()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
