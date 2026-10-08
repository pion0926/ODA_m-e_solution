from __future__ import annotations

from .db import connection, current_account_id, current_project_id


def record_token_usage(body: dict, model: str = "") -> None:
    usage = body.get("usage") if isinstance(body, dict) else None
    account_id = current_account_id()
    if not usage or not account_id:
        return
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or prompt + completion)
    if total <= 0:
        return
    with connection() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO token_usage_events
               (account_id,project_id,model,prompt_tokens,completion_tokens,total_tokens)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (account_id, current_project_id(), str(model or body.get("model") or "")[:200], prompt, completion, total),
        )
