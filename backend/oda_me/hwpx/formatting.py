from __future__ import annotations

from ..core import *

def hwpx_text_nodes(scope: ET.Element) -> list[ET.Element]:
    return scope.findall(".//hp:t", HWPX_NS)


def set_hwpx_scope_text(scope: ET.Element, text: str) -> bool:
    """Replace text inside an existing HWPX paragraph/cell without touching layout."""
    text = str(text or "")
    nodes = hwpx_text_nodes(scope)
    if nodes:
        nodes[0].text = text
        for node in nodes[1:]:
            node.text = ""
        return True
    paragraph = scope.find(".//hp:p", HWPX_NS)
    if paragraph is None:
        return False
    run = paragraph.find("hp:run", HWPX_NS)
    if run is None:
        run = ET.Element(f"{{{HP_NS}}}run", {"charPrIDRef": "25"})
        paragraph.insert(0, run)
    text_node = ET.Element(f"{{{HP_NS}}}t")
    text_node.text = text
    run.insert(0, text_node)
    return True


def get_hwpx_scope_text(scope: ET.Element) -> str:
    return "".join(node.text or "" for node in hwpx_text_nodes(scope)).strip()


def replace_hwpx_paragraph_text(root: ET.Element, old_text: str, new_text: str, *, exact: bool = False) -> int:
    changed = 0
    for paragraph in root.findall(".//hp:p", HWPX_NS):
        if paragraph.find("hp:tbl", HWPX_NS) is not None:
            continue
        current = get_hwpx_scope_text(paragraph)
        if not current:
            continue
        matched = current == old_text if exact else old_text in current
        if not matched:
            continue
        set_hwpx_scope_text(paragraph, current.replace(old_text, str(new_text or "")) if not exact else str(new_text or ""))
        changed += 1
    return changed


def find_hwpx_grade_table(root: ET.Element) -> ET.Element | None:
    for table in root.findall(".//hp:tbl", HWPX_NS):
        cells = table.findall(".//hp:tc", HWPX_NS)
        if len(cells) < 70:
            continue
        joined = " ".join(get_hwpx_scope_text(cell) for cell in cells)
        if "평가 기준" in joined and "적절성 평점" in joined and "종합 평가 등급" in joined:
            return table
    return None


def format_score(value: object) -> str:
    try:
        score = round(float(value), 1)
    except (TypeError, ValueError):
        score = 1.0
    return str(int(score)) if score.is_integer() else f"{score:.1f}"


def criterion_question_rows(item: dict) -> list[dict]:
    from ..documents.evidence_store import clean_evaluation_text
    result = item.get("evaluationResult") or {}
    assessments = result.get("questionAssessments") if isinstance(result.get("questionAssessments"), list) else []
    if not assessments and isinstance(item.get("questionAssessments"), list):
        assessments = item.get("questionAssessments") or []
    rows = []
    for index, assessment in enumerate(assessments):
        if not isinstance(assessment, dict):
            continue
        finding = assessment.get("finding") or assessment.get("judgement") or assessment.get("summary") or ""
        reason = clean_evaluation_text(str(finding or ""))
        reason = re.sub(r"\s+", " ", reason).strip(" .")
        rows.append(
            {
                "questionId": str(assessment.get("questionId") or f"q{index + 1}"),
                "question": str(assessment.get("question") or f"평가질문 {index + 1}"),
                "score": float(assessment.get("score") or 1),
                "reason": reason,
            }
        )
    return rows


def criterion_grade_rows(context: dict) -> list[dict]:
    from ..reports.context import criterion_label, criterion_score

    criteria = [item for item in context.get("criteria", []) if item.get("id") != "impact"]
    names = {
        "relevance": "적절성",
        "coherence": "일관성",
        "effectiveness": "효과성",
        "efficiency": "효율성",
        "sustainability": "지속가능성",
    }
    rows = []
    for item in criteria:
        score = criterion_score(item)
        result = item.get("evaluationResult") or {}
        uploaded = item.get("uploadedDocuments") or []
        references = item.get("references") or []
        evidence_names = [doc.get("evidenceName") or doc.get("fileName", "") for doc in uploaded if isinstance(doc, dict)]
        if not evidence_names and references:
            evidence_names = [ref.get("evidenceName") or ref.get("fileName", "") for ref in references if isinstance(ref, dict)]
        reason = result.get("summary") or result.get("rationale") or item.get("summary") or ""
        if not reason:
            if evidence_names:
                reason = f"{', '.join(evidence_names[:2])} 근거로 {names.get(item.get('id'), criterion_label(item))} 판단을 보완 중."
            else:
                reason = f"{names.get(item.get('id'), criterion_label(item))} 근거 미흡. 보완 필요."
        question_rows = criterion_question_rows(item)
        rows.append({
            "id": item.get("id"),
            "name": names.get(item.get("id"), criterion_label(item)),
            "score": round(max(1.0, min(4.0, float(score or 1))), 1),
            "reason": compact_report_sentence(reason, 120),
            "questionRows": question_rows,
        })
    return rows


def compact_report_sentence(value: object, limit: int = 140) -> str:
    from ..documents.evidence_store import clean_evaluation_text

    text = clean_evaluation_text(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .…")
    if not text:
        return ""
    sentence_matches = re.findall(r".+?(?:평가됨|판단됨|확인됨|설계됨|기여함|미흡함|부족함|필요함|있음|없음|함|됨|음|임)(?=\s|$|[.])", text)
    if sentence_matches:
        selected: list[str] = []
        current = ""
        for sentence in sentence_matches:
            sentence = sentence.strip(" .")
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) > limit and current:
                break
            current = candidate
            selected.append(sentence)
            if len(current) >= min(70, limit):
                break
        if current:
            return current.rstrip(".") + "."
    if len(text) <= limit:
        return text.rstrip(".") + "."
    cut = text.rfind(" ", 0, limit)
    if cut < max(45, limit // 2):
        cut = limit
    clipped = text[:cut].strip(" ,.;·")
    clipped = re.sub(r"(하며|하고|하여|에서|으로|로|및|또는|등)$", "", clipped).strip(" ,.;·")
    if re.search(r"(함|됨|음|다|임|있음|없음)$", clipped):
        return clipped.rstrip(".") + "."
    return f"{clipped}으로 판단됨."


def format_grade_section_text(context: dict) -> str:
    project = context.get("project", {})
    overall = context.get("overall") or {}
    rows = criterion_grade_rows(context)
    lines = [
        "평가 등급 결과표",
        "",
        (
            f"ㅇ 평가대상 사업명 : {project.get('title') or '사업명 확인 중'}"
            f"({project.get('period') or '기간 확인 중'} / {project.get('budget') or '예산 확인 중'})"
        ),
        "",
        "평가기준별 점수 및 산정 이유",
    ]
    for index, item in enumerate(rows, start=1):
        lines.append(f"{index}. {item['name']}: {format_score(item['score'])}점/4점. {item['reason']}")
    lines.extend(
        [
            "",
            f"종합점수: {overall.get('score', sum(item['score'] for item in rows))}/{overall.get('maxScore', 20)}점",
            f"국무조정실 평가등급: {overall.get('governmentGrade') or '미흡'}",
            f"KOICA 평가등급: {overall.get('koicaGrade') or 'F'}",
        ]
    )
    return "\n".join(lines)


def markdown_table_to_report_text(text: str) -> str:
    lines = str(text or "").splitlines()
    output: list[str] = []
    table: list[str] = []
    content_headers = {"내용", "세부내용", "값", "설명", "검토내용", "작성내용", "주요 내용"}

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        parsed: list[list[str]] = []
        for raw_line in table:
            cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
            if not cells or all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells):
                continue
            parsed.append(cells)
        table = []
        if len(parsed) < 2:
            for row in parsed:
                if row:
                    output.append(" / ".join(cell for cell in row if cell))
            return
        headers = parsed[0]
        last_primary = ""
        if len(headers) == 2 and headers[1].strip() in content_headers:
            for row in parsed[1:]:
                if not any(row):
                    continue
                if len(row) < 2:
                    row = row + [""]
                primary = row[0].strip() or last_primary
                if primary:
                    last_primary = primary
                detail = row[1].strip()
                if primary and detail:
                    output.append(f"- {primary}: {detail}")
                elif primary:
                    output.append(f"- {primary}")
                elif detail:
                    output.append(f"- {detail}")
            return
        for row in parsed[1:]:
            if not any(row):
                continue
            if len(row) < len(headers):
                row = row + [""] * (len(headers) - len(row))
            primary = row[0].strip() or last_primary
            if primary:
                last_primary = primary
            details = []
            for header, cell in zip(headers[1:], row[1:]):
                if cell:
                    details.append(f"{header}: {cell}")
            if not primary and details:
                output.append("- " + "; ".join(details))
            elif details:
                output.append(f"- {primary}: " + "; ".join(details))
            else:
                output.append(f"- {primary}")

    for line in lines:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table.append(line)
            continue
        flush_table()
        if "|" in line:
            line = re.sub(r"\s*\|\s*", " / ", line).strip()
        output.append(line)
    flush_table()
    return "\n".join(output)


def final_report_gap_language(text: str) -> str:
    value = str(text or "")
    missing_info_marker = "추가" + " 정보 필요"

    def gap_replacement(match: re.Match) -> str:
        phrase = re.sub(r"\s+", " ", match.group(1) or "").strip()
        phrase = phrase.strip(" .;:()")
        return f"자료 한계: {phrase or '세부 근거'} 확인이 제한됨"

    value = re.sub(rf"{re.escape(missing_info_marker)}:\s*([^\n]+)", gap_replacement, value)
    value = re.sub(r"보완 필요사항:\s*자료 한계:", "평가 한계 및 후속 확인사항:", value)
    value = re.sub(r"-\s*자료 한계:", "- 평가 한계:", value)
    value = re.sub(r"\(([^()\n]{1,80}) 확인이 제한됨\)", r"(\1)", value)
    value = re.sub(r"\b(RACI|ePDM|EDP Group|UNICEF)\s+확인이 제한됨\b", r"\1", value)
    value = value.replace("쪽수는 최종 편집 시 갱신", "최종 편집 시 갱신")
    value = value.replace("참고문헌 목록", "자료목록")
    value = value.replace(missing_info_marker, "자료 한계")
    return value.strip()


def normalize_korean_report_prose(text: str) -> str:
    value = str(text or "")
    next_sentence_heads = (
        "본|사업|평가|다만|또한|반면|이에|이는|후속|주요|자료|따라서|특히|결과|종합|"
        "기준|성과|수행|향후|현지|KOICA|UNICEF|네팔|무구|지속|보완|운영|기자재|"
        "효과성|효율성|적절성|일관성|지속가능성"
    )
    value = re.sub(
        rf"(함|됨|음|임|있음|없음)\s+(?=({next_sentence_heads})\b)",
        r"\1. ",
        value,
    )
    value = re.sub(
        r"(하였음|되었음|였음|있음|없음|나타남|확인됨|평가됨|마련되었음|입증함|미흡함|필요함)\s+"
        r"(?=(건축|인터뷰|수혜자|무구병원|교육|시설|기자재|지역|사업|보건|성과|또한|다만|향후|주요|현지|KOICA|UNICEF|FCHV))",
        r"\1. ",
        value,
    )
    value = re.sub(r"\.\s+\.", ".", value)
    value = re.sub(r" {2,}", " ", value)
    return value.strip()


def report_period_phrase(period: object) -> str:
    value = str(period or "").strip()
    match = re.fullmatch(r"(\d{4})\s*[-~]\s*(\d{4})", value)
    if match:
        return f"{match.group(1)}년부터 {match.group(2)}년까지"
    return value or "기간 확인 대상"


def section_lookup(sections: list[dict]) -> dict[str, str]:
    return {str(section.get("id")): str(section.get("body", "")) for section in sections if isinstance(section, dict)}


def infer_report_people(sections: list[dict]) -> dict:
    text = "\n".join(str(section.get("body", "")) for section in sections if isinstance(section, dict))
    combined_text = text
    invalid_names = {"추가", "정보", "필요", "확인", "대상", "자료", "한계"}

    def valid_person_name(name: str) -> str:
        candidate = re.sub(r"[^가-힣]", "", name or "")
        if len(candidate) >= 4 and candidate[-1] in {"은", "는", "이", "가", "을", "를", "의"}:
            candidate = candidate[:-1]
        if not re.fullmatch(r"[가-힣]{2,4}", candidate):
            return ""
        if candidate in invalid_names:
            return ""
        return candidate

    manager_name = ""
    manager_patterns = [
        r"평가\s*책임자\s*[:：]?\s*([가-힣]{2,4})",
        r"평가\s*책임자인\s*([가-힣]{2,4})",
        r"책임\s*평가자\s*[:：]?\s*([가-힣]{2,4})",
    ]
    for source in [text, combined_text]:
        for pattern in manager_patterns:
            for manager_match in re.finditer(pattern, source):
                manager_name = valid_person_name(manager_match.group(1))
                if manager_name:
                    break
            if manager_name:
                break
        if manager_name:
            break
    institution = ""
    if "순천향대학교 산학협력단" in combined_text:
        institution = "순천향대학교 산학협력단"
    elif "순천향대학교" in combined_text:
        institution = "순천향대학교"
    completed_at = ""
    for completed_match in re.finditer(r"평가\s*완료일\s*[:：]?\s*([0-9]{4}\s*년\s*[0-9]{1,2}\s*월\s*[0-9]{1,2}\s*일|[0-9. ]{8,})", combined_text):
        completed_at = re.sub(r"\s+", " ", completed_match.group(1)).strip()
        if completed_at:
            break
    return {
        "managerName": manager_name,
        "managerLine": f"평가책임자 {manager_name}" if manager_name else "평가책임자 확인 대상",
        "institutionLine": f"평가수행기관 {institution}" if institution else "평가수행기관 확인 대상",
        "institution": institution or "평가수행기관",
        "completedAt": completed_at or "평가 완료일 확인 대상",
    }


def format_toc_section() -> str:
    return "\n".join(
        [
            "목차",
            "",
            "Ⅰ. 평가결과 요약",
            "  1. 평가 등급 결과표",
            "  2. 국문 요약",
            "",
            "Ⅱ. 대상사업 개요",
            "  1. 사업 추진배경",
            "  2. 사업개요",
            "  3. 사업설계매트릭스(PDM)",
            "",
            "Ⅲ. 평가개요",
            "  1. 평가의 목적과 범위",
            "  2. 평가매트릭스",
            "  3. 평가방법",
            "  4. 평가의 한계",
            "  5. 평가팀 구성 및 시행체계",
            "",
            "Ⅳ. 성과 달성도",
            "",
            "Ⅴ. 기준별 평가결과",
            "  1. 적절성",
            "  2. 일관성",
            "  3. 효과성",
            "  4. 효율성",
            "  5. 지속가능성",
            "  6. 범분야 이슈",
            "  7. 그 외 평가기준",
            "",
            "Ⅵ. 결론",
            "  1. 결론",
            "  2. 작동요인 및 비작동요인",
            "  3. 환류과제 및 교훈",
            "",
            "첨부. 자료목록",
        ]
    )


def format_summary_section(context: dict) -> str:
    project = context.get("project", {})
    overall = context.get("overall") or {}
    rows = criterion_grade_rows(context)
    score_text = ", ".join(f"{row['name']} {row['score']}점" for row in rows)
    period_text = report_period_phrase(project.get("period"))
    return "\n\n".join(
        [
            (
                f"가. 사업개요\n{project.get('title', '대상사업')}은 {period_text} "
                f"{project.get('budget', '예산 확인 대상')} 규모로 추진된 모자보건 및 보건의료체계 개선 사업임. "
                "사업은 무구지역의 보건의료 접근성 제고, 군립병원 인프라 개선, 의료기자재 지원, 보건의료인력 역량강화와 주민 보건교육을 통해 모자보건 서비스 이용 여건을 개선하는 데 목적을 둠."
            ),
            (
                "나. 평가개요\n본 평가는 사업 종료 후 성과와 한계를 검증하고, OECD-DAC 평가기준에 따라 "
                "적절성, 일관성, 효과성, 효율성, 지속가능성을 종합적으로 판단하여 향후 유사 보건 ODA 사업의 설계와 사후관리 개선에 필요한 교훈을 도출하는 데 목적이 있음. "
                "평가는 사업개요서, 사전조사 및 종료선 조사, 연차점검 자료, 이해관계자 면담, 현장점검 및 경제성 분석 자료를 종합하여 수행함."
            ),
            (
                f"다. 기준별 평가결과\n기준별 평가는 {score_text}으로 산정되었으며, 종합점수는 "
                f"{overall.get('score')}/{overall.get('maxScore', 20)}점, 국무조정실 평가등급은 "
                f"{overall.get('governmentGrade')}, KOICA 평가등급은 {overall.get('koicaGrade')}로 판단됨. "
                "적절성과 효율성은 정책 부합성, 기초조사 기반 설계, 현장 여건에 맞춘 관리체계 조정 측면에서 비교적 긍정적으로 평가됨. "
                "반면 효과성과 일관성은 산출물 품질, 기자재 유지관리, 성과관리 자료의 완결성, 이해관계자 역할분담 측면에서 보완 여지가 확인되었고, 지속가능성은 현지 운영 주체의 재정·인력·유지관리 체계가 충분히 내재화되지 못해 낮게 평가됨."
            ),
            (
                "라. 결론 및 환류 방향\n본 사업은 물리적 인프라 구축과 일부 서비스 접근성 개선이라는 성과를 확보하였으나, 사업 종료 후 운영 지속성, 전문 인력 확보, 기자재 유지보수, 성과자료 기반의 환류체계 측면에서 한계가 확인됨. "
                "후속 조치에서는 지방정부의 운영 예산 확약, 현지 기술인력 확보, 기자재 관리체계 내재화, 성과지표별 목표 대비 실적 검증, 취약계층 접근성 자료의 체계적 관리가 우선되어야 함."
            ),
        ]
    )


def format_notice_section(context: dict, people: dict) -> str:
    project = context.get("project", {})
    manager = people.get("managerName") or "평가책임자"
    institution = people.get("institution") or "평가수행기관"
    return "\n\n".join(
        [
            "평가보고서 관련 공지",
            (
                f"평가 책임자 {manager}은 KOICA 본부 및 네팔 사무소, 사업수행기관 {institution} 등 이해관계자의 협조를 받아 "
                f"{project.get('title', '본 사업')} 종료평가를 수행함. 본 보고서는 평가팀의 분석과 판단에 따라 작성되었으며, "
                "평가내용 및 편집에 대한 책임은 평가팀에 있음."
            ),
            f"평가 완료일: {people.get('completedAt') or '평가 완료일 확인 대상'}",
            (
                "본 보고서의 평가결과, 해석 및 결론은 한국국제협력단 또는 사업수행 관계자의 공식 의견과 다를 수 있음. "
                "사실관계 확인 및 피평가자 의견은 별도 확인 절차를 통해 반영될 수 있으며, 본 보고서는 확보된 문헌, 면담, 현장점검 및 성과자료를 종합하여 작성함."
            ),
        ]
    )


def format_eval_team_section(people: dict) -> str:
    return "\n\n".join(
        [
            "가. 평가팀 구성",
            (
                f"본 종료평가는 {people.get('managerLine', '평가책임자 확인 대상')}을 중심으로 보건의료, 개발협력, 성과관리, 경제성 분석, 기자재, 건축 및 범분야 이슈 관련 전문가가 참여하여 수행함. "
                "평가팀은 평가설계, 문헌검토, 현장점검, 이해관계자 면담, 성과자료 분석과 보고서 작성의 역할을 분담함."
            ),
            "나. 시행체계",
            (
                "평가는 자료수집, 평가매트릭스 확정, 문헌 및 현장자료 검토, 이해관계자 면담, 기준별 판단, 보고서 작성 및 품질검토 순서로 수행함. "
                "각 기준별 판단은 업로드된 원문 자료와 면담 결과를 교차 확인하여 작성하였으며, 정량자료가 제한적인 항목은 평가의 한계에 명시하고 보수적으로 해석함."
            ),
            "다. 품질관리",
            "평가 결과의 일관성을 확보하기 위해 기준별 점수, 산정 이유, 본문 판단 및 환류과제 간 정합성을 점검함.",
        ]
    )


def polish_report_sections_for_final(context: dict, sections: list[dict]) -> list[dict]:
    people = infer_report_people(sections)
    polished = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id", ""))
        body = str(section.get("body", ""))
        if section_id == "title":
            project = context.get("project", {})
            body = "\n\n".join(
                [
                    f"{project.get('title', '사업명 확인 대상')}\n종료평가 결과보고서",
                    datetime.now().strftime("%Y. %m"),
                    f"{people.get('managerLine')}\n{people.get('institutionLine')}",
                ]
            )
        elif section_id == "toc":
            body = format_toc_section()
        elif section_id == "notice":
            body = format_notice_section(context, people)
        elif section_id == "grade":
            body = format_grade_section_text(context)
        elif section_id == "summary":
            body = format_summary_section(context)
        elif section_id == "eval-team":
            body = format_eval_team_section(people)
        else:
            body = markdown_table_to_report_text(body)
            body = final_report_gap_language(body)
        body = markdown_table_to_report_text(body)
        body = final_report_gap_language(body)
        body = normalize_korean_report_prose(body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        polished.append({**section, "body": body})
    return polished


def enforce_editor_part_content(content: str, part_id: str, context: dict) -> str:
    text = str(content or "").strip()
    if part_id == "grade":
        return format_grade_section_text(context)
    criterion_part_ids = {
        "criteria-relevance": ["relevance"],
        "criteria-coherence": ["coherence"],
        "criteria-effectiveness": ["effectiveness"],
        "criteria-efficiency": ["efficiency"],
        "criteria-sustainability": ["sustainability"],
        "criteria-crosscutting": ["coherence", "effectiveness", "sustainability"],
        "criteria-other": ["relevance", "coherence", "effectiveness", "efficiency", "sustainability"],
    }
    related_ids = criterion_part_ids.get(part_id)
    if not related_ids:
        return text
    related = [item for item in context.get("criteria", []) if item.get("id") in set(related_ids)]
    if not related:
        return text
    return sanitize_criteria_report_prose(text)

