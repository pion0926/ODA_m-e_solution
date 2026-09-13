from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from psycopg.types.json import Jsonb

from .db import connection, current_project_id
from .openrouter import AnalysisError, MissingApiKey, analyze_performance_risks
from .pdm_source import extract_authoritative_pdm_slots
from .pdm_evidence import enrich_from_evidence
from .reported_metrics_source import is_metrics_header, select_reported_metrics_source


TIER_DEFINITIONS = (
    ("impact", "영향", "impact_summary", "impact_indicator", "impact_mov", "impact_assumption"),
    ("outcome", "성과", "outcome_summary", "outcome_indicator", "outcome_mov", "outcome_assumption"),
    ("outputs", "산출물", "outputs_summary", "outputs_indicator", "outputs_mov", "outputs_assumption"),
)

TIER_LABELS = {
    "impact": "Impact(영향)",
    "outcome": "Outcome(성과)",
    "outputs": "Output(산출물)",
}

_NUMBERED_LINE = re.compile(r"^\s*(\d+(?:[.-]\d+)*(?:-\d+)?)\.\s*(.+?)\s*$")


def _numbered_items(text: str) -> list[dict]:
    items: list[dict] = []
    for index, raw_line in enumerate(str(text or "").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        match = _NUMBERED_LINE.match(line)
        if match:
            code, value = match.groups()
        else:
            code, value = str(index), line
        normalized = re.sub(r"[.-]+", ".", code).strip(".")
        items.append({"code": code, "normalized_code": normalized, "text": value.strip()})
    return items


def _model_from_slots(slots: dict[str, str]) -> dict:
    tiers = []
    for tier_id, tier_name, summary_key, indicator_key, mov_key, assumption_key in TIER_DEFINITIONS:
        indicators = _numbered_items(slots.get(indicator_key, ""))
        means = {item["normalized_code"]: item for item in _numbered_items(slots.get(mov_key, ""))}
        rows = []
        for position, indicator in enumerate(indicators, 1):
            mean = means.get(indicator["normalized_code"])
            indicator_id = f"{tier_id}-{indicator['normalized_code'].replace('.', '-')}"
            rows.append({
                "id": indicator_id,
                "position": position,
                "code": indicator["code"],
                "text": indicator["text"],
                "mov": mean["text"] if mean else "PDM에 검증수단 미기재",
                "mov_code": mean["code"] if mean else "",
            })
        tiers.append({
            "id": tier_id,
            "name": tier_name,
            "summary": slots.get(summary_key, ""),
            "assumption": slots.get(assumption_key, ""),
            "indicators": rows,
        })
    return {"source_cells": {key: slots.get(key, "") for key in slots}, "tiers": tiers}


def _source_priority(name: str) -> tuple[int, str]:
    lowered = name.lower()
    if "최신 pdm" in lowered:
        return 0, lowered
    if "pdm 1차 수정" in lowered:
        return 1, lowered
    if "pdm" in lowered and "원안" not in lowered:
        return 2, lowered
    return 3, lowered


def _documents() -> list[dict]:
    with connection() as conn:
        return conn.execute(
            """SELECT id,original_name,stored_path,extracted_path,size_bytes,summary,analysis,queue_position
                 FROM intake_documents WHERE status='completed' ORDER BY queue_position"""
        ).fetchall()


def _select_pdm_source(documents: list[dict]) -> tuple[dict, dict[str, str]]:
    candidates = sorted(
        [item for item in documents if "pdm" in item["original_name"].lower() and item["original_name"].lower().endswith(".pdf")],
        key=lambda item: (
            -int(item.get("queue_position") or 0),
            _source_priority(item["original_name"])[0],
            _source_priority(item["original_name"])[1],
        ),
    )
    for item in candidates:
        slots = extract_authoritative_pdm_slots(item["stored_path"])
        if slots:
            return item, slots
    raise RuntimeError("표 구조를 읽을 수 있는 PDM PDF가 없습니다.")


def _safe_document_name(document: dict) -> str:
    return str(document.get("original_name") or "").lower()


def _is_evidence_document(document: dict) -> bool:
    name = _safe_document_name(document)
    return not any(token in name for token in ("readme", "업로드_안내", "자료요청", "메일초안", "pdm", "사업계획서"))


def _matches_pdm_requirement(document: dict, mov: str, indicator: str) -> tuple[bool, float, str]:
    name = _safe_document_name(document)
    evidence_name = name.split("__", 1)[-1]
    if not _is_evidence_document(document) or "자료없음" in name:
        return False, 0.0, ""
    requirement = f"{mov} {indicator}".lower()
    rules: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
        (("보건통계",), ("보건통계", "연보"), "보건통계 연보"),
        (("rrcem", "국립응급의료센터"), ("rrcem", "국립응급의료센터", "연례"), "응급의료센터 연례자료"),
        (("강의계획서", "학사 운영"), ("강의계획서", "교육과정_1학년", "교육과정_2,3학년"), "학사운영·강의계획"),
        (("정부 승인", "승인 공문"), ("job code", "승인서", "수총기관공문", "승인 공문"), "정부 승인 공문"),
        (("자격시험 결과",), ("자격시험", "졸업시험"), "자격시험 결과"),
        (("졸업생 취업",), ("졸업생 취업", "취업 현황", "추적조사"), "졸업생 취업 조사"),
        (("cpcr 교육센터 운영",), ("cpcr", "운영 일지", "운영일지"), "CPCR 운영 일지"),
        (("교원 연수 결과",), ("교원역량", "강사 양성"), "교원 연수 결과"),
        (("출판물 실물", "배포리스트"), ("교육과정_교재", "교재 ", "교재개발"), "교재·배포자료"),
        (("실습실 사용 대장",), ("실습실 사용", "사용 대장"), "실습실 사용 대장"),
        (("자격시험 매뉴얼",), ("자격시험 매뉴얼", "졸업시험 매뉴얼"), "자격시험 매뉴얼"),
        (("강사 자격증 발급",), ("강사 자격증", "발급 대장"), "강사 자격 발급대장"),
        (("훈련 결과 보고서", "영상 자료"), ("mci", "훈련 결과", "모의훈련"), "MCI 훈련 결과"),
    ]
    for requirement_tokens, filename_tokens, label in rules:
        if any(token in requirement for token in requirement_tokens):
            hits = [token for token in filename_tokens if token in evidence_name]
            if not hits:
                return False, 0.0, ""
            if label == "교원 연수 결과" and "결과보고서" not in name:
                return False, 0.0, ""
            if label == "CPCR 운영 일지" and not any(token in evidence_name for token in ("운영 일지", "운영일지", "교육 결과보고서")):
                return False, 0.0, ""
            if label == "MCI 훈련 결과" and not any(token in name for token in ("훈련 결과", "모의훈련", "영상")):
                return False, 0.0, ""
            return True, min(0.98, 0.86 + 0.03 * len(hits)), f"{label}와 문서명 신호({', '.join(hits[:4])}) 일치"
    return False, 0.0, ""


def _evidence_document_ids(documents: list[dict], evidence: str, program: str, indicator: str) -> list[str]:
    evidence_text = str(evidence or "").lower()
    program_text = str(program or "").lower()
    indicator_text = str(indicator or "").lower()
    matches: list[str] = []
    for document in documents:
        if not _is_evidence_document(document) or "자료없음" in _safe_document_name(document):
            continue
        name = _safe_document_name(document)
        matched = False
        if "검수조서" in evidence_text:
            matched = "검수조서" in name
        elif "강의계획서" in evidence_text:
            matched = "강의계획서" in name
        elif "만족도" in evidence_text:
            matched = "만족도" in name
        elif any(token in evidence_text for token in ("교재 원고", "교재 4권")):
            matched = "교육과정_교재" in name or ("교재" in name and "성과지표" not in name)
        elif "수료명단" in evidence_text:
            matched = "출석부" in name or "수료" in name
        elif "교육 결과보고서" in evidence_text:
            matched = "결과보고서" in name and any(token in name for token in ("교육", "강사 양성", "cpcr"))
        elif "회의록" in evidence_text:
            matched = "회의록" in name
        elif "결과보고서" in evidence_text:
            topic_tokens = [token for token in ("교원", "강사", "교육", "cpcr", "mci", "워크샵") if token in f"{program_text} {indicator_text}"]
            matched = "결과보고서" in name and (not topic_tokens or any(token in name for token in topic_tokens))
        elif "mou" in evidence_text or "loi" in evidence_text:
            matched = "mou" in name or "loi" in name or "협약" in name
        elif "논문" in evidence_text:
            matched = "논문" in name
        elif "발표 사진" in evidence_text:
            matched = "학술" in name and "사진" in name
        if matched:
            matches.append(str(document["id"]))
    return list(dict.fromkeys(matches))


def _achievement_rate(value: str) -> float | None:
    cleaned = str(value or "").strip().replace("%", "").replace(",", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    if "%" in str(value):
        return round(number, 1)
    return round(number * 100, 1)


def _performance_indicators(documents: list[dict]) -> tuple[list[dict], dict | None]:
    """Read reported values used only to enrich the authoritative PDM roster."""
    source, text = select_reported_metrics_source(documents)
    if not source:
        return [], None
    rows: list[dict] = []
    current_program = ""
    for line in text.splitlines():
        if "|" not in line or is_metrics_header(line):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) >= 7:
            program, indicator, target, actual, rate, evidence, note = cells[:7]
            current_program = program or current_program
        elif len(cells) == 6:
            program = current_program
            indicator, target, actual, rate, evidence, note = cells
        elif len(cells) >= 3:
            program = current_program
            indicator, target, actual = cells[:3]
            rate = evidence = note = ""
        else:
            continue
        achievement = _achievement_rate(rate)
        if achievement is None:
            status = "unset" if actual in ("", "-") else "watch"
        elif achievement >= 100:
            status = "ok"
        elif achievement >= 70:
            status = "watch"
        else:
            status = "under"
        rows.append({
            "id": f"annual-{len(rows) + 1}",
            "program": program,
            "indicator": indicator,
            "target": target,
            "actual": actual,
            "achievement_rate": achievement,
            "evidence": evidence,
            "note": note,
            "status": status,
            "evidence_document_ids": _evidence_document_ids(documents, evidence, program, indicator),
        })
    return rows, source


_INDICATOR_ALIASES = (
    ("졸업시험", "자격시험"),
    ("심폐소생술", "cpcr"),
    ("master instructor", "전문 강사"),
    ("masterinstructor", "전문강사"),
    ("전공 관련 분야", "취업"),
    ("전공관련분야", "취업"),
)
_INDICATOR_STOPWORDS = {
    "및", "여부", "수", "건", "명", "회", "종", "비율", "증가", "감소", "완료",
    "현지", "지역", "대상", "사업", "프로그램", "교육", "운영", "개발", "실시",
}


def _normalized_indicator_text(value: object) -> str:
    text = str(value or "").casefold()
    for source, target in _INDICATOR_ALIASES:
        text = text.replace(source, target)
    text = re.sub(r"\([^)]*(?:%|명|건|회|종|유/무|5)[^)]*\)", " ", text)
    return re.sub(r"[^0-9a-z가-힣]+", " ", text).strip()


def _indicator_tokens(value: object) -> set[str]:
    return {
        token for token in _normalized_indicator_text(value).split()
        if len(token) >= 2 and token not in _INDICATOR_STOPWORDS
    }


def _indicator_measure_dimension(value: object) -> str:
    compact = re.sub(r"\s+", "", str(value or "").casefold())
    if "횟수" in compact or re.search(r"\(회\)", compact):
        return "event_count"
    if "인원" in compact or "수(명)" in compact or "여부(명)" in compact:
        return "people_count"
    if "%" in compact or "비율" in compact or "합격률" in compact or "취업률" in compact or "가동률" in compact:
        return "ratio"
    if "건수" in compact or "개발건" in compact or re.search(r"\(건\)", compact):
        return "item_count"
    return ""


def _indicator_match_score(pdm_indicator: object, reported_indicator: object) -> float:
    pdm_text = _normalized_indicator_text(pdm_indicator)
    reported_text = _normalized_indicator_text(reported_indicator)
    if not pdm_text or not reported_text:
        return 0.0
    if pdm_text == reported_text:
        return 1.0
    pdm_compact = pdm_text.replace(" ", "")
    reported_compact = reported_text.replace(" ", "")
    containment = 0.0
    if min(len(pdm_compact), len(reported_compact)) >= 5 and (
        pdm_compact in reported_compact or reported_compact in pdm_compact
    ):
        containment = 0.82
    pdm_tokens = _indicator_tokens(pdm_text)
    reported_tokens = _indicator_tokens(reported_text)
    overlap = pdm_tokens & reported_tokens
    dice = (2 * len(overlap) / (len(pdm_tokens) + len(reported_tokens))) if (pdm_tokens or reported_tokens) else 0.0
    sequence = SequenceMatcher(None, pdm_compact, reported_compact).ratio()
    pdm_dimension = _indicator_measure_dimension(pdm_indicator)
    reported_dimension = _indicator_measure_dimension(reported_indicator)
    dimension_mismatch = bool(pdm_dimension and reported_dimension and pdm_dimension != reported_dimension)
    strong_signatures = (
        ("자격시험", "합격률"), ("취업률",), ("cpcr", "강사"),
        ("mci", "훈련"), ("표준", "승인"),
    )
    for signals in strong_signatures:
        if all(signal in pdm_compact and signal in reported_compact for signal in signals):
            if dimension_mismatch:
                return min(0.48, max(containment, dice, sequence))
            return max(0.84, min(1.0, max(containment, dice, sequence) + 0.14))
    distinctive = (("교재",), ("유지보수", "장비"))
    bonus = 0.0
    for signals in distinctive:
        if all(signal in pdm_compact and signal in reported_compact for signal in signals):
            bonus = max(bonus, 0.14)
    score = max(containment, dice, sequence) + bonus
    if dimension_mismatch:
        score -= 0.28
    elif pdm_dimension and pdm_dimension == reported_dimension:
        score += 0.05
    return min(1.0, max(0.0, score))


def _format_reported_metric_value(value: object, pdm_indicator: object) -> str:
    text = str(value or "-").strip() or "-"
    if _indicator_measure_dimension(pdm_indicator) != "ratio":
        return text
    numeric = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)", text.replace(",", ""))
    if not numeric:
        return text
    number = float(numeric.group(1))
    if 0 <= number <= 1:
        percent = number * 100
        return f"{percent:g}%"
    return text


def _monitoring_indicators_from_pdm(
    tiers: list[dict],
    reported_rows: list[dict],
    documents: list[dict],
) -> list[dict]:
    """Use only PDM OVI rows and optionally attach matching reported values."""
    result: list[dict] = []
    available = {index for index in range(len(reported_rows))}
    for tier in tiers:
        tier_id = str(tier.get("id") or "")
        tier_name = str(tier.get("name") or "")
        tier_label = TIER_LABELS.get(tier_id, f"{tier_id.title()}({tier_name})")
        for indicator in tier.get("indicators") or []:
            candidates = sorted(
                (
                    (_indicator_match_score(indicator.get("text"), reported_rows[index].get("indicator")), index)
                    for index in available
                ),
                reverse=True,
            )
            best_score, best_index = candidates[0] if candidates else (0.0, -1)
            reported = reported_rows[best_index] if best_score >= 0.62 else {}
            if reported:
                available.discard(best_index)
            target = _format_reported_metric_value(reported.get("target"), indicator.get("text"))
            actual = _format_reported_metric_value(reported.get("actual"), indicator.get("text"))
            achievement_rate = reported.get("achievement_rate")
            status = str(reported.get("status") or "unset") if reported else "unset"
            mov = str(indicator.get("mov") or "PDM에 검증수단 미기재").strip()
            evidence_document_ids = _evidence_document_ids(
                documents,
                mov,
                str(tier.get("summary") or tier_label),
                str(indicator.get("text") or ""),
            )
            result.append({
                "id": str(indicator.get("id") or f"{tier_id}-{len(result) + 1}"),
                "tier_id": tier_id,
                "tier_name": tier_name,
                "tier_label": tier_label,
                "program": tier_label,
                "pdm_code": str(indicator.get("code") or ""),
                "indicator": str(indicator.get("text") or ""),
                "target": target,
                "actual": actual,
                "achievement_rate": achievement_rate,
                "evidence": mov,
                "note": str(reported.get("note") or ""),
                "status": status,
                "evidence_document_ids": evidence_document_ids,
                "reported_indicator": str(reported.get("indicator") or ""),
                "reported_match_confidence": round(best_score, 3) if reported else None,
            })
    return result


def _fallback_performance_risk(indicator: dict) -> dict:
    status = indicator.get("status") or "unset"
    target = str(indicator.get("target") or "미설정")
    actual = str(indicator.get("actual") or "미확인")
    rate = indicator.get("achievement_rate")
    rate_text = f"{rate}%" if rate is not None else "산정 불가"
    evidence = str(indicator.get("evidence") or "산출근거 미기재")
    note = str(indicator.get("note") or "").strip()
    has_target = target not in {"", "-", "미설정", "미확인"}
    missing_mov = evidence in {"", "산출근거 미기재", "PDM에 검증수단 미기재"}
    root_causes = []
    if note:
        root_causes.append(f"원자료 비고에서 확인된 사항: {note}")
    if not indicator.get("evidence_document_ids"):
        if missing_mov:
            root_causes.append("PDM에 객관적 검증수단이 정의되지 않아 실적을 입증할 문서 기준을 확정할 수 없습니다.")
        else:
            root_causes.append(f"'{evidence}'에 해당하는 연결 문서가 없어 실적 검증이 제한됩니다.")
    if not root_causes:
        root_causes.append("현재 자료만으로 미달 원인을 확정할 수 없어 프로그램 책임자 확인이 필요합니다.")

    if status == "unset":
        title = f"{indicator.get('indicator') or '성과지표'} 실적 미확인"
        target_analysis = (
            f"목표 {target}에 대한 최신 실적이 확인되지 않아"
            if has_target else "PDM 목표값과 최신 실적이 확인되지 않아"
        )
        evidence_analysis = (
            "PDM에 객관적 검증수단도 기재되지 않았습니다."
            if missing_mov else f"현재 산출근거는 '{evidence}'입니다."
        )
        analysis = f"{target_analysis} 달성도를 산정할 수 없습니다. {evidence_analysis} 목표값·측정값·측정일·산식 확인 전에는 성과 달성 여부를 판단할 수 없습니다."
        forecast = "실적과 측정기준을 확정하지 않으면 종료평가에서 효과성 판단의 근거 부족으로 이어질 가능성이 높습니다."
        target_action = (
            f"성과관리 담당자는 지표 책임부서와 협의해 목표 {target}의 최신 측정값, 측정일, 분모·분자 또는 산식을 7일 이내 확정합니다."
            if has_target
            else "성과관리 담당자는 지표 책임부서와 협의해 목표값, 최신 측정값, 측정일, 분모·분자 또는 산식을 7일 이내 확정합니다."
        )
        evidence_action = (
            "PDM 지표 정의서에 객관적 검증수단, 작성기관, 작성주기와 책임부서를 명시하고 승인본을 연결합니다."
            if missing_mov
            else f"'{evidence}' 원본을 확보하고 작성기관·작성일·대상기간을 확인한 뒤 지표 실적과 연결합니다."
        )
        recommendations = [
            target_action,
            evidence_action,
            "값을 확정할 수 없으면 미확인 사유, 자료 확보 책임자, 다음 확인일을 성과관리대장에 기록합니다.",
        ]
        evidence_needed = [
            "승인된 PDM 지표 정의서" if missing_mov else f"{evidence} 원본",
            "목표값·최신 측정값과 측정일", "지표 산식 또는 분모·분자 근거",
        ]
        priority = "high"
    else:
        title = f"{indicator.get('indicator') or '성과지표'} 목표 달성 위험"
        analysis = f"목표 {target} 대비 실적 {actual}, 달성도 {rate_text}로 확인됩니다. 현재 수준이 유지되면 목표 달성 또는 종료평가 시점의 충분한 성과 입증이 어려울 수 있으며, '{evidence}'의 검증 가능성도 함께 점검해야 합니다."
        forecast = "개선조치와 추가 측정 없이 현재 추세가 이어지면 목표 미달 또는 증빙 불충분 상태로 종료평가에 반영될 가능성이 있습니다."
        recommendations = [
            f"프로그램 책임자는 목표 {target} 대비 실적 {actual}의 차이를 대상·지역·기간별로 분해하고 원인별 보완조치와 책임자를 7일 이내 지정합니다.",
            "다음 측정일까지의 월별 또는 분기별 회복 목표를 설정하고 실제 실적을 같은 산식으로 추적합니다.",
            f"'{evidence}' 원본과 실적 산출표를 연결해 수치, 대상기간, 작성기관이 서로 일치하는지 교차검증합니다.",
        ]
        evidence_needed = [f"{evidence} 원본", "목표 대비 실적 차이 분석표", "개선조치 담당자·기한·후속 측정계획"]
        priority = "high" if status == "under" else "medium"
    return {
        "risk_title": title,
        "risk_analysis": analysis,
        "root_causes": root_causes,
        "forecast": forecast,
        "recommendations": recommendations,
        "evidence_needed": evidence_needed,
        "priority": priority,
        "analysis_source": "rules",
    }


def _attach_performance_risk_analysis(performance: list[dict], analyze_risks: bool) -> dict:
    risks = [item for item in performance if item.get("status") != "ok"]
    for item in risks:
        item["risk_analysis"] = _fallback_performance_risk(item)
    metadata = {
        "status": "not_requested" if not analyze_risks else "fallback",
        "provider": "rules",
        "model": None,
        "analyzed_count": len(risks),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not analyze_risks or not risks:
        return metadata
    try:
        response = analyze_performance_risks(performance)
        by_id = {item["id"]: item for item in response.get("items", [])}
        for item in risks:
            ai_result = by_id.get(item["id"])
            if ai_result:
                usable_result = {
                    key: value for key, value in ai_result.items()
                    if value not in (None, "", [])
                }
                item["risk_analysis"] = {**item["risk_analysis"], **usable_result}
        metadata.update({
            "status": "completed",
            "provider": "openrouter",
            "model": response.get("model"),
            "analyzed_count": len(by_id),
        })
    except (MissingApiKey, AnalysisError) as exc:
        metadata["fallback_reason"] = str(exc)[:500]
    return metadata


def refresh_pdm_model(*, analyze_risks: bool = False) -> uuid.UUID:
    # Upload workers and manual refreshes must not overwrite each other's snapshots.
    with connection() as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(current_project_id()),))
        return _refresh_pdm_model(analyze_risks=analyze_risks)


def _refresh_pdm_model(*, analyze_risks: bool = False) -> uuid.UUID:
    documents = _documents()
    if not documents:
        raise RuntimeError("PDM 모델을 만들 완료 문서가 없습니다.")
    source, slots = _select_pdm_source(documents)
    model = _model_from_slots(slots)
    reported_performance, performance_source = _performance_indicators(documents)
    performance = _monitoring_indicators_from_pdm(model["tiers"], reported_performance, documents)
    model["performance_indicators"] = performance
    model["performance_source_document_id"] = str(performance_source["id"]) if performance_source else None
    model["performance_source_file_name"] = performance_source["original_name"] if performance_source else None
    model["monitoring"] = {
        "roster_source": "latest_pdm_ovi",
        "indicator_count": len(performance),
        "reported_metric_count": len(reported_performance),
        "matched_reported_metric_count": sum(
            1 for item in performance if item.get("reported_match_confidence") is not None
        ),
    }

    assignments: list[tuple] = []
    for tier in model["tiers"]:
        for indicator in tier["indicators"]:
            for document in documents:
                matched, confidence, rationale = _matches_pdm_requirement(document, indicator["mov"], indicator["text"])
                if matched:
                    assignments.append((document["id"], indicator["id"], tier["id"], indicator["mov"], confidence, rationale))

    model["monitoring"]["evidence_analysis"] = enrich_from_evidence(performance, documents, assignments)
    model["risk_analysis"] = _attach_performance_risk_analysis(performance, analyze_risks)

    model_id = uuid.uuid4()
    with connection() as conn, conn.transaction():
        conn.execute("DELETE FROM pdm_document_assignments")
        conn.execute("DELETE FROM pdm_models")
        conn.execute(
            """INSERT INTO pdm_models(id,source_document_id,source_file_name,pdm_version,model)
               VALUES (%s,%s,%s,'source-table-v1',%s)""",
            (model_id, source["id"], source["original_name"], Jsonb(model)),
        )
        for assignment in assignments:
            conn.execute(
                """INSERT INTO pdm_document_assignments
                   (document_id,indicator_id,tier,requirement_title,confidence,rationale)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(document_id,indicator_id) DO UPDATE SET
                     tier=excluded.tier,requirement_title=excluded.requirement_title,
                     confidence=excluded.confidence,rationale=excluded.rationale""",
                assignment,
            )
    return model_id
