from __future__ import annotations

import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from backend.oda_me.hwpx.patchers import (
    achievement_item_fields,
    parse_achievement_items,
    parse_feedback_items,
)

from .quality_profile import layout_profile


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    path = next((candidate for candidate in candidates if candidate.exists()), candidates[-1])
    return ImageFont.truetype(str(path), size=size)


def _colors(profile: dict[str, Any]) -> dict[str, str]:
    defaults = {
        "navy": "173B57", "teal": "238B8D", "green": "2E8B57",
        "yellow": "D6A21E", "red": "C44E52", "paper": "F7F5EF",
        "ink": "1D2A31", "muted": "5B6870", "line": "D4DDE1",
    }
    configured = profile.get("colors") if isinstance(profile.get("colors"), dict) else {}
    return {key: f"#{str(configured.get(key) or value).lstrip('#')}" for key, value in defaults.items()}


def _canvas(profile: dict[str, Any]) -> tuple[Image.Image, ImageDraw.ImageDraw, dict[str, str]]:
    width = max(1200, int(profile.get("width_pixels") or 1600))
    height = max(675, int(profile.get("height_pixels") or 900))
    colors = _colors(profile)
    image = Image.new("RGB", (width, height), colors["paper"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 22, height), fill=colors["teal"])
    return image, draw, colors


def _bmp_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="BMP")
    value = output.getvalue()
    if not value.startswith(b"BM"):
        raise RuntimeError("보고서 보조 도표 BMP 생성에 실패했습니다.")
    return value


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: object, size: int, color: str, *, bold: bool = False) -> None:
    draw.text(xy, str(value or ""), font=_font(size, bold=bold), fill=color)


def _compact(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" .")
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


def build_grade_overview_bmp(context: dict, profile: dict[str, Any]) -> bytes:
    image, draw, colors = _canvas(profile)
    title = str(profile.get("grade_title") or "DAC 기준별 평가등급 요약")
    _text(draw, (74, 56), title, 46, colors["navy"], bold=True)
    _text(draw, (76, 122), "평가기준별 4점 척도 · 저장된 평가결과 기준", 23, colors["muted"])

    criteria = context.get("criteria") if isinstance(context.get("criteria"), list) else []
    rows: list[tuple[str, float]] = []
    for criterion in criteria:
        if not isinstance(criterion, dict) or criterion.get("id") == "impact":
            continue
        evaluation = criterion.get("evaluationResult") if isinstance(criterion.get("evaluationResult"), dict) else {}
        try:
            value = evaluation.get('score', criterion.get('currentScore4'))
            score = float(value) if value is not None else None
        except (TypeError, ValueError):
            score = None
        rows.append((str(criterion.get("name") or criterion.get("id") or "평가기준"), max(0.0, min(4.0, score)) if score is not None else None))
    rows = rows[:5]

    left, top, bar_width, row_gap = 260, 225, 950, 112
    for index, (label, score) in enumerate(rows):
        y = top + index * row_gap
        _text(draw, (78, y + 7), label, 28, colors["ink"], bold=True)
        draw.rounded_rectangle((left, y, left + bar_width, y + 48), radius=20, fill="#E5E9EB")
        if score is None:
            _text(draw, (left + 25, y + 2), '자료보완 · 판정보류', 28, colors['muted'])
            continue
        color = colors["green"] if score >= 3.5 else colors["yellow"] if score >= 2.5 else colors["red"]
        draw.rounded_rectangle((left, y, left + int(bar_width * score / 4), y + 48), radius=20, fill=color)
        _text(draw, (left + bar_width + 28, y + 2), f"{score:.1f} / 4.0", 28, color, bold=True)

    overall = context.get("overall") if isinstance(context.get("overall"), dict) else {}
    score = float(overall['score']) if overall.get('score') is not None else None
    max_score = float(overall.get("maxScore") or 20)
    grade = str(overall.get("koicaGrade") or "-")
    government = str(overall.get("governmentGrade") or "-")
    badge = (1235, 208, 1530, 760)
    draw.rounded_rectangle(badge, radius=28, fill="#FFFFFF", outline=colors["line"], width=3)
    _text(draw, (1302, 252), "종합 결과", 26, colors["muted"], bold=True)
    _text(draw, (1288, 332), f"{score:.1f}" if score is not None else '보류', 70, colors["navy"], bold=True)
    _text(draw, (1405, 373), f"/ {max_score:g}", 28, colors["muted"])
    _text(draw, (1308, 482), f"KOICA {grade}", 34, colors["teal"], bold=True)
    _text(draw, (1318, 548), government, 31, colors["ink"], bold=True)
    _text(draw, (1280, 680), "※ 세부 산정 이유는 평가등급 결과표 참조", 18, colors["muted"])
    return _bmp_bytes(image)


def _achievement_status(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    if any(token in text for token in ("미달성", "위험", "부진")):
        return "주의"
    if any(token in text for token in ("유보", "확인중", "확인필요", "미기재")):
        return "확인 필요"
    if any(token in text for token in ("진행", "양호", "부분")):
        return "진행 중"
    if "달성" in text or re.search(r"(?:100(?:\.0)?|9\d(?:\.\d+)?)%", text):
        return "달성"
    return "확인 필요"


def build_performance_overview_bmp(sections_by_id: dict[str, str], profile: dict[str, Any]) -> bytes:
    image, draw, colors = _canvas(profile)
    title = str(profile.get("performance_title") or "성과지표 상태 및 후속조치 우선순위")
    _text(draw, (74, 56), title, 46, colors["navy"], bold=True)
    _text(draw, (76, 122), "최신 PDM 지표와 환류과제의 현재 상태를 간결하게 요약함", 23, colors["muted"])

    items = parse_achievement_items(sections_by_id.get("achievement") or "")[:14]
    status_counts = Counter(
        _achievement_status(achievement_item_fields(item, index).get("achievement"))
        for index, item in enumerate(items)
    )
    status_order = (
        ("달성", colors["green"]),
        ("진행 중", colors["yellow"]),
        ("주의", colors["red"]),
        ("확인 필요", colors["muted"]),
    )

    draw.rounded_rectangle((74, 205, 770, 788), radius=28, fill="#FFFFFF", outline=colors["line"], width=3)
    _text(draw, (112, 242), f"성과지표 {len(items)}개", 31, colors["navy"], bold=True)
    max_count = max([status_counts.get(label, 0) for label, _ in status_order] + [1])
    for index, (label, color) in enumerate(status_order):
        y = 330 + index * 102
        count = status_counts.get(label, 0)
        _text(draw, (116, y + 5), label, 25, colors["ink"], bold=True)
        draw.rounded_rectangle((278, y, 650, y + 42), radius=17, fill="#E5E9EB")
        if count:
            draw.rounded_rectangle((278, y, 278 + int(372 * count / max_count), y + 42), radius=17, fill=color)
        _text(draw, (675, y + 1), f"{count}개", 27, color, bold=True)

    feedback = parse_feedback_items(sections_by_id.get("feedback") or "")[:6]
    priority_counts = Counter(
        "상" if "상" in str(row.get("priority") or "") else "하" if "하" in str(row.get("priority") or "") else "중"
        for row in feedback
    )
    draw.rounded_rectangle((810, 205, 1530, 788), radius=28, fill="#FFFFFF", outline=colors["line"], width=3)
    _text(draw, (850, 242), f"후속조치 {len(feedback)}건", 31, colors["navy"], bold=True)
    priorities = (("상", colors["red"]), ("중", colors["yellow"]), ("하", colors["teal"]))
    for index, (label, color) in enumerate(priorities):
        x = 850 + index * 205
        draw.rounded_rectangle((x, 318, x + 166, 448), radius=22, fill=color)
        _text(draw, (x + 21, 338), f"우선 {label}", 23, "#FFFFFF", bold=True)
        _text(draw, (x + 57, 382), str(priority_counts.get(label, 0)), 40, "#FFFFFF", bold=True)
    _text(draw, (850, 500), "우선 확인 과제", 24, colors["muted"], bold=True)
    high_first = sorted(feedback, key=lambda row: {"상": 0, "중": 1, "하": 2}.get(str(row.get("priority") or "중"), 1))
    for index, row in enumerate(high_first[:3]):
        y = 552 + index * 68
        color = colors["red"] if "상" in str(row.get("priority") or "") else colors["yellow"]
        draw.ellipse((852, y + 10, 866, y + 24), fill=color)
        _text(draw, (882, y), _compact(row.get("task"), 34), 21, colors["ink"])
    return _bmp_bytes(image)


def build_supplemental_report_visuals(context: dict, sections_by_id: dict[str, str]) -> dict[str, bytes | bool]:
    profile = layout_profile("supplemental_visuals")
    enabled = bool(profile.get("enabled", True))
    if not enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "grade_bmp": build_grade_overview_bmp(context, profile),
        "performance_bmp": build_performance_overview_bmp(sections_by_id, profile),
    }
