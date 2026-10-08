"""Project-scoped visual cache, independent of a later HWPX export failing.

An unchanged diagram is not sent to an external model on each conversion retry.
No sample or another tenant's image can act as a fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from .db import current_project_id

CACHE_ROOT = Path(os.getenv("THEORY_ARTIFACT_CACHE_DIR", "/app/data/theory_artifacts"))


def _folder(digest: str) -> Path:
    project_id = current_project_id()
    if not project_id or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("변화이론 캐시에는 명시적인 프로젝트와 입력 지문이 필요합니다.")
    return CACHE_ROOT / str(uuid.UUID(str(project_id))) / digest


def load_theory_artifact(digest: str) -> dict | None:
    folder = _folder(digest)
    try:
        metadata = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if metadata.get("input_digest") != digest:
            return None
        result = dict(metadata["metadata"])
        for extension in ("pptx", "png"):
            payload = (folder / ("theory." + extension)).read_bytes()
            if hashlib.sha256(payload).hexdigest() != metadata["sha256"][extension]:
                return None
            result[extension] = payload
        result["source"] = "project_input_cache"
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_theory_artifact(digest: str, artifacts: dict) -> None:
    folder = _folder(digest)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"input_digest": digest, "sha256": {},
                "metadata": {key: value for key, value in artifacts.items() if key not in ("pptx", "png")}}
    for extension in ("pptx", "png"):
        payload = artifacts[extension]
        temporary = folder / (uuid.uuid4().hex + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(folder / ("theory." + extension))
        manifest["sha256"][extension] = hashlib.sha256(payload).hexdigest()
    # Publish the manifest last so incomplete writes are never treated as valid.
    temporary = folder / (uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    temporary.replace(folder / "manifest.json")
