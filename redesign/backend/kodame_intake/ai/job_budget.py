"""One budget shared by nested retries and copied thread contexts."""
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_job = ContextVar('ai_job_budget', default=None)


class BudgetExceeded(RuntimeError):
    pass


@contextmanager
def job_budget(ident=None):
    seconds = float(os.getenv('AI_JOB_SECONDS', '3600'))
    token = _job.set({'id': str(ident or uuid.uuid4()),
                     'deadline': time.monotonic()+seconds if seconds > 0 else None})
    try:
        yield
    finally:
        _job.reset(token)


def current_job():
    job = _job.get()
    if job and job['deadline'] is not None and time.monotonic() >= job['deadline']:
        raise BudgetExceeded('AI 작업의 전체 시간 한도에 도달했습니다. 완료 결과는 보존됩니다.')
    return job['id'] if job else 'request-' + str(uuid.uuid4())
