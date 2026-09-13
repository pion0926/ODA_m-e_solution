"""Ephemeral, tenant-scoped section proof using the production HWPX adapters.

No section/report writes, export jobs, LLM calls or client-provided file paths.
The document is a proof, not a new source of truth: edits remain report content.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import time
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path

from backend.oda_me.hwpx.patchers import (
    cleanup_hwpx_placeholder_text_xml, find_hwpx_tag_spans,
    get_hwpx_xml_scope_text, repack_hwpx_preserving_original_entries,
)
from .db import connection
from .hwpx_adapters.registry import SPEC_BY_PART, apply_section_adapter_xml
from .hwpx_layout.pipeline import finalize_report_header_layout, finalize_report_section_layout
from .hwpx_layout.tables import refresh_evaluation_matrix_split_heights_xml
from .hwpx_layout.toc_columns import fixed_toc_columns
from .report_exporter import (
    EXPORT_DIR, TEMPLATE_PATH, TEMPLATE_SHA256,
    _pipeline_context, _scrub_xml_reader_text,
)

BOUNDARY_PATH = Path("/app/config/report_section_preview.json")
if not BOUNDARY_PATH.exists():
    BOUNDARY_PATH = Path.cwd() / "config/report_section_preview.json"


def _heading(text: str) -> str:
    text = re.sub(r"<[^>]*>", "", html.unescape(text))
    return re.sub(r"[^a-z0-9가-힣]", "", unicodedata.normalize("NFKC", text).lower())


def top_level_paragraphs(xml: str) -> list[tuple[int, int]]:
    result, depth, start = [], 0, 0
    for match in re.finditer(r"</?hp:p(?=[\s>])[^>]*>", xml):
        tag = match.group()
        if tag.startswith("</"):
            depth -= 1
            if depth == 0:
                result.append((start, match.end()))
        else:
            if depth == 0:
                start = match.start()
            if tag.endswith("/>"):
                if depth == 0:
                    result.append((start, match.end()))
            else:
                depth += 1
    return result


def isolate_section_xml(xml: str, part_id: str, boundaries: dict | None = None) -> str:
    rules = boundaries or json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))["boundaries"]
    start_label, end_label = rules[part_id]
    paragraphs = top_level_paragraphs(xml)
    if not paragraphs:
        raise ValueError("미리보기 문단이 없습니다.")

    def locate(label: str | None, fallback: int, after: int = 0) -> int:
        if label is None:
            return fallback
        key = _heading(label)
        for index, (start, end) in enumerate(paragraphs):
            if index < after:
                continue
            para = xml[start:end]
            # Some headings share an anchor paragraph with the following table.
            # Match the heading outside tables, never their nested cell text.
            for a, b in reversed(find_hwpx_tag_spans(para, "hp:tbl")):
                para = para[:a] + para[b:]
            if _heading(get_hwpx_xml_scope_text(para)) == key:
                return index
        raise ValueError(f"섹션 경계를 찾지 못했습니다: {part_id} / {label}")

    start_index = locate(start_label, 0)
    end_index = locate(end_label, len(paragraphs), start_index + 1)
    selected = [xml[a:b] for a, b in paragraphs[start_index:end_index]]
    while selected and not get_hwpx_xml_scope_text(selected[-1]).strip() and not re.search(r"<hp:(?:tbl|pic|secPr)\b", selected[-1]):
        selected.pop()
    if not selected:
        raise ValueError("선택 섹션이 비었습니다.")
    # Copy the same paper/orientation settings, never inherit a prior section's
    # content. A preview starts at local page 1, not a guessed full-report page.
    if not any("<hp:secPr" in item for item in selected):
        spans = find_hwpx_tag_spans(xml, "hp:secPr")
        if spans:
            sec_pr = xml[spans[0][0]:spans[0][1]]
            selected[0] = re.sub(r"(<hp:run\b[^>]*>)", lambda m: m.group() + sec_pr, selected[0], count=1)
    selected[0] = re.sub(r'pageBreak="1"', 'pageBreak="0"', selected[0], count=1)
    body = "".join(selected)
    body = re.sub(r'(<hp:startNum\b[^>]*\bpage=")[^"]*', r'\g<1>1', body)
    opening = re.search(r"<hs:sec\b[^>]*>", xml)
    if not opening:
        raise ValueError("HWPX 구역 선언이 없습니다.")
    return xml[:opening.end()] + body + "</hs:sec>"


def package_single_section(template: bytes, section_xml: str, header_xml: str,
                           theory_png: bytes | None = None) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(template)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            name = info.filename
            raw = source.read(name)
            if re.fullmatch(r"Contents/section\d+\.xml", name):
                if name != "Contents/section0.xml":
                    continue
                raw = section_xml.encode("utf-8")
            elif name == "Contents/header.xml":
                raw = re.sub(r'\bsecCnt="\d+"', 'secCnt="1"', header_xml).encode("utf-8")
            elif name == "Contents/content.hpf":
                text = raw.decode("utf-8")
                text = re.sub(r'<opf:item\b(?=[^>]*\bhref="Contents/section\d+\.xml")[^>]*/>', '', text)
                text = text.replace("</opf:manifest>", '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/></opf:manifest>')
                text = re.sub(r'<opf:itemref\b(?=[^>]*\bidref="section\d+")[^>]*/>', '', text)
                text = text.replace("</opf:spine>", '<opf:itemref idref="section0" linear="yes"/></opf:spine>')
                raw = text.encode("utf-8")
            elif name == "Preview/PrvText.txt":
                raw = get_hwpx_xml_scope_text(section_xml).encode("utf-8")
            elif name.startswith("Preview/"):
                continue
            elif name == "BinData/image1.png" and theory_png:
                raw = theory_png
            target.writestr(info, raw)
    # The full-report repacker deliberately restores missing original entries;
    # using it here would reintroduce all eight removed physical sections.
    return out.getvalue()


def build_section_preview(part_id: str, content: str) -> dict:
    started = time.perf_counter()
    spec = SPEC_BY_PART[part_id]
    template = TEMPLATE_PATH.read_bytes()
    if hashlib.sha256(template).hexdigest() != TEMPLATE_SHA256:
        raise ValueError("고정 원본 양식이 변경되었습니다. 관리자 검토가 필요합니다.")
    if not content.strip():
        raise ValueError("아직 작성된 내용이 없습니다. AI 섹션 생성 후 미리보기를 확인하세요.")
    context, prepared, _ = _pipeline_context({part_id: content}, preview_part=part_id)
    theory_png = None
    if part_id == "theory":
        with connection() as conn:
            exports = conn.execute("SELECT id FROM report_exports WHERE status='completed' ORDER BY completed_at DESC LIMIT 12").fetchall()
        for export in exports:
            candidate = EXPORT_DIR / f"{export['id']}-theory.png"
            if candidate.is_file():
                theory_png = candidate.read_bytes()
                break
    with zipfile.ZipFile(BytesIO(template)) as source:
        header = finalize_report_header_layout(source.read("Contents/header.xml").decode("utf-8"), context["project"]).xml
        xml = source.read(spec.hwpx_path).decode("utf-8")
    xml = apply_section_adapter_xml(spec.number, xml, context, prepared).xml
    xml = finalize_report_section_layout(spec.hwpx_path, xml, context["project"], theory_png=theory_png).xml
    xml = cleanup_hwpx_placeholder_text_xml(xml)
    xml = _scrub_xml_reader_text(xml, context["project"], context.get("_raw_source_names", []))
    if spec.hwpx_path != "Contents/section1.xml":
        xml = re.sub(r"<hp:linesegarray>[\s\S]*?</hp:linesegarray>", "", xml)
    if spec.hwpx_path == "Contents/section4.xml":
        xml, _ = refresh_evaluation_matrix_split_heights_xml(xml)
    xml = isolate_section_xml(xml, part_id)
    if part_id == "theory" and not theory_png:
        # Do not show the template's unrelated sample-project diagram.
        for start, end in reversed(find_hwpx_tag_spans(xml, "hp:pic")):
            xml = xml[:start] + xml[end:]
    data = package_single_section(template, xml, header, theory_png)
    if part_id == "toc":
        data, _ = fixed_toc_columns(data, section_path="Contents/section0.xml")
        note = "목차는 전체 HWPX 저장 완료 후 실제 본문 쪽수로 확정됩니다. 이 화면은 양식 확인용입니다."
    elif part_id == "theory":
        note = "변화이론 그림은 최근 저장본을 표시합니다. 본문 수정 후 전체 HWPX 저장 시 그림도 갱신됩니다." if theory_png else "변화이론 그림은 전체 HWPX 저장 시 생성됩니다. 현재 화면은 본문 미리보기입니다."
    else:
        note = "선택한 섹션만 고정 양식으로 표시합니다. 표시 쪽수는 섹션 내부 쪽수이며 전체 보고서 쪽수와 다를 수 있습니다."
    return {"part_id": part_id, "file_name": f"section-{spec.number:02d}.hwpx",
            "hwpx_base64": base64.b64encode(data).decode("ascii"),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "render_ms": round((time.perf_counter() - started) * 1000), "note": note}
