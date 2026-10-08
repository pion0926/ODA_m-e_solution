"""Bound in-flight provider requests per process, including nested thread pools."""
import os
import threading
import time
from contextlib import contextmanager

MAX_IN_FLIGHT = max(1,min(16,int(os.getenv('AI_MAX_IN_FLIGHT','4'))))
_slots = threading.BoundedSemaphore(MAX_IN_FLIGHT)

@contextmanager
def request_slot(payload=None):
    from ..intake_control import check
    from ..report_cancellation import check_cancelled
    deadline=time.monotonic()+300
    while not _slots.acquire(timeout=1):
        check()
        check_cancelled()
        if time.monotonic() >= deadline:
            raise TimeoutError('AI 요청 대기 한도를 초과했습니다. 잠시 후 다시 실행해 주세요.')
    try:
        check()
        check_cancelled()
        from ..translation_jobs import check_translation
        check_translation()
        from .global_budget import global_slot
        from ..llm_models import current_llm_model
        with global_slot(payload if payload is not None else {'model':current_llm_model(),'messages':[]}) as reservation:
            yield reservation
    finally:
        _slots.release()
