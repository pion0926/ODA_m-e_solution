from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

from backend.oda_me.hwpx.patchers import (
    find_hwpx_all_tag_spans,
    get_hwpx_xml_scope_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit parenthetical detail labels in an HWPX report.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    result: dict[str, object] = {
        "path": str(args.path),
        "labeled_detail_paragraphs": 0,
        "mixed_style_ok": 0,
        "style_errors": [],
        "declarative_endings": [],
        "duplicate_detail_labels": [],
        "effectiveness_example": {},
        "crosscutting_example": {},
    }
    effectiveness_texts: list[str] = []
    crosscutting_texts: list[str] = []
    with zipfile.ZipFile(args.path, "r") as archive:
        for name in archive.namelist():
            if not re.fullmatch(r"Contents/section\d+\.xml", name):
                continue
            xml = archive.read(name).decode("utf-8")
            current_parent = ""
            labels_for_parent: set[str] = set()
            in_crosscutting = False
            for start, end in find_hwpx_all_tag_spans(xml, "hp:p"):
                paragraph = xml[start:end]
                text = get_hwpx_xml_scope_text(paragraph).strip()
                if text.startswith("ㅇ "):
                    current_parent = text[2:].strip()
                    labels_for_parent = set()
                elif re.match(r"^\d+\.\s+", text):
                    current_parent = ""
                    labels_for_parent = set()
                if name == "Contents/section7.xml" and text == "6. 범분야 이슈":
                    in_crosscutting = True
                    crosscutting_texts.append(text)
                elif in_crosscutting and text == "7. 그 외 평가기준":
                    in_crosscutting = False
                elif in_crosscutting and (text.startswith("ㅇ ") or text.startswith("- (")):
                    crosscutting_texts.append(text)
                if name == "Contents/section6.xml" and (
                    text in {"3. 효과성", "ㅇ 산출 및 성과 달성"}
                    or text.startswith("- (산출·성과 진척)")
                ):
                    effectiveness_texts.append(text)
                if not re.match(r"^-\s+\([^()]{2,15}\)\s+\S", text):
                    continue
                label = re.match(r"^-\s+\(([^()]{2,15})\)\s+", text)
                if label:
                    label_text = label.group(1).strip()
                    if label_text in labels_for_parent:
                        result["duplicate_detail_labels"].append(
                            {"section": name, "parent": current_parent, "label": label_text}
                        )
                    labels_for_parent.add(label_text)
                result["labeled_detail_paragraphs"] += 1
                runs = [
                    (int(char_id), get_hwpx_xml_scope_text(body))
                    for char_id, body in re.findall(
                        r'<hp:run\b[^>]*charPrIDRef="(\d+)"[^>]*>(.*?)</hp:run>',
                        paragraph,
                        re.DOTALL,
                    )
                ]
                expected = (
                    len(runs) >= 3
                    and runs[0][0] == 28
                    and runs[0][1] == "- "
                    and runs[1][0] == 18
                    and re.fullmatch(r"\([^()]{2,15}\)", runs[1][1]) is not None
                    and runs[2][0] == 28
                    and runs[2][1].startswith(" ")
                )
                if expected:
                    result["mixed_style_ok"] += 1
                else:
                    result["style_errors"].append({"section": name, "text": text[:160], "runs": runs[:4]})
                if re.search(r"(?:다|습니다)\.", text):
                    result["declarative_endings"].append({"section": name, "text": text[:200]})
    result["effectiveness_example"] = {
        "heading_found": "3. 효과성" in effectiveness_texts,
        "topic_found": "ㅇ 산출 및 성과 달성" in effectiveness_texts,
        "detail": next((item for item in effectiveness_texts if item.startswith("- (산출·성과 진척)")), ""),
    }
    result["crosscutting_example"] = {
        "heading_found": "6. 범분야 이슈" in crosscutting_texts,
        "parent_found": "ㅇ 젠더·인권·취약계층 고려" in crosscutting_texts,
        "labels": [
            match.group(1)
            for item in crosscutting_texts
            if (match := re.match(r"^-\s+\(([^()]{2,15})\)\s+", item))
        ],
    }
    result["ok"] = bool(
        result["labeled_detail_paragraphs"]
        and result["labeled_detail_paragraphs"] == result["mixed_style_ok"]
        and not result["style_errors"]
        and not result["declarative_endings"]
        and not result["duplicate_detail_labels"]
        and result["effectiveness_example"]["heading_found"]
        and result["effectiveness_example"]["topic_found"]
        and result["effectiveness_example"]["detail"]
        and result["crosscutting_example"]["heading_found"]
        and result["crosscutting_example"]["parent_found"]
        and len(result["crosscutting_example"]["labels"]) >= 2
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
