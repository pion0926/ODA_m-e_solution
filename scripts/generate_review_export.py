from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from kodame_intake import report_exporter
from kodame_intake.db import connection, open_pool, tenant_context
from kodame_intake.theory_visual import normalize_theory_visual_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True, type=uuid.UUID)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    args = parser.parse_args()

    plan = normalize_theory_visual_plan(
        json.loads(args.plan.read_text(encoding="utf-8"))
    )
    artifacts = {
        "plan": plan,
        "pptx": args.pptx.read_bytes(),
        "png": args.png.read_bytes(),
        "model": "local-reviewed-current-project-fixture",
        "design_version": plan["design_version"],
        "render_source": "libreoffice_pptx",
        "source": "local_reviewed_artifact",
    }
    export_id = uuid.uuid4()
    open_pool()
    with tenant_context(args.project_id):
        with connection() as conn, conn.transaction():
            conn.execute(
                """INSERT INTO report_exports(id,status,progress,stage,message,project_id)
                   VALUES (%s,'queued',0,'queued','QA 검증용 내보내기 대기 중',%s)""",
                (export_id, args.project_id),
            )
    report_exporter._load_cached_theory_visual_artifacts = lambda: artifacts
    report_exporter.run_report_export(export_id, args.project_id)
    with tenant_context(args.project_id):
        with connection() as conn:
            row = conn.execute(
                """SELECT id,status,progress,stage,message,error_message,output_path,
                          file_name,validation
                     FROM report_exports WHERE id=%s""",
                (export_id,),
            ).fetchone()
    print(json.dumps(dict(row), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
