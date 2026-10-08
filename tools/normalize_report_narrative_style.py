from __future__ import annotations

import argparse
import json
import re
import uuid

from psycopg.types.json import Jsonb

from backend.oda_me.hwpx.adapters.summary_ko import normalize_summary_ko_document
from kodame_intake.db import connection, open_pool, pool, tenant_context
from kodame_intake.report_sources import strip_inline_source_citations
from report_outline import (
    NARRATIVE_OUTLINE_PART_IDS,
    canonical_narrative_outline_text,
    narrative_outline_issues,
)


def normalized_section_content(part_id: str, content: object) -> str:
    cleaned = strip_inline_source_citations(str(content or "").strip())
    if part_id == "summary-ko":
        return normalize_summary_ko_document(cleaned)
    return canonical_narrative_outline_text(part_id, cleaned)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize one project's report narrative hierarchy and nominal endings."
    )
    parser.add_argument("--project-id", required=True, type=uuid.UUID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    open_pool()
    result: dict[str, object] = {
        "project_id": str(args.project_id),
        "applied": args.apply,
        "changed": [],
        "unchanged": [],
        "errors": [],
        "remaining_declarative_details": [],
    }
    target_ids = tuple(sorted((*NARRATIVE_OUTLINE_PART_IDS, "summary-ko")))
    failed = False
    try:
        with tenant_context(args.project_id), connection() as conn, conn.transaction():
            rows = conn.execute(
                """SELECT part_id,content,generation_metadata
                   FROM report_sections
                   WHERE project_id=%s AND part_id=ANY(%s::text[])
                   ORDER BY section_number""",
                (args.project_id, list(target_ids)),
            ).fetchall()
            for row in rows:
                part_id = str(row["part_id"])
                before = str(row.get("content") or "")
                after = ""
                try:
                    after = normalized_section_content(part_id, before)
                    if part_id in NARRATIVE_OUTLINE_PART_IDS:
                        issues = narrative_outline_issues(part_id, after)
                        if issues:
                            raise ValueError("; ".join(issues))
                    for line in after.splitlines():
                        if line.lstrip().startswith("- ") and re.search(r"다\.(?:\s|$)", line):
                            result["remaining_declarative_details"].append(
                                {"part_id": part_id, "text": line[:180]}
                            )
                    bucket = "changed" if after != before else "unchanged"
                    result[bucket].append(part_id)
                    if args.apply and after != before:
                        metadata = dict(row.get("generation_metadata") or {})
                        metadata["narrative_style_normalized"] = "coherent-detail-label-v2"
                        conn.execute(
                            """UPDATE report_sections
                               SET content=%s,generation_metadata=%s,updated_at=now()
                               WHERE project_id=%s AND part_id=%s""",
                            (after, Jsonb(metadata), args.project_id, part_id),
                        )
                except Exception as exc:  # keep the remaining sections auditable
                    residual = [
                        sentence.strip()
                        for line in after.splitlines()
                        if line.lstrip().startswith("- ")
                        for sentence in re.findall(r"[^.]{0,160}(?:다|습니다)\.", line)
                    ]
                    result["errors"].append(
                        {"part_id": part_id, "message": str(exc), "residual": residual}
                    )
            if result["errors"] or result["remaining_declarative_details"]:
                failed = True
                if args.apply:
                    raise RuntimeError("style normalization audit failed")
    finally:
        pool.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
