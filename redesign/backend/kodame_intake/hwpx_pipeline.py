from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict
from typing import Iterable

from backend.oda_me.hwpx.adapters.summary_ko import parse_summary_ko_section, render_summary_ko_document
from backend.oda_me.reports.context import (
    parse_structured_section_slots,
    structured_slots_to_json,
)
from report_outline import (
    NARRATIVE_OUTLINE_PART_IDS,
    canonical_narrative_outline_lines,
)

from .assessment_context import assessment_date
from .hwpx_adapters import (
    AUTHORING_SHAPES,
    SECTION_ADAPTERS,
    SECTION_PIPELINES,
    SPEC_BY_PART,
    hwpx_authoring_contract,
    validate_section_adapters,
)
from .hwpx_adapters.summary_ko import _summary_fragment, _summary_slots
from .report_text import sanitize_report_text
from .hwpx_adapters.structured_input import MISSING_SLOT_TEXT, read_slot_input


def validate_hwpx_pipeline_contracts() -> None:
    """Backward-compatible entry point backed by 27 physical adapter modules."""
    validate_section_adapters()


validate_hwpx_pipeline_contracts()


_INTERNAL_SLUGS = (
    "criteria-crosscutting",
    "working-factors",
    "nonworking-factors",
    "criteria-other",
)
_OUTER_HEADING_WORDS = {
    "cover": ("표지",),
    "toc": ("목차",),
    "notice": ("평가보고서 관련 공지",),
    "grade": ("평가등급 결과표",),
    "summary-ko": ("평가결과 요약", "국문 요약"),
    "project-background": ("대상사업개요", "대상사업 개요", "사업 추진배경"),
    "project-overview": ("대상사업개요", "대상사업 개요", "사업개요"),
    "pdm": ("대상사업개요", "대상사업 개요", "사업설계매트릭스"),
    "eval-purpose": ("평가개요", "평가의 목적과 범위"),
    "eval-matrix": ("평가개요", "평가매트릭스"),
    "eval-methods": ("평가개요", "평가방법", "평가 방법"),
    "eval-limitations": ("평가개요", "평가의 한계", "평가의 한계 및 보완 조치"),
    "eval-team": ("평가개요", "평가팀 구성 및 시행체계"),
    "achievement": ("성과 달성도", "성과달성도"),
    "criteria-relevance": ("기준별 평가결과", "적절성"),
    "criteria-coherence": ("기준별 평가결과", "일관성"),
    "criteria-effectiveness": ("기준별 평가결과", "효과성"),
    "criteria-efficiency": ("기준별 평가결과", "효율성"),
    "criteria-sustainability": ("기준별 평가결과", "지속가능성"),
    "criteria-crosscutting": ("기준별 평가결과", "범분야 이슈"),
    "criteria-other": ("기준별 평가결과", "그 외 평가기준"),
    "conclusion": ("결론",),
    "working-factors": ("작동요인 및 비작동요인", "작동요인"),
    "nonworking-factors": ("작동요인 및 비작동요인", "비작동요인"),
    "theory": ("변화이론 분석",),
    "feedback": ("환류과제 및 교훈", "환류과제"),
    "lessons": ("환류과제 및 교훈", "교훈"),
}


def _plain_heading(value: str) -> str:
    text = re.sub(r"[*_`#]", "", value)
    text = re.sub(r"^\s*(?:[-•ㅇ❍∙ㆍ]\s*)+", "", text)
    text = re.sub(r"^[\s(]*(?:제)?[ⅠⅡⅢⅣⅤⅥIVX0-9.-]+(?:장)?[)\].\s]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\([^)]*[A-Za-z][^)]*\)\s*$", "", text)
    return re.sub(r"\s+", "", text).strip(".:：-()")


def _is_outer_heading(part_id: str, value: str) -> bool:
    normalized = _plain_heading(value)
    return any(normalized == _plain_heading(word) for word in _OUTER_HEADING_WORDS.get(part_id, ()))


def _clean_cross_section_heading(part_id: str, value: str) -> str:
    """Remove parent headings leaked into a saved subsection draft."""
    text = value.strip()
    # Some drafts join the chapter and subsection headings into one Markdown
    # heading (for example ``III. 평가개요 | 5. 평가팀 구성 및 시행체계``).
    # A combined line contains at least two known outer labels and is not
    # reader-facing content.
    if len(text) < 180:
        normalized = _plain_heading(text)
        outer_hits = {
            _plain_heading(word)
            for word in _OUTER_HEADING_WORDS.get(part_id, ())
            if _plain_heading(word) and _plain_heading(word) in normalized
        }
        if len(outer_hits) >= 2:
            return ""
    if part_id != "conclusion" and re.match(
        r"^(?:[가-하]\.\s*)?(?:Ⅵ|VI)\.?\s*결론\s*$", text, re.IGNORECASE
    ):
        return ""
    if part_id in {"working-factors", "nonworking-factors", "theory"}:
        if re.match(r"^2\.?\s*작동요인\s*및\s*비작동요인\s*$", text):
            return ""
        # Drafts occasionally contain both a Korean outline token and a
        # visible Arabic subsection number. Keep only the stable number.
        text = re.sub(r"^[가-하]\.\s*(\d+(?:\.\d+)*)[.)]?\s+", r"\1. ", text)
    return text


def _clean_inline(value: str) -> str:
    text = unicodedata.normalize("NFKC", sanitize_report_text(value))
    # NFKC converts the reader-facing compatibility jamo ``ㅇ`` (U+3147)
    # into the leading consonant ``ᄋ`` (U+110B).  The latter is not our list
    # marker and was therefore treated as ordinary prose by the outline
    # adapter.  That produced a synthetic parent followed by a visible
    # ``- ᄋ`` line in HWPX.  Restore only a standalone leading marker; normal
    # Korean syllables and jamo occurring inside content remain untouched.
    text = re.sub(r"^(\s*)ᄋ(?=\s+\S)", r"\1ㅇ", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:p|div|span|strong|em|b|i|table|tr|td|th)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?hp:[^>]+>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"\((?:" + "|".join(re.escape(item) for item in _INTERNAL_SLUGS) + r")\)", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = text.replace("✦", "").replace("✅", "").replace("❌", "")
    text = text.replace("“", "‘").replace("”", "’").replace("…", "...")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?。、])", r"\1", text)
    return text.strip()


def _restore_korean_sentence_boundaries(value: str) -> str:
    """Restore sentence stops omitted by some compact LLM drafts.

    The rule is deliberately limited to common report-style declarative
    endings followed by a new Korean sentence. It does not touch headings,
    abbreviations, decimals, or already punctuated prose.
    """
    endings = (
        "하였다|되었다|수행하였다|검토하였다|분석하였다|평가하였다|"
        "판단하였다|확인하였다|도출하였다|제시하였다|마련하였다|"
        "한다|된다|있다|없다|필요하다|기대된다|판단된다|확인된다|"
        "수행된다|검토한다|분석한다|평가한다|도출한다|제시한다|"
        "제공한다|활용된다|요구된다|목적이다|결과이다"
    )
    return re.sub(
        rf"(?<![.!?。])({endings})\s+(?=[가-힣])",
        r"\1. ",
        str(value or ""),
    )


def markdown_tables(value: str) -> list[dict[str, list]]:
    lines = str(value or "").replace("\r", "").split("\n")
    tables: list[dict[str, list]] = []
    index = 0
    while index < len(lines) - 1:
        if "|" not in lines[index] or not re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            index += 1
            continue
        header = [_clean_inline(item) for item in lines[index].strip().strip("|").split("|")]
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index]:
            row = [_clean_inline(item) for item in lines[index].strip().strip("|").split("|")]
            if any(row):
                rows.append(row)
            index += 1
        tables.append({"header": header, "rows": rows})
    return tables


def _table_as_report_lines(table: dict[str, list]) -> list[str]:
    header = [str(item) for item in table.get("header", [])]
    result: list[str] = []
    for row in table.get("rows", []):
        cells = list(row) + [""] * max(0, len(header) - len(row))
        pairs = [(header[index], cells[index]) for index in range(min(len(header), len(cells))) if cells[index]]
        if not pairs:
            continue
        first_label, first_value = pairs[0]
        result.append(f"ㅇ {first_label}: {first_value}" if first_label else f"ㅇ {first_value}")
        result.extend(f"- {label}: {cell}" for label, cell in pairs[1:] if label and cell)
    return result


def normalize_section_text(part_id: str, value: str, max_chars: int | None = None) -> tuple[str, dict]:
    spec = SPEC_BY_PART[part_id]
    maximum = max_chars or spec.max_chars
    source = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    structured_input = read_slot_input(part_id, value)
    if structured_input.detected:
        # Parse before prose sanitization. Keys/schema must never become
        # reader text or be reclassified as a generated paragraph.
        source = "\n\n".join([*structured_input.slots.values(), *structured_input.unassigned_values])
    if part_id == "summary-ko":
        try:
            slots = parse_summary_ko_section(source)
            normalized = render_summary_ko_document(slots)
            warnings: list[str] = []
        except Exception:
            # Legacy/free-text drafts are converted by the deterministic
            # five-block composer below. New drafts must already validate.
            normalized = source.strip()
            warnings = ["레거시 국문 요약을 5개 고정 블록으로 변환"]
        return normalized, {
            "part_id": part_id,
            "mode": spec.mode,
            "adapter": spec.adapter,
            "input_chars": len(source),
            "output_chars": len(normalized),
            "removed_outer_headings": 0,
            "converted_markdown_tables": 0,
            "truncated": False,
            "warnings": warnings,
        }
    source = re.sub(r"^```(?:markdown|md|text)?\s*|\s*```$", "", source.strip(), flags=re.IGNORECASE)
    lines = source.split("\n")
    output: list[str] = []
    removed_headings = 0
    table_count = 0
    heading_index = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if "|" in line and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index]:
                table_lines.append(lines[index])
                index += 1
            parsed = markdown_tables("\n".join(table_lines))
            if parsed:
                output.extend(_table_as_report_lines(parsed[0]))
                table_count += 1
            continue
        heading = re.match(r"^\s*(#{1,6})\s*(.*?)\s*$", line)
        if heading:
            label = _clean_cross_section_heading(part_id, _clean_inline(heading.group(2)))
            if not label or _is_outer_heading(part_id, label):
                removed_headings += 1
            else:
                if part_id in NARRATIVE_OUTLINE_PART_IDS:
                    label = re.sub(
                        r"^(?:\d+(?:\.\d+)*\s*[.)]?|[가-하]\s*[.)]|[①-⑳])\s*",
                        "",
                        label,
                    ).strip()
                    marker = " ㅇ " if len(heading.group(1)) <= 3 else "  - "
                    output.append(marker + label)
                    index += 1
                    continue
                heading_index += 1
                # NFKC converts circled numbers such as ① into a bare "1".
                # Restore an explicit delimiter instead of adding a second
                # Korean outline token (for example "가. 1 ...").
                label = re.sub(r"^(\d+(?:\.\d+)*)\s+", r"\1. ", label)
                korean_outline = "가나다라마바사아자차카타파하"
                label = re.sub(
                    rf"^([{korean_outline}])\s+",
                    r"\1. ",
                    label,
                )
                # LLM drafts sometimes emit non-standard Hangul sequences
                # such as 가/까/나. Re-number any explicit Hangul outline by
                # its actual heading position so the exported report always
                # follows 가/나/다. Words such as '첫 번째' are not touched
                # because they have no outline delimiter.
                if re.match(r"^[가-힣]\s*[.)]", label):
                    current_outline = korean_outline[min(heading_index - 1, len(korean_outline) - 1)]
                    label = re.sub(r"^[가-힣]\s*[.)]\s*", f"{current_outline}. ", label)
                    output.append(label)
                elif re.match(r"^(?:\d+(?:\.\d+)*|[①-⑳])\s*[.)]", label):
                    output.append(label)
                else:
                    output.append(f"{korean_outline[min(heading_index - 1, len(korean_outline) - 1)]}. {label}")
            index += 1
            continue
        cleaned = _clean_cross_section_heading(part_id, _clean_inline(line))
        if not cleaned:
            if output and output[-1] != "":
                output.append("")
            index += 1
            continue
        if _is_outer_heading(part_id, cleaned) and len(cleaned) < 50:
            removed_headings += 1
            index += 1
            continue
        cleaned = re.sub(r"^\s*[-*+]\s+", "- ", cleaned)
        cleaned = re.sub(r"^\s*[•●▪■◆◇]\s*", "- ", cleaned)
        cleaned = _restore_korean_sentence_boundaries(cleaned)
        output.append(cleaned)
        index += 1

    if part_id in NARRATIVE_OUTLINE_PART_IDS:
        output = canonical_narrative_outline_lines(part_id, output)
    while output and not output[0]:
        output.pop(0)
    while output and not output[-1]:
        output.pop()
    normalized = "\n".join(output)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip("\n")
    if not normalized and part_id not in {"cover", "toc", "grade"}:
        normalized = MISSING_SLOT_TEXT
    # The editor draft and HWPX must carry the same reader-facing content.
    # Earlier code silently cut text at a character budget, which created
    # incomplete sentences and made the preview disagree with the saved
    # section.  Length is now a diagnostic/generation concern; pagination
    # adapters own physical fit without deleting reviewed prose.
    over_budget = len(normalized) > maximum
    truncated = False
    diagnostics = {
        "part_id": part_id,
        "mode": spec.mode,
        "adapter": spec.adapter,
        "input_chars": len(source),
        "output_chars": len(normalized),
        "over_budget": over_budget,
        "removed_outer_headings": removed_headings,
        "converted_markdown_tables": table_count,
        "truncated": truncated,
        "warnings": structured_input.warnings + (["작성 내용이 없는 섹션을 명시적 확인 문구로 표시함"] if not str(value or "").strip() else []) + ([f"권장 {maximum}자를 초과함; 전체 본문을 보존하고 조판 단계에서 페이지를 확장함"] if over_budget else []),
        "structured_input": structured_input.detected,
        "structured_slot_count": len(structured_input.slots),
    }
    return normalized, diagnostics


def _paragraphs(value: str) -> list[str]:
    lines = [line.strip() for line in str(value or "").splitlines()]
    result: list[str] = []
    for line in lines:
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line).strip()
        if re.match(r"^\|?\s*:?-{3,}(?:\s*\|\s*:?-{3,})+\s*\|?$", line):
            continue
        if "|" in line:
            cells = [_clean_inline(cell) for cell in line.strip().strip("|").split("|")]
            line = " · ".join(cell for cell in cells if cell)
        if re.match(r"^[가-하]\.[^.!?]{1,80}$", line):
            continue
        if line.startswith("- ") and result:
            result[-1] = f"{result[-1]} {line[2:]}".strip()
        else:
            result.append(line)
    return result


def _compact(value: str, limit: int = 520, fallback: str = "확인된 자료 범위에서 추가 검토가 필요하다.") -> str:
    text = " ".join(_paragraphs(value)) or _clean_inline(value)
    text = re.sub(r"\s+", " ", text).strip(" -")
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    sentences = re.findall(r"[^.!?。]+[.!?。]", text)
    selected = ""
    for sentence in sentences:
        if len(selected) + len(sentence) + 1 > limit:
            break
        selected = f"{selected} {sentence}".strip()
    if selected:
        return selected
    return text[:limit].rstrip(" ,;:-") + "."


def _keyword_fragment(value: str, keywords: Iterable[str], limit: int, fallback: str = "") -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if any(keyword in line for keyword in keywords):
            chosen = [line]
            for following in lines[index + 1:index + 4]:
                if re.match(r"^[가-하]\.|^\d+[.)]", following):
                    break
                chosen.append(following)
            return _compact(" ".join(chosen), limit, fallback)
    return _compact(value, limit, fallback) if not fallback else fallback


def _value(context: dict, key: str, fallback: str = "확인 필요") -> str:
    project = context.get("project") or {}
    return str(project.get(key) or fallback).strip()


def _heading_groups(value: str) -> list[str]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_starts_with_heading = False
    for line in str(value or "").splitlines():
        text = re.sub(r"^#{1,6}\s*", "", line.strip()).strip()
        if not text:
            if current and not (current_starts_with_heading and len(current) == 1):
                groups.append(current)
                current = []
                current_starts_with_heading = False
            continue
        is_heading = bool(re.match(r"^(?:[가-하]|\d+(?:\.\d+)*)[.)]\s+", text))
        is_heading = is_heading or bool(re.match(r"^(?:개발문제|정부정책|대상지역|ODA\s*정합성|사업선정)\b", text))
        is_heading = is_heading or bool(re.match(r"^\([^()]{2,90}\)$", text))
        if is_heading and current:
            groups.append(current)
            current = [text]
            current_starts_with_heading = True
        else:
            current.append(text)
            if len(current) == 1:
                current_starts_with_heading = is_heading
    if current:
        groups.append(current)
    return ["\n".join(group) for group in groups if group]


def _background_slots(value: str) -> dict[str, str]:
    keys = (
        "mdg_maternal_health_context",
        "government_policy_context",
        "target_region_need",
        "koica_policy_alignment",
        "project_selection_rationale",
    )
    parsed = read_slot_input("project-background", value)
    if parsed.detected:
        return parsed.complete(list(keys))
    groups = _heading_groups(value)
    keyword_map = {
        keys[0]: ("구조", "보건", "응급", "현황"),
        keys[1]: ("정부", "정책", "전략", "제도"),
        keys[2]: ("수요", "지역", "필요", "취약"),
        keys[3]: ("지원", "한국", "ODA", "정합"),
        keys[4]: ("선정", "추진", "타당", "논리"),
    }
    fallback_titles = {
        keys[0]: "개발문제와 구조적 취약성",
        keys[1]: "정부 정책과 제도적 방향",
        keys[2]: "대상지역의 수요와 지원 필요성",
        keys[3]: "ODA 정책 및 지원전략과의 정합성",
        keys[4]: "사업 선정과 형성 논리",
    }
    result: dict[str, str] = {}
    unused = list(groups)
    for key in keys:
        match = next((item for item in unused if any(word in item for word in keyword_map[key])), "")
        if match:
            unused.remove(match)
        elif unused:
            match = unused.pop(0)
        else:
            match = "해당 항목의 작성 내용이 없어 추가 확인이 필요함."
        lines = [line.strip() for line in match.splitlines() if line.strip()]
        first = lines[0] if lines else ""
        circle_heading = bool(re.match(r"^[ㅇ❍○◦ᄋ]\s+", first))
        first = re.sub(r"^[ㅇ❍○◦ᄋ]\s+", "", first)
        inline_title = re.match(r"^\(([^()]{2,90})\)\s*(.*)$", first)
        heading_match = re.match(
            r"^(?:\(([^()]+)\)|(?:[가-하]|\d+(?:\.\d+)*)[.)]\s*(.+))$",
            first,
        )
        if inline_title:
            title = inline_title.group(1).strip()
            body_source = " ".join(filter(None, [inline_title.group(2).strip(), *lines[1:]]))
        elif circle_heading:
            title = first
            body_source = " ".join(lines[1:])
        elif heading_match:
            title = next((item for item in heading_match.groups() if item), fallback_titles[key]).strip()
            body_source = " ".join(lines[1:])
        else:
            title = fallback_titles[key]
            body_source = " ".join(lines)
        # Export is a layout transform, not a second summary generator.
        body = body_source.strip()
        result[key] = f"({title}) {body}"
    if unused:
        result[keys[-1]] += "\n\n" + "\n\n".join(unused)
    return result


def _table_rows_by_label(raw: str) -> list[tuple[str, list[str], list[str]]]:
    rows = []
    for table in markdown_tables(raw):
        header = [str(item) for item in table["header"]]
        for row in table["rows"]:
            cells = [str(item) for item in row]
            rows.append((cells[0] if cells else "", cells, header))
    return rows


def _lookup_row(rows: list[tuple[str, list[str], list[str]]], labels: Iterable[str], fallback: str = "") -> str:
    for label, cells, _header in rows:
        if any(key.replace(" ", "") in label.replace(" ", "") for key in labels):
            return " / ".join(cell for cell in cells[1:] if cell).strip()
    return fallback


def _overview_slots(context: dict, raw: str, normalized: str) -> dict[str, str]:
    from backend.oda_me.reports.context import SECTION7_PROJECT_OVERVIEW_SLOT_KEYS
    from backend.oda_me.reports.overview_records import legacy_overview_slots
    parsed = read_slot_input("project-overview", raw)
    if parsed.detected or not raw.strip():
        return parsed.complete(SECTION7_PROJECT_OVERVIEW_SLOT_KEYS)
    legacy = legacy_overview_slots(raw)
    if legacy is not None:
        return legacy
    if raw.lstrip().startswith("▣"):
        raise ValueError("사업개요 12개 셀의 경계를 식별할 수 없습니다. 사업개요를 항목별 JSON으로 다시 생성해 주세요.")
    rows = _table_rows_by_label(raw)
    activities = _value(context, "activities", _compact(normalized, 700))
    outputs = _value(context, "outputs", activities)
    project = context.get("project") or {}
    title_en = _lookup_row(rows, ("사업명(영문)", "영문 사업명"), "")
    if not title_en:
        candidate = str(project.get("title_en") or "").strip()
        if "확인 필요" not in candidate and "미기재" not in candidate:
            title_en = candidate
    title_en = title_en or "등록 자료에 영문 사업명이 별도 기재되지 않음"
    sector = _lookup_row(rows, ("사업분야", "분야"), "")
    if not sector:
        candidate = str(project.get("sector") or "").strip()
        if "확인 필요" not in candidate and "미기재" not in candidate:
            sector = candidate
    if not sector and re.search(r"학과|대학|교육과정|교육\s*프로그램", _value(context, "title") + " " + activities):
        sector = "교육"
    sector = sector or "등록 자료에 사업분야가 별도 기재되지 않음"
    return {
        "project_name_ko": "▣ 국문: " + _value(context, "title"),
        "project_name_en": "▣ 영문: " + title_en,
        "target_country_region": "▣ " + f"{_value(context, 'country')} · {_value(context, 'location')}",
        "project_period_budget": "▣ 기간: " + _value(context, "period") + " / ▣ 총 사업예산: " + _value(context, "budget"),
        "project_sector": "▣ " + sector,
        "project_purpose": "▣ " + _value(context, "objective", _lookup_row(rows, ("사업목적", "목적"), _compact(normalized, 500))),
        "pcp_feasibility_review": "󰁯 " + _lookup_row(rows, ("PCP", "사전타당성", "선정 경과"), "해당 검토자료 확인 필요"),
        "korean_textbook_development": "▣ 교육과정·교재 개발 / " + _keyword_fragment(activities, ("교재", "교육과정", "프로그램"), 520),
        "korean_equipment_support": "▣ 기자재·실습환경 / " + _keyword_fragment(outputs, ("기자재", "실습", "장비"), 520),
        "korean_expert_dispatch": "▣ 전문가·교원 역량강화 / " + _keyword_fragment(activities, ("전문가", "교원", "역량"), 520),
        "korean_invitation_training": "▣ 교육·연수 / " + _keyword_fragment(activities, ("연수", "교육", "훈련"), 520),
        "partner_contribution": "▣ 지원기관: " + _value(context, "donor") + " / 수행기관: " + _value(context, "implementer") + " / 협력기관: " + _value(context, "partner"),
    }


def _pdm_slots(context: dict, raw: str, normalized: str) -> dict[str, str]:
    source_slots = context.get("_pdm_source_slots")
    if isinstance(source_slots, dict) and all(
        str(source_slots.get(key) or "").strip()
        for key in (
            "impact_summary", "impact_indicator", "impact_mov", "impact_assumption",
            "outcome_summary", "outcome_indicator", "outcome_mov", "outcome_assumption",
            "outputs_summary", "outputs_indicator", "outputs_mov", "outputs_assumption",
            "activities", "inputs", "preconditions",
        )
    ):
        # The uploaded PDM is the authoritative design document.  These
        # values come from its physical table cells and must not be replaced
        # by overview prose or a generated report narrative.
        def normalize_pdm_value(value: object) -> str:
            text = str(value or "").strip()
            return re.sub(r"\bRRC\s+EM\b", "RRCEM", text, flags=re.IGNORECASE)

        return {key: normalize_pdm_value(value) for key, value in source_slots.items()}

    parsed = read_slot_input("pdm", raw)
    if parsed.detected or not raw.strip():
        from backend.oda_me.reports.context import STRUCTURED_SECTION_SLOT_KEYS
        return parsed.complete(STRUCTURED_SECTION_SLOT_KEYS["pdm"])

    table_slots: dict[str, str] = {}
    for table in markdown_tables(raw):
        headers = [re.sub(r"\s+", "", str(item)).lower() for item in table["header"]]
        if not any("narrative" in item or "요약" in item for item in headers):
            continue

        def column(*labels: str) -> int:
            return next(
                (
                    index for index, header in enumerate(headers)
                    if any(label.lower().replace(" ", "") in header for label in labels)
                ),
                -1,
            )

        summary_index = column("요약", "narrative")
        indicator_index = column("검증지표", "ovi", "indicator")
        mov_index = column("검증수단", "mov", "verification")
        assumption_index = column("중요가정", "assumption")
        if min(summary_index, indicator_index, mov_index, assumption_index) < 0:
            continue

        def cell(row: list[str], index: int) -> str:
            return _compact(row[index], 10000) if index < len(row) else ""

        for raw_row in table["rows"]:
            row = [str(item) for item in raw_row]
            label = re.sub(r"[\s*_]", "", row[0] if row else "").lower()
            if "impact" in label or "영향" in label or "상위목표" in label:
                prefix = "impact"
            elif "outcome" in label or "성과" in label:
                prefix = "outcome"
            elif "output" in label or "산출" in label:
                prefix = "outputs"
            elif "activit" in label or "활동" in label:
                table_slots["activities"] = cell(row, summary_index)
                continue
            elif "input" in label or "투입" in label:
                table_slots["inputs"] = cell(row, summary_index)
                table_slots.setdefault("preconditions", cell(row, assumption_index))
                continue
            elif "precondition" in label or "선행조건" in label or "전제조건" in label:
                table_slots["preconditions"] = cell(row, summary_index)
                continue
            else:
                continue
            table_slots[f"{prefix}_summary"] = cell(row, summary_index)
            table_slots[f"{prefix}_indicator"] = cell(row, indicator_index)
            table_slots[f"{prefix}_mov"] = cell(row, mov_index)
            table_slots[f"{prefix}_assumption"] = cell(row, assumption_index)

    rows = _table_rows_by_label(raw)
    def row(labels: tuple[str, ...], fallback: str) -> str:
        return _lookup_row(rows, labels, fallback)
    objective = _value(context, "objective", _compact(normalized, 520))
    outcomes = table_slots.get("outcome_summary") or _value(context, "outcomes", row(("성과", "Outcome"), objective))
    outputs = table_slots.get("outputs_summary") or _value(context, "outputs", row(("산출", "Output"), outcomes))
    activities = table_slots.get("activities") or _value(context, "activities", row(("활동", "Activities"), outputs))
    gaps = _value(context, "evidence_gaps", "후속 성과와 운영 지속성 자료의 보완이 필요하다.")
    return {
        "impact_summary": table_slots.get("impact_summary") or row(("상위목표", "Impact"), objective),
        "impact_indicator": table_slots.get("impact_indicator") or row(("상위목표 지표", "Impact Indicator"), "상위목표 지표는 최신 PDM과 후속 성과자료를 대조한다."),
        "impact_mov": table_slots.get("impact_mov") or row(("상위목표 검증", "Impact MOV"), "최신 PDM, 국가·기관 성과통계, 후속 추적자료"),
        "impact_assumption": table_slots.get("impact_assumption") or row(("상위목표 가정",), gaps),
        "outcome_summary": outcomes,
        "outcome_indicator": table_slots.get("outcome_indicator") or row(("성과지표", "Outcome Indicator"), "성과지표는 최신 PDM과 연차별 성과자료를 대조한다."),
        "outcome_mov": table_slots.get("outcome_mov") or row(("성과 검증", "Outcome MOV"), "연차별 성과자료 및 자체평가 결과"),
        "outcome_assumption": table_slots.get("outcome_assumption") or row(("성과 가정",), gaps),
        "outputs_summary": outputs,
        "outputs_indicator": table_slots.get("outputs_indicator") or row(("산출지표", "Output Indicator"), "산출지표는 계획 대비 수행실적으로 확인한다."),
        "outputs_mov": table_slots.get("outputs_mov") or row(("산출 검증", "Output MOV"), "사업계획서, 수행실적, 검수·교육·승인 자료"),
        "outputs_assumption": table_slots.get("outputs_assumption") or row(("산출 가정",), gaps),
        "activities": activities,
        "inputs": table_slots.get("inputs") or row(("투입", "Inputs"), f"총사업비 {_value(context, 'budget')}; 수행기관 {_value(context, 'implementer')}"),
        "preconditions": table_slots.get("preconditions") or row(("전제조건", "Precondition"), "협력기관의 제도적 협력과 운영 인력·재원의 확보"),
    }


def _matrix_slots(raw: str, evaluations: list[dict]) -> dict[str, str]:
    parsed = read_slot_input("eval-matrix", raw)
    if parsed.detected or not raw.strip():
        from backend.oda_me.reports.context import SECTION10_EVAL_MATRIX_SLOT_KEYS
        return parsed.complete(SECTION10_EVAL_MATRIX_SLOT_KEYS)
    tables = markdown_tables(raw)
    result: dict[str, str] = {}
    labels = {
        "적절": "relevance", "일관": "coherence", "효과": "effectiveness",
        "효율": "efficiency", "지속": "sustainability", "인권": "human_rights",
        "젠더": "gender", "성평등": "gender", "환경": "environment",
    }
    column_names = {
        "question": ("질문",), "indicator": ("지표", "판단기준"),
        "source": ("출처", "자료원", "자료"), "method": ("방법", "분석"),
    }
    for table in tables:
        headers = [item.replace(" ", "") for item in table["header"]]
        for row in table["rows"]:
            cells = list(row) + [""] * max(0, len(headers) - len(row))
            # The criterion must come from the criterion cell, never from a
            # word that happens to occur in the question.  Looking at the
            # first two cells previously classified an efficiency question
            # as the relevance row when the first cell was sparse.
            criterion_cell = cells[0] if cells else ""
            prefix = next((value for key, value in labels.items() if key in criterion_cell), "")
            if not prefix:
                continue
            for suffix, synonyms in column_names.items():
                position = next((idx for idx, header in enumerate(headers) if any(word in header for word in synonyms)), -1)
                if position >= 0 and position < len(cells) and cells[position]:
                    result[f"{prefix}_{suffix}"] = cells[position].strip()
    evaluation_by_id = {str(item.get("id")): item for item in evaluations}
    for prefix in ("relevance", "coherence", "effectiveness", "efficiency", "sustainability"):
        item = evaluation_by_id.get(prefix) or {}
        assessments = (item.get("evaluationResult") or {}).get("questionAssessments") or []
        evaluated_questions = " / ".join(str(q.get("question") or "") for q in assessments if q.get("question"))
        if evaluated_questions:
            # Re-evaluation can make a draft stale; that is a revision warning,
            # not permission for the export adapter to rewrite saved content.
            result.setdefault(f"{prefix}_question", evaluated_questions)
        else:
            result.setdefault(f"{prefix}_question", f"{prefix} 평가질문")
        result.setdefault(f"{prefix}_indicator", "질문별 1~4점 루브릭과 확인된 정성·정량 근거")
        result.setdefault(f"{prefix}_source", "등록 사업문서 및 평가질문에 연결된 근거자료")
        result.setdefault(f"{prefix}_method", "문헌검토, 자료 간 교차대조 및 기여분석")
    defaults = {
        "human_rights": "사업 설계와 수행에서 인권 및 취약계층 접근성이 고려되었는가?",
        "gender": "성평등 관점과 성별 분리자료가 설계·성과관리에 반영되었는가?",
        "environment": "환경·기후 위험과 완화조치가 설계·운영에 반영되었는가?",
    }
    for prefix, question in defaults.items():
        result.setdefault(f"{prefix}_question", question)
        result.setdefault(f"{prefix}_indicator", "설계 반영 여부, 이행근거 및 분리통계")
        result.setdefault(f"{prefix}_source", "사업계획, 수행실적 및 성과자료")
        result.setdefault(f"{prefix}_method", "문헌검토 및 근거 간 교차대조")
    return result


def prepare_hwpx_sections(
    context: dict,
    raw_sections: dict[str, str],
    evaluations: list[dict],
    *,
    selected_parts: set[str] | None = None,
) -> tuple[dict[str, str], dict]:
    prepared: dict[str, str] = {}
    diagnostics: list[dict] = []
    for adapter in SECTION_ADAPTERS:
        spec = adapter.spec
        text, report = adapter.normalize(raw_sections.get(spec.part_id, ""), normalize_section_text)
        prepared[spec.part_id] = text
        report["source_module"] = adapter.source_module
        diagnostics.append(report)

    diagnostics_by_part = {item["part_id"]: item for item in diagnostics}
    # The first pass derives reader prose from values, never JSON syntax. Each
    # independent adapter owns its second-stage machine representation. Keep
    # the legacy dependency order exactly: grade and the two source tables are
    # preserved before the cover/summary composer reads neighboring sections.
    preparation_numbers = (4, 26, 27, 1, 5, 6, 7, 8, 9, 10)
    ordered_adapters = [
        next(item for item in SECTION_ADAPTERS if item.spec.number == number)
        for number in preparation_numbers
    ]
    ordered_adapters.extend(
        item for item in SECTION_ADAPTERS if item.spec.number not in preparation_numbers
    )
    for adapter in ordered_adapters:
        # A section proof may read neighboring prose, but must not validate or
        # synthesize unrelated (possibly still empty) sections. Full exports
        # retain the complete dependency order and all contracts by default.
        if selected_parts is not None and adapter.spec.part_id not in selected_parts:
            continue
        result = adapter.prepare(context, raw_sections, prepared, evaluations)
        if isinstance(result, tuple):
            prepared_value, extra_diagnostics = result
            diagnostics_by_part[adapter.spec.part_id].update(extra_diagnostics)
        else:
            prepared_value = result
        prepared[adapter.spec.part_id] = prepared_value

    today = assessment_date().isoformat()
    return prepared, {
        "schema": "kodame-hwpx-conversion-report-v1",
        "converted_at": today,
        "template_contract": {
            "logical_sections": 27,
            "physical_sections": 9,
            "font_policy": "원본 charPr/style 상속; 신규 폰트 생성 금지",
            "paragraph_policy": "의미 단위별 원본 본문 문단 복제 후 변경된 물리 구역의 linesegarray 전체 제거",
            "table_policy": "검토된 값 셀만 치환; 너비·병합·테두리·배경 보존",
            "package_policy": "수정하지 않은 ZIP 엔트리는 원본 바이트 보존",
        },
        "sections": diagnostics,
        "pipeline_specs": [asdict(item) for item in SECTION_PIPELINES],
        "warnings": [warning for item in diagnostics for warning in item["warnings"]],
    }


def preserve_structured_grade_section(raw_value: object, normalized_fallback: object = "") -> str:
    """Return canonical grade JSON without passing its keys through prose cleanup."""

    grade_slots = parse_structured_section_slots(raw_value, "grade")
    if grade_slots is None:
        # One earlier manual-save route treated the JSON as report prose and
        # changed every underscore to a space.  Repair that known legacy shape
        # once at the adapter boundary so existing reviewed rationales are not
        # discarded while the database row is resaved in canonical form.
        try:
            legacy = json.loads(str(raw_value or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            legacy = None
        legacy_slots = legacy.get("slots") if isinstance(legacy, dict) else None
        if isinstance(legacy_slots, dict):
            repaired = {
                re.sub(r"\s+", "_", str(key).strip()): value
                for key, value in legacy_slots.items()
                if str(key).strip()
            }
            if any(key.endswith("_reason") for key in repaired):
                grade_slots = repaired
    if grade_slots is None:
        return str(normalized_fallback or "")
    return structured_slots_to_json("grade", grade_slots)


def export_policy_json() -> str:
    return json.dumps([asdict(item) for item in SECTION_PIPELINES], ensure_ascii=False, indent=2)
