"""Forward-only, checksummed migrations. Rollback uses a verified DB/file backup."""
import hashlib
from pathlib import Path


def apply_migrations(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
        version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())''')
    for path in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
        sql = path.read_text(encoding='utf-8')
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        previous = conn.execute('SELECT checksum FROM schema_migrations WHERE version=%s', (path.stem,)).fetchone()
        if previous:
            if previous['checksum'] != checksum:
                raise RuntimeError(f'Applied migration changed: {path.stem}')
            continue
        conn.execute(sql)
        conn.execute('INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)', (path.stem, checksum))
