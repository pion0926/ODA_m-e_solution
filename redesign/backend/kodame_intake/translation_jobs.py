"""Queue uncached screen translations without blocking HTTP reads."""
import uuid
from contextvars import ContextVar
from psycopg.types.json import Jsonb
from fastapi.encoders import jsonable_encoder
from .db import connection
from .llm_models import current_llm_model
from .localized_views import collect_text_slots, _source_digest, _cached_translation, localize_project_views

_active = ContextVar('translation_job', default=None)


def check_translation():
    ident = _active.get()
    if ident:
        with connection() as conn:
            row = conn.execute('SELECT status FROM translation_jobs WHERE id=%s', (ident,)).fetchone()
        if not row or row['status'] == 'cancelled':
            raise RuntimeError('사용자가 화면 번역을 중지했습니다.')


def request_translation(views, locale, source_locale):
    if locale == source_locale:
        return {'locale':locale, 'translation_status':'source','views':views}
    digest = _source_digest(views, collect_text_slots(views))
    cached = _cached_translation(locale,digest)
    if cached:
        return {'locale':locale,'translation_status':'cached','source_digest':digest,'views':cached}
    from .workflow_queue import enqueue
    with connection() as conn, conn.transaction():
        row = conn.execute('''INSERT INTO translation_jobs(id,locale,source_locale,digest,views)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT(project_id,locale,digest) DO NOTHING RETURNING *''',
            (uuid.uuid4(),locale,source_locale,digest,Jsonb(jsonable_encoder(views)))).fetchone()
        if row:
            enqueue(conn,'translation',[row['id']],current_llm_model())
        else:
            row = conn.execute('SELECT * FROM translation_jobs WHERE locale=%s AND digest=%s',(locale,digest)).fetchone()
    return {'locale':locale,'translation_status':row['status'],'job_id':str(row['id']),
            'error_message':row['error_message'],'views':views,'source_digest':digest}


def run_translation(ident):
    with connection() as conn:
        row = conn.execute("UPDATE translation_jobs SET status='running' WHERE id=%s AND status='queued' RETURNING *", (ident,)).fetchone()
    if not row:
        return
    token = _active.set(ident)
    try:
        check_translation()
        localize_project_views(row['views'],locale=row['locale'],source_locale=row['source_locale'])
    except Exception:
        with connection() as conn:
            conn.execute("UPDATE translation_jobs SET status='failed',error_message='화면 번역이 완료되지 않았습니다. 원래 언어로 표시합니다.',completed_at=now() WHERE id=%s AND status='running'", (ident,))
        raise
    finally:
        _active.reset(token)
    with connection() as conn:
        conn.execute("UPDATE translation_jobs SET status='completed',completed_at=now() WHERE id=%s AND status='running'",(ident,))
