"""Conservative reuse of an immutable, verified HWPX for identical inputs."""
from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from .project_lifecycle import capture_input_snapshot, snapshots_match

STAMP_VERSION = 'verified-export-runtime-v1'


def _mapping(value):
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=4096)
def _file_digest(path: str, size: int, modified: int, changed: int) -> str:
    # Metadata is only the in-process memoization key; persisted identity is
    # always a digest of bytes, so rebuilding an image does not invalidate it.
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _runtime_files():
    package = Path(__file__).resolve().parent
    root = package.parent
    if not (root / 'backend/oda_me').is_dir():
        root = package.parents[2]  # repository execution, without /app mounts
    configured_rhwp = os.getenv('RHWP_ASSET_ROOT')
    rhwp = Path(configured_rhwp) if configured_rhwp else root / 'rhwp'
    if not configured_rhwp and not rhwp.is_dir():
        rhwp = root / 'assets/rhwp'
    requirements = root / 'requirements.txt'
    if not requirements.is_file():
        requirements = root / 'redesign/backend/requirements.txt'
    required = [requirements, root / 'samples/5-1. 종료평가 결과보고서 placeholder.hwpx',
                rhwp / 'index.html', rhwp / 'version.json']
    configured_profile = os.getenv('REPORT_QUALITY_PROFILE_PATH', '').strip()
    if configured_profile:
        required.append(Path(configured_profile))
    groups = [('service', package, '*.py'), ('hwpx_backend', root / 'backend/oda_me', '*.py'),
              ('config', root / 'config', '*.json'), ('prompts', root / 'prompts', '*'),
              ('sections', root / 'hwpx_sections', '*'), ('rhwp', rhwp, '*')]
    if not all(path.is_file() for path in required) or not all(folder.is_dir() for _, folder, _ in groups):
        return None
    files = [(f'required/{index}', path) for index, path in enumerate(required)]
    for label, folder, pattern in groups:
        members = sorted(path for path in folder.rglob(pattern) if path.is_file() and '__pycache__' not in path.parts)
        if not members:
            return None
        files.extend((f'{label}/{path.relative_to(folder).as_posix()}', path) for path in members)
    # Shared report policy modules live beside the package in the image.
    shared = root if (root / 'report_prompts.py').is_file() else root / 'backend'
    for name in ('report_prompts.py', 'report_few_shot.py', 'report_outline.py', 'report_writing_policy.py', 'evaluation_specs.py'):
        path = shared / name
        if not path.is_file():
            return None
        files.append((f'shared/{name}', path))
    return files


def export_runtime_fingerprint() -> dict | None:
    """An incomplete or unreadable runtime never qualifies an older artifact."""
    try:
        images = {key: os.getenv(key, '') for key in ('REPORT_API_IMAGE_REVISION', 'REPORT_KORDOC_IMAGE_REVISION')}
        # Docker image IDs cover native fonts/browser/OS dependencies and the
        # separate kordoc engine. Mutable tags and unknown dev images fail shut.
        if not all(re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in images.values()):
            return None
        files = _runtime_files()
        if not files:
            return None
        manifest = []
        for label, path in files:
            stat = path.stat()
            manifest.append((label, _file_digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))
        identity = {'files': manifest, 'browser_path': os.getenv('PLAYWRIGHT_BROWSERS_PATH', '')}
        digest = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
        return {'version': STAMP_VERSION, 'sha256': digest, 'images': images}
    except (OSError, ValueError):
        return None


def report_sections_digest(conn) -> str:
    rows = conn.execute('SELECT part_id,content,status,updated_at FROM report_sections ORDER BY part_id').fetchall()
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def reusable_export(row, *, snapshot, sections_digest, runtime, export_dir, model) -> bool:
    if row.get('status') != 'completed' or not runtime or runtime.get('version') != STAMP_VERSION:
        return False
    validation = row.get('validation') or {}
    if not isinstance(validation, dict) or validation.get('export_runtime') != runtime:
        return False
    if not snapshot.get('document_digest') or not snapshot.get('workflow_digest') or not (snapshot.get('evaluation_basis_id') or snapshot.get('evaluation_run_id')):
        return False
    if not snapshots_match(_mapping(validation.get('input_snapshot')), snapshot):
        return False
    if not sections_digest or validation.get('source_sections_sha256') != sections_digest:
        return False
    if not model or _mapping(validation.get('theory_visual')).get('model') != model:
        return False
    for key in ('layout_contract', 'semantic_coverage', 'project_identity_validation', 'toc_visible_validation'):
        if not isinstance(validation.get(key), dict) or validation[key].get('ok') is not True:
            return False
    final = _mapping(validation.get('rhwp_final'))
    expected = final.get('source_sha256')
    if (validation.get('rhwp_toc_verified') is not True or final.get('ok') is not True
            or _mapping(final.get('geometry_validation')).get('ok') is not True
            or not isinstance(expected, str) or len(expected) != 64):
        return False
    try:
        path = Path(row.get('output_path') or '').resolve()
        if export_dir.resolve() not in path.parents or not path.is_file():
            return False
        # Recheck bytes on every hit, independent of timestamp or size; a file
        # with forged/restored metadata must never be mistaken for validation.
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == expected
    except (OSError, ValueError):
        return False


def find_reusable_export(conn, *, snapshot, export_dir, model):
    runtime = export_runtime_fingerprint()
    if not runtime:
        return None
    sections_digest = report_sections_digest(conn)
    rows = conn.execute("""SELECT * FROM report_exports WHERE status='completed'
        AND output_path IS NOT NULL ORDER BY completed_at DESC LIMIT 12""").fetchall()
    for row in rows:
        if reusable_export(row, snapshot=snapshot, sections_digest=sections_digest,
                           runtime=runtime, export_dir=export_dir, model=model):
            # Uploads and manual section edits do not all use the workflow
            # lock. Re-read their identities after filesystem verification.
            if (snapshots_match(snapshot, capture_input_snapshot(conn))
                    and sections_digest == report_sections_digest(conn)
                    and runtime == export_runtime_fingerprint()):
                return row
            return None
    return None
