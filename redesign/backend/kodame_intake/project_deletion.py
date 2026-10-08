"""Administrator deletion with reviewed scope and durable file cleanup."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .db import connection, tenant_context
from .settings import DATA_DIR
from .theory_artifact_store import CACHE_ROOT


def _safe_path(path):
    resolved = path.resolve()
    root = DATA_DIR.resolve()
    if resolved.is_relative_to(root) and len(resolved.relative_to(root).parts) >= 2:
        return True
    # A configured external visual cache has one UUID directory per project.
    cache = CACHE_ROOT.resolve()
    if resolved.is_relative_to(cache):
        parts = resolved.relative_to(cache).parts
        try:
            return bool(parts) and str(uuid.UUID(parts[0])) == parts[0]
        except ValueError:
            pass
    return False


def _preview(conn, project_id):
    project = conn.execute('SELECT id,name,is_bootstrap FROM projects WHERE id=%s', (project_id,)).fetchone()
    if not project:
        raise HTTPException(404, '프로젝트가 존재하지 않습니다.')
    accounts = conn.execute('''SELECT a.id,a.email,a.display_name,
        ARRAY(SELECT p.name FROM projects p WHERE p.id<>%s AND
          (p.owner_account_id=a.id OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=p.id AND m.account_id=a.id)) ORDER BY p.id) other_projects
        FROM accounts a WHERE NOT a.is_admin AND (a.id IN
          (SELECT account_id FROM project_members WHERE project_id=%s) OR a.id IN
          (SELECT owner_account_id FROM projects WHERE id=%s)) ORDER BY a.id''', (project_id, project_id, project_id)).fetchall()
    counts = {}
    for table in ('intake_documents', 'evaluation_runs', 'report_sections', 'report_exports', 'presentation_exports'):
        counts[table] = conn.execute(f'SELECT count(*) n FROM {table} WHERE project_id=%s', (project_id,)).fetchone()['n']
    result = {'id': str(project['id']), 'name': project['name'], 'accounts': [
        {'id': str(a['id']), 'username': a['email'], 'display_name': a['display_name'], 'other_projects': a['other_projects']} for a in accounts], 'counts': counts}
    result['revision'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def preview(project_id):
    with tenant_context(system=True), connection() as conn:
        return _preview(conn, project_id)


def cleanup_files():
    """Committed manifests survive crashes; never remove shared storage roots."""
    with tenant_context(system=True), connection() as conn, conn.transaction():
        rows = conn.execute('SELECT id,paths FROM project_file_cleanup ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 10').fetchall()
        for row in rows:
            remaining = []
            for raw in row['paths']:
                path = Path(raw)
                try:
                    if not _safe_path(path):
                        raise ValueError('Unsafe cleanup path')
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)
                except (OSError, ValueError):
                    remaining.append(raw)
            if remaining:
                conn.execute('UPDATE project_file_cleanup SET paths=%s WHERE id=%s', (Jsonb(remaining), row['id']))
            else:
                conn.execute('DELETE FROM project_file_cleanup WHERE id=%s', (row['id'],))


def delete(project_id, actor_id, name, revision, confirmed):
    project_id = uuid.UUID(str(project_id))
    with tenant_context(system=True), connection() as conn, conn.transaction():
        # Match workflow admission lock and serialize membership changes/FK inserts.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f'kodame:workflow:{project_id}',))
        conn.execute('LOCK TABLE accounts, projects, project_members, intake_documents IN SHARE ROW EXCLUSIVE MODE')
        current = _preview(conn, project_id)
        if not confirmed or name != current['name'] or revision != current['revision']:
            raise HTTPException(409, '삭제 대상이 변경되었거나 최종 확인이 없습니다. 삭제 화면을 다시 열어 확인해 주세요.')
        for table, statuses in (('intake_documents', ['processing']),
                                ('evaluation_runs', ['queued','running']), ('pdm_refresh_runs', ['queued','running']),
                                ('report_generation_runs', ['queued','running']), ('report_sections', ['generating']),
                                ('report_exports', ['queued','running']), ('presentation_exports', ['queued','running']),
                                ('translation_jobs', ['queued','running'])):
            if conn.execute(f'SELECT 1 FROM {table} WHERE project_id=%s AND status=ANY(%s) LIMIT 1', (project_id, statuses)).fetchone():
                raise HTTPException(409, '처리 중인 문서 또는 AI 작업이 있습니다. 완료 또는 취소 후 삭제해 주세요.')
        paths = {str(DATA_DIR / 'originals' / str(project_id)), str(DATA_DIR / 'presentation_exports' / 'checkpoints' / str(project_id)), str(CACHE_ROOT / str(project_id))}
        for row in conn.execute('SELECT id,stored_path,extracted_path FROM intake_documents WHERE project_id=%s', (project_id,)).fetchall():
            paths.update(str(p) for p in (row['stored_path'], row['extracted_path'], DATA_DIR / 'extracted' / f"{row['id']}.txt") if p)
        for table, directory in (('report_exports','report_exports'), ('presentation_exports','presentation_exports')):
            for row in conn.execute(f'SELECT id,output_path FROM {table} WHERE project_id=%s', (project_id,)).fetchall():
                if row['output_path']:
                    paths.add(row['output_path'])
                for pattern in (f"{row['id']}.*", f"{row['id']}-*"):
                    paths.update(str(p) for p in (DATA_DIR / directory).glob(pattern))
                paths.add(str(DATA_DIR / directory / 'diagnostics' / str(row['id'])))
        # Validate every target before committing an irreversible deletion.
        for raw in paths:
            if not _safe_path(Path(raw)):
                raise HTTPException(409, '관리 저장소 밖의 연관 파일이 있어 삭제할 수 없습니다. 저장 경로를 점검해 주세요.')
        other_paths = conn.execute('''SELECT stored_path path FROM intake_documents WHERE project_id<>%s
            UNION ALL SELECT extracted_path FROM intake_documents WHERE project_id<>%s
            UNION ALL SELECT output_path FROM report_exports WHERE project_id<>%s
            UNION ALL SELECT output_path FROM presentation_exports WHERE project_id<>%s''', (project_id,) * 4).fetchall()
        targets = [Path(p).resolve() for p in paths]
        if any(Path(row['path']).resolve().is_relative_to(target) for row in other_paths if row['path'] for target in targets):
            raise HTTPException(409, '다른 프로젝트와 공유된 파일이 있어 삭제할 수 없습니다. 파일 연결을 점검해 주세요.')
        ids = [uuid.UUID(a['id']) for a in current['accounts']]
        conn.execute('INSERT INTO project_file_cleanup(id,paths) VALUES (%s,%s)', (project_id, Jsonb(sorted(paths))))
        conn.execute("INSERT INTO service_lifecycle_flags(key) VALUES ('demo_seed_deleted') ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO service_lifecycle_flags(key) SELECT 'bootstrap_deleted' FROM projects WHERE id=%s AND is_bootstrap ON CONFLICT DO NOTHING", (project_id,))
        # Keep other projects, transferring administrative ownership if necessary.
        conn.execute('UPDATE projects SET owner_account_id=%s WHERE id<>%s AND owner_account_id=ANY(%s)', (uuid.UUID(str(actor_id)), project_id, ids))
        conn.execute('DELETE FROM token_usage_events WHERE project_id=%s OR account_id=ANY(%s)', (project_id, ids))
        conn.execute('DELETE FROM project_ai_changes WHERE account_id=ANY(%s)', (ids,))
        conn.execute('DELETE FROM projects WHERE id=%s', (project_id,))
        conn.execute('DELETE FROM accounts WHERE id=ANY(%s) AND NOT is_admin', (ids,))
    cleanup_files()
    with tenant_context(system=True), connection() as conn:
        pending = bool(conn.execute('SELECT 1 FROM project_file_cleanup WHERE id=%s', (project_id,)).fetchone())
    return {'deleted': True, 'deleted_accounts': len(ids), 'cleanup_pending': pending}
