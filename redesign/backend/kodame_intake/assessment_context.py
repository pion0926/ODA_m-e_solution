from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo


SEOUL = ZoneInfo("Asia/Seoul")


def assessment_date() -> date:
    return datetime.now(SEOUL).date()


def _period_end(period: str) -> date | None:
    candidates: list[date] = []
    for year, month, day in re.findall(
        r"(20\d{2})\s*(?:년|[./-])\s*(\d{1,2})\s*(?:월|[./-])\s*(\d{1,2})\s*일?",
        period,
    ):
        try:
            candidates.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    if not candidates:
        for year, month in re.findall(r"(20\d{2})\s*(?:년|[./-])\s*(\d{1,2})\s*월?", period):
            try:
                year_value, month_value = int(year), int(month)
                candidates.append(date(year_value, month_value, monthrange(year_value, month_value)[1]))
            except ValueError:
                continue
    return candidates[-1] if candidates else None


def project_phase(period: str, as_of: date | None = None) -> str:
    end = _period_end(str(period or ""))
    if end is None:
        return "unknown"
    return "ongoing" if (as_of or assessment_date()) <= end else "ended"


def assessment_label(status: str) -> str:
    return "현재시점 문헌기반 평가" if status != "ended" else "종료시점 평가"


def assessment_scope(overview: dict) -> dict:
    period = str((overview.get("period") or {}).get("text") or "")
    as_of = assessment_date()
    status = project_phase(period, as_of)
    return {
        "project_period": period,
        "project_status": status,
        "assessment_as_of": as_of.isoformat(),
        "allowed_report_label": assessment_label(status),
    }
