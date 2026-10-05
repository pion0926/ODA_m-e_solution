"""Read-only live classification probe; results are saved for review, not committed to DB."""
import json
from pathlib import Path
import sys

from kodame_intake.db import open_pool, connection, tenant_context
from kodame_intake.document_classification import classify_content
from kodame_intake.document_slots import document_slot_matches
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_ai import get_project_model

project_id, destination, *document_ids = sys.argv[1:]
if not document_ids:
    raise SystemExit('Explicit authorized document IDs are required.')
open_pool()
with tenant_context(project_id=project_id), llm_model_context(get_project_model(project_id)):
    with connection() as conn:
        rows = conn.execute("SELECT id,original_name,extracted_path FROM intake_documents WHERE status='completed' AND id=ANY(%s::uuid[]) ORDER BY queue_position", (document_ids,)).fetchall()
    results = []
    for row in rows:
        text = Path(row['extracted_path']).read_text(encoding='utf-8')
        classification = classify_content(text)
        assignments = document_slot_matches(row['original_name'], {'content_classification': classification})
        result = {'id': str(row['id']), 'file': row['original_name'], 'classification': classification, 'assignments': assignments}
        results.append(result)
        Path(destination).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
