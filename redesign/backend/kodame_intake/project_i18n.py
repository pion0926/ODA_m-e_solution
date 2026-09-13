from __future__ import annotations

from fastapi import HTTPException

from .db import connection, current_account_id, current_project_id
from .translations import LANGUAGES, translation_seed


def resolve_project_locale(requested: str | None = None) -> tuple[str, str]:
    """Return the validated display locale and the project's source locale."""
    project_id = current_project_id()
    account_id = current_account_id()
    with connection() as conn:
        project = conn.execute(
            "SELECT default_locale,supported_locales FROM projects WHERE id=%s",
            (project_id,),
        ).fetchone()
        member = conn.execute(
            "SELECT preferred_locale FROM project_members WHERE project_id=%s AND account_id=%s",
            (project_id, account_id),
        ).fetchone()
    if not project:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    supported = project["supported_locales"] or ["ko"]
    preferred = str(requested or (member or {}).get("preferred_locale") or project["default_locale"]).strip().lower()
    if preferred not in supported:
        raise HTTPException(422, "이 프로젝트에서 제공하지 않는 언어입니다.")
    return preferred, project["default_locale"]


def get_project_i18n() -> dict:
    project_id = current_project_id()
    account_id = current_account_id()
    with connection() as conn:
        project = conn.execute(
            "SELECT default_locale,supported_locales FROM projects WHERE id=%s",
            (project_id,),
        ).fetchone()
        member = conn.execute(
            "SELECT preferred_locale FROM project_members WHERE project_id=%s AND account_id=%s",
            (project_id, account_id),
        ).fetchone()
        rows = conn.execute(
            "SELECT locale,translations FROM project_translations WHERE project_id=%s",
            (project_id,),
        ).fetchall()
    if not project:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    supported = project["supported_locales"] or ["ko"]
    saved = {row["locale"]: row["translations"] for row in rows}
    translations = {locale: saved.get(locale) or translation_seed(locale) for locale in supported}
    preferred = (member or {}).get("preferred_locale") or project["default_locale"]
    if preferred not in supported:
        preferred = project["default_locale"]
    return {
        "default_locale": project["default_locale"],
        "supported_locales": supported,
        "preferred_locale": preferred,
        "languages": {locale: LANGUAGES[locale] for locale in supported if locale in LANGUAGES},
        "translations": translations,
    }


def set_preferred_locale(locale: str) -> dict:
    project_id = current_project_id()
    account_id = current_account_id()
    normalized = str(locale or "").strip().lower()
    with connection() as conn, conn.transaction():
        project = conn.execute(
            "SELECT default_locale,supported_locales FROM projects WHERE id=%s",
            (project_id,),
        ).fetchone()
        if not project or normalized not in (project["supported_locales"] or []):
            raise HTTPException(422, "이 프로젝트에서 제공하지 않는 언어입니다.")
        updated = conn.execute(
            """UPDATE project_members SET preferred_locale=%s
               WHERE project_id=%s AND account_id=%s RETURNING account_id""",
            (normalized, project_id, account_id),
        ).fetchone()
        if not updated:
            raise HTTPException(403, "프로젝트 구성원만 언어를 선택할 수 있습니다.")
    return {"preferred_locale": normalized}
