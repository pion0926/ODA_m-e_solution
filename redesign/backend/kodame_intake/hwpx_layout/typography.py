from __future__ import annotations

import re


def normalize_report_text_colors_header_xml(xml: str) -> tuple[str, int]:
    """Render every non-white document text style as full black.

    The official template contains legacy red/blue/near-black authoring styles.
    Generated report content can inherit one of them through a retained run,
    which makes otherwise identical body text appear gray or colored in rHWP.
    White reverse text remains white; every other text style is normalized.
    """

    changed = 0

    def normalize(match: re.Match[str]) -> str:
        nonlocal changed
        opening = match.group(0)
        color = re.search(r'\btextColor="([^"]+)"', opening)
        if not color or color.group(1).lower() in {"#000000", "#ffffff"}:
            return opening
        changed += 1
        return re.sub(r'(\btextColor=")[^"]+', r"\g<1>#000000", opening, count=1)

    return re.sub(r"<hh:charPr\b[^>]*>", normalize, xml), changed
