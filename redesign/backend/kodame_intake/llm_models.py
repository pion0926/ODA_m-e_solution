from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from .settings import OPENROUTER_MODEL


MODEL_OPTIONS = (
    {
        "id": "google/gemini-3.5-flash-lite",
        "name": "Gemini 3.5 Flash Lite",
        "provider": "Google",
        "description": "빠른 문서 분류와 반복 작성에 적합한 기본 모델",
        "tier": "speed",
    },
    {
        "id": "anthropic/claude-opus-4.8",
        "name": "Claude Opus 4.8",
        "provider": "Anthropic",
        "description": "복잡한 평가 판단과 고품질 보고서 작성에 적합한 고성능 모델",
        "tier": "quality",
    },
)

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
    value = validate_model(model) if model else DEFAULT_MODEL
    token = _model_override.set(value)
    try:
        yield value
    finally:
        _model_override.reset(token)

