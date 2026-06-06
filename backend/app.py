from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib import error, request
from urllib.parse import quote, unquote, urlparse
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8001
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TEXT_DIR = DATA_DIR / "extracted_text"
EVALUATION_DIR = DATA_DIR / "evaluations"
REPORT_DIR = DATA_DIR / "reports"
HWP_REPORT_SCRIPT = ROOT / "backend" / "hwp_report.ps1"
HWP_REPORT_TEMPLATE_PATH = Path(r"F:\2025 국제협력\평가용 참고자료\관련 서식\5-1. 종료평가 결과보고서 양식.hwp")
PROJECT_OVERVIEW_UPLOAD_DIR = DATA_DIR / "project_overview"
PROJECT_OVERVIEW_STATE_PATH = PROJECT_OVERVIEW_UPLOAD_DIR / "current.json"
PROJECT_OVERVIEW_EVIDENCE_NAME = "사업개요서 또는 사업요청서 (PCP)"

PROJECT_OVERVIEW_PATH = Path(
    r"F:\(주)AIMNE\2026년도 사업제안\KOICA\CTS\공모 제출\2-1. (Seed1) 2026-2027 CTS 국문 사업개요서(에이아이엠앤이컨설팅(주)_v2).hwp"
)

PROJECT = {
    "title": "AI 기반 ODA 성과관리·평가 자동화 솔루션 개발",
    "period": "2026-2027 CTS Seed1",
    "budget": "예산 확인 필요",
    "overviewFileName": PROJECT_OVERVIEW_PATH.name,
    "overviewUrl": "/api/project/overview-file",
    "overviewPreviewUrl": "/api/project/overview-preview",
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
                            "projectTitle": overview.get("projectTitle") or infer_project_title(extracted_text, overview.get("name", stored_path.name)) or PROJECT["title"],
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
        "name": PROJECT_OVERVIEW_PATH.name,
        "path": str(PROJECT_OVERVIEW_PATH),
        "size": stat.st_size if stat else 0,
        "lastModified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat else None,
        "downloadUrl": PROJECT["overviewUrl"],
        "source": "original",
    }


def project_payload() -> dict:
    overview = current_project_overview()
    return {
        **PROJECT,
        "title": overview.get("projectTitle") or PROJECT["title"],
        "period": overview.get("projectPeriod") or PROJECT["period"],
        "budget": overview.get("projectBudget") or PROJECT["budget"],
        "overviewFileName": overview["name"],
        "overviewSource": overview["source"],
    }

from evaluation_specs import (  # noqa: E402
    COMMON_SCORING_NOTES,
    RELEVANCE_EVIDENCE,
    RELEVANCE_SCORING,
    build_criteria,
    get_evaluation_prompt,
)

CRITERIA = build_criteria()


class OpenRouterClient:
    """OpenRouter 호출을 위한 최소 클라이언트."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "google/gemini-3.1-flash-lite")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.app_title = os.getenv("OPENROUTER_APP_TITLE", "ODA ImpactOps Prototype")
        self.referer = os.getenv("OPENROUTER_REFERER", "http://127.0.0.1:8001")

    def status(self) -> dict:
        return {
            "provider": "openrouter",
            "configured": bool(self.api_key),
            "model": self.model,
            "baseUrl": self.base_url,
            "appTitle": self.app_title,
            "referer": self.referer,
        }

    def build_messages(self, task: str, context: dict) -> list[dict]:
        return [
            {
                "role": "system",
                "content": "You are an OECD DAC and KOICA ODA evaluation expert. Write in Korean with evidence-based reasoning.",
            },
            {
                "role": "user",
                "content": json.dumps({"task": task, "context": context}, ensure_ascii=False),
            },
        ]

    def request_chat_completion(self, messages: list[dict]) -> dict:
        if not self.api_key:
            return {"implemented": True, "ok": False, "error": "OPENROUTER_API_KEY is not configured", "status": self.status()}
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": self.referer,
                "X-Title": self.app_title,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"implemented": True, "ok": True, "status": self.status(), "content": content, "raw": data}
        except error.URLError as exc:
            return {"implemented": True, "ok": False, "status": self.status(), "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"implemented": True, "ok": False, "status": self.status(), "error": str(exc)}


OPENROUTER = OpenRouterClient()


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


def normalize_extracted_text(text: str) -> str:
    readable = "".join(char if char.isprintable() or char in "\n\r\t" else " " for char in text)
    readable = re.sub(r"\r\n?", "\n", readable)
    readable = re.sub(r"[ \t]+", " ", readable)
    readable = re.sub(r"\n{3,}", "\n\n", readable)
    return readable.strip()


def extract_text(raw: bytes, filename: str, mime_type: str) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".html", ".xml"} or mime_type.startswith("text/"):
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "utf-16"):
            try:
                return normalize_extracted_text(raw.decode(encoding)), "decoded_text"
            except UnicodeDecodeError:
                continue
    utf16_text = normalize_extracted_text(raw.decode("utf-16le", errors="ignore"))
    if any(token in utf16_text for token in ("사업개요서", "사업규모", "사업기간", "사업비", "사업명")):
        return utf16_text[:30000], "utf16le_strings"
    decoded = raw.decode("latin-1", errors="ignore")
    fragments = re.findall(r"[A-Za-z0-9가-힣 .,;:()/%+\-_\[\]\n\r]{8,}", decoded)
    text = "\n".join(fragment.strip() for fragment in fragments if fragment.strip())
    if text:
        return normalize_extracted_text(text)[:20000], "binary_printable_strings"
    return "텍스트 자동 추출이 필요한 바이너리 문서입니다. PDF/HWP/DOCX 전용 파서 연동 후 본문 추출 품질을 개선할 수 있습니다.", "needs_parser"


def clean_title_candidate(value: str) -> str | None:
    candidate = re.sub(r"\s+", " ", value).strip(" \t\r\n:：-–—|[]()")
    candidate = re.sub(r"^(?:[\dIVXivx]+[.)-]\s*)+", "", candidate).strip()
    candidate = re.sub(r"\s*\((?:Project|프로젝트).*$", "", candidate, flags=re.IGNORECASE).strip()
    if not 5 <= len(candidate) <= 160:
        return None
    lower_candidate = candidate.lower()
    blocked = (
        "\ubaa9\ucc28",
        "\ud45c ",
        "\uadf8\ub9bc",
        "\ucc38\uace0",
        "\uc5c6\uc74c",
        "table",
        "figure",
    )
    if any(token in lower_candidate for token in blocked):
        return None
    return candidate


def infer_project_title(extracted_text: str, fallback_filename: str) -> str | None:
    labels = (
        "\uc0ac\uc5c5\uba85",
        "\uc0ac\uc5c5 \uba85",
        "\uc0ac\uc5c5\uc81c\ubaa9",
        "\uc0ac\uc5c5 \uc81c\ubaa9",
        "\uacfc\uc81c\uba85",
        "\ud504\ub85c\uc81d\ud2b8\uba85",
        "project title",
        "project name",
        "title",
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    joined = "\n".join(lines[:200])
    spaced_korean_match = re.search(r"사\s*업\s*명\s*[<>\s:：\-|▪ㆍ]*\s*(.+?)(?:>|$|\n)", joined, re.IGNORECASE)
    if spaced_korean_match:
        title = clean_title_candidate(spaced_korean_match.group(1))
        if title:
            return title
    table_match = re.search(rf"(?:{label_pattern})\s*[<>\s:：\-|▪ㆍ]*\s*(.+?)(?:>|$|\n)", joined, re.IGNORECASE)
    if table_match:
        title = clean_title_candidate(table_match.group(1))
        if title:
            return title
    for index, line in enumerate(lines[:200]):
        normalized = re.sub(r"\s+", " ", line)
        match = re.match(rf"^(?:{label_pattern})\s*[:：\-|]?\s*(.+)$", normalized, re.IGNORECASE)
        if match:
            title = clean_title_candidate(match.group(1))
            if title:
                return title
            if index + 1 < len(lines):
                title = clean_title_candidate(lines[index + 1])
                if title:
                    return title

    keywords = (
        "ODA",
        "KOICA",
        "CTS",
        "\uc131\uacfc\uad00\ub9ac",
        "\ud3c9\uac00",
        "\uc790\ub3d9\ud654",
        "\uc194\ub8e8\uc158",
        "\uc0ac\uc5c5",
    )
    for line in lines[:120]:
        title = clean_title_candidate(line)
        if title and sum(1 for keyword in keywords if keyword.lower() in title.lower()) >= 2:
            return title

    stem = Path(fallback_filename).stem
    stem = re.sub(r"^\d+(?:-\d+)?\.\s*", "", stem)
    stem = re.sub(r"\([^)]*\)", " ", stem)
    return clean_title_candidate(stem)


def normalize_period(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    value = value.replace("~", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"년", "", value)
    return value.strip("-")


def clean_budget_candidate(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n:：-–—/|<>[]()▪")


def extract_project_period_budget(extracted_text: str) -> tuple[str | None, str | None]:
    text = normalize_extracted_text(extracted_text)
    labels = (
        "사업규모/기간",
        "사업 규모/기간",
        "사업비/기간",
        "사업비 / 기간",
        "사업기간/사업비",
        "기간/사업비",
        "사업기간",
        "사업 기간",
        "사업규모",
        "사업 규모",
        "사업비",
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    period_pattern = r"(?:19|20)\d{2}\s*(?:[.~\-–—]\s*(?:19|20)\d{2}|년\s*[.~\-–—]?\s*(?:19|20)\d{2}\s*년?)"
    budget_patterns = (
        r"\d[\d,.]*\s*만\s*불\s*(?:\([^)]{1,80}\))?",
        r"\d[\d,.]*\s*불\s*(?:\([^)]{1,80}\))?",
        r"\d[\d,.]*\s*억\s*\d*[\d,.]*\s*만?\s*원",
        r"\d[\d,.]*\s*만\s*원",
        r"\d[\d,.]*\s*원",
    )

    contexts = []
    for match in re.finditer(label_pattern, text, re.IGNORECASE):
        contexts.append(text[match.start() : match.start() + 260])
    contexts.append(text[:3000])

    for context in contexts:
        period_match = re.search(period_pattern, context)
        budget_match = next((re.search(pattern, context) for pattern in budget_patterns if re.search(pattern, context)), None)
        if period_match or budget_match:
            period = normalize_period(period_match.group(0)) if period_match else None
            budget = re.sub(r"\s+", " ", budget_match.group(0)).strip(" \t\r\n:：-–—/|<>[]▪") if budget_match else None
            return period, budget
    return None, None


def document_meta_dir(criterion_id: str) -> Path:
    return UPLOAD_DIR / criterion_id / "_meta"


def persist_document_metadata(criterion_id: str, document: dict) -> None:
    meta_dir = document_meta_dir(criterion_id)
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{document['id']}.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def list_uploaded_documents(criterion_id: str) -> list[dict]:
    meta_dir = document_meta_dir(criterion_id)
    if not meta_dir.exists():
        return []
    documents = []
    for path in sorted(meta_dir.glob("*.json")):
        try:
            documents.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return documents


def find_uploaded_document(criterion_id: str, document_id: str) -> tuple[dict | None, Path | None]:
    meta_path = document_meta_dir(criterion_id) / f"{document_id}.json"
    if not meta_path.exists():
        return None, None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")), meta_path
    except json.JSONDecodeError:
        return None, meta_path


def delete_uploaded_document(criterion_id: str, document_id: str) -> dict | None:
    document, meta_path = find_uploaded_document(criterion_id, document_id)
    if not document:
        return None
    for key in ("rawPath", "textPath"):
        path_value = document.get(key)
        if not path_value:
            continue
        path = Path(path_value)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    if meta_path:
        meta_path.unlink(missing_ok=True)
    return document


def remove_document_metadata_by_evidence(criterion_id: str, evidence_name: str) -> None:
    meta_dir = document_meta_dir(criterion_id)
    if not meta_dir.exists():
        return
    for path in meta_dir.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if document.get("evidenceName") == evidence_name:
            path.unlink(missing_ok=True)


def attach_uploaded_documents() -> None:
    for criterion in CRITERIA:
        documents = list_uploaded_documents(criterion["id"])
        criterion["uploadedDocuments"] = documents
        criterion["evidenceStatus"] = {document.get("evidenceName", ""): document for document in documents}


def evaluation_path(criterion_id: str) -> Path:
    return EVALUATION_DIR / f"{criterion_id}.json"


def clean_evaluation_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned_lines = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = line.strip()
        if re.fullmatch(r"[-–—]{3,}", cleaned):
            continue
        cleaned = cleaned.replace("**", "")
        cleaned = re.sub(r"^[-•ㅇ]\s*평가결과\s*[:：]\s*", "- ", cleaned)
        cleaned = re.sub(r"^평가결과\s*[:：]\s*", "", cleaned)
        replacements = {
            "하였습니다": "하였음",
            "되었습니다": "되었음",
            "어렵습니다": "어려움",
            "필수적입니다": "필수",
            "부족합니다": "부족",
            "부재합니다": "부재",
            "불가능합니다": "불가능",
            "필요합니다": "필요",
            "있습니다": "있음",
            "없습니다": "없음",
            "합니다": "함",
            "됩니다": "됨",
            "입니다": "임",
        }
        for before, after in replacements.items():
            cleaned = cleaned.replace(before, after)
        cleaned = re.sub(r"([가-힣\]])[.。]\s*", r"\1 ", cleaned)
        cleaned = re.sub(r"\s+[.。]\s*$", "", cleaned)
        cleaned_lines.append(cleaned.rstrip())
    return "\n".join(cleaned_lines).strip()


def extract_score_from_text(text: str | None) -> int | None:
    if not text:
        return None
    patterns = [
        r"예상\s*점수\s*[:：]?\s*([1-4])\s*점",
        r"평가\s*결과\s*점수\s*[:：]?\s*([1-4])\s*점",
        r"예상점수\s*[:：]?\s*([1-4])\s*점",
        r"종합판정[\s\S]{0,120}?([1-4])\s*점",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text), re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def clean_evaluation_result(evaluation: dict | None) -> dict | None:
    if not evaluation:
        return evaluation
    result = dict(evaluation)
    if result.get("summary"):
        result["summary"] = clean_evaluation_text(result["summary"])
    text_score = extract_score_from_text(result.get("summary"))
    llm_content = result.get("llm", {}).get("content") if isinstance(result.get("llm"), dict) else None
    text_score = text_score or extract_score_from_text(llm_content)
    if text_score:
        result["score"] = text_score
    sections = []
    for section in result.get("sections", []) or []:
        section_copy = dict(section)
        if section_copy.get("title"):
            section_copy["title"] = clean_evaluation_text(section_copy["title"])
        if section_copy.get("body"):
            section_copy["body"] = clean_evaluation_text(section_copy["body"])
        sections.append(section_copy)
    result["sections"] = sections
    return result


def save_evaluation_result(criterion_id: str, evaluation: dict | None) -> None:
    if not evaluation:
        return
    evaluation = clean_evaluation_result(evaluation)
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "criterionId": criterion_id,
        "evaluation": evaluation,
        "score": evaluation.get("score"),
        "savedAt": now_label(),
    }
    evaluation_path(criterion_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_evaluation_result(criterion_id: str) -> dict | None:
    path = evaluation_path(criterion_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return clean_evaluation_result(payload.get("evaluation"))


def apply_persisted_evaluations() -> None:
    for criterion in CRITERIA:
        evaluation = load_evaluation_result(criterion["id"])
        if not evaluation:
            continue
        criterion["evaluationResult"] = evaluation
        if evaluation.get("score"):
            criterion["currentScore4"] = evaluation["score"]
            criterion["scoreStatus"] = "평가 완료"


def save_uploaded_document(criterion_id: str, body: dict) -> dict:
    filename = safe_filename(body.get("fileName", "uploaded_file"))
    mime_type = body.get("mimeType", "application/octet-stream")
    raw = base64.b64decode(body.get("contentBase64", ""))
    document_id = uuid.uuid4().hex[:12]
    criterion_upload_dir = UPLOAD_DIR / criterion_id
    criterion_text_dir = TEXT_DIR / criterion_id
    criterion_upload_dir.mkdir(parents=True, exist_ok=True)
    criterion_text_dir.mkdir(parents=True, exist_ok=True)
    raw_path = criterion_upload_dir / f"{document_id}_{filename}"
    raw_path.write_bytes(raw)
    extracted_text, extraction_method = extract_text(raw, filename, mime_type)
    text_path = criterion_text_dir / f"{document_id}.txt"
    text_path.write_text(extracted_text, encoding="utf-8")
    document = {
        "id": document_id,
        "criterionId": criterion_id,
        "evidenceName": body.get("evidenceName", ""),
        "fileName": filename,
        "mimeType": mime_type,
        "size": len(raw),
        "rawPath": str(raw_path),
        "textPath": str(text_path),
        "textPreview": extracted_text[:1200],
        "extractionMethod": extraction_method,
        "uploadedAt": now_label(),
    }
    persist_document_metadata(criterion_id, document)
    return document


def evidence_candidates() -> list[dict]:
    candidates = []
    for criterion in CRITERIA:
        if criterion.get("id") == "impact":
            continue
        for item in criterion.get("evidence", []):
            candidates.append(
                {
                    "criterionId": criterion["id"],
                    "criterionName": criterion["name"],
                    "evidenceName": item.get("name", ""),
                    "category": item.get("category", ""),
                }
            )
    return candidates


def token_set(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", " ", value).lower()
    return {token for token in normalized.split() if len(token) >= 2}


def heuristic_match_document(filename: str, extracted_text: str) -> dict | None:
    source_tokens = token_set(f"{filename} {extracted_text[:3000]}")
    best = None
    best_score = 0.0
    for candidate in evidence_candidates():
        candidate_tokens = token_set(f"{candidate['criterionName']} {candidate['category']} {candidate['evidenceName']}")
        if not candidate_tokens:
            continue
        overlap = source_tokens & candidate_tokens
        score = len(overlap) / max(4, len(candidate_tokens))
        if score > best_score:
            best = candidate
            best_score = score
    if best and best_score >= 0.18:
        return {**best, "confidence": round(min(best_score, 0.95), 2), "method": "heuristic"}
    return None


def parse_llm_json(content: str) -> dict | None:
    if not content:
        return None
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def llm_match_document(filename: str, extracted_text: str) -> dict | None:
    candidates = evidence_candidates()
    task = """
업로드 문서가 어떤 ODA 평가 기준의 필수 증빙 항목에 해당하는지 분류하세요.
반드시 JSON 객체만 반환하세요.
형식: {"matched": true|false, "criterionId": "...", "evidenceName": "...", "confidence": 0.0~1.0, "reason": "..."}
적절한 항목이 없거나 확신이 낮으면 {"matched": false, "reason": "..."}를 반환하세요.
"""
    context = {
        "fileName": filename,
        "textPreview": extracted_text[:5000],
        "candidates": candidates,
    }
    result = OPENROUTER.request_chat_completion(OPENROUTER.build_messages(task, context))
    parsed = parse_llm_json(result.get("content", "")) if result.get("ok") else None
    if not parsed or not parsed.get("matched"):
        return None
    criterion_id = parsed.get("criterionId")
    evidence_name = parsed.get("evidenceName")
    candidate = next((item for item in candidates if item["criterionId"] == criterion_id and item["evidenceName"] == evidence_name), None)
    if not candidate:
        return None
    return {
        **candidate,
        "confidence": float(parsed.get("confidence", 0.6) or 0.6),
        "method": "llm",
        "reason": parsed.get("reason", ""),
    }


def match_document_target(filename: str, extracted_text: str) -> dict | None:
    heuristic = heuristic_match_document(filename, extracted_text)
    if heuristic:
        return heuristic
    return llm_match_document(filename, extracted_text)


def batch_upload_documents(files: list[dict]) -> dict:
    proposals = []
    for file_body in files:
        filename = safe_filename(file_body.get("fileName", "uploaded_file"))
        raw = base64.b64decode(file_body.get("contentBase64", ""))
        mime_type = file_body.get("mimeType", "application/octet-stream")
        extracted_text, _ = extract_text(raw, filename, mime_type)
        target = match_document_target(filename, extracted_text)
        document = save_uploaded_document(
            "_pending",
            {
                **file_body,
                "fileName": filename,
                "mimeType": mime_type,
                "evidenceName": target["evidenceName"] if target else "분류 제안 필요",
            },
        )
        document["matchStatus"] = "proposal_ready" if target else "proposal_unmatched"
        document["suggestedMatch"] = target
        persist_document_metadata("_pending", document)
        proposals.append(document)

    return {
        "proposals": proposals,
        "dashboard": dashboard_payload(),
    }


def move_staged_document(source_bucket: str, document_id: str, criterion_id: str, evidence_name: str, status: str) -> dict:
    criterion = find_criterion(criterion_id)
    if not criterion:
        raise ValueError("Criterion not found")
    document, meta_path = find_uploaded_document(source_bucket, document_id)
    if not document:
        raise ValueError("Document not found")
    target_upload_dir = UPLOAD_DIR / criterion_id
    target_text_dir = TEXT_DIR / criterion_id
    target_upload_dir.mkdir(parents=True, exist_ok=True)
    target_text_dir.mkdir(parents=True, exist_ok=True)

    raw_path = Path(document.get("rawPath", ""))
    text_path = Path(document.get("textPath", ""))
    if raw_path.exists():
        new_raw_path = target_upload_dir / raw_path.name
        raw_path.replace(new_raw_path)
        document["rawPath"] = str(new_raw_path)
    if text_path.exists():
        new_text_path = target_text_dir / text_path.name
        text_path.replace(new_text_path)
        document["textPath"] = str(new_text_path)
    if meta_path:
        meta_path.unlink(missing_ok=True)

    document.update(
        {
            "criterionId": criterion_id,
            "evidenceName": evidence_name,
            "matchStatus": status,
            "assignedAt": now_label(),
        }
    )
    document.pop("suggestedMatch", None)
    persist_document_metadata(criterion_id, document)
    return document


def confirm_batch_documents(assignments: list[dict]) -> dict:
    assigned = []
    updated_criteria = set()
    for assignment in assignments:
        criterion_id = assignment.get("criterionId", "")
        evidence_name = assignment.get("evidenceName", "").strip()
        document_id = assignment.get("documentId", "")
        if not criterion_id or not evidence_name or not document_id:
            continue
        document = move_staged_document("_pending", document_id, criterion_id, evidence_name, "confirmed_assigned")
        assigned.append(document)
        updated_criteria.add(criterion_id)

    evaluations = {}
    for criterion_id in updated_criteria:
        criterion = find_criterion(criterion_id)
        evaluation = generate_criterion_evaluation(criterion_id, None)
        if criterion and evaluation:
            criterion["evaluationResult"] = evaluation
            if evaluation.get("score"):
                criterion["currentScore4"] = evaluation["score"]
                criterion["scoreStatus"] = "평가 완료"
            save_evaluation_result(criterion_id, evaluation)
            evaluations[criterion_id] = evaluation

    return {"assigned": assigned, "evaluations": evaluations, "dashboard": dashboard_payload()}


def assign_unmatched_document(document_id: str, criterion_id: str, evidence_name: str) -> dict:
    criterion = find_criterion(criterion_id)
    document = move_staged_document("_unmatched", document_id, criterion_id, evidence_name, "manual_assigned")
    evaluation = generate_criterion_evaluation(criterion_id, document)
    if evaluation:
        criterion["evaluationResult"] = evaluation
        if evaluation.get("score"):
            criterion["currentScore4"] = evaluation["score"]
            criterion["scoreStatus"] = "평가 완료"
        save_evaluation_result(criterion_id, evaluation)
    return {"document": document, "evaluationResult": evaluation, "dashboard": dashboard_payload()}


def sync_project_overview_to_relevance(overview: dict, extracted_text: str, extraction_method: str) -> dict:
    document_id = "project_overview"
    criterion_id = "relevance"
    criterion_upload_dir = UPLOAD_DIR / criterion_id
    criterion_text_dir = TEXT_DIR / criterion_id
    criterion_upload_dir.mkdir(parents=True, exist_ok=True)
    criterion_text_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(overview["path"])
    raw_path = criterion_upload_dir / f"{document_id}_{overview['name']}"
    if source_path.exists():
        raw_path.write_bytes(source_path.read_bytes())
    text_path = criterion_text_dir / f"{document_id}.txt"
    text_path.write_text(extracted_text, encoding="utf-8")

    remove_document_metadata_by_evidence(criterion_id, PROJECT_OVERVIEW_EVIDENCE_NAME)
    document = {
        "id": document_id,
        "criterionId": criterion_id,
        "evidenceName": PROJECT_OVERVIEW_EVIDENCE_NAME,
        "fileName": overview["name"],
        "mimeType": mimetypes.guess_type(overview["name"])[0] or "application/octet-stream",
        "size": overview["size"],
        "rawPath": str(raw_path),
        "textPath": str(text_path),
        "textPreview": extracted_text[:1200],
        "extractionMethod": extraction_method,
        "uploadedAt": now_label(),
        "source": "project_overview",
    }
    persist_document_metadata(criterion_id, document)
    return document


def ensure_project_overview_evidence_synced() -> None:
    overview = current_project_overview()
    if overview.get("source") != "uploaded" or not overview.get("exists"):
        return
    for document in list_uploaded_documents("relevance"):
        if document.get("evidenceName") == PROJECT_OVERVIEW_EVIDENCE_NAME and document.get("fileName") == overview.get("name"):
            return
    text_path_value = overview.get("textPath")
    text_path = Path(text_path_value) if text_path_value else None
    if text_path and text_path.exists():
        extracted_text = text_path.read_text(encoding="utf-8")
    else:
        raw_path = Path(overview["path"])
        raw = raw_path.read_bytes() if raw_path.exists() else b""
        mime_type = mimetypes.guess_type(overview.get("name", ""))[0] or "application/octet-stream"
        extracted_text, extraction_method = extract_text(raw, overview.get("name", raw_path.name), mime_type)
        overview["extractionMethod"] = extraction_method
    sync_project_overview_to_relevance(
        overview,
        extracted_text,
        overview.get("extractionMethod", "synced_project_overview"),
    )


def relevance_context(document: dict | None = None) -> dict:
    uploaded_texts = []
    if (TEXT_DIR / "relevance").exists():
        for path in sorted((TEXT_DIR / "relevance").glob("*.txt")):
            uploaded_texts.append({"path": str(path), "text": path.read_text(encoding="utf-8")[:6000]})
    return {
        "project": project_payload(),
        "criterion": find_criterion("relevance"),
        "uploadedDocument": document,
        "uploadedTexts": uploaded_texts,
        "commonScoringNotes": COMMON_SCORING_NOTES,
        "scoringRubric": RELEVANCE_SCORING,
        "requiredEvidence": RELEVANCE_EVIDENCE,
    }


def fallback_relevance_evaluation(document: dict | None = None, llm_result: dict | None = None) -> dict:
    uploaded_count = len(list((TEXT_DIR / "relevance").glob("*.txt"))) if (TEXT_DIR / "relevance").exists() else 0
    score = 2 if uploaded_count < 4 else 3
    if uploaded_count >= 10:
        score = 4
    summary = (
        f"현재 적절성 관련 업로드 문서는 {uploaded_count}건입니다. "
        "필수 증빙 전체가 완비되기 전까지 4점 상한 적용은 보류되며, 핵심 설계·수요·정책 부합성 자료 누락 시 최대 2점으로 제한될 수 있습니다."
    )
    return {
        "status": "generated" if llm_result and llm_result.get("ok") else "fallback",
        "score": score,
        "summary": llm_result.get("content") if llm_result and llm_result.get("ok") else summary,
        "sections": [
            {
                "title": "수요 및 정책 부합성",
                "body": "수요조사서, 협력국 국가개발전략, KOICA CPS/CAS 매핑 자료가 업로드되어야 근거 기반 판단이 가능함.",
            },
            {
                "title": "사업 설계 및 논리모형의 타당성",
                "body": "최신 PDM, ToC, 문제나무 분석, 이해관계자 역할분담 문서가 업로드되면 설계 타당성 평가 정확도가 높아짐.",
            },
            {
                "title": "상황 변화에 대한 대응성",
                "body": "정기 모니터링 보고서와 Change Log/JSC 회의록이 없으면 변경관리 대응성 점수 상한이 제한될 수 있음.",
            },
        ],
        "model": OPENROUTER.model,
        "llm": llm_result or {},
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def generate_relevance_evaluation(document: dict | None = None) -> dict:
    return generate_criterion_evaluation("relevance", document)


def criterion_context(criterion_id: str, document: dict | None = None) -> dict:
    uploaded_texts = []
    text_dir = TEXT_DIR / criterion_id
    if text_dir.exists():
        for path in sorted(text_dir.glob("*.txt")):
            uploaded_texts.append({"path": str(path), "text": path.read_text(encoding="utf-8")[:6000]})
    criterion = find_criterion(criterion_id)
    return {
        "project": project_payload(),
        "criterion": criterion,
        "uploadedDocument": document,
        "uploadedTexts": uploaded_texts,
        "commonScoringNotes": COMMON_SCORING_NOTES,
        "scoringRubric": criterion.get("scoringRubric") if criterion else None,
        "requiredEvidence": criterion.get("evidenceGroups") if criterion else None,
    }


def fallback_coherence_evaluation(document: dict | None = None, llm_result: dict | None = None) -> dict:
    uploaded_count = len(list((TEXT_DIR / "coherence").glob("*.txt"))) if (TEXT_DIR / "coherence").exists() else 0
    score = 2 if uploaded_count < 3 else 3
    if uploaded_count >= 8:
        score = 4
    summary = (
        f"현재 일관성 관련 업로드 문서는 {uploaded_count}건입니다. "
        "타 공여 개입 매핑, 조정 회의록/MoU, 역할분담 문서, 세이프가드 자료가 모두 확인되기 전까지 4점 상한 적용은 보류됩니다."
    )
    return {
        "status": "generated" if llm_result and llm_result.get("ok") else "fallback",
        "score": score,
        "summary": llm_result.get("content") if llm_result and llm_result.get("ok") else summary,
        "sections": [
            {
                "title": "내적 일관성",
                "body": "국내 정책, KOICA 타 사업, SDGs·인권·젠더·환경 등 국제규범 및 세이프가드 준수 근거가 업로드되어야 내적 일관성 판단이 가능함.",
            },
            {
                "title": "외적 일관성",
                "body": "타 공여기관, 수원국 정부 및 현지 민간 개입과의 조정 회의록, MoU, 매핑 자료가 업로드되어야 중복 방지와 부가가치 창출 수준을 판단할 수 있음.",
            },
        ],
        "model": OPENROUTER.model,
        "llm": llm_result or {},
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def generate_coherence_evaluation(document: dict | None = None) -> dict:
    return generate_criterion_evaluation("coherence", document)


def fallback_generic_evaluation(criterion_id: str, document: dict | None = None, llm_result: dict | None = None) -> dict:
    criterion = find_criterion(criterion_id) or {}
    criterion_name = criterion.get("name", criterion_id)
    text_dir = TEXT_DIR / criterion_id
    uploaded_count = len(list(text_dir.glob("*.txt"))) if text_dir.exists() else 0
    required_count = len(criterion.get("evidence", []))
    score = 1
    if uploaded_count:
        score = 2
    if required_count and uploaded_count >= max(2, required_count // 2):
        score = 3
    if required_count and uploaded_count >= required_count:
        score = 4

    summary = (
        f"현재 {criterion_name} 관련 업로드 문서는 {uploaded_count}건입니다. "
        f"필수 증빙 {required_count}건의 충족 여부와 문서 내용에 따라 1~4점 평가가 산정됩니다."
    )
    scoring = criterion.get("scoringRubric") or []
    return {
        "status": "generated" if llm_result and llm_result.get("ok") else "fallback",
        "score": score,
        "summary": llm_result.get("content") if llm_result and llm_result.get("ok") else summary,
        "sections": [
            {
                "title": item.get("question", f"{criterion_name} 평가질문"),
                "body": "업로드된 증빙자료와 평가 기준표를 기준으로 평가결과 초안을 생성합니다.",
            }
            for item in scoring
        ],
        "model": OPENROUTER.model,
        "llm": llm_result or {},
        "lastDocument": document,
        "updatedAt": now_label(),
    }


def generate_criterion_evaluation(criterion_id: str, document: dict | None = None) -> dict | None:
    prompt = get_evaluation_prompt(criterion_id)
    if not prompt:
        return None
    context = relevance_context(document) if criterion_id == "relevance" else criterion_context(criterion_id, document)
    messages = OPENROUTER.build_messages(prompt, context)
    llm_result = OPENROUTER.request_chat_completion(messages)
    if criterion_id == "relevance":
        return clean_evaluation_result(fallback_relevance_evaluation(document, llm_result))
    if criterion_id == "coherence":
        return clean_evaluation_result(fallback_coherence_evaluation(document, llm_result))
    return clean_evaluation_result(fallback_generic_evaluation(criterion_id, document, llm_result))


def overall_grade(score: int) -> tuple[str, str]:
    if score >= 18:
        return "A", "매우 성공적"
    if score >= 16:
        return "B", "성공적"
    if score >= 14:
        return "C", "성공적"
    if score >= 12:
        return "D", "부분 성공적"
    if score >= 10:
        return "E", "부분 성공적"
    return "F", "미흡"


CRITERION_LABELS = {
    "relevance": "적절성",
    "coherence": "일관성",
    "effectiveness": "효과성",
    "efficiency": "효율성",
    "sustainability": "지속가능성",
    "impact": "영향",
}


CRITERION_ENGLISH = {
    "relevance": "Relevance",
    "coherence": "Coherence",
    "effectiveness": "Effectiveness",
    "efficiency": "Efficiency",
    "sustainability": "Sustainability",
    "impact": "Impact",
}


def grade_label(score: int) -> tuple[str, str]:
    if score >= 18:
        return "A", "매우 성공적"
    if score >= 16:
        return "B", "성공적"
    if score >= 14:
        return "C", "성공적"
    if score >= 12:
        return "D", "부분 성공적"
    if score >= 10:
        return "E", "부분 성공적"
    return "F", "미흡"


def criterion_label(criterion: dict) -> str:
    return CRITERION_LABELS.get(criterion.get("id", ""), criterion.get("name", "평가기준"))


def report_criteria() -> list[dict]:
    return [criterion for criterion in CRITERIA if criterion.get("id") != "impact"]


def reference_documents_for_report() -> list[dict]:
    documents = []
    for criterion in CRITERIA:
        for document in list_uploaded_documents(criterion["id"]):
            documents.append(
                {
                    **document,
                    "criterionName": criterion_label(criterion),
                    "criterionId": criterion["id"],
                }
            )
    documents.sort(key=lambda item: item.get("uploadedAt", ""), reverse=True)
    return [{**document, "referenceNumber": index + 1} for index, document in enumerate(documents)]


def short_text(value: str | None, limit: int = 900) -> str:
    text = clean_evaluation_text(value or "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def plain_lines(value: str | None) -> list[str]:
    text = short_text(value, 1800)
    lines = [line.strip(" -\t") for line in text.split("\n") if line.strip(" -\t")]
    return lines or ["업로드된 문서와 저장된 평가 결과를 기준으로 작성 대기"]


def references_for_criterion(criterion_id: str, references: list[dict]) -> list[dict]:
    return [document for document in references if document.get("criterionId") == criterion_id]


def docx_paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{style_xml}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def docx_table(rows: list[list[str]]) -> str:
    table_rows = []
    for row in rows:
        cells = "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>{docx_paragraph(str(cell))}</w:tc>'
            for cell in row
        )
        table_rows.append(f"<w:tr>{cells}</w:tr>")
    return (
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="0" w:type="auto"/></w:tblPr>'
        + "".join(table_rows)
        + "</w:tbl>"
    )


def build_report_docx(project: dict, criteria: list[dict], references: list[dict], overall: dict) -> bytes:
    body = [
        docx_paragraph("종료평가 결과보고서", "Title"),
        docx_paragraph(project.get("title", "사업명 확인 필요"), "Heading1"),
        docx_table(
            [
                ["사업기간", project.get("period", "기간 확인 필요")],
                ["사업비", project.get("budget", "사업비 확인 필요")],
                ["종합점수", f"{overall['score']}/{overall['maxScore']}점"],
                ["KOICA 평가등급", overall["koicaGrade"]],
                ["국무조정실 평가등급", overall["governmentGrade"]],
                ["작성일", now_label()],
            ]
        ),
        docx_paragraph("1. 평가결과", "Heading1"),
    ]
    for index, criterion in enumerate(criteria, start=1):
        evaluation = criterion.get("evaluationResult") or {}
        criterion_id = criterion.get("id", "")
        title = f"{index}. {criterion_label(criterion)}({CRITERION_ENGLISH.get(criterion_id, '')})"
        score = evaluation.get("score") or criterion.get("currentScore4", 1)
        criterion_refs = references_for_criterion(criterion_id, references)
        citation = " ".join(f"[{document['referenceNumber']}]" for document in criterion_refs[:5])
        body.append(docx_paragraph(f"{title} - {score}점/4점 {citation}".strip(), "Heading2"))
        for line in plain_lines(evaluation.get("summary")):
            body.append(docx_paragraph(f"- {line}"))
        for section in evaluation.get("sections", []) or []:
            if section.get("title"):
                body.append(docx_paragraph(section["title"], "Heading3"))
            for line in plain_lines(section.get("body")):
                body.append(docx_paragraph(f"- {line}"))

    body.append(docx_paragraph("2. 참고문헌 목록", "Heading1"))
    if references:
        body.append(docx_table([["번호", "평가기준", "문서명", "증빙 항목"]] + [
            [
                str(document["referenceNumber"]),
                document.get("criterionName", ""),
                document.get("fileName", ""),
                document.get("evidenceName", ""),
            ]
            for document in references
        ]))
    else:
        body.append(docx_paragraph("등록된 참고문헌 없음"))

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        "</w:body></w:document>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="25"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="8EA3C2"/><w:left w:val="single" w:sz="4" w:space="0" w:color="8EA3C2"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="8EA3C2"/><w:right w:val="single" w:sz="4" w:space="0" w:color="8EA3C2"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="D7DFEA"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="D7DFEA"/></w:tblBorders></w:tblPr></w:style>'
        "</w:styles>"
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        docx.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        docx.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", styles_xml)
    return output.getvalue()


def xlsx_cell(column: int, row: int, value: str | int) -> str:
    column_name = ""
    number = column
    while number:
        number, remainder = divmod(number - 1, 26)
        column_name = chr(65 + remainder) + column_name
    ref = f"{column_name}{row}"
    if isinstance(value, int):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def build_grade_xlsx(project: dict, criteria: list[dict], references: list[dict], overall: dict) -> bytes:
    rows = [
        ["종료평가 등급 결과표", "", "", ""],
        ["사업명", project.get("title", ""), "작성일", now_label()],
        ["기간", project.get("period", ""), "사업비", project.get("budget", "")],
        ["평가기준", "점수(1~4)", "주요 평가결과", "근거문서 번호"],
    ]
    for criterion in criteria:
        evaluation = criterion.get("evaluationResult") or {}
        criterion_refs = references_for_criterion(criterion["id"], references)
        rows.append(
            [
                criterion_label(criterion),
                int(evaluation.get("score") or criterion.get("currentScore4", 1)),
                short_text(evaluation.get("summary"), 350),
                ", ".join(f"[{document['referenceNumber']}]" for document in criterion_refs[:8]),
            ]
        )
    rows += [
        ["종합점수", int(overall["score"]), f"{overall['maxScore']}점 만점", ""],
        ["KOICA 평가등급", overall["koicaGrade"], "국무조정실 평가등급", overall["governmentGrade"]],
    ]
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(xlsx_cell(column_index, row_index, value) for column_index, value in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols><col min="1" max="1" width="22"/><col min="2" max="2" width="14"/><col min="3" max="3" width="70"/><col min="4" max="4" width="22"/></cols>'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        xlsx.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        xlsx.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        xlsx.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="종료평가 등급 결과표" sheetId="1" r:id="rId1"/></sheets></workbook>')
        xlsx.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


def build_report_plain_text(project: dict, criteria: list[dict], references: list[dict], overall: dict) -> str:
    lines = [
        "종료평가 결과보고서",
        "",
        f"사업명: {project.get('title', '사업명 확인 필요')}",
        f"사업기간: {project.get('period', '기간 확인 필요')}",
        f"사업비: {project.get('budget', '사업비 확인 필요')}",
        f"종합점수: {overall['score']}/{overall['maxScore']}점",
        f"KOICA 평가등급: {overall['koicaGrade']}",
        f"국무조정실 평가등급: {overall['governmentGrade']}",
        f"작성일: {now_label()}",
        "",
        "1. 평가결과",
        "",
    ]
    for index, criterion in enumerate(criteria, start=1):
        evaluation = criterion.get("evaluationResult") or {}
        criterion_id = criterion.get("id", "")
        criterion_refs = references_for_criterion(criterion_id, references)
        citation = " ".join(f"[{document['referenceNumber']}]" for document in criterion_refs[:5])
        score = evaluation.get("score") or criterion.get("currentScore4", 1)
        lines += [
            f"{index}. {criterion_label(criterion)}({CRITERION_ENGLISH.get(criterion_id, '')}) 평가결과",
            f"평가점수: {score}점/4점 {citation}".strip(),
            "",
        ]
        lines.extend(f"- {line}" for line in plain_lines(evaluation.get("summary")))
        lines.append("")
        for section in evaluation.get("sections", []) or []:
            if section.get("title"):
                lines.append(section["title"])
            lines.extend(f"- {line}" for line in plain_lines(section.get("body")))
            lines.append("")
    lines += ["2. 참고문헌 목록", ""]
    if references:
        lines.extend(
            f"[{document['referenceNumber']}] {document.get('fileName', '')} | {document.get('criterionName', '')} | {document.get('evidenceName', '')}"
            for document in references
        )
    else:
        lines.append("등록된 참고문헌 없음")
    return "\n".join(lines).strip() + "\n"


def build_template_hwp_report(project: dict, criteria: list[dict], references: list[dict], overall: dict) -> tuple[bytes | None, str | None]:
    if not HWP_REPORT_TEMPLATE_PATH.exists() or not HWP_REPORT_SCRIPT.exists():
        return None, "HWP template or automation script not found."
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    content_path = REPORT_DIR / f"hwp_report_content_{timestamp}.txt"
    output_path = REPORT_DIR / f"원본양식_기반_종료평가_보고서_{timestamp}.hwp"
    content_path.write_text(build_report_plain_text(project, criteria, references, overall), encoding="utf-8")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HWP_REPORT_SCRIPT),
        "-TemplatePath",
        str(HWP_REPORT_TEMPLATE_PATH),
        "-OutputPath",
        str(output_path),
        "-ContentPath",
        str(content_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=90)
    except Exception as exc:  # noqa: BLE001
        return None, f"HWP generation failed: {exc}"
    if not output_path.exists() or output_path.stat().st_size <= 0:
        return None, "HWP generation completed without an output file."
    return output_path.read_bytes(), None


def build_evaluation_report_package() -> tuple[bytes, str]:
    attach_uploaded_documents()
    apply_persisted_evaluations()
    project = project_payload()
    criteria = report_criteria()
    references = reference_documents_for_report()
    total_score = sum(item.get("currentScore4", 1) for item in criteria)
    koica_grade, government_grade = grade_label(total_score)
    overall = {
        "score": total_score,
        "maxScore": 20,
        "koicaGrade": koica_grade,
        "governmentGrade": government_grade,
    }
    docx_bytes = build_report_docx(project, criteria, references, overall)
    xlsx_bytes = build_grade_xlsx(project, criteria, references, overall)
    hwp_bytes, hwp_error = build_template_hwp_report(project, criteria, references, overall)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"ODA_종료평가_보고서_패키지_{timestamp}.zip"
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        if hwp_bytes:
            package.writestr("0_원본양식_기반_종료평가_보고서.hwp", hwp_bytes)
        else:
            package.writestr("0_HWP_생성_안내.txt", hwp_error or "HWP report generation was skipped.")
        package.writestr("1_종료평가_결과보고서.docx", docx_bytes)
        package.writestr("2_종료평가_등급_결과표.xlsx", xlsx_bytes)
        package.writestr(
            "3_참고문헌_목록.txt",
            "\n".join(
                f"[{document['referenceNumber']}] {document.get('fileName', '')} | {document.get('criterionName', '')} | {document.get('evidenceName', '')}"
                for document in references
            )
            or "등록된 참고문헌 없음",
        )
    return output.getvalue(), package_name


def dashboard_payload() -> dict:
    ensure_project_overview_evidence_synced()
    attach_uploaded_documents()
    apply_persisted_evaluations()
    grade_criteria = [item for item in CRITERIA if item.get("id") != "impact"]
    total_score = sum(item.get("currentScore4", 1) for item in grade_criteria)
    koica_grade, gov_grade = overall_grade(total_score)
    return {
        "project": project_payload(),
        "criteria": CRITERIA,
        "unmatchedDocuments": list_uploaded_documents("_unmatched"),
        "pendingDocuments": list_uploaded_documents("_pending"),
        "overall": {
            "score": total_score,
            "maxScore": 20,
            "koicaGrade": koica_grade,
            "governmentGrade": gov_grade,
            "rule": "KOICA 평가등급은 영향 항목을 제외한 5개 기준 합산으로 산정하며, 미평가 또는 문서 미업로드 항목은 기본 1점으로 산정",
        },
        "updatedAt": now_label(),
        "chartA": {
            "title": "DAC 6대 기준 현재 평가점수",
            "description": "각 기준은 1~4점 척도로 표시되며, 미평가 항목은 1점으로 산정합니다.",
            "series": [
                {"name": "현재 평가점수", "key": "currentScore4", "color": "#52d5ff"},
            ],
        },
        "chartB": {
            "title": "DAC 6대 기준 목표 대비 현황",
            "description": "목표점수 4점 대비 현재 평가점수를 비교합니다.",
            "series": [
                {"name": "목표점수", "key": "targetScore4", "color": "#7a6dff"},
                {"name": "현재 평가점수", "key": "currentScore4", "color": "#52d5ff"},
            ],
        },
    }


def project_overview_preview() -> dict:
    overview = current_project_overview()
    return {
        "project": project_payload(),
        "file": overview,
        "sections": [
            {"title": "문서 유형", "body": "2026-2027 CTS Seed1 국문 사업개요서 원본 HWP 파일입니다."},
            {"title": "임시 미리보기", "body": "현재 앱은 원본 파일을 연결한 상태이며, HWP 본문 렌더링은 PDF/HTML 변환 모듈 연동 후 제공할 수 있습니다."},
            {"title": "확인 항목", "body": "사업기간, 예산, 성과관리·평가 자동화 솔루션 범위, DAC 6대 기준 대응 자료를 원본에서 확인하세요."},
        ],
    }


def save_project_overview(body: dict) -> dict:
    filename = safe_filename(body.get("fileName", PROJECT_OVERVIEW_PATH.name))
    mime_type = body.get("mimeType", "application/octet-stream")
    raw = base64.b64decode(body.get("contentBase64", ""))
    PROJECT_OVERVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_path = PROJECT_OVERVIEW_UPLOAD_DIR / f"{timestamp}_{filename}"
    stored_path.write_bytes(raw)
    extracted_text, extraction_method = extract_text(raw, filename, mime_type)
    text_path = PROJECT_OVERVIEW_UPLOAD_DIR / f"{timestamp}_{Path(filename).stem}.txt"
    text_path.write_text(extracted_text, encoding="utf-8")
    project_title = infer_project_title(extracted_text, filename) or PROJECT["title"]
    project_period, project_budget = extract_project_period_budget(extracted_text)
    overview = {
        "exists": True,
        "name": filename,
        "path": str(stored_path),
        "size": len(raw),
        "lastModified": now_label(),
        "downloadUrl": PROJECT["overviewUrl"],
        "source": "uploaded",
        "projectTitle": project_title,
        "projectPeriod": project_period or "기간 확인 필요",
        "projectBudget": project_budget or "사업비 확인 필요",
        "textPath": str(text_path),
        "textPreview": extracted_text[:1200],
        "extractionMethod": extraction_method,
    }
    PROJECT_OVERVIEW_STATE_PATH.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    synced_document = sync_project_overview_to_relevance(overview, extracted_text, extraction_method)
    relevance = find_criterion("relevance")
    evaluation = generate_relevance_evaluation(synced_document) if relevance else None
    if relevance and evaluation:
        relevance["evaluationResult"] = evaluation
        if evaluation.get("score"):
            relevance["currentScore4"] = evaluation["score"]
            relevance["scoreStatus"] = "평가 완료"
        save_evaluation_result("relevance", evaluation)
    return {
        "saved": True,
        "project": project_payload(),
        "file": overview,
        "syncedDocument": synced_document,
        "evaluationResult": evaluation,
        "dashboard": dashboard_payload(),
        "message": "사업개요서 수정본이 업로드되었습니다.",
    }


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
        if path == "/api/references/batch-upload":
            self.send_json(batch_upload_documents(body.get("files", [])))
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
            evaluation = generate_criterion_evaluation(criterion_id, document)
            if evaluation:
                criterion["evaluationResult"] = evaluation
                if evaluation and evaluation.get("score"):
                    criterion["currentScore4"] = evaluation["score"]
                    criterion["scoreStatus"] = "평가 완료"
                save_evaluation_result(criterion_id, evaluation)
            self.send_json({"saved": True, "document": document, "evaluationResult": evaluation, "dashboard": dashboard_payload()})
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
                self.send_json({"deleted": True, "document": deleted, "dashboard": dashboard_payload()})
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
