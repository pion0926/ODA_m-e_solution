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


def is_system_performance_note(item: str, note: str) -> bool:
    """Identify only the generator's complete canonical record and note marker.

    Free-form notes, quoted mentions and legacy/manual table aliases are not
    classified from keywords. The saved record remains available for review;
    this predicate is used only by the HWPX reader projection.
    """
    from .achievement_records import indexed_record_fields

    fields = indexed_record_fields(item)
    required = {'성과지표', '기초선', '목표치', '종료선', '대비결과', '지표입증수단(MOV)', '비고'}
    if fields is None or not required.issubset(fields):
        return False
    marker = '저장된 성과지표 분석 결과를 반영함'
    return note == marker or note.startswith(marker + ';')
