from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

from .db import connection
from .llm_models import DEFAULT_MODEL, MODEL_OPTIONS, validate_model


def get_account_settings(account_id: uuid.UUID | str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """SELECT a.id,a.email,a.display_name,s.llm_model,s.locale,s.timezone,
                      s.preferences,s.updated_at
                 FROM accounts a
                 LEFT JOIN account_settings s ON s.account_id=a.id
                WHERE a.id=%s""",
            (account_id,),
        ).fetchone()
    if not row:
        raise LookupError("계정을 찾을 수 없습니다.")
    stored_model = row.get("llm_model")
    try:
        model = validate_model(stored_model) if stored_model else DEFAULT_MODEL
    except ValueError:
        model = DEFAULT_MODEL
    return {
        "account": {
            "id": str(row["id"]),
            "email": row["email"],
            "display_name": row["display_name"],
        },
        "llm_model": model,
        "locale": row.get("locale") or "ko-KR",
        "timezone": row.get("timezone") or "Asia/Seoul",
        "preferences": row.get("preferences") or {},
        "model_options": [dict(item) for item in MODEL_OPTIONS],
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def update_account_model(account_id: uuid.UUID | str, model: str) -> dict:
    selected = validate_model(model)
    with connection() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO account_settings(account_id,llm_model,locale,timezone,preferences)
               VALUES (%s,%s,'ko-KR','Asia/Seoul',%s)
               ON CONFLICT(account_id) DO UPDATE SET
                 llm_model=excluded.llm_model,updated_at=now()""",
            (account_id, selected, Jsonb({})),
        )
    return get_account_settings(account_id)

