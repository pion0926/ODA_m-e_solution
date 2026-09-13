"""Read-only tenant-scoped scenario evidence; never reads credentials or writes DB."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from kodame_intake.db import connection, pool, tenant_context

parser = argparse.ArgumentParser()
parser.add_argument("--project-id", type=UUID, required=True)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
pool.open()
with tenant_context(args.project_id), connection() as conn, conn.transaction():
    conn.execute("SET TRANSACTION READ ONLY")
    documents = conn.execute("SELECT id,original_name,status,size_bytes,sha256 FROM intake_documents ORDER BY queue_position").fetchall()
    pdm = conn.execute("SELECT source_document_id,source_file_name,model FROM pdm_models LIMIT 1").fetchone()
    run = conn.execute("SELECT id,status,model,started_at,completed_at,error_message FROM evaluation_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    criteria = conn.execute("SELECT criterion_id,criterion_name,score,question_assessments FROM criterion_evaluations WHERE run_id=%s ORDER BY id", (run["id"],)).fetchall() if run else []
    for criterion in criteria:
        for question in criterion["question_assessments"]:
            question.pop("evidence_quotes", None)
    sections = conn.execute("SELECT section_number,part_id,title,status,content,quality_score,quality_report,error_message,generation_metadata->>'fallback_used' AS fallback_used,generation_metadata->>'operation' AS operation FROM report_sections ORDER BY section_number").fetchall()
    for section in sections:
        content = section.pop("content") or ""
        section["content_chars"] = len(content)
        section["content_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    exports = conn.execute("SELECT id,status,file_name,output_path,validation,error_message FROM report_exports ORDER BY created_at DESC LIMIT 3").fetchall()
checks = []
questions = [q for c in criteria for q in c["question_assessments"]]
checks.append({"check":"DAC question count", "pass":len(questions)==11, "actual":len(questions)})
checks.append({"check":"DAC trace check count", "pass":sum(len(q.get("scoring_trace",{}).get("checks",[])) for q in questions)==33})
for c in criteria:
    qs = c["question_assessments"]
    checks.append({"check":f"{c['criterion_id']} question average", "pass":float(c["score"])==round(sum(q["score"] for q in qs)/len(qs),1)})
for q in questions:
    trace = q.get("scoring_trace", {})
    checks.append({"check":q["question_id"]+" complete trace", "pass":len(trace.get("checks",[]))==3 and trace.get("selected_score")==q["score"] and bool(trace.get("version"))})
    checks.append({"check":q["question_id"]+" full-score evidence gate", "pass":q["score"]!=4 or all(x["status"]=="met" for x in trace.get("checks",[]))})
payload = {"captured_at":datetime.now(timezone.utc).isoformat(), "project_id":str(args.project_id),
           "documents":documents, "pdm":pdm, "evaluation":run, "criteria":criteria,
           "sections":sections, "exports":exports, "checks":checks}
output = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
print(json.dumps({"project_id":str(args.project_id), "documents":len(documents), "evaluation_status":run["status"] if run else None,
                  "questions":len(questions), "checks_passed":sum(c["pass"] for c in checks), "checks_total":len(checks),
                  "written_sections":sum(s["content_chars"]>0 for s in sections), "output":str(args.output or "")}, ensure_ascii=False))
pool.close()
