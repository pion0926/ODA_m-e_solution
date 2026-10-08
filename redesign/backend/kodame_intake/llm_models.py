from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from .settings import OPENROUTER_MODEL
from .model_catalog import MODEL_OPTIONS


ALLOWED_MODEL_IDS = frozenset(item["id"] for item in MODEL_OPTIONS)
DEFAULT_MODEL = OPENROUTER_MODEL if OPENROUTER_MODEL in ALLOWED_MODEL_IDS else MODEL_OPTIONS[0]["id"]

_model_override: ContextVar[str] = ContextVar("kodame_llm_model", default="")


def validate_model(model: str) -> str:
    value = str(model or "").strip()
    if value not in ALLOWED_MODEL_IDS:
        raise ValueError("지원하지 않는 AI 모델입니다.")
    return value


def current_llm_model() -> str:
    return _model_override.get() or DEFAULT_MODEL


@contextmanager
def llm_model_context(model: str | None = None):
    value = validate_model(model) if model else current_llm_model()
    token = _model_override.set(value)
    try:
        yield value
    finally:
        _model_override.reset(token)
