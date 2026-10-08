"""Reader projection for known numeric-validation metadata in grade cells.

Saved judgments retain their exact diagnostics. Only the complete, generated
diagnostic block is projected here; ordinary values and unknown prose survive.
"""
import re


_NUMBER = r"[+-]?\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?"
_UNVERIFIED_VALUE = (
    rf"측정값\s+{_NUMBER}를\s+지정한\s+원문에서\s+확인할\s+수\s+"
    r"(?:없습니다|없음)\.?"
)
_KNOWN_BLOCK = re.compile(
    r"(?:일부\s+정량\s+비교\s+수치가\s+원문\s+검증을\s+통과하지\s+못해\s+"
    r"해당\s+항목을\s+미확인으로\s+처리했습니다\.?\s*)?"
    r"정량\s+비교\s+수치를\s+지정된\s+원문에서\s+검증하지\s+못해\s+"
    r"이\s+항목의\s+판정을\s+(?:보류합니다|보류함)\.?\s*"
    rf"(?:{_UNVERIFIED_VALUE}(?:\s+|$))+"
)
READER_MEASUREMENT_LIMITATION = "일부 정량 비교는 원문 근거가 충분히 확인되지 않아 계산에서 제외함."
_LEGACY_READER_LIMITATION = "정량 비교 근거가 충분히 확인되지 않아 해당 항목의 판정을 보류함."


def readable_grade_reason(value: str) -> str:
    """Replace an exact known diagnostic block without editing other facts."""
    # Existing saved grade drafts may already carry the previous reader
    # projection. Upgrade only its exact generated prefix on export.
    if value.startswith(_LEGACY_READER_LIMITATION):
        value = READER_MEASUREMENT_LIMITATION + value[len(_LEGACY_READER_LIMITATION):]
    return _KNOWN_BLOCK.sub(
        lambda match: READER_MEASUREMENT_LIMITATION + (" " if match.end() < len(value) else ""),
        value,
    )
