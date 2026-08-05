from __future__ import annotations

from ..core import *
from ..documents.evidence_store import batch_upload_documents, confirm_batch_documents, intake_rules_payload, save_intake_rules
from ..hwpx.patchers import build_cover_grade_body_patched_hwpx
from ..reports.editor import (
    generate_report_editor_auto_draft,
    normalize_exported_hwp,
    report_editor_payload,
    reset_report_editor_to_template,
    revise_report_section,
    save_report_editor,
    validate_exported_hwpx,
)
from ..reports.export_builders import build_evaluation_report_package
from ..reports.section_settings import save_section_settings, section_settings_payload
from ..utils.common import find_criterion, now_label
from .dashboard import dashboard_payload, project_overview_preview

class OdaHandler(BaseHTTPRequestHandler):
    server_version = "ODAImpactOps/0.4"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/dashboard":
            self.send_json(dashboard_payload())
            return
        if path == "/api/project/overview-file":
            self.serve_project_overview()
            return
        if path == "/api/project/overview-preview":
            self.send_json(project_overview_preview())
            return
        if path == "/api/reports/editor":
            self.send_json(report_editor_payload())
            return
        if path == "/api/reports/prompts":
            self.send_json(report_prompt_assets())
            return
        if path == "/api/reports/section-settings":
            self.send_json(section_settings_payload())
            return
        if path == "/api/samples/templates":
            self.send_json(sample_templates_payload())
            return
        if path == "/api/references/intake-rules":
            self.send_json(intake_rules_payload())
            return
        if path.startswith("/api/samples/templates/"):
            file_name = unquote(path.rsplit("/", 1)[-1])
            self.serve_sample_template(file_name)
            return
        if path == "/api/reports/template/5-1":
            template_path = SAMPLE_REPORT_HWPX_PATH if SAMPLE_REPORT_HWPX_PATH.exists() else SAMPLE_REPORT_HWP_PATH
            if not template_path.exists():
                self.send_error(404, "5-1 template not found")
                return
            raw = template_path.read_bytes()
            is_hwpx = template_path.suffix.lower() == ".hwpx"
            self.send_response(200)
            self.send_header("Content-Type", "application/x-hwp+zip" if is_hwpx else "application/x-hwp")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=\"5-1-final-evaluation-template{template_path.suffix}\"",
            )
            self.send_header("X-Template-File", quote(template_path.name))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/api/reports/editor/body-test-hwpx/download":
            try:
                payload = build_cover_grade_body_patched_hwpx()
                raw = base64.b64decode(payload.get("data") or "")
                filename = payload.get("fileName") or "5-1-final-evaluation-report.hwpx"
                self.send_binary(raw, "application/x-hwp+zip", filename)
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path.startswith("/api/reports/evaluation-package"):
            raw, filename = build_evaluation_report_package()
            self.send_binary(raw, "application/zip", filename)
            return
        if path == "/api/ai/openrouter/status":
            self.send_json(OPENROUTER.status())
            return
        if path.startswith("/api/criteria/") and path.endswith("/download"):
            parts = path.strip("/").split("/")
            if len(parts) == 6 and parts[0] == "api" and parts[1] == "criteria" and parts[3] == "documents":
                self.serve_uploaded_document(parts[2], parts[4])
                return
            self.send_error(404, "Document not found")
            return
        if path.startswith("/api/criteria/"):
            apply_persisted_evaluations()
            attach_uploaded_documents()
            criterion = find_criterion(path.rsplit("/", 1)[-1])
            if criterion:
                self.send_json({"criterion": criterion})
                return
            self.send_error(404, "Criterion not found")
            return
        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        body = read_json(self)
        if path == "/api/project/overview-file":
            self.send_json(save_project_overview(body))
            return
        if path == "/api/reports/editor":
            try:
                self.send_json(save_report_editor(body))
            except ValueError as exc:
                self.send_error(400, str(exc))
            return
        if path == "/api/reports/section-settings":
            try:
                self.send_json(save_section_settings(body))
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if path == "/api/reports/editor/reset-template":
            try:
                self.send_json(reset_report_editor_to_template())
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reports/editor/chat":
            try:
                self.send_json(revise_report_section(body))
            except ValueError as exc:
                self.send_error(400, str(exc))
            return
        if path == "/api/reports/editor/auto-draft":
            try:
                self.send_json(generate_report_editor_auto_draft(body))
            except ValueError as exc:
                self.send_error(400, str(exc))
            return
        if path == "/api/reports/hwp/normalize":
            try:
                self.send_json(normalize_exported_hwp(body))
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reports/hwpx/validate":
            try:
                self.send_json(validate_exported_hwpx(body))
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reports/editor/template-hwpx":
            try:
                self.send_json(build_cover_grade_body_patched_hwpx())
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reports/editor/cover-hwpx":
            try:
                self.send_json(build_cover_grade_body_patched_hwpx())
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reports/editor/cover-grade-hwpx":
            try:
                self.send_json(build_cover_grade_body_patched_hwpx())
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reports/editor/body-test-hwpx":
            try:
                self.send_json(build_cover_grade_body_patched_hwpx())
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/references/batch-upload":
            self.send_json(batch_upload_documents(body.get("files", [])))
            return
        if path == "/api/references/intake-rules":
            try:
                self.send_json(save_intake_rules(body))
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=400)
            return
        if path == "/api/references/batch-confirm":
            try:
                self.send_json(confirm_batch_documents(body.get("assignments", [])))
            except ValueError as exc:
                self.send_error(404, str(exc))
            return
        if path.startswith("/api/references/unmatched/") and path.endswith("/assign"):
            document_id = path.strip("/").split("/")[3]
            try:
                self.send_json(assign_unmatched_document(document_id, body.get("criterionId", ""), body.get("evidenceName", "")))
            except ValueError as exc:
                self.send_error(404, str(exc))
            return
        if path.startswith("/api/criteria/") and path.endswith("/documents"):
            criterion_id = path.split("/")[-2]
            criterion = find_criterion(criterion_id)
            if not criterion:
                self.send_error(404, "Criterion not found")
                return
            document = save_uploaded_document(criterion_id, body)
            shared_documents = apply_shared_evidence(document)
            affected = {criterion_id, *(item.get("criterionId", "") for item in shared_documents)}
            evaluations = regenerate_affected_criteria({item for item in affected if item})
            self.send_json(
                {
                    "saved": True,
                    "document": document,
                    "sharedDocuments": shared_documents,
                    "evaluationResult": evaluations.get(criterion_id),
                    "evaluations": evaluations,
                    "dashboard": dashboard_payload(),
                }
            )
            return
        if path.startswith("/api/criteria/") and path.endswith("/evidence"):
            criterion_id = path.split("/")[-2]
            criterion = find_criterion(criterion_id)
            if not criterion:
                self.send_error(404, "Criterion not found")
                return
            self.send_json(
                {
                    "saved": True,
                    "criterionId": criterion_id,
                    "items": body.get("items", []),
                    "audit": {
                        "action": f"{criterion['name']} 자료 체크리스트 저장",
                        "checkedBy": "Reviewer",
                        "checkedAt": now_label(),
                    },
                }
            )
            return
        if path == "/api/ai/openrouter/draft":
            task = body.get("task", "DAC 평가 기준별 보완 권고안 초안 작성")
            criterion_id = body.get("criterionId")
            criterion = find_criterion(criterion_id) if criterion_id else None
            context = {
                "project": PROJECT,
                "criterion": criterion,
                "criteria": CRITERIA if not criterion else None,
                "userInput": body.get("input", {}),
            }
            messages = OPENROUTER.build_messages(task, context)
            self.send_json(OPENROUTER.request_chat_completion(messages))
            return
        self.send_error(404, "API endpoint not found")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/criteria/") and "/documents/" in path:
            parts = path.strip("/").split("/")
            if len(parts) == 5 and parts[0] == "api" and parts[1] == "criteria" and parts[3] == "documents":
                criterion_id = parts[2]
                document_id = parts[4]
                criterion = find_criterion(criterion_id)
                if not criterion:
                    self.send_error(404, "Criterion not found")
                    return
                deleted = delete_uploaded_document(criterion_id, document_id)
                if not deleted:
                    self.send_error(404, "Document not found")
                    return
                evaluation = regenerate_criterion_evaluation(criterion_id)
                self.send_json({"deleted": True, "document": deleted, "evaluationResult": evaluation, "dashboard": dashboard_payload()})
                return
        self.send_error(404, "API endpoint not found")

    def serve_project_overview(self) -> None:
        overview = current_project_overview()
        target = Path(overview["path"])
        if not target.exists():
            self.send_error(404, "Project overview file not found")
            return
        raw = target.read_bytes()
        filename = target.name
        self.send_response(200)
        self.send_header("content-type", "application/x-hwp")
        self.send_header("content-length", str(len(raw)))
        self.send_header("content-disposition", f"inline; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(raw)

    def serve_uploaded_document(self, criterion_id: str, document_id: str) -> None:
        document = next((item for item in list_uploaded_documents(criterion_id) if item.get("id") == document_id), None)
        if not document:
            self.send_error(404, "Document not found")
            return
        target = Path(document.get("rawPath", "")).resolve()
        upload_root = UPLOAD_DIR.resolve()
        if not str(target).startswith(str(upload_root)) or not target.exists() or not target.is_file():
            self.send_error(404, "Document file not found")
            return
        raw = target.read_bytes()
        filename = document.get("fileName") or target.name
        content_type = document.get("mimeType") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.send_header("content-disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(raw)

    def serve_sample_template(self, file_name: str) -> None:
        target = (SAMPLES_DIR / Path(file_name).name).resolve()
        sample_root = SAMPLES_DIR.resolve()
        if not str(target).startswith(str(sample_root)) or not target.exists() or not target.is_file():
            self.send_error(404, "Sample template not found")
            return
        raw = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_binary(raw, content_type, target.name)

    def send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def send_binary(self, raw: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.send_header("content-disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def serve_static(self, request_path: str) -> None:
        safe_path = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        target = (ROOT / safe_path).resolve()
        if not str(target).startswith(str(ROOT)) or not target.exists() or target.is_dir():
            target = ROOT / "index.html"
        raw = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix in {".html", ".css", ".js", ".jsx"}:
            content_type = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".jsx": "text/babel"}[target.suffix]
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{now_label()}] {self.address_string()} {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), OdaHandler)
    print(f"ODA ImpactOps Python backend running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

