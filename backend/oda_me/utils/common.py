from __future__ import annotations

from ..core import *

def now_label() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()
    return cleaned or "uploaded_file"


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("content-length", "0"))
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def find_criterion(criterion_id: str) -> dict | None:
    return next((item for item in CRITERIA if item["id"] == criterion_id), None)

