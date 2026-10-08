"""Reader labels for known saved performance-selection diagnostics."""
from __future__ import annotations

import re


_UNDATED_ACTUAL_NOTE = re.compile(
    r"(?P<prefix>^|;\s*)actual:\s*기준일\s*미기재,\s*동일\s*단위\s*수치\s*우선\s*비교"
    r"(?=\s*(?:[;|]|·\s*목표:|$))",
    re.MULTILINE,
)
_READER_NOTE = "실적 선택 기준: 기준일이 없어 같은 단위의 수치를 우선 비교함"
_SYSTEM_INTERPRETATION_FALLBACK = (
    'ㅇ 저장된 목표·실적과 남은 근거 공백을 구분하여 해석함. 기준일 또는 자료 범위가 다른 목표는 '
    '단순 합산하지 않으며, 미확인 실적은 0으로 간주하지 않음.'
)


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


def system_performance_interpretation_omissions(
    texts: list[str], has_system_records: bool, only_system_records: bool = False,
) -> set[int]:
    """Exclude only the exact generic fallback and a resulting empty heading."""
    if not has_system_records:
        return set()
    omitted = {index for index, text in enumerate(texts)
               if text.strip() == _SYSTEM_INTERPRETATION_FALLBACK}
    if only_system_records:
        omitted.update(index for index, text in enumerate(texts)
                       if text.strip() == '2. 성과지표별 목표 대비 실적 분석'
                       or text.strip().startswith('최신 사업설계매트릭스(PDM)에 명시된 성과 및 산출물 지표를 기준으로 한 지표별 세부 실적'))
    for index, text in enumerate(texts):
        if text.strip() != '3. 종합 평가 및 시사점':
            continue
        following = [other for other in range(index + 1, len(texts)) if texts[other].strip()]
        if following and all(other in omitted for other in following):
            omitted.add(index)
    return omitted
