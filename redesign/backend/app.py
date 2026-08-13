from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8100"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))

CRITERIA = [
    {"id": "relevance", "name": "적절성", "score": 4.0, "evidence": {"secured": 10, "required": 10}},
    {"id": "coherence", "name": "일관성", "score": 3.5, "evidence": {"secured": 5, "required": 9}},
    {"id": "effectiveness", "name": "효과성", "score": 3.0, "evidence": {"secured": 6, "required": 10}},
    {"id": "efficiency", "name": "효율성", "score": 3.5, "evidence": {"secured": 4, "required": 7}},
    {"id": "impact", "name": "영향", "score": 1.0, "evidence": {"secured": 3, "required": 8}},
    {"id": "sustainability", "name": "지속가능성", "score": 3.5, "evidence": {"secured": 4, "required": 6}},
]

class ApiHandler(BaseHTTPRequestHandler):
    server_version = "KODAME-Redesign/0.1"

    def send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        now = datetime.now(timezone.utc).isoformat()
        if path == "/healthz":
            self.send_json(200, {"ok": True, "service": "kodame-redesign-api", "version": "0.1"})
        elif path == "/api/v2":
            self.send_json(200, {"name": "KODAME Redesign API", "version": "v2", "status": "prototype"})
        elif path == "/api/v2/dashboard":
            self.send_json(200, {"project": {"name": "라오스 직업기술교육 역량강화 사업", "country": "라오스", "donor": "KOICA"}, "progress": 69, "criteria": CRITERIA, "updated_at": now})
        elif path == "/api/v2/criteria":
            self.send_json(200, {"items": CRITERIA, "updated_at": now})
        elif path == "/api/v2/documents":
            self.send_json(200, {"items": [], "total": 0, "status": "contract-ready"})
        elif path == "/api/v2/reports/sections":
            self.send_json(200, {"items": [], "total": 0, "status": "contract-ready"})
        else:
            self.send_json(404, {"error": "not_found", "path": path})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"KODAME redesign API running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), ApiHandler).serve_forever()

if __name__ == "__main__":
    main()
