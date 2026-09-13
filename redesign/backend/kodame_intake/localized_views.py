from __future__ import annotations

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from .db import connection, current_project_id
from .openrouter import AnalysisError, MissingApiKey, _request_json
from .translations import LANGUAGES


SCREEN_SCOPES = ("dashboard", "project_overview", "pdm", "evaluation")

# Only human-readable fields are translated. IDs, codes, statuses, scores,
# document names, dates, URLs and other application-contract values never enter
# the translation prompt and therefore cannot be changed by the model.
TRANSLATABLE_KEYS = {
    "name",
    "business_name",
    "country",
    "location",
    "period",
    "budget",
    "donor",
    "implementer",
    "partner",
    "objective",
    "beneficiaries",
    "activities",
    "outputs",
    "outcomes",
    "text",
    "summary",
    "assumption",
    "preconditions",
    "mov",
    "target",
    "actual",
    "evidence",
    "note",
    "indicator",
    "program",
    "tier_name",
    "tier_label",
    "government_grade",
    "risk_title",
    "risk_analysis",
    "forecast",
    "root_causes",
    "recommendations",
    "evidence_needed",
    "question",
    "finding",
    "evidence_gaps",
    "action_items",
    "score_reason",
    "formula",
    "message",
    "hint",
    "type",
    "criterion",
    "title",
    "detail",
}

TRANSLATION_SYSTEM_PROMPT = """You translate user-interface content for an ODA performance-management and evaluation system.
Translate every supplied value completely into the requested target language.
Use professional public-sector and international-development terminology.
Preserve PDM, DAC, OECD, KOICA, CPCR, MCI Triage, OVI, organization names, codes, numbers, units and date ranges unless a conventional localized name exists.
Do not summarize, add facts, remove qualifications, or change list order.
Preserve line breaks and bullet structure inside each value.
Return one JSON object only, with a `translations` object containing every input key exactly once. Do not use Markdown."""


class ViewTranslationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextSlot:
    key: str
    path: tuple[str | int, ...]
    source: str


def _contains_language_text(value: str) -> bool:
    return any(character.isalpha() for character in value)


def _walk_translatable_strings(value: Any, path: tuple[str | int, ...] = ()) -> Iterable[tuple[tuple[str | int, ...], str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = (*path, key)
            if isinstance(item, str) and key in TRANSLATABLE_KEYS:
                cleaned = item.strip()
                if cleaned and _contains_language_text(cleaned):
                    yield child_path, item
            elif isinstance(item, (dict, list)):
                yield from _walk_translatable_strings(item, child_path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            child_path = (*path, index)
            if isinstance(item, str):
                parent_key = path[-1] if path else ""
                cleaned = item.strip()
                if parent_key in TRANSLATABLE_KEYS and cleaned and _contains_language_text(cleaned):
                    yield child_path, item
            elif isinstance(item, (dict, list)):
                yield from _walk_translatable_strings(item, child_path)


def collect_text_slots(views: dict[str, Any]) -> list[TextSlot]:
    slots: list[TextSlot] = []
    for index, (path, source) in enumerate(_walk_translatable_strings(views), start=1):
        slots.append(TextSlot(key=f"t{index:04d}", path=path, source=source))
    return slots


def _set_path(payload: Any, path: tuple[str | int, ...], value: str) -> None:
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def _source_digest(views: dict[str, Any], slots: list[TextSlot]) -> str:
    stable = {
        "contract": 1,
        "scopes": list(SCREEN_SCOPES),
        "values": [{"path": list(slot.path), "source": slot.source} for slot in slots],
    }
    return hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _translation_batches(slots: list[TextSlot], *, max_items: int = 45, max_chars: int = 18000) -> list[list[TextSlot]]:
    batches: list[list[TextSlot]] = []
    batch: list[TextSlot] = []
    characters = 0
    for slot in slots:
        size = len(slot.source)
        if batch and (len(batch) >= max_items or characters + size > max_chars):
            batches.append(batch)
            batch = []
            characters = 0
        batch.append(slot)
        characters += size
    if batch:
        batches.append(batch)
    return batches


def _translate_batch(batch: list[TextSlot], locale: str, source_locale: str) -> tuple[dict[str, str], str]:
    target = LANGUAGES[locale]["native_name"]
    source = LANGUAGES.get(source_locale, {}).get("native_name", source_locale)
    translation_request = {
        "source_language": source,
        "target_language": target,
        "items": [{"key": slot.key, "value": slot.source} for slot in batch],
        "response_shape": {
            "translations": {slot.key: f"translated value for {slot.key}" for slot in batch}
        },
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        prompt = {
            **translation_request,
            "attempt": attempt,
            "validation": "Every key in response_shape.translations is mandatory.",
        }
        try:
            result, model = _request_json(
                TRANSLATION_SYSTEM_PROMPT,
                json.dumps(prompt, ensure_ascii=False, indent=2),
                "KODAME Localized Dashboard and Project Overview",
            )
            values = result.get("translations")
            if not isinstance(values, dict):
                raise ViewTranslationError("번역 응답에 translations 객체가 없습니다.")
            missing = [slot.key for slot in batch if not str(values.get(slot.key) or "").strip()]
            if missing:
                raise ViewTranslationError(f"번역 응답에서 {len(missing)}개 문장이 누락되었습니다.")
            return {slot.key: str(values[slot.key]).strip() for slot in batch}, model
        except (AnalysisError, ViewTranslationError) as exc:
            last_error = exc
    raise ViewTranslationError(f"번역 배치 검증이 3회 실패했습니다: {last_error}") from last_error


def _cached_translation(locale: str, digest: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """SELECT payload FROM project_content_translations
               WHERE locale=%s AND scope='dashboard_project_overview' AND source_digest=%s""",
            (locale, digest),
        ).fetchone()
    return dict(row["payload"]) if row else None


def _cache_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return jsonable_encoder(payload)


def _store_translation(locale: str, digest: str, payload: dict[str, Any], model: str) -> None:
    # PDM assignment rows can contain UUID/datetime values. FastAPI normally
    # converts them at the response boundary, but this cache is written before
    # that boundary, so normalize it explicitly for JSONB as well.
    cache_payload = _cache_safe_payload(payload)
    with connection() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO project_content_translations(
                   project_id,locale,scope,source_digest,payload,model,updated_at
               ) VALUES (%s,%s,'dashboard_project_overview',%s,%s,%s,now())
               ON CONFLICT(project_id,locale,scope,source_digest) DO UPDATE
               SET payload=EXCLUDED.payload,model=EXCLUDED.model,updated_at=now()""",
            (current_project_id(), locale, digest, Jsonb(cache_payload), model),
        )


def localize_project_views(
    views: dict[str, Any],
    *,
    locale: str,
    source_locale: str = "ko",
) -> dict[str, Any]:
    normalized = str(locale or source_locale).strip().lower()
    if normalized not in LANGUAGES:
        raise ViewTranslationError("지원하지 않는 화면 언어입니다.")
    if normalized == source_locale:
        return {
            "locale": normalized,
            "translation_status": "source",
            "translated_count": 0,
            "views": views,
        }

    slots = collect_text_slots(views)
    digest = _source_digest(views, slots)
    cached = _cached_translation(normalized, digest)
    if cached:
        return {
            "locale": normalized,
            "translation_status": "cached",
            "source_digest": digest,
            "translated_count": len(slots),
            "views": cached,
        }

    translations: dict[str, str] = {}
    models: list[str] = []
    try:
        batches = _translation_batches(slots)
        # A project can contain hundreds of PDM/DAC display strings. Independent
        # batches are translated concurrently so the first language switch is
        # bounded by a few model calls instead of the sum of every model call.
        workers = min(4, len(batches)) or 1
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="view-i18n") as executor:
            results = executor.map(
                lambda batch: _translate_batch(batch, normalized, source_locale),
                batches,
            )
            for values, model in results:
                translations.update(values)
                models.append(model)
    except (MissingApiKey, AnalysisError, ViewTranslationError) as exc:
        raise ViewTranslationError(str(exc)) from exc

    if len(translations) != len(slots):
        raise ViewTranslationError("동적 화면 번역 완전성 검증에 실패했습니다.")
    localized = copy.deepcopy(views)
    for slot in slots:
        _set_path(localized, slot.path, translations[slot.key])
    model = models[-1] if models else ""
    _store_translation(normalized, digest, localized, model)
    return {
        "locale": normalized,
        "translation_status": "generated",
        "source_digest": digest,
        "translated_count": len(slots),
        "model": model,
        "views": localized,
    }
