"""Fence document attempts and cooperate with user cancellation."""
from contextvars import ContextVar
from contextlib import contextmanager
from .db import connection

_attempt = ContextVar('intake_attempt', default=None)


class IntakeStopped(BaseException):
    """Bypass provider retry handlers; caught at the worker boundary."""


def finish_attempt():
    _attempt.set(None)


@contextmanager
def attempt_context(document_id, token):
    marker = _attempt.set((document_id, token))
    try:
        yield
    finally:
        _attempt.reset(marker)


def check(conn=None, *, lock=False):
    attempt = _attempt.get()
    if not attempt:
        return
    if conn is None:
        with connection() as current:
            return check(current)
    row = conn.execute('SELECT status,run_token,cancel_requested FROM intake_documents WHERE id=%s' + (' FOR UPDATE' if lock else ''), (attempt[0],)).fetchone()
    if not row or row['status'] != 'processing' or row['run_token'] != attempt[1] or row['cancel_requested']:
        raise IntakeStopped()
