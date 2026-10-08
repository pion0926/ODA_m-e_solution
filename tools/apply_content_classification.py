"""Apply reviewed classification results only to explicitly named documents."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb
from kodame_intake.db import open_pool, connection, tenant_context
from kodame_intake.document_classification import VERSION
from kodame_intake.document_slots import document_slot_matches
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_ai import get_project_model
from kodame_intake.pdm_monitoring import refresh_pdm_model
from kodame_intake.project_overview import generate_project_overview

project_id, source, *ids = sys.argv[1:]
if not ids:
    raise SystemExit('Explicit authorized document IDs are required.')
results = json.loads(Path(source).read_text(encoding='utf-8'))
if {item['id'] for item in results} != set(ids):
    raise SystemExit('Reviewed result IDs must match the authorized IDs exactly.')
open_pool()
with tenant_context(project_id=project_id), llm_model_context(get_project_model(project_id)):
    with connection() as conn, conn.transaction():
        rows = conn.execute('SELECT id,original_name,analysis FROM intake_documents WHERE id=ANY(%s::uuid[]) FOR UPDATE', (ids,)).fetchall()
        if len(rows) != len(ids):
            raise RuntimeError('Documents are missing from the selected project.')
        assignments = conn.execute('SELECT * FROM document_slot_assignments WHERE document_id=ANY(%s::uuid[])', (ids,)).fetchall()
        backup = Path('/app/data/classification-backups')
        backup.mkdir(parents=True, exist_ok=True)
        path = backup / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json')
        path.write_text(json.dumps({'documents': rows, 'assignments': assignments}, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
        by_id = {str(row['id']): row for row in rows}
        for item in results:
            row = by_id[item['id']]
            classification = item['classification']
            if classification['version'] != VERSION or item['file'] != row['original_name']:
                raise RuntimeError('Classification version or source does not match.')
            analysis = {**(row['analysis'] or {}), 'content_classification': classification,
                        'document_type': classification['document_type']}
            conn.execute('UPDATE intake_documents SET analysis=%s,updated_at=now() WHERE id=%s', (Jsonb(analysis), row['id']))
            conn.execute('DELETE FROM document_slot_assignments WHERE document_id=%s', (row['id'],))
            for match in document_slot_matches(row['original_name'], analysis):
                conn.execute('''INSERT INTO document_slot_assignments
                    (document_id,criterion,criterion_name,slot_id,slot_title,confidence,rationale)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                    (row['id'], match['criterion'], match['criterion_name'], match['slot_id'],
                     match['slot_title'], match['confidence'], match['rationale']))
    print('Applied reviewed classifications; backup:', path, flush=True)
    model_id = refresh_pdm_model(analyze_risks=False)
    print('PDM snapshot:', model_id, flush=True)
    generate_project_overview()
    print('Project overview refreshed.', flush=True)
