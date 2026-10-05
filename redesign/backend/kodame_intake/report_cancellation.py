"""Cooperative cancellation keeps the workflow lock until the worker exits."""
from contextlib import contextmanager
from contextvars import ContextVar

from .db import connection

_run = ContextVar("report_generation_run", default=None)


class ReportCancelled(Exception):
    pass


def current_generation_run_id():
    value = _run.get()
    return str(value) if value else None


@contextmanager
def generation_run(run_id):
    token = _run.set(run_id)
    try:
        yield
    finally:
        _run.reset(token)


def check_cancelled():
    run_id = _run.get()
    if run_id:
        with connection() as conn:
            row = conn.execute("SELECT cancel_requested FROM report_generation_runs WHERE id=%s", (run_id,)).fetchone()
        if row and row["cancel_requested"]:
            raise ReportCancelled("사용자 요청으로 보고서 생성을 중단했습니다. 저장된 본문은 보존됩니다.")
