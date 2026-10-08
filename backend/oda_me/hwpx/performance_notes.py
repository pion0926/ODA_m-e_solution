"""Reader labels for known saved performance-selection diagnostics."""
from __future__ import annotations

import re


_UNDATED_ACTUAL_NOTE = re.compile(
    r"(?P<prefix>^|;\s*)actual:\s*기준일\s*미기재,\s*동일\s*단위\s*수치\s*우선\s*비교"
    r"(?=\s*(?:[;|]|·\s*목표:|$))",
    re.MULTILINE,
)
_READER_NOTE = "실적 선택 기준: 기준일이 없어 같은 단위의 수치를 우선 비교함"


def readable_performance_notes(value: str) -> str:
    """Project only the exact system note, leaving figures and quoted prose intact."""
    return _UNDATED_ACTUAL_NOTE.sub(lambda match: match.group("prefix") + _READER_NOTE, value)
