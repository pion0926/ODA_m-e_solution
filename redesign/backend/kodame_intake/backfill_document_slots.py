from __future__ import annotations

import argparse
import uuid

from .db import connection, open_pool, pool, tenant_context
from .document_slots import document_slot_matches
from .pdm_monitoring import refresh_pdm_model


def rebuild(project_id: uuid.UUID) -> int:
    with tenant_context(project_id):
        with connection() as conn, conn.transaction():
            rows = conn.execute("SELECT id,original_name,analysis FROM intake_documents ORDER BY queue_position").fetchall()
            conn.execute("DELETE FROM document_slot_assignments")
            for row in rows:
                for match in document_slot_matches(row["original_name"], row["analysis"] or {}):
                    conn.execute(
                        """INSERT INTO document_slot_assignments
                           (document_id,criterion,criterion_name,slot_id,slot_title,confidence,rationale)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (row["id"], match["criterion"], match["criterion_name"], match["slot_id"],
                         match["slot_title"], match["confidence"], match["rationale"]),
                    )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=uuid.UUID, required=True)
    args = parser.parse_args()
    open_pool()
    try:
        count = rebuild(args.project_id)
        print(f"document_slot_assignments rebuilt for {count} documents")
        with tenant_context(args.project_id):
            model_id = refresh_pdm_model()
        print(f"pdm_document_assignments rebuilt: {model_id}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
