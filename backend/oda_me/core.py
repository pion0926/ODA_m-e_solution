from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
import zlib
import xml.etree.ElementTree as ET
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path, PureWindowsPath
from urllib import error, request
from urllib.parse import quote, unquote, urlparse
from xml.sax.saxutils import escape


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
ET.register_namespace("hp", HP_NS)
ET.register_namespace("hs", HS_NS)
HWPX_NS = {"hp": HP_NS, "hs": HS_NS}


ROOT = Path(__file__).resolve().parents[2]
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8001"))
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TEXT_DIR = DATA_DIR / "extracted_text"
EVALUATION_DIR = DATA_DIR / "evaluations"
REPORT_DIR = DATA_DIR / "reports"
REPORT_EDITOR_STATE_PATH = REPORT_DIR / "report_editor_state.json"
SAMPLE_REPORT_SECTIONS_PATH = DATA_DIR / "sample_analysis" / "nepal_mugu_27_sections.json"
REPORT_GENERATOR_VERSION = "rag_rewrite_v5"
CRITERION_EVALUATION_VERSION = "criterion_eval_v7_question_average"
REFERENCE_TEXT_CACHE_DIR = DATA_DIR / "reference_text_cache"
REPORT_FULL_REFERENCE_CHAR_BUDGET = int(os.getenv("REPORT_FULL_REFERENCE_CHAR_BUDGET", "2200000"))
REPORT_FULL_REFERENCE_DOC_CHAR_LIMIT = int(os.getenv("REPORT_FULL_REFERENCE_DOC_CHAR_LIMIT", "220000"))
REPORT_FULL_REFERENCE_ENABLED = os.getenv("REPORT_FULL_REFERENCE_ENABLED", "1") != "0"
EVALUATION_REFERENCE_CHAR_BUDGET = int(os.getenv("EVALUATION_REFERENCE_CHAR_BUDGET", "900000"))
EVALUATION_REFERENCE_DOC_CHAR_LIMIT = int(os.getenv("EVALUATION_REFERENCE_DOC_CHAR_LIMIT", "90000"))
REPORT_FULL_REFERENCE_DISABLED_PARTS = {
    "grade",
    "summary-ko",
    "criteria-other",
    "conclusion",
    "working-factors",
    "nonworking-factors",
}
REPORT_LIMITED_REFERENCE_PART_LIMITS = {
    "eval-matrix": 10,
    "eval-methods": 12,
    "eval-limitations": 12,
    "feedback": 14,
    "lessons": 14,
}
REPORT_LIMITED_REFERENCE_KEYWORDS = {
    "eval-matrix": (
        "pdm", "성과지표", "평가질문", "조사", "survey", "baseline", "endline", "인터뷰", "면담", "현장", "자료출처",
    ),
    "eval-methods": (
        "인터뷰", "면담", "조사", "survey", "baseline", "endline", "현장", "점검", "만족도", "회의록", "수혜자", "이해관계자",
    ),
    "eval-limitations": (
        "인터뷰", "면담", "조사", "survey", "baseline", "endline", "현장", "점검", "만족도", "변경", "지연", "리스크", "한계", "공백",
    ),
    "feedback": (
        "연차", "점검", "종료", "보고서", "인터뷰", "면담", "현장", "PDM", "변경", "지연", "리스크", "유지관리", "인력", "예산", "기자재", "병원", "UNICEF",
    ),
    "lessons": (
        "작동요인", "비작동요인", "교훈", "제언", "연차", "점검", "종료", "인터뷰", "면담", "현장", "PDM", "유지관리", "인력", "기자재", "3-Delay", "UNICEF",
    ),
}
HWP_REPORT_SCRIPT = ROOT / "backend" / "hwp_report.ps1"
HWP_REPORT_TEMPLATE_PATH = Path(r"F:\2025 국제협력\평가용 참고자료\관련 서식\5-1. 종료평가 결과보고서 양식.hwp")
RHWP_BIN = os.getenv("RHWP_BIN", "rhwp")
RHWP_TIMEOUT_SECONDS = int(os.getenv("RHWP_TIMEOUT_SECONDS", "30"))
HWP_SUFFIXES = {".hwp", ".hwpx"}
SAMPLES_DIR = ROOT / "samples"
SAMPLE_REPORT_HWP_PATH = SAMPLES_DIR / "5-1. 종료평가 결과보고서 양식.hwp"
SAMPLE_REPORT_ORIGINAL_HWPX_PATH = SAMPLES_DIR / "5-1. 종료평가 결과보고서 양식.hwpx"
SAMPLE_REPORT_PLACEHOLDER_HWPX_PATH = SAMPLES_DIR / "5-1. 종료평가 결과보고서 placeholder.hwpx"
SAMPLE_REPORT_HWPX_PATH = SAMPLE_REPORT_PLACEHOLDER_HWPX_PATH
SAMPLE_GRADE_XLSX_PATH = SAMPLES_DIR / "5-2. 종료평가 등급 결과표(엑셀버전).xlsx"
SAMPLE_LESSON_PPTX_PATH = SAMPLES_DIR / "5-3. 분야별 평가 교훈 리포트 양식.pptx"
SAMPLE_FAQ_HWP_PATH = SAMPLES_DIR / "9. 평가업무수행 길라잡이 FAQ.hwp"
PROJECT_OVERVIEW_UPLOAD_DIR = DATA_DIR / "project_overview"
PROJECT_OVERVIEW_STATE_PATH = PROJECT_OVERVIEW_UPLOAD_DIR / "current.json"
PROJECT_OVERVIEW_EVIDENCE_NAME = "사업개요서 또는 사업요청서 (PCP)"
DEFAULT_TOC_PAGE_MAP = {
    "summary_ko_page": 4,
    "project_background_page": 6,
    "project_overview_page": 7,
    "pdm_page": 8,
    "evaluation_purpose_page": 9,
    "evaluation_matrix_page": 10,
    "evaluation_methods_page": 11,
    "evaluation_limitations_page": 12,
    "evaluation_team_page": 13,
    "achievement_page": 14,
    "criteria_relevance_page": 15,
    "criteria_coherence_page": 15,
    "criteria_effectiveness_page": 15,
    "criteria_efficiency_page": 16,
    "criteria_sustainability_page": 16,
    "criteria_crosscutting_page": 16,
    "criteria_other_page": 16,
    "conclusion_page": 17,
    "factors_page": 18,
    "feedback_lessons_page": 20,
    "appendix_summary_en_page": 21,
    "appendix_fieldwork_page": 21,
    "appendix_daily_activities_page": 21,
    "appendix_interviewees_page": 21,
    "appendix_survey_page": 21,
    "appendix_references_page": 21,
    "appendix_other_page": 21,
}

PROJECT_OVERVIEW_PATH = Path(
    r"F:\(주)AIMNE\2026년도 사업제안\KOICA\CTS\공모 제출\2-1. (Seed1) 2026-2027 CTS 국문 사업개요서(에이아이엠앤이컨설팅(주)_v2).hwp"
)


def display_path_name(path: Path | str) -> str:
    value = str(path)
    if "\\" in value or re.match(r"^[A-Za-z]:", value):
        return PureWindowsPath(value).name
    return Path(value).name

PROJECT = {
    "title": "AI 기반 ODA 성과관리·평가 자동화 솔루션 개발",
    "period": "2026-2027 CTS Seed1",
    "budget": "예산 확인 필요",
    "overviewFileName": display_path_name(PROJECT_OVERVIEW_PATH),
    "overviewUrl": "/api/project/overview-file",
    "overviewPreviewUrl": "/api/project/overview-preview",
}

UNCONFIRMED_PROJECT = {
    "title": "사업명 미확정",
    "period": "사업개요서 업로드 전",
    "budget": "예산 미확정",
}

SAMPLE_TEMPLATE_LABELS = {
    "5-1. 종료평가 결과보고서 양식.hwp": "종료평가 결과보고서 양식(HWP)",
    "5-1. 종료평가 결과보고서 양식.hwpx": "종료평가 결과보고서 양식(HWPX)",
    "5-1. 종료평가 결과보고서 placeholder.hwpx": "종료평가 결과보고서 placeholder(HWPX)",
    "5-2. 종료평가 등급 결과표(엑셀버전).xlsx": "종료평가 등급 결과표",
    "5-3. 분야별 평가 교훈 리포트 양식.pptx": "분야별 평가 교훈 리포트 양식",
    "5-6. 현지 평가 컨설턴트 개인정보 수집 및 활용동의서_국영문.hwp": "현지 평가 컨설턴트 개인정보 동의서",
    "9. 평가업무수행 길라잡이 FAQ.hwp": "평가업무수행 길라잡이 FAQ",
}


def current_project_overview() -> dict:
    if PROJECT_OVERVIEW_STATE_PATH.exists():
        overview = json.loads(PROJECT_OVERVIEW_STATE_PATH.read_text(encoding="utf-8"))
        if overview.get("source") == "uploaded" and (
            not overview.get("projectTitle") or not overview.get("projectPeriod") or not overview.get("projectBudget")
        ):
            try:
                stored_path = Path(overview["path"])
                if stored_path.exists():
                    raw = stored_path.read_bytes()
                    mime_type = mimetypes.guess_type(overview.get("name", ""))[0] or "application/octet-stream"
                    extracted_text, extraction_method = extract_text(raw, overview.get("name", stored_path.name), mime_type)
                    text_path = PROJECT_OVERVIEW_UPLOAD_DIR / f"{stored_path.stem}.txt"
                    text_path.write_text(extracted_text, encoding="utf-8")
                    project_period, project_budget = extract_project_period_budget(extracted_text)
                    overview.update(
                        {
                            "projectTitle": overview.get("projectTitle") or infer_project_title(extracted_text, overview.get("name", stored_path.name)) or "사업명 자료 기반 보수 작성",
                            "projectPeriod": project_period or overview.get("projectPeriod") or "기간 확인 필요",
                            "projectBudget": project_budget or overview.get("projectBudget") or "사업비 확인 필요",
                            "textPath": str(text_path),
                            "textPreview": extracted_text[:1200],
                            "extractionMethod": extraction_method,
                        }
                    )
                    PROJECT_OVERVIEW_STATE_PATH.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        return overview
    exists = PROJECT_OVERVIEW_PATH.exists()
    stat = PROJECT_OVERVIEW_PATH.stat() if exists else None
    return {
        "exists": exists,
        "name": display_path_name(PROJECT_OVERVIEW_PATH),
        "path": str(PROJECT_OVERVIEW_PATH),
        "size": stat.st_size if stat else 0,
        "lastModified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat else None,
        "downloadUrl": PROJECT["overviewUrl"],
        "source": "original" if exists else "missing",
    }


def project_payload() -> dict:
    overview = current_project_overview()
    has_uploaded_overview = overview.get("source") == "uploaded" and bool(overview.get("exists"))
    return {
        **PROJECT,
        "title": overview.get("projectTitle") if has_uploaded_overview else UNCONFIRMED_PROJECT["title"],
        "period": overview.get("projectPeriod") if has_uploaded_overview else UNCONFIRMED_PROJECT["period"],
        "budget": overview.get("projectBudget") if has_uploaded_overview else UNCONFIRMED_PROJECT["budget"],
        "overviewFileName": overview["name"],
        "overviewSource": overview["source"],
        "overviewReady": has_uploaded_overview,
    }


def sample_templates_payload() -> dict:
    templates = []
    if SAMPLES_DIR.exists():
        for path in sorted(SAMPLES_DIR.iterdir(), key=lambda item: item.name):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in {".hwp", ".hwpx", ".xlsx", ".pptx", ".pdf"}:
                continue
            if path.name not in SAMPLE_TEMPLATE_LABELS:
                continue
            templates.append(
                {
                    "id": path.name,
                    "name": SAMPLE_TEMPLATE_LABELS.get(path.name, path.name),
                    "fileName": path.name,
                    "extension": suffix.replace(".", "").upper(),
                    "size": path.stat().st_size,
                    "updatedAt": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "downloadUrl": f"/api/samples/templates/{quote(path.name)}",
                }
            )
    return {"templates": templates}


def safe_filename_part(value: str, fallback: str = "ODA_사업") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or fallback


from evaluation_specs import (  # noqa: E402
    COMMON_SCORING_NOTES,
    RELEVANCE_EVIDENCE,
    RELEVANCE_SCORING,
    build_criteria,
    get_evaluation_prompt,
)
from report_prompts import EDITOR_REPORT_PARTS, REPORT_MASTER_PROMPT, REPORT_PART_PROMPTS, report_prompt_assets  # noqa: E402

CRITERIA = build_criteria()


