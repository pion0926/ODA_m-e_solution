from __future__ import annotations

import argparse
import collections
import html
import re
import zipfile
from pathlib import Path


def visible_text(xml: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", xml)).split())


def physical_row_height(row_xml: str) -> int:
    heights = [
        int(value)
        for value in re.findall(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', row_xml)
    ]
    return min(heights) if heights else 0


def inspect(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
        colors = collections.Counter(
            re.findall(r'<hh:charPr\b[^>]*\btextColor="([^"]+)"', header)
        )
        nonblack = [
            (char_id, color)
            for char_id, color in re.findall(
                r'<hh:charPr\b[^>]*\bid="(\d+)"[^>]*\btextColor="([^"]+)"',
                header,
            )
            if color.lower() not in {"#000000", "#ffffff"}
        ]
        print(f"char_colors={dict(colors)} nonblack={nonblack}")
        nonblack_map = dict(nonblack)
        used_nonblack: collections.Counter[str] = collections.Counter()
        for name in archive.namelist():
            if not re.fullmatch(r"Contents/section\d+\.xml", name):
                continue
            section_xml = archive.read(name).decode("utf-8")
            for char_id in re.findall(r'charPrIDRef="(\d+)"', section_xml):
                if char_id in nonblack_map:
                    used_nonblack[char_id] += 1
        print(f"used_nonblack={dict(used_nonblack)}")
        for char_id in (18, 43, 44, 58, 62, 63, 65, 74, 76, 79, 81, 82, 84, 85, 92):
            match = re.search(
                rf'<hh:charPr\b(?=[^>]*\bid="{char_id}")[\s\S]*?</hh:charPr>',
                header,
            )
            if match:
                opening = re.match(r"<hh:charPr\b[^>]*>", match.group(0))
                print(f"charPr={char_id} opening={opening.group(0) if opening else ''}")
        for section_path in (
            "Contents/section3.xml",
            "Contents/section4.xml",
            "Contents/section5.xml",
            "Contents/section7.xml",
            "Contents/section8.xml",
        ):
            xml = archive.read(section_path).decode("utf-8")
            print(
                f"### {section_path}: chars={len(xml)} pictures={xml.count('<hp:pic')}"
            )
            tables = re.findall(r"<hp:tbl\b.*?</hp:tbl>", xml, re.DOTALL)
            for index, table in enumerate(tables):
                rows = re.findall(r"<hp:tr\b.*?</hp:tr>", table, re.DOTALL)
                row_heights = [physical_row_height(row) for row in rows]
                text = visible_text(table)
                if section_path == "Contents/section4.xml" or (
                    section_path == "Contents/section5.xml"
                    and "성과지표" in text
                    and "기초선" in text
                ):
                    print(
                        f"table={index} rows={len(rows)} row_heights={row_heights} "
                        f"total={sum(row_heights)} text={text[:180]}"
                    )
                    print(
                        "  paraPrIDs="
                        + str(sorted(set(re.findall(r'paraPrIDRef="(\d+)"', table))))
                    )
                    for row_index, row in enumerate(rows):
                        print(
                            f"  row={row_index} height={row_heights[row_index]} "
                            f"text={visible_text(row)[:240]}"
                        )
                        if section_path == "Contents/section4.xml" and index == 0:
                            for cell in re.findall(r"<hp:tc\b.*?</hp:tc>", row, re.DOTALL):
                                col = re.search(r'<hp:cellAddr\b[^>]*\bcolAddr="(\d+)"', cell)
                                span = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', cell)
                                size = re.search(
                                    r'<hp:cellSz\b[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"',
                                    cell,
                                )
                                print(
                                    f"    cell col={col.group(1) if col else '?'} "
                                    f"rowSpan={span.group(1) if span else '1'} "
                                    f"size={size.groups() if size else ('?', '?')} "
                                    f"text={visible_text(cell)[:120]}"
                                )
            if section_path == "Contents/section8.xml":
                refs = re.findall(r'binaryItemIDRef="([^"]+)"', xml)
                print(f"image_refs={refs}")
                for picture_index, picture in enumerate(
                    re.findall(r"<hp:pic\b.*?</hp:pic>", xml, re.DOTALL),
                    start=1,
                ):
                    size = re.search(r"<hp:sz\b[^>]*/>", picture)
                    clip = re.search(r"<hp:imgClip\b[^>]*/>", picture)
                    dim = re.search(r"<hp:imgDim\b[^>]*/>", picture)
                    print(
                        f"picture={picture_index} size={size.group(0) if size else ''} "
                        f"clip={clip.group(0) if clip else ''} dim={dim.group(0) if dim else ''}"
                    )
            targets = {
                "4. 평가의 한계",
                "5. 평가팀 구성 및 시행체계",
                "3. 종합 평가 및 시사점",
                "(2) 비작동요인",
            }
            paragraphs = re.findall(r"<hp:p\b.*?</hp:p>", xml, re.DOTALL)
            for paragraph_index, paragraph in enumerate(paragraphs):
                text = visible_text(paragraph)
                if text not in targets:
                    continue
                previous = paragraphs[paragraph_index - 1] if paragraph_index else ""
                opening = re.match(r"<hp:p\b[^>]*>", paragraph)
                print(
                    f"heading={text} previous={visible_text(previous)[-120:]} "
                    f"opening={opening.group(0) if opening else ''}"
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    inspect(args.path)


if __name__ == "__main__":
    main()
