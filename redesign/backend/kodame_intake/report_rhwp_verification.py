"""Finalize TOC numbers from the actual rHWP preview, preserving the source export."""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from psycopg.types.json import Jsonb

from .db import connection
from .hwpx_layout.toc import patch_toc_page_numbers, validate_toc_page_numbers
from .report_exporter import EXPORT_DIR

from backend.oda_me.hwpx.toc_registry import TOC_ROWS, destination_title, normalized_title

DESTINATIONS = tuple((key, destination_title(key, label)) for key, label, _ in TOC_ROWS)


def rhwp_page_map(payload: dict) -> dict[str, str]:
    total = payload.get('page_count')
    pages = payload.get('page_texts')
    if type(total) is not int or not 3 <= total <= 200 or not isinstance(pages, list) or len(pages) != total:
        raise ValueError('rHWP 전체 페이지 검사 결과가 필요합니다.')
    if [row.get('page_number') for row in pages] != list(range(1, total+1)):
        raise ValueError('rHWP 페이지 순서 또는 누락을 확인해야 합니다.')
    if any(not isinstance(row.get('text'), str) or len(row['text']) > 100000 for row in pages):
        raise ValueError('rHWP 페이지 텍스트 형식이 올바르지 않습니다.')
    compact = [(row['page_number'], normalized_title(row['text'])) for row in pages[2:]]
    result, minimum = {}, 3
    for key, title in DESTINATIONS:
        found = next((page for page, text in compact if page >= minimum and normalized_title(title) in text), None)
        if found is None:
            raise ValueError(f'rHWP 목차 목적지를 찾을 수 없습니다: {title}')
        result[key], minimum = str(found), found
    return result


def finalize_rhwp_toc(source_id: uuid.UUID, payload: dict) -> dict:
    page_map = rhwp_page_map(payload)
    with connection() as conn:
        source = conn.execute('SELECT * FROM report_exports WHERE id=%s', (source_id,)).fetchone()
    if not source or source['status'] != 'completed' or not source.get('output_path'):
        raise ValueError('현재 사업에서 완료된 원본 내보내기를 찾을 수 없습니다.')
    source_path = Path(source['output_path']).resolve()
    if EXPORT_DIR.resolve() not in source_path.parents or not source_path.is_file():
        raise ValueError('내보내기 파일 경로가 유효하지 않습니다.')
    raw = source_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if payload.get('source_sha256') != digest:
        raise ValueError('검사한 파일과 원본 파일이 다릅니다. 미리보기를 다시 열어 검사해 주세요.')
    # Client observations identify the file but never constitute a final
    # pagination proof. Render and re-render the exact output server-side.
    from .rhwp_renderer import finalize_toc_with_rhwp
    updated, final = finalize_toc_with_rhwp(raw)
    page_map = final['page_map']
    check = final['visible_validation']
    export_id = uuid.uuid4()
    path = EXPORT_DIR / f'{export_id}.hwpx'
    path.write_bytes(updated)
    validation = dict(source.get('validation') or {})
    validation.update(toc_page_map=page_map, toc_visible_validation=check, toc_source='rhwp_final_render',
                      rhwp_toc_verified=True, source_export_id=str(source_id), source_sha256=digest,
                      rhwp_page_count=final['page_count'], rhwp_final=final, visual_review_required=True)
    name = Path(source.get('file_name') or 'report.hwpx').stem + '-rHWP검증.hwpx'
    with connection() as conn, conn.transaction():
        return conn.execute(
            """INSERT INTO report_exports(id,status,progress,stage,message,output_path,file_name,validation,started_at,completed_at)
               VALUES (%s,'completed',100,'completed','rHWP 실제 쪽수 반영 완료; 시각 검토 별도',%s,%s,%s,now(),now()) RETURNING *""",
            (export_id,str(path),name,Jsonb(validation)),
        ).fetchone()
