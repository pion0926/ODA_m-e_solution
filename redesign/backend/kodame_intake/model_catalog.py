"""Reviewed model allowlist; live routing prices, never subscription prices.

Add a model to model_catalog.json only after checking its structured text API.
Public catalog retrieval never sends credentials or project content.
"""
from __future__ import annotations

import copy
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock

import httpx

CATALOG = json.loads(Path(__file__).with_name("model_catalog.json").read_text(encoding="utf-8"))
MODEL_OPTIONS = tuple(CATALOG["models"])
_cache = None
_attempt_at = 0.0
_lock = Lock()
_logger = logging.getLogger(__name__)


def _fetch_catalog() -> dict:
    """Retry an incomplete upstream/cache response once through a fresh URL."""
    for attempt in range(2):
        try:
            options = {"params": {"refresh": str(time.time_ns())}} if attempt else {}
            response = httpx.get(CATALOG["source"], timeout=8.0, **options)
            response.raise_for_status()
            return parse_catalog(response.json(), datetime.now(timezone.utc).isoformat())
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            _logger.warning("Model catalog fetch failed: attempt=%s error=%s", attempt + 1, type(exc).__name__)
            if attempt:
                raise


def per_million(value):
    try:
        number = Decimal(str(value))
        return float(number * 1_000_000) if number.is_finite() and number >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_catalog(data: dict, checked_at: str) -> dict:
    if not isinstance(data.get("data"), list) or not data["data"]:
        raise ValueError("모델 목록 응답이 비어 있습니다.")
    offered = {row["id"]: row for row in data["data"] if isinstance(row, dict) and row.get("id")}
    rows = []
    for item in MODEL_OPTIONS:
        live = offered.get(item["id"])
        price = (live or {}).get("pricing") or {}
        parameters = (live or {}).get("supported_parameters") or []
        architecture = (live or {}).get("architecture") or {}
        usable = bool(live and "response_format" in parameters and
                      "text" in architecture.get("output_modalities", ["text"]))
        rows.append({**item, "available": usable,
                     "input": per_million(price.get("prompt")),
                     "output": per_million(price.get("completion")),
                     "pricing_overrides": price.get("overrides") or [],
                     "context_length": (live or {}).get("context_length"),
                     "temperature": "temperature" in parameters})
    return {"models": rows, "checked_at": checked_at, "source": CATALOG["source"],
            "official_sources": CATALOG["official_sources"], "price_status": "live"}


def get_model_catalog(*, refresh: bool = False) -> dict:
    global _cache, _attempt_at
    with _lock:
        # A failed upstream call is also throttled; user traffic cannot hammer it.
        elapsed = time.monotonic() - _attempt_at
        retry_interval = 15 if refresh or (_cache and _cache.get("price_status") == "stale") else 3600
        if _cache is None or elapsed > retry_interval:
            _attempt_at = time.monotonic()
            try:
                _cache = _fetch_catalog()
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                _cache = copy.deepcopy(_cache or {
                    **CATALOG, "models": [{**r, "available": None} for r in MODEL_OPTIONS]})
                _cache["price_status"] = "stale"
        result = copy.deepcopy(_cache)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(result["checked_at"])).total_seconds()
    result["can_assign"] = result["price_status"] == "live" and age < 86400
    result["currency"] = "USD"
    result["unit"] = "1M tokens"
    result["billing_note"] = (
        "OpenRouter 경유 표준 텍스트 입력·출력 100만 토큰당 USD 참고 단가입니다. "
        "구독 요금이 아니며 캐시, 추론 토큰, 긴 문맥 추가 단가, 도구, 공급 경로, 세금·충전 수수료에 따라 "
        "실제 청구액이 달라집니다. 예시는 보고서 1건 견적이 아닙니다."
    )
    return result


def require_available_model(model: str) -> str:
    from .llm_models import validate_model
    selected = validate_model(model)
    catalog = get_model_catalog()
    option = next(r for r in catalog["models"] if r["id"] == selected)
    if not catalog["can_assign"] or not option["available"]:
        raise ValueError("모델 제공 상태를 확인할 수 없습니다. 가격·모델 목록을 새로고침한 후 다시 배정해 주세요.")
    return selected


def prepare_model_payload(payload: dict) -> dict:
    """Normalize known provider differences without changing the selected model."""
    from .llm_models import validate_model
    result = dict(payload)
    model = validate_model(result["model"])
    option = next(r for r in MODEL_OPTIONS if r["id"] == model)
    if not option["temperature"]:
        result.pop("temperature", None)
        result.pop("top_p", None)
    # No alternate model routing; provider outages must never switch project policy.
    result.pop("models", None)
    result.pop("route", None)
    return result
