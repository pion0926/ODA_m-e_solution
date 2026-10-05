from __future__ import annotations
from .llm_models import current_llm_model
from .model_catalog import prepare_model_payload

import json
import hashlib
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

import httpx
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from .report_text import sanitize_report_text
from .settings import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_REFERER,
)
from .theory_visual_prompt import (
    THEORY_VISUAL_DESIGN_VERSION,
    THEORY_VISUAL_SCHEMA,
    theory_visual_messages,
)
from .usage import record_token_usage
from .ai.request_limits import request_slot


PALETTE = {
    "paper": "FFFFFF",
    "ink": "111111",
    "muted": "333333",
    "challenge": "AFC6ED",
    "challenge_light": "E5EEF9",
    "activity": "F4B38F",
    "activity_light": "FCE9E1",
    "factor": "A9E4EA",
    "output": "A9C95F",
    "output_light": "EEF5D9",
    "outcome": "8E72B5",
    "outcome_light": "EEE9F4",
    "working": "174A70",
    "nonworking": "8B2923",
    "line": "AAB5BE",
    "white": "FFFFFF",
}

COLUMN_LABELS = (
    "당면과제",
    "주요 활동",
    "작동·비작동요인",
    "산출물",
    "작동·비작동요인",
    "중장기성과",
)
# Keep every shape inside a 0.4in capture-safe boundary. The previous layout
# ended only 0.18in from the slide edge, so rHWP's picture-frame rounding could
# clip the right arrowhead and lower legend after PPTX-to-PNG insertion.
COLUMN_X = (0.42, 2.05, 4.43, 6.23, 7.95, 9.93)
COLUMN_W = (1.49, 2.25, 1.65, 1.58, 1.82, 2.90)
HEADER_COLORS = ("challenge", "activity", "factor", "output", "factor", "outcome")


def _clean(value: Any, limit: int) -> str:
    text = sanitize_report_text(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:limit].rstrip(" ,.;:") if len(text) > limit else text


def _extract_json(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Claude 변화이론 응답이 JSON 객체가 아닙니다.")
    return result


def _message_content(response: httpx.Response) -> str:
    payload = response.json()
    record_token_usage(payload, current_llm_model())
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return str(content or "")


def theory_visual_source(context: dict, sections_by_id: dict[str, str]) -> dict:
    return {
        "project": context.get("project") or {},
        "theory": _clean(sections_by_id.get("theory"), 5200),
        "working_factors": _clean(sections_by_id.get("working-factors"), 2800),
        "nonworking_factors": _clean(sections_by_id.get("nonworking-factors"), 2800),
        "pdm": _clean(sections_by_id.get("pdm"), 5200),
        "project_overview": _clean(sections_by_id.get("project-overview"), 2600),
        "achievement": _clean(sections_by_id.get("achievement"), 3200),
        "conclusion": _clean(sections_by_id.get("conclusion"), 2600),
    }


def theory_visual_input_digest(context: dict, sections_by_id: dict[str, str], input_snapshot: dict) -> str:
    # Include full relevant text, not only the prompt excerpts. Uploading or
    # re-evaluating documents must invalidate a previously rendered diagram.
    relevant = {key: sections_by_id.get(key, "") for key in (
        "theory", "working-factors", "nonworking-factors", "pdm", "project-overview", "achievement", "conclusion")}
    payload = {"project": context.get("project"), "sections": relevant, "model": current_llm_model(),
               "document_digest": input_snapshot.get("document_digest"),
               "evaluation_run_id": input_snapshot.get("evaluation_run_id"),
               "design_version": THEORY_VISUAL_DESIGN_VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def request_theory_visual_plan(context: dict, sections_by_id: dict[str, str]) -> dict[str, Any]:
    """Ask the assigned project model to rebuild the six-column visual."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY가 설정되지 않아 변화이론 도식을 생성할 수 없습니다.")
    source = theory_visual_source(context, sections_by_id)
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": "KODAME Theory of Change Visual",
    }
    payload = {
        "model": current_llm_model(),
        "messages": theory_visual_messages(source),
        "temperature": 0.2,
        "max_completion_tokens": 4500,
        "response_format": {"type": "json_schema", "json_schema": THEORY_VISUAL_SCHEMA},
    }
    with request_slot(payload) as reservation, httpx.Client(timeout=httpx.Timeout(300.0, connect=20.0)) as client:
        response = client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=prepare_model_payload(payload))
    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenRouter Claude 변화이론 호출 실패: HTTP {response.status_code} {response.text[:300]}"
        )
    return normalize_theory_visual_plan(_extract_json(_message_content(response)))


def _normalized_text_list(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
    limit: int,
) -> list[str]:
    values = value if isinstance(value, list) else []
    result = [_clean(item, limit) for item in values if _clean(item, limit)][:maximum]
    if len(result) < minimum:
        raise ValueError(f"변화이론 {name} 항목은 {minimum}개 이상이어야 합니다.")
    return result


def _normalized_factors(value: object, name: str) -> list[dict[str, str]]:
    values = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for item in values[:4]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        text = _clean(item.get("text"), 48)
        if kind in {"working", "nonworking"} and text:
            result.append({"kind": kind, "text": text})
    if len(result) < 2:
        raise ValueError(f"변화이론 {name} 화살표는 2개 이상이어야 합니다.")
    kinds = {item["kind"] for item in result}
    if "working" not in kinds:
        result[0]["kind"] = "working"
    if "nonworking" not in kinds:
        result[-1]["kind"] = "nonworking"
    return result


def normalize_theory_visual_plan(raw: dict[str, Any]) -> dict[str, Any]:
    activities = raw.get("activity_groups") if isinstance(raw.get("activity_groups"), list) else []
    normalized_activities: list[dict[str, Any]] = []
    for item in activities[:3]:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label"), 24)
        values = _normalized_text_list(
            item.get("items"), name="주요 활동 세부", minimum=2, maximum=3, limit=42
        )
        normalized_activities.append({"label": label or "활동 묶음", "items": values})
    if len(normalized_activities) < 2:
        raise ValueError("변화이론 주요 활동 묶음은 2개 이상이어야 합니다.")

    return {
        "design_version": THEORY_VISUAL_DESIGN_VERSION,
        "title": _clean(raw.get("title"), 28) or "변화이론 분석",
        "subtitle": _clean(raw.get("subtitle"), 120),
        "challenges": _normalized_text_list(
            raw.get("challenges"), name="당면과제", minimum=3, maximum=5, limit=44
        ),
        "activity_groups": normalized_activities,
        "pre_output_factors": _normalized_factors(
            raw.get("pre_output_factors"), "활동-산출 작동·비작동요인"
        ),
        "outputs": _normalized_text_list(
            raw.get("outputs"), name="산출물", minimum=3, maximum=5, limit=44
        ),
        "post_output_factors": _normalized_factors(
            raw.get("post_output_factors"), "산출-성과 작동·비작동요인"
        ),
        "outcomes": _normalized_text_list(
            raw.get("outcomes"), name="중장기성과", minimum=3, maximum=5, limit=44
        ),
    }


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def _ppt_text(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    value: object,
    *,
    size: float = 10,
    color: str = "ink",
    bold: bool = False,
    align=PP_ALIGN.CENTER,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.04)
    frame.margin_top = frame.margin_bottom = Inches(0.02)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = str(value or "")
    run.font.name = "나눔고딕"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(PALETTE[color])
    return box


def _ppt_shape(slide, shape_type, x, y, w, h, *, fill: str, line: str, radius=None):
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius is not None and getattr(shape, "adjustments", None):
        shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(PALETTE[fill])
    shape.line.color.rgb = _rgb(PALETTE[line])
    shape.line.width = Pt(1.1)
    return shape


def _ppt_node_column(slide, values: Iterable[str], x: float, w: float, *, fill: str, line: str):
    values = list(values)
    top, bottom, gap = 1.80, 6.55, 0.10
    height = (bottom - top - gap * (len(values) - 1)) / len(values)
    for index, value in enumerate(values):
        y = top + index * (height + gap)
        _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, y, w, height, fill=fill, line=line, radius=0.08)
        _ppt_text(slide, x + 0.07, y + 0.03, w - 0.14, height - 0.06, value, size=9.1)


def _ppt_activity_groups(slide, groups: list[dict[str, Any]], x: float, w: float):
    top, bottom, gap = 1.80, 6.55, 0.10
    group_h = (bottom - top - gap * (len(groups) - 1)) / len(groups)
    for index, group in enumerate(groups):
        y = top + index * (group_h + gap)
        outer = _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, y, w, group_h, fill="white", line="nonworking", radius=0.06)
        outer.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        _ppt_text(slide, x + 0.08, y + 0.04, w - 0.16, 0.28, group["label"], size=8.7, color="muted", bold=True)
        items = group["items"]
        item_gap = 0.06
        item_top = y + 0.38
        item_h = (group_h - 0.46 - item_gap * (len(items) - 1)) / len(items)
        for item_index, value in enumerate(items):
            item_y = item_top + item_index * (item_h + item_gap)
            _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x + 0.10, item_y, w - 0.20, item_h, fill="activity_light", line="activity_light", radius=0.06)
            _ppt_text(slide, x + 0.16, item_y + 0.01, w - 0.32, item_h - 0.02, value, size=8.7)


def _ppt_factor_arrows(slide, factors: list[dict[str, str]], x: float, w: float):
    top, bottom, gap = 1.80, 6.55, 0.12
    height = (bottom - top - gap * (len(factors) - 1)) / len(factors)
    for index, factor in enumerate(factors):
        y = top + index * (height + gap)
        color = "working" if factor["kind"] == "working" else "nonworking"
        _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, x, y, w, height, fill="white", line=color)
        _ppt_text(slide, x + 0.07, y + 0.03, w - 0.26, height - 0.06, factor["text"], size=8.3, color=color, bold=factor["kind"] == "nonworking")


def build_theory_pptx_bytes(plan: dict[str, Any]) -> bytes:
    """Create one editable 16:9 slide using the approved six-column grammar."""

    presentation = Presentation()
    presentation.slide_width = Inches(13.333333)
    presentation.slide_height = Inches(7.5)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(PALETTE["paper"])
    _ppt_text(slide, 0.42, 0.18, 8.55, 0.40, plan["title"], size=19, bold=True, align=PP_ALIGN.LEFT)
    _ppt_text(slide, 0.44, 0.60, 12.35, 0.36, plan["subtitle"], size=9.7, color="muted", align=PP_ALIGN.LEFT)

    for label, x, w, color in zip(COLUMN_LABELS, COLUMN_X, COLUMN_W, HEADER_COLORS):
        _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, x, 1.14, w, 0.46, fill=color, line=color)
        _ppt_text(slide, x + 0.05, 1.16, w - 0.20, 0.40, label, size=9.2, color="white" if color == "outcome" else "ink", bold=True)

    _ppt_node_column(slide, plan["challenges"], COLUMN_X[0], COLUMN_W[0], fill="challenge_light", line="challenge")
    _ppt_activity_groups(slide, plan["activity_groups"], COLUMN_X[1], COLUMN_W[1])
    _ppt_factor_arrows(slide, plan["pre_output_factors"], COLUMN_X[2], COLUMN_W[2])
    _ppt_node_column(slide, plan["outputs"], COLUMN_X[3], COLUMN_W[3], fill="output_light", line="output")
    _ppt_factor_arrows(slide, plan["post_output_factors"], COLUMN_X[4], COLUMN_W[4])
    _ppt_node_column(slide, plan["outcomes"], COLUMN_X[5], COLUMN_W[5], fill="outcome_light", line="outcome")

    _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, 4.55, 6.88, 0.55, 0.20, fill="white", line="working")
    _ppt_text(slide, 5.13, 6.84, 0.62, 0.28, "작동요인", size=8.2, color="working", align=PP_ALIGN.LEFT)
    _ppt_shape(slide, MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, 6.10, 6.88, 0.55, 0.20, fill="white", line="nonworking")
    _ppt_text(slide, 6.68, 6.84, 0.78, 0.28, "비작동요인", size=8.2, color="nonworking", align=PP_ALIGN.LEFT)

    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def _font(size: int, *, bold: bool = False):
    candidates = [
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), candidates[-1])
    return ImageFont.truetype(str(path), size=size)


def _wrap(draw: ImageDraw.ImageDraw, value: str, font, width: int, max_lines: int) -> str:
    lines: list[str] = []
    current = ""
    for word in str(value or "").split():
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    result = "\n".join(lines[:max_lines])
    if len(lines) >= max_lines and " ".join(lines) != str(value or "").strip():
        result = result.rstrip(" .") + "…"
    return result


def _hex(name: str) -> str:
    return f"#{PALETTE[name]}"


def _draw_arrow(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str, outline: str, width: int = 3):
    x1, y1, x2, y2 = box
    head = max(18, int((x2 - x1) * 0.16))
    mid = (y1 + y2) // 2
    points = [(x1, y1), (x2 - head, y1), (x2 - head, y1 + (y2 - y1) // 4), (x2, mid), (x2 - head, y2 - (y2 - y1) // 4), (x2 - head, y2), (x1, y2)]
    draw.polygon(points, fill=fill, outline=outline)
    if width > 1:
        draw.line(points + [points[0]], fill=outline, width=width, joint="curve")


def build_theory_png_bytes(plan: dict[str, Any]) -> bytes:
    """Fallback renderer used only when a PPT renderer is unavailable."""

    image = Image.new("RGB", (2000, 1125), _hex("paper"))
    draw = ImageDraw.Draw(image)
    draw.text((65, 27), plan["title"], font=_font(43, bold=True), fill=_hex("ink"))
    draw.text((68, 88), _wrap(draw, plan["subtitle"], _font(21), 1800, 2), font=_font(21), fill=_hex("muted"), spacing=4)
    scale = 145
    xs = [int(x * scale) for x in COLUMN_X]
    ws = [int(w * scale) for w in COLUMN_W]
    header_y1, header_y2 = 170, 238
    for label, x, w, color in zip(COLUMN_LABELS, xs, ws, HEADER_COLORS):
        _draw_arrow(draw, (x, header_y1, x + w, header_y2), fill=_hex(color), outline=_hex(color), width=2)
        text_fill = _hex("white") if color == "outcome" else _hex("ink")
        bbox = draw.textbbox((0, 0), label, font=_font(18, bold=True))
        draw.text((x + (w - (bbox[2] - bbox[0])) / 2 - 5, 184), label, font=_font(18, bold=True), fill=text_fill)
    body_top, body_bottom = 270, 990

    def nodes(values: list[str], column: int, fill: str, line: str):
        gap = 14
        h = (body_bottom - body_top - gap * (len(values) - 1)) // len(values)
        for index, value in enumerate(values):
            y = body_top + index * (h + gap)
            draw.rounded_rectangle((xs[column], y, xs[column] + ws[column], y + h), radius=16, fill=_hex(fill), outline=_hex(line), width=2)
            font = _font(18)
            wrapped = _wrap(draw, value, font, ws[column] - 28, 4)
            bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=4, align="center")
            draw.multiline_text((xs[column] + (ws[column] - (bbox[2] - bbox[0])) / 2, y + (h - (bbox[3] - bbox[1])) / 2), wrapped, font=font, fill=_hex("ink"), spacing=4, align="center")

    nodes(plan["challenges"], 0, "challenge_light", "challenge")
    nodes(plan["outputs"], 3, "output_light", "output")
    nodes(plan["outcomes"], 5, "outcome_light", "outcome")
    groups = plan["activity_groups"]
    gap = 14
    group_h = (body_bottom - body_top - gap * (len(groups) - 1)) // len(groups)
    for index, group in enumerate(groups):
        y = body_top + index * (group_h + gap)
        draw.rounded_rectangle((xs[1], y, xs[1] + ws[1], y + group_h), radius=16, fill=_hex("white"), outline=_hex("nonworking"), width=2)
        draw.text((xs[1] + 14, y + 10), group["label"], font=_font(16, bold=True), fill=_hex("muted"))
        item_top = y + 45
        item_gap = 8
        item_h = (group_h - 55 - item_gap * (len(group["items"]) - 1)) // len(group["items"])
        for item_index, value in enumerate(group["items"]):
            item_y = item_top + item_index * (item_h + item_gap)
            draw.rounded_rectangle((xs[1] + 12, item_y, xs[1] + ws[1] - 12, item_y + item_h), radius=10, fill=_hex("activity_light"))
            wrapped = _wrap(draw, value, _font(16), ws[1] - 44, 3)
            draw.multiline_text((xs[1] + 22, item_y + 9), wrapped, font=_font(16), fill=_hex("ink"), spacing=3)

    def factors(values: list[dict[str, str]], column: int):
        factor_gap = 16
        h = (body_bottom - body_top - factor_gap * (len(values) - 1)) // len(values)
        for index, item in enumerate(values):
            y = body_top + index * (h + factor_gap)
            color = item["kind"]
            _draw_arrow(draw, (xs[column], y, xs[column] + ws[column], y + h), fill=_hex("white"), outline=_hex(color), width=3)
            font = _font(15, bold=item["kind"] == "nonworking")
            wrapped = _wrap(draw, item["text"], font, ws[column] - 42, 5)
            draw.multiline_text((xs[column] + 15, y + 12), wrapped, font=font, fill=_hex(color), spacing=3, align="center")

    factors(plan["pre_output_factors"], 2)
    factors(plan["post_output_factors"], 4)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_theory_pptx_to_png_bytes(pptx: bytes, plan: dict[str, Any]) -> tuple[bytes, str]:
    """Render the authored PPTX to PNG; retain a deterministic fallback."""

    office = shutil.which("libreoffice") or shutil.which("soffice")
    pdftoppm = shutil.which("pdftoppm")
    if office and pdftoppm:
        with tempfile.TemporaryDirectory(prefix="kodame-theory-") as temp_name:
            temp = Path(temp_name)
            pptx_path = temp / "theory.pptx"
            pptx_path.write_bytes(pptx)
            profile_uri = (temp / "lo-profile").resolve().as_uri()
            converted = subprocess.run(
                [office, "--headless", f"-env:UserInstallation={profile_uri}", "--convert-to", "pdf", "--outdir", str(temp), str(pptx_path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            pdf_path = temp / "theory.pdf"
            if converted.returncode == 0 and pdf_path.is_file():
                raster = subprocess.run(
                    [pdftoppm, "-f", "1", "-singlefile", "-png", "-r", "300", str(pdf_path), str(temp / "theory")],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=False,
                )
                png_path = temp / "theory.png"
                if raster.returncode == 0 and png_path.is_file():
                    png = png_path.read_bytes()
                    with Image.open(BytesIO(png)) as rendered:
                        if rendered.width >= 1600 and rendered.height >= 850:
                            return png, "libreoffice_pptx"
    return build_theory_png_bytes(plan), "pillow_fallback"


def build_theory_visual_artifacts(context: dict, sections_by_id: dict[str, str]) -> dict[str, Any]:
    plan = request_theory_visual_plan(context, sections_by_id)
    pptx = build_theory_pptx_bytes(plan)
    png, render_source = render_theory_pptx_to_png_bytes(pptx, plan)
    if len(pptx) < 5000 or not png.startswith(b"\x89PNG"):
        raise RuntimeError("변화이론 PPTX/PNG 산출물 검증에 실패했습니다.")
    return {
        "plan": plan,
        "pptx": pptx,
        "png": png,
        "model": current_llm_model(),
        "design_version": THEORY_VISUAL_DESIGN_VERSION,
        "render_source": render_source,
    }
