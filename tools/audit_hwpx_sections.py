"""Static audit for the 27-section K-ODAME evaluation-report HWPX.

This checker deliberately does not mutate the document.  It exposes the
paragraph/table evidence used by the visual rHWP review so recurring layout
defects can be reproduced without relying on screenshots alone.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import zipfile
from pathlib import Path


PHYSICAL_SECTION_PATHS = tuple(f"Contents/section{index}.xml" for index in range(9))


def _texts(scope: str) -> list[str]:
    return [
        html.unescape(re.sub(r"<[^>]+>", "", item))
        for item in re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", scope, re.S)
    ]


def _tag_spans(xml: str, tag: str) -> list[tuple[int, int]]:
    token = re.compile(rf"</?{re.escape(tag)}\b[^>]*>")
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for match in token.finditer(xml):
        if match.group(0).startswith("</"):
            if stack:
                spans.append((stack.pop(), match.end()))
        elif not match.group(0).endswith("/>"):
            stack.append(match.start())
    return sorted(spans)


def _paragraphs(xml: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    leaf_paragraphs = [
        xml[start:end]
        for start, end in _tag_spans(xml, "hp:p")
        if xml[start:end].count("<hp:p") == 1
    ]
    for index, paragraph in enumerate(leaf_paragraphs):
        opening = re.match(r"<hp:p\b[^>]*>", paragraph)
        text = re.sub(r"\s+", " ", "".join(_texts(paragraph))).strip()
        result.append(
            {
                "index": index,
                "text": text,
                "para_pr": (
                    re.search(r'\bparaPrIDRef="([^"]+)"', opening.group(0)).group(1)
                    if opening and re.search(r'\bparaPrIDRef="([^"]+)"', opening.group(0))
                    else ""
                ),
                "tabs": re.findall(r"<hp:tab\b[^>]*/?>", paragraph),
                "line_breaks": len(re.findall(r"<hp:lineBreak\b", paragraph)),
                "table_count": len(re.findall(r"<hp:tbl\b", paragraph)),
            }
        )
    return result


def audit(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as package:
        sections = {
            section_path: package.read(section_path).decode("utf-8")
            for section_path in PHYSICAL_SECTION_PATHS
            if section_path in package.namelist()
        }
        header_xml = package.read("Contents/header.xml").decode("utf-8")

    section_results: dict[str, object] = {}
    issues: list[dict[str, object]] = []
    for section_path, xml in sections.items():
        paragraphs = _paragraphs(xml)
        visible = "\n".join(str(item["text"]) for item in paragraphs if item["text"])
        section_results[section_path] = {
            "paragraph_count": len(paragraphs),
            "table_count": len(re.findall(r"<hp:tbl\b", xml)),
            "paragraphs": paragraphs,
        }
        for paragraph in paragraphs:
            text = str(paragraph["text"])
            if re.fullmatch(r"[-ㅇ•·]", text):
                issues.append({"path": section_path, "paragraph": paragraph["index"], "code": "orphan-marker", "text": text})
            if re.search(r"(?:^|\s)#{1,6}\s|\*\*|__", text):
                issues.append({"path": section_path, "paragraph": paragraph["index"], "code": "markdown-residue", "text": text[:180]})
            if re.search(r"\([^()\n]{0,220}(?:pp?\.\s*\d+|\d+\s*쪽)[^()\n]{0,120}\)", text, re.I):
                issues.append({"path": section_path, "paragraph": paragraph["index"], "code": "inline-citation", "text": text[:180]})
            if len(text) > 420 and not paragraph["line_breaks"] and not paragraph["table_count"]:
                issues.append({"path": section_path, "paragraph": paragraph["index"], "code": "dense-paragraph", "characters": len(text), "text": text[:180]})
        for duplicate in ("7. 그 외 평가기준", "그 외 평가기준"):
            if visible.count(duplicate) > 1:
                issues.append({"path": section_path, "code": "duplicate-heading", "text": duplicate, "count": visible.count(duplicate)})

    toc = section_results.get("Contents/section1.xml", {}).get("paragraphs", [])
    toc_rows = []
    in_toc = False
    for paragraph in toc:
        text = str(paragraph["text"])
        if re.sub(r"\s+", "", text) == "목차":
            in_toc = True
            continue
        if not in_toc or not text:
            continue
        numeric = re.search(r"(\d+)\s*$", text)
        toc_rows.append(
            {
                "paragraph": paragraph["index"],
                "text": text,
                "page": numeric.group(1) if numeric else "",
                "para_pr": paragraph["para_pr"],
                "tab_count": len(paragraph["tabs"]),
            }
        )
    if toc_rows:
        for row in toc_rows:
            if row["text"].startswith(tuple(f"{index}." for index in range(1, 10))) and not row["page"]:
                issues.append({"path": "Contents/section1.xml", "paragraph": row["paragraph"], "code": "toc-page-missing", "text": row["text"]})

    return {
        "schema": "kodame-hwpx-section-audit-v1",
        "file": str(path.resolve()),
        "physical_sections": section_results,
        "toc_rows": toc_rows,
        "header_para_pr_count": len(re.findall(r"<hh:paraPr\b", header_xml)),
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hwpx", type=Path)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--ascii", action="store_true")
    args = parser.parse_args()
    result = audit(args.hwpx)
    if args.compact:
        result["physical_sections"] = {
            key: {name: value for name, value in item.items() if name != "paragraphs"}
            for key, item in result["physical_sections"].items()
        }
    print(json.dumps(result, ensure_ascii=args.ascii, indent=2))


if __name__ == "__main__":
    main()
