import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from ..db import connection
from ..evaluation_versions import current_bundle, approve, compare
from ..admin import has_menu_permission

router = APIRouter(prefix='/api/v2/report/review')


class Approval(BaseModel):
    revision: str = Field(min_length=64, max_length=64)
    source_fidelity: bool
    conclusion_validity: bool
    note: str = Field(min_length=1, max_length=4000)


@router.get('')
def review_status():
    with connection() as conn:
        current = current_bundle(conn)
        versions = conn.execute('SELECT id,revision,reviewer_name,review,created_at FROM evaluation_versions ORDER BY created_at DESC').fetchall()
    return {**current, 'versions': versions,
            'submission_status': 'approved' if any(v['revision'] == current['revision'] for v in versions) else 'human_review_required'}


@router.post('/approve', status_code=201)
def approve_version(payload: Approval, request: Request):
    if not has_menu_permission(request.state.auth, 'evaluation_report'):
        raise HTTPException(403, '보고서 검토 권한이 필요합니다.')
    with connection() as conn, conn.transaction():
        return approve(conn, payload)


@router.get('/versions/{version_id}')
def version_detail(version_id: uuid.UUID):
    with connection() as conn:
        version = conn.execute('SELECT * FROM evaluation_versions WHERE id=%s', (version_id,)).fetchone()
        if not version:
            raise HTTPException(404, '승인 버전을 찾을 수 없습니다.')
        current = current_bundle(conn)
    return {'version': version, 'changes_to_current': compare(version['payload'], current['payload'])}
