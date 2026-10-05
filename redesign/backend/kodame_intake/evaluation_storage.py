"""Bounded retries for idempotent DAC checkpoint writes, without another AI call."""
from functools import wraps
import time
from psycopg import OperationalError
from psycopg.errors import SerializationFailure, DeadlockDetected
from psycopg_pool import PoolTimeout


def retry_storage(operation):
    @wraps(operation)
    def run(*args, **kwargs):
        for attempt in range(3):
            try:
                return operation(*args, **kwargs)
            except (OperationalError, SerializationFailure, DeadlockDetected, PoolTimeout):
                if attempt == 2:
                    raise
                time.sleep(0.25 * 2**attempt)
    return run
