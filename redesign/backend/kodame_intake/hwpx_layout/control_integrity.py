"""Narrow, text-preserving repairs for native Hangul control compatibility."""
from __future__ import annotations

import re

_EMPTY_CONTROL = re.compile(r"<hp:ctrl\b[^>]*>\s*</hp:ctrl>|<hp:ctrl\b[^>]*/>")


def remove_empty_controls_xml(xml: str) -> tuple[str, int]:
    """Remove only childless controls, never populated controls or their runs.

    Removing a header/footer can leave its enclosing hp:ctrl empty. Native
    Hangul terminated on the September 2026 report containing two such nodes;
    removing only those nodes made the same report open in the user's test.
    Preserve the XML bytes elsewhere, including line caches and table layout.
    """
    return _EMPTY_CONTROL.subn("", xml)
