from __future__ import annotations

import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://kodame:kodame@postgres:5432/kodame")
ADMIN_DATABASE_URL = os.getenv("ADMIN_DATABASE_URL", DATABASE_URL)
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
ORIGINALS_DIR = DATA_DIR / "originals"
EXTRACTED_DIR = DATA_DIR / "extracted"
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(128 * 1024 * 1024)))
MAX_EXTRACTED_CHARS = int(os.getenv("MAX_EXTRACTED_CHARS", "600000"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3.5-flash-lite")
OPENROUTER_PRESENTATION_MODEL = os.getenv(
    "OPENROUTER_PRESENTATION_MODEL", "anthropic/claude-opus-5"
)
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "http://127.0.0.1:8002")
PRESENTATION_REFERENCE_PROFILE_PATH = Path(
    os.getenv(
        "PRESENTATION_REFERENCE_PROFILE_PATH",
        "/app/config/presentation_reference_profile.json",
    )
)
PRESENTATION_MIN_QUALITY_SCORE = max(
    0.0, min(100.0, float(os.getenv("PRESENTATION_MIN_QUALITY_SCORE", "90")))
)
PRESENTATION_MAX_GENERATION_ATTEMPTS = max(
    1, min(5, int(os.getenv("PRESENTATION_MAX_GENERATION_ATTEMPTS", "3")))
)
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "kodame_session")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "false").strip().lower() in {"1", "true", "yes", "on"}
BOOTSTRAP_ADMIN_EMAIL = os.getenv("KODAME_BOOTSTRAP_EMAIL", "admin@kodame.local")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("KODAME_BOOTSTRAP_PASSWORD", "admin")
BOOTSTRAP_ADMIN_NAME = os.getenv("KODAME_BOOTSTRAP_NAME", "KODAME 관리자")
SEED_DEMO_ACCOUNTS = os.getenv("KODAME_SEED_DEMO_ACCOUNTS", "false").strip().lower() in {"1", "true", "yes", "on"}
BOOTSTRAP_PROJECT_NAME = os.getenv(
    "KODAME_BOOTSTRAP_PROJECT_NAME",
    "운영자 기본 프로젝트",
)
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "3"))
WORKER_STEP_DELAY_SECONDS = float(os.getenv("WORKER_STEP_DELAY_SECONDS", "1"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "4"))
TAXONOMY_VERSION = "2026-08-13.1"

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".hwp", ".hwpx", ".zip"}
