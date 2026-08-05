from __future__ import annotations

from ..core import *
from ..documents.evidence_store import clean_evaluation_text, list_uploaded_documents
from ..hwpx.formatting import markdown_table_to_report_text, normalize_korean_report_prose

def overall_grade(score: float) -> tuple[str, str]:
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


def grade_label(score: float) -> tuple[str, str]:
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


def criterion_score(criterion: dict) -> float:
    evaluation = criterion.get("evaluationResult") or {}
    try:
        return round(max(1.0, min(4.0, float(evaluation.get("score") or criterion.get("currentScore4") or criterion.get("score") or 1))), 1)
    except (TypeError, ValueError):
        return 1.0


def read_document_excerpt(document: dict, limit: int = 1400) -> str:
    text_path = document.get("textPath")
    if not text_path:
        return ""
    try:
        text = Path(text_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return short_text(text, limit)


def extract_hwp_template_text(path: Path, cache_key: str) -> str:
    cache_dir = DATA_DIR / "sample_analysis" / cache_key
    cache_file = cache_dir / "combined.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="replace")
    if not path.exists():
        return ""
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{cache_key}_") as tmp:
        out_dir = Path(tmp) / "text"
        try:
            subprocess.run(
                [RHWP_BIN, "export-text", str(path), "-o", str(out_dir)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=RHWP_TIMEOUT_SECONDS,
            )
        except Exception:
            return ""
        text = "\n\n".join(
            file.read_text(encoding="utf-8", errors="replace")
            for file in sorted(out_dir.glob("*.txt"))
        )
    cache_file.write_text(text, encoding="utf-8")
    return text


def extract_sample_pdf_context(limit: int = 6000) -> str:
    cache_file = DATA_DIR / "sample_analysis" / "sample_reports.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="replace")[:limit]
    if not SAMPLES_DIR.exists():
        return ""
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    chunks = []
    for pdf_path in sorted(SAMPLES_DIR.glob("*.pdf"))[:5]:
        try:
            reader = PdfReader(str(pdf_path))
            pages = []
            for page in reader.pages[:4]:
                pages.append(page.extract_text() or "")
            chunks.append(f"[{pdf_path.name}]\n" + short_text("\n".join(pages), 1600))
        except Exception:
            continue
    text = "\n\n".join(chunks)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(text, encoding="utf-8")
    return text[:limit]


def extract_sample_hwp_context(limit: int = 10000) -> str:
    cache_file = DATA_DIR / "sample_analysis" / "sample_hwp_reports.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="replace")[:limit]
    if not SAMPLES_DIR.exists():
        return ""
    chunks = []
    for hwp_path in sorted(SAMPLES_DIR.glob("*.hwp")):
        if hwp_path.name == SAMPLE_REPORT_HWP_PATH.name or "FAQ" in hwp_path.name or "5-6" in hwp_path.name:
            continue
        text = extract_hwp_template_text(hwp_path, f"sample_hwp_{hwp_path.stem}")
        if text:
            chunks.append(f"[{hwp_path.name}]\n{short_text(text, 7000)}")
    text = "\n\n".join(chunks)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(text, encoding="utf-8")
    return text[:limit]


def build_report_context(project: dict, criteria: list[dict], references: list[dict], overall: dict) -> dict:
    faq_text = extract_hwp_template_text(SAMPLE_FAQ_HWP_PATH, "faq")
    report_template_text = extract_hwp_template_text(SAMPLE_REPORT_HWP_PATH, "report_template")
    sample_reports = "\n\n".join([extract_sample_pdf_context(), extract_sample_hwp_context()])
    criterion_items = []
    for criterion in criteria:
        criterion_id = criterion.get("id", "")
        evaluation = criterion.get("evaluationResult") or {}
        criterion_refs = references_for_criterion(criterion_id, references)
        question_assessments = [
            {
                "questionId": item.get("questionId", ""),
                "question": short_text(item.get("question"), 300),
                "score": item.get("score", 1),
                "finding": short_text(item.get("finding"), 500),
                "evidenceUsed": item.get("evidenceUsed", []),
                "evidenceGaps": item.get("evidenceGaps", []),
            }
            for item in (evaluation.get("questionAssessments") or [])
            if isinstance(item, dict)
        ]
        criterion_items.append(
            {
                "id": criterion_id,
                "name": criterion_label(criterion),
                "englishName": CRITERION_ENGLISH.get(criterion_id, ""),
                "score": criterion_score(criterion),
                "summary": short_text(evaluation.get("summary"), 1200),
                "questionAssessments": question_assessments,
                "evaluationResult": {
                    "score": criterion_score(criterion),
                    "summary": short_text(evaluation.get("summary"), 1200),
                    "questionAssessments": question_assessments,
                },
                "sections": [
                    {
                        "title": section.get("title", ""),
                        "body": short_text(section.get("body"), 1000),
                    }
                    for section in (evaluation.get("sections") or [])[:5]
                ],
                "references": [
                    {
                        "number": document.get("referenceNumber"),
                        "fileName": document.get("fileName", ""),
                        "evidenceName": document.get("evidenceName", ""),
                        "excerpt": read_document_excerpt(document, 1000),
                    }
                    for document in criterion_refs[:6]
                ],
            }
        )
    return {
        "project": project,
        "overall": overall,
        "criteria": criterion_items,
        "references": references,
        "guidance": {
            "reportTemplate": short_text(report_template_text, 9000),
            "faq": short_text(faq_text, 9000),
            "sampleReports": short_text(sample_reports, 14000),
            "ragPolicy": (
                "FAQ, template, and sample reports are retrieval references only. "
                "Use them to infer required sections, evaluator reasoning, evidence density, and formal Korean report tone. "
                "Do not copy, lightly paraphrase, or preserve sample report sentences; write new current-project analysis."
            ),
        },
    }


def sample_reference_for_editor_part(part: dict, limit: int = 4500) -> str:
    section_reference = sample_section_reference_for_editor_part(str(part.get("id") or ""), limit)
    if section_reference:
        return section_reference
    if part.get("id") == "cover":
        return ""
    sample_text = extract_sample_hwp_context(limit=18000)
    if not sample_text:
        return ""
    headings = [str(item) for item in part.get("sampleHeadings", []) if str(item).strip()]
    chunks = []
    for heading in headings:
        index = sample_text.find(heading)
        if index < 0:
            continue
        start = max(0, index - 500)
        end = min(len(sample_text), index + 2800)
        snippet = sample_text[start:end].strip()
        if snippet and snippet not in chunks:
            chunks.append(snippet)
        if sum(len(chunk) for chunk in chunks) >= limit:
            break
    if not chunks:
        return short_text(sample_text, limit)
    return short_text("\n\n--- sample excerpt ---\n\n".join(chunks), limit)


def read_sample_report_sections() -> dict:
    if not SAMPLE_REPORT_SECTIONS_PATH.exists():
        return {}
    try:
        return json.loads(SAMPLE_REPORT_SECTIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def sample_section_reference_for_editor_part(part_id: str, limit: int = 4500) -> str:
    payload = read_sample_report_sections()
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    section = next((item for item in sections if str(item.get("partId")) == part_id), None)
    if not section or not str(section.get("exampleText") or "").strip():
        return ""
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    header = (
        f"잘 작성된 실제 보고서 예시({source.get('fileName', 'sample report')}) - {section.get('title', part_id)}\n"
        "주의: 이 예시는 구조, 논리 전개, 문체, 근거 밀도를 참고하기 위한 RAG 자료이다. 문장을 복사하거나 가깝게 패러프레이즈하지 말고 현재 사업 자료로 새로 작성한다.\n"
    )
    return short_text(header + "\n" + str(section.get("exampleText") or ""), limit)


CRITERIA_REPORT_PART_IDS = {
    "criteria-relevance",
    "criteria-coherence",
    "criteria-effectiveness",
    "criteria-efficiency",
    "criteria-sustainability",
    "criteria-crosscutting",
    "criteria-other",
}


CRITERIA_OUTPUT_STYLE_CONTRACT = (
    "Write this criterion as final KOICA evaluation report prose, matching the provided good sample's structure and tone. "
    "Use analytic subsection headings and completed paragraphs, usually with Korean report bullets such as 'ㅇ (...)'. "
    "Do not include the parent section title or markdown headings: no 'Ⅴ. 기준별 평가결과', no 'V. 기준별 평가결과', "
    "no standalone criterion title such as '3. 효과성', and no lines starting with '#', '##', or '###'. "
    "Use a consistent rhythm: subsection heading on its own line, then body bullets directly below it; use at most one blank line before the next subsection heading. "
    "Do not write working memo labels or score memo lines: no '평가점수:', '관련 기준 점수:', '판단:', '근거:', '한계:', "
    "'점수 산정 이유:', '보완 필요사항:', or '활용근거:'. "
    "Do not repeat evaluation questions as question sentences. Convert them into report subsection headings and analysis. "
    "Criterion scores are handled by the grade table; reflect the judgement naturally in prose only when useful."
)


def editor_part_output_contract(part_id: str) -> str:
    contracts = {
        "cover": (
            "OUTPUT CONTRACT FOR (1) COVER:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments, no extra keys outside the schema.\n"
            "Required JSON shape:\n"
            "{\n"
            "  \"schema\": \"section1_cover_slots_v1\",\n"
            "  \"slots\": {\n"
            "    \"project_title\": \"Korean project title only, one line, max 80 chars\",\n"
            "    \"report_title\": \"종료평가 결과보고서\",\n"
            "    \"report_date\": \"YYYY. MM\",\n"
            "    \"evaluation_manager\": \"평가책임자 ... or 평가책임자 확인 필요\",\n"
            "    \"evaluation_institution\": \"평가수행기관 ... or 평가수행기관 확인 필요\"\n"
            "  }\n"
            "}\n"
            "Rules: report_title must be exactly 종료평가 결과보고서. "
            "Do not include table of contents, notice, grade table, body, annex, XML, markdown, or explanations. "
            "Each slot value must be a single string without line breaks."
        ),
        "toc": (
            "OUTPUT CONTRACT FOR (2) TOC:\n"
            "Section 2 is deterministic. Do not ask the LLM to estimate page numbers.\n"
            "Return only one JSON object if a manual value is explicitly supplied. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section2_toc_slots_v1\",\"slots\":{\"remove_page_notice\":\"\",\"page_numbers\":{}}}.\n"
            "The actual page_numbers are filled by algorithm from data/reports/toc_page_map.json or data/reports/toc_source.pdf after PDF conversion. Do not invent body text or page numbers."
        ),
        "notice": (
            "OUTPUT CONTRACT FOR (3) NOTICE:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section3_notice_slots_v1\",\"slots\":{\"responsible_evaluator_name_first\":\"...\",\"country_name\":\"...\",\"evaluated_project_name\":\"...\"}}.\n"
            "Only provide values for template placeholders. Use '확인 필요' for unknown names, dates, affiliations, grades, and review members."
        ),
        "grade": (
            "OUTPUT CONTRACT FOR (4) GRADE TABLE:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section4_grade_slots_v1\",\"slots\":{\"project_label\":\"...\",\"relevance_total_score\":\"3점\",\"overall_score\":\"14/20점\",\"koica_grade\":\"C\"}}.\n"
            "Use available criteria scores and overall grades exactly. Reasons must be short one-line strings. "
            "Every total_reason must use the label '{criterion} 종합 평가: ...', never '{criterion} 종합 평균: ...'. "
            "Efficiency must include both question rows and the efficiency_total_score/efficiency_total_reason row."
        ),
        "summary-ko": (
            "OUTPUT CONTRACT FOR (5) SUMMARY:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section5_summary_slots_v1\",\"slots\":{...}}.\n"
            "The slots object must include exactly these keys: "
            + ", ".join(SECTION5_SUMMARY_SLOT_KEYS)
            + ". Each value replaces one existing paragraph in the placeholder. "
            "Preserve the placeholder outline labels and bullet prefixes inside the values, such as '가. 사업명 :', '- (평가목적)', and 'ㅇ 결론'. "
            "Do not return one combined summary body."
        ),
        "project-background": (
            "OUTPUT CONTRACT FOR (6) PROJECT BACKGROUND:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section6_project_background_slots_v1\",\"slots\":{...}}.\n"
            "The slots object must include exactly these keys: "
            + ", ".join(SECTION6_PROJECT_BACKGROUND_SLOT_KEYS)
            + ". Each value replaces one existing bullet paragraph in the placeholder. "
            "Every value must start with the existing bullet prefix 'ㅇ '. "
            "Do not return one combined background body."
        ),
        "project-overview": (
            "OUTPUT CONTRACT FOR (7) PROJECT OVERVIEW:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section7_project_overview_slots_v1\",\"slots\":{...}}.\n"
            "The slots object must include exactly these keys: "
            + ", ".join(SECTION7_PROJECT_OVERVIEW_SLOT_KEYS)
            + ". Each value replaces one existing cell in the original project overview table. "
            "Do not return a markdown table or one combined body."
        ),
        "pdm": (
            "OUTPUT CONTRACT FOR (8) PDM:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section8_pdm_slots_v1\",\"slots\":{\"impact_summary\":\"...\",\"impact_indicator\":\"...\",\"impact_mov\":\"...\",\"impact_assumption\":\"...\",\"outcome_summary\":\"...\",\"outcome_indicator\":\"...\",\"outcome_mov\":\"...\",\"outcome_assumption\":\"...\",\"outputs_summary\":\"...\",\"outputs_indicator\":\"...\",\"outputs_mov\":\"...\",\"outputs_assumption\":\"...\",\"activities\":\"...\",\"inputs\":\"...\",\"preconditions\":\"...\"}}.\n"
            "Each slot replaces one existing PDM table cell. Keep values concise; do not return a markdown table or combined body."
        ),
        "eval-purpose": (
            "OUTPUT CONTRACT FOR (9) EVALUATION PURPOSE/SCOPE:\n"
            "Return only one JSON object: {\"schema\":\"section9_eval_purpose_slots_v1\",\"slots\":{\"evaluation_purpose_scope_body\":\"...\"}}.\n"
            "State purpose, intended users, evaluation scope, period, criteria, and use of results."
        ),
        "eval-matrix": (
            "OUTPUT CONTRACT FOR (10) EVALUATION MATRIX:\n"
            "Return only one JSON object. No markdown fence, no prose, no comments.\n"
            "Required JSON shape: {\"schema\":\"section10_eval_matrix_slots_v1\",\"slots\":{...}}.\n"
            "The slots object must include exactly these keys: "
            + ", ".join(SECTION10_EVAL_MATRIX_SLOT_KEYS)
            + ". Each value replaces one existing cell in the original evaluation matrix table. "
            "Do not return a markdown table or one combined body."
        ),
        "eval-methods": (
            "OUTPUT CONTRACT FOR (11) 평가방법: write final report prose describing document review, performance data review, interviews, field checks, "
            "triangulation, and quality assurance based on available records. Do not write '추가 정보 필요', '자료 없음', or '확인 필요'."
        ),
        "eval-limitations": (
            "OUTPUT CONTRACT FOR (12) 평가 한계: write final report prose explaining evidence/time/access/data limitations, their effect on interpretation, "
            "and mitigation. Do not write placeholder guidance such as '추가 정보 필요', '자료 없음', or '확인 필요'."
        ),
        "eval-team": (
            "OUTPUT CONTRACT FOR (13) 평가팀: write final report prose on roles, responsibilities, execution system, and quality control. "
            "If names are not evidenced, use role-based descriptions rather than placeholder names or '확인 필요'."
        ),
        "achievement": (
            "OUTPUT CONTRACT FOR (14) 성과 달성도: write 3-5 labeled items for table parsing using fields 성과지표, 기초선, 목표치, 종료선, 대비 결과, "
            "지표입증수단(MOV), 비고. Do not write markdown tables or missing-information placeholders."
        ),
        "criteria-relevance": (
            "OUTPUT CONTRACT FOR (15) 적절성: assess demand, policy fit, design logic, and response to context changes. "
            "Do not write missing-information placeholders. "
            + CRITERIA_OUTPUT_STYLE_CONTRACT
        ),
        "criteria-coherence": "OUTPUT CONTRACT FOR (16) 일관성: assess internal and external coherence, complementarity, duplication avoidance, and coordination. " + CRITERIA_OUTPUT_STYLE_CONTRACT,
        "criteria-effectiveness": "OUTPUT CONTRACT FOR (17) 효과성: assess output achievement, outcome achievement, equity/inclusion, and contribution factors. " + CRITERIA_OUTPUT_STYLE_CONTRACT,
        "criteria-efficiency": "OUTPUT CONTRACT FOR (18) 효율성: assess budget execution, schedule, procurement, input-output relation, and management efficiency. " + CRITERIA_OUTPUT_STYLE_CONTRACT,
        "criteria-sustainability": "OUTPUT CONTRACT FOR (19) 지속가능성: assess institutional, financial, organizational, staffing, maintenance, and community sustainability. " + CRITERIA_OUTPUT_STYLE_CONTRACT,
        "criteria-crosscutting": "OUTPUT CONTRACT FOR (20) 범분야 이슈: assess gender, environment, human rights, vulnerable groups, safeguards, and inclusion only where evidence supports it. " + CRITERIA_OUTPUT_STYLE_CONTRACT,
        "criteria-other": "OUTPUT CONTRACT FOR (21) 그 외 평가기준: include only evidence-supported project-specific criteria; if not applicable, explain briefly in report prose. " + CRITERIA_OUTPUT_STYLE_CONTRACT,
        "conclusion": "OUTPUT CONTRACT FOR (22) 결론: synthesize findings already established in previous sections. No new evidence or claims.",
        "working-factors": "OUTPUT CONTRACT FOR (23) 작동요인: identify factors that helped results, grouped by design, implementation, partnership, and context with evidence.",
        "nonworking-factors": "OUTPUT CONTRACT FOR (24) 비작동요인: identify constraints that reduced results, framed as improvement analysis, not blame.",
        "theory": "OUTPUT CONTRACT FOR (25) 변화이론 분석: explain whether input-activity-output-outcome pathway worked, where assumptions held or failed, and why.",
        "feedback": (
            "OUTPUT CONTRACT FOR (26) 환류과제: return 3 to 5 numbered action items. "
            "Each item must use separate lines exactly in this order: 관찰사항:, 환류과제:, 담당 주체:, 선정 사유:, 우선순위:, 후속 확인자료:. "
            "Do not combine fields with semicolons in one line. Do not invent new issues outside prior evaluation findings."
        ),
        "lessons": (
            "OUTPUT CONTRACT FOR (27) 교훈: return 3 to 5 reusable lessons. "
            "Each lesson must start with '❍ (교훈 제목)' followed by one concise analysis paragraph, then 1 to 2 lines starting '- 체크리스트 질문:'. "
            "Checklist questions must be practical yes/no review questions for future similar projects. Do not add new facts."
        ),
    }
    return contracts.get(part_id, "OUTPUT CONTRACT: return only the selected part content. Do not include adjacent headings or any other report part.")


def cover_title_override_from_request(user_request: str) -> str:
    text = str(user_request or "").strip()
    patterns = [
        r"ㅇㅇ사업\s*대신\s*(.+?)(?:으로|로)\s*수정",
        r"사업명(?:을|를)?\s*(.+?)(?:으로|로)\s*수정",
        r"(.+?)(?:으로|로)\s*수정",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .。\"'")
            if value:
                return value
    return ""


SECTION1_COVER_SCHEMA = "section1_cover_slots_v1"
SECTION1_COVER_SLOT_KEYS = (
    "project_title",
    "report_title",
    "report_date",
    "evaluation_manager",
    "evaluation_institution",
)

STRUCTURED_SECTION_SCHEMAS = {
    "cover": "section1_cover_slots_v1",
    "toc": "section2_toc_slots_v1",
    "notice": "section3_notice_slots_v1",
    "grade": "section4_grade_slots_v1",
    "summary-ko": "section5_summary_slots_v1",
    "project-background": "section6_project_background_slots_v1",
    "project-overview": "section7_project_overview_slots_v1",
    "pdm": "section8_pdm_slots_v1",
    "eval-purpose": "section9_eval_purpose_slots_v1",
    "eval-matrix": "section10_eval_matrix_slots_v1",
}

SECTION5_SUMMARY_SLOT_KEYS = [
    "project_name_line",
    "business_background",
    "business_overview",
    "evaluation_purpose",
    "evaluation_scope",
    "evaluation_method_overview",
    "document_review_method",
    "stakeholder_interview_method",
    "field_survey_method",
    "evaluation_limitations",
    "achievement_summary",
    "relevance_summary",
    "coherence_summary",
    "effectiveness_summary",
    "efficiency_summary",
    "sustainability_summary",
    "crosscutting_human_rights_gender",
    "crosscutting_environment",
    "conclusion_goal_achievement",
    "conclusion_dac_results",
    "conclusion_crosscutting_results",
    "lesson_working_factors",
    "lesson_nonworking_factors",
    "recommendation_project_model",
    "recommendation_project_management",
    "recommendation_structural_limits",
    "recommendation_other",
]

SECTION6_PROJECT_BACKGROUND_SLOT_KEYS = [
    "mdg_maternal_health_context",
    "government_policy_context",
    "target_region_need",
    "koica_policy_alignment",
    "project_selection_rationale",
]

SECTION7_PROJECT_OVERVIEW_SLOT_KEYS = [
    "project_name_ko",
    "project_name_en",
    "target_country_region",
    "project_period_budget",
    "project_sector",
    "project_purpose",
    "pcp_feasibility_review",
    "korean_textbook_development",
    "korean_equipment_support",
    "korean_expert_dispatch",
    "korean_invitation_training",
    "partner_contribution",
]

SECTION10_EVAL_MATRIX_SLOT_KEYS = [
    "relevance_question",
    "relevance_indicator",
    "relevance_source",
    "relevance_method",
    "coherence_question",
    "coherence_indicator",
    "coherence_source",
    "coherence_method",
    "effectiveness_question",
    "effectiveness_indicator",
    "effectiveness_source",
    "effectiveness_method",
    "efficiency_question",
    "efficiency_indicator",
    "efficiency_source",
    "efficiency_method",
    "sustainability_question",
    "sustainability_indicator",
    "sustainability_source",
    "sustainability_method",
    "human_rights_question",
    "human_rights_indicator",
    "human_rights_source",
    "human_rights_method",
    "gender_question",
    "gender_indicator",
    "gender_source",
    "gender_method",
    "environment_question",
    "environment_indicator",
    "environment_source",
    "environment_method",
]

STRUCTURED_SECTION_SLOT_KEYS = {
    "summary-ko": SECTION5_SUMMARY_SLOT_KEYS,
    "project-background": SECTION6_PROJECT_BACKGROUND_SLOT_KEYS,
    "project-overview": SECTION7_PROJECT_OVERVIEW_SLOT_KEYS,
    "pdm": [
        "impact_summary",
        "impact_indicator",
        "impact_mov",
        "impact_assumption",
        "outcome_summary",
        "outcome_indicator",
        "outcome_mov",
        "outcome_assumption",
        "outputs_summary",
        "outputs_indicator",
        "outputs_mov",
        "outputs_assumption",
        "activities",
        "inputs",
        "preconditions",
    ],
    "eval-purpose": ["evaluation_purpose_scope_body"],
    "eval-matrix": SECTION10_EVAL_MATRIX_SLOT_KEYS,
}


def extract_json_object_text(value: object) -> str:
    text = str(value or "").strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1].strip()
    return text


def one_line_cover_slot(value: object, fallback: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text or fallback
    return text[:max_chars].rstrip() if len(text) > max_chars else text


def parse_section1_cover_slots(value: object, context: dict | None = None) -> dict | None:
    raw = extract_json_object_text(value)
    if not raw.startswith("{"):
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    slots = parsed.get("slots") if isinstance(parsed.get("slots"), dict) else parsed
    if not isinstance(slots, dict):
        return None
    project = (context or {}).get("project", {}) if isinstance(context, dict) else {}
    project_title_fallback = str(project.get("title") or "사업명 확인 필요")
    return {
        "project_title": one_line_cover_slot(slots.get("project_title"), project_title_fallback, 80),
        "report_title": "종료평가 결과보고서",
        "report_date": one_line_cover_slot(slots.get("report_date"), datetime.now().strftime("%Y. %m"), 20),
        "evaluation_manager": one_line_cover_slot(slots.get("evaluation_manager"), "평가책임자 확인 필요", 40),
        "evaluation_institution": one_line_cover_slot(slots.get("evaluation_institution"), "평가수행기관 확인 필요", 60),
    }


def section1_cover_slots_to_json(slots: dict) -> str:
    normalized = {
        "project_title": one_line_cover_slot(slots.get("project_title"), "사업명 확인 필요", 80),
        "report_title": "종료평가 결과보고서",
        "report_date": one_line_cover_slot(slots.get("report_date"), datetime.now().strftime("%Y. %m"), 20),
        "evaluation_manager": one_line_cover_slot(slots.get("evaluation_manager"), "평가책임자 확인 필요", 40),
        "evaluation_institution": one_line_cover_slot(slots.get("evaluation_institution"), "평가수행기관 확인 필요", 60),
    }
    return json.dumps({"schema": SECTION1_COVER_SCHEMA, "slots": normalized}, ensure_ascii=False, indent=2)


def structured_slots_to_json(part_id: str, slots: dict) -> str:
    schema = STRUCTURED_SECTION_SCHEMAS.get(part_id)
    if not schema:
        return json.dumps({"slots": slots}, ensure_ascii=False, indent=2)
    clean_slots = {
        str(key): value
        for key, value in (slots or {}).items()
        if key is not None
    }
    return json.dumps({"schema": schema, "slots": clean_slots}, ensure_ascii=False, indent=2)


def parse_structured_section_slots(value: object, part_id: str = "") -> dict | None:
    raw = extract_json_object_text(value)
    if not raw.startswith("{"):
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    schema = STRUCTURED_SECTION_SCHEMAS.get(part_id)
    if schema and parsed.get("schema") not in {schema, None}:
        return None
    slots = parsed.get("slots") if isinstance(parsed.get("slots"), dict) else parsed
    return slots if isinstance(slots, dict) else None


def legacy_cover_text_to_slots(text: str, context: dict | None = None) -> dict:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    project = (context or {}).get("project", {}) if isinstance(context, dict) else {}
    project_title = next(
        (
            line for line in lines
            if "종료평가 결과보고서" not in line
            and not re.search(r"\d{4}\.\s*\d{1,2}", line)
            and not line.startswith("평가책임자")
            and not line.startswith("평가수행기관")
        ),
        str(project.get("title") or "사업명 확인 필요"),
    )
    return {
        "project_title": project_title,
        "report_title": "종료평가 결과보고서",
        "report_date": next((line for line in lines if re.search(r"\d{4}\.\s*\d{1,2}", line)), datetime.now().strftime("%Y. %m")),
        "evaluation_manager": next((line for line in lines if line.startswith("평가책임자")), "평가책임자 확인 필요"),
        "evaluation_institution": next((line for line in lines if line.startswith("평가수행기관")), "평가수행기관 확인 필요"),
    }


EDITOR_PART_HEADING_PATTERNS = {
    "summary-ko": [
        r"^\s*(?:Ⅰ|I)\.?\s*평가결과\s*요약.*$",
        r"^\s*1\.?\s*국문\s*요약\s*$",
    ],
    "project-background": [
        r"^\s*(?:Ⅱ|II)\.?\s*대상사업\s*개요.*$",
        r"^\s*1\.?\s*사업\s*추진배경\s*$",
    ],
    "project-overview": [
        r"^\s*(?:Ⅱ|II)\.?\s*대상사업\s*개요.*$",
        r"^\s*2\.?\s*사업개요\s*$",
        r"^\s*2\.?\s*사업\s*개요\s*$",
    ],
    "pdm": [
        r"^\s*(?:Ⅱ|II)\.?\s*대상사업\s*개요.*$",
        r"^\s*3\.?\s*사업설계매트릭스\s*\(?PDM\)?\s*$",
    ],
    "eval-purpose": [
        r"^\s*(?:Ⅲ|III)\.?\s*평가개요.*$",
        r"^\s*1\.?\s*평가의\s*목적과\s*범위\s*$",
    ],
    "eval-matrix": [
        r"^\s*(?:Ⅲ|III)\.?\s*평가개요.*$",
        r"^\s*2\.?\s*평가\s*매트릭스.*$",
    ],
    "eval-methods": [
        r"^\s*(?:Ⅲ|III)\.?\s*평가개요.*$",
        r"^\s*3\.?\s*평가\s*방법\s*$",
    ],
    "eval-limitations": [
        r"^\s*(?:Ⅲ|III)\.?\s*평가개요.*$",
        r"^\s*4\.?\s*평가의\s*한계\s*$",
    ],
    "eval-team": [
        r"^\s*(?:Ⅲ|III)\.?\s*평가개요.*$",
        r"^\s*5\.?\s*평가팀\s*구성\s*및\s*시행체계\s*$",
    ],
    "achievement": [r"^\s*(?:Ⅳ|IV)\.?\s*성과\s*달성도\s*$"],
    "criteria-relevance": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*1\.?\s*적절성\s*$"],
    "criteria-coherence": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*2\.?\s*일관성\s*$"],
    "criteria-effectiveness": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*3\.?\s*효과성\s*$"],
    "criteria-efficiency": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*4\.?\s*효율성\s*$"],
    "criteria-sustainability": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*5\.?\s*지속가능성\s*$"],
    "criteria-crosscutting": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*6\.?\s*범분야\s*이슈\s*$"],
    "criteria-other": [r"^\s*(?:Ⅴ|V)\.?\s*기준별\s*평가결과.*$", r"^\s*7\.?\s*그\s*외\s*평가기준\s*$"],
    "conclusion": [r"^\s*(?:Ⅵ|VI|IV)\.?\s*결론.*$", r"^\s*1\.?\s*결론.*$"],
    "working-factors": [r"^\s*(?:Ⅵ|VI|IV)\.?\s*결론.*$", r"^\s*2\.?\s*작동요인\s*및\s*비작동요인\s*$", r"^\s*\(?1\)?\s*작동\s*요인\s*$"],
    "nonworking-factors": [r"^\s*(?:Ⅵ|VI|IV)\.?\s*결론.*$", r"^\s*2\.?\s*작동요인\s*및\s*비작동요인\s*$", r"^\s*\(?2\)?\s*비작동\s*요인\s*$"],
    "theory": [r"^\s*(?:Ⅵ|VI|IV)\.?\s*결론.*$", r"^\s*\(?3\)?\s*변화이론\s*분석\s*$"],
    "feedback": [r"^\s*(?:Ⅵ|VI|IV)\.?\s*결론.*$", r"^\s*3\.?\s*환류과제\s*및\s*교훈\s*$", r"^\s*\(?1\)?\s*환류과제\s*$"],
    "lessons": [r"^\s*(?:Ⅵ|VI|IV)\.?\s*결론.*$", r"^\s*3\.?\s*환류과제\s*및\s*교훈\s*$", r"^\s*\(?2\)?\s*교훈\s*$"],
}


def strip_editor_part_headings(text: str, part_id: str) -> str:
    patterns = EDITOR_PART_HEADING_PATTERNS.get(part_id, [])
    if not patterns:
        return text.strip()
    cleaned_lines = []
    skipped_heading = False
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        normalized = line.strip()
        if normalized and any(re.match(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            skipped_heading = True
            continue
        if skipped_heading and not normalized and not cleaned_lines:
            continue
        cleaned_lines.append(line.rstrip())
    cleaned = "\n".join(cleaned_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


CRITERIA_MEMO_LABEL_PATTERN = re.compile(
    r"^\s*(?:[-ㆍ·•∙]\s*)?(?:"
    r"판단|근거|평가\s*근거|확인\s*증빙|한계|평가\s*한계|"
    r"평가\s*한계\s*및\s*후속\s*확인사항|점수\s*산정\s*이유|산정\s*이유|"
    r"보완\s*필요사항|개선\s*필요사항|활용근거|평가질문|질문"
    r")\s*[:：]\s*"
)


def sanitize_criteria_report_prose(text: str) -> str:
    """Keep criterion sections in final report prose, not scoring memo format."""
    cleaned_lines: list[str] = []
    previous_blank = False
    criterion_names = r"적절성|일관성|효과성|효율성|지속가능성|범분야\s*이슈|그\s*외\s*평가기준"
    for raw_line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        stripped = re.sub(r"^\s*#{1,6}\s*", "", stripped).strip()
        stripped = re.sub(r"^\s*\*{1,3}(.+?)\*{1,3}\s*$", r"\1", stripped).strip()

        if re.match(r"^(?:[IVX]+|[ⅠⅡⅢⅣⅤⅥ])\.?\s*기준별\s*평가결과\b.*$", stripped, re.IGNORECASE):
            continue
        if re.match(rf"^\d+\.?\s*(?:{criterion_names})\s*$", stripped):
            continue
        if re.match(rf"^(?:[IVX]+|[ⅠⅡⅢⅣⅤⅥ])\.?\s*기준별\s*평가결과\s+\d+\.?\s*(?:{criterion_names})\s*$", stripped, re.IGNORECASE):
            continue
        if stripped in {"기준별 평가결과", "평가결과"}:
            continue

        if re.match(r"^\s*(?:[-ㆍ·•∙]\s*)?(?:평가\s*점수|관련\s*기준\s*점수)\s*[:：]", stripped):
            continue
        if re.search(r"\d+\s*점\s*/\s*4\s*점|\d+\s*/\s*4\s*점", stripped):
            continue

        label_match = CRITERIA_MEMO_LABEL_PATTERN.match(stripped)
        label_text = label_match.group(0) if label_match else ""
        if label_match and re.search(r"점수\s*산정|산정\s*이유", label_text):
            continue
        without_label = CRITERIA_MEMO_LABEL_PATTERN.sub("", stripped).strip()
        if not without_label:
            continue
        if (
            without_label.endswith("?")
            and re.search(r"(?:하였는가|되었는가|있는가|인가|했는가|는지|었는지)\?$", without_label)
        ):
            continue

        is_heading = bool(re.match(r"^\s*(?:\d+(?:\.\d+)*\.?|[가-힣]\.)\s+", without_label))
        had_label = without_label != stripped
        had_markdown_bullet = bool(re.match(r"^\s*[-ㆍ·•∙]\s+", stripped))
        if had_label and re.search(r"확인\s*증빙|활용근거|평가\s*근거", label_text):
            without_label = f"주요 근거는 {without_label} 등으로 확인됨."
        elif had_label and re.search(r"한계|보완\s*필요사항|개선\s*필요사항", label_text):
            without_label = f"다만, {without_label}"
        if had_label and not is_heading and not without_label.startswith(("ㅇ", "∙", "·", "ㆍ")):
            without_label = "ㅇ " + without_label
        elif had_markdown_bullet and not without_label.startswith(("ㅇ", "∙", "·", "ㆍ")):
            without_label = re.sub(r"^\s*[-ㆍ·•∙]\s*", "ㅇ ", without_label).strip()

        cleaned_lines.append(without_label.strip())
        previous_blank = False

    text = normalize_korean_report_prose("\n".join(cleaned_lines).strip())
    return normalize_criteria_report_line_breaks(text)


def normalize_criteria_report_line_breaks(text: str) -> str:
    """Use one stable report rhythm for DAC criterion sections."""
    output: list[str] = []
    previous_kind = ""
    for raw_line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line.strip())
        if not line:
            continue
        line = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
        line = re.sub(r"^\s*[-•∙ㆍ·]\s+", "ㅇ ", line)
        if re.match(r"^\d+\.\d+\.?\s+", line):
            kind = "subheading"
        elif re.match(r"^(?:ㅇ|∙|ㆍ|·)\s+", line):
            kind = "bullet"
        else:
            kind = "paragraph"
        if output and kind == "subheading" and previous_kind != "subheading":
            output.append("")
        if output and kind == "paragraph" and previous_kind == "paragraph":
            output.append("")
        output.append(line)
        previous_kind = kind
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()


def _normalize_feedback_section_once(text: object) -> str:
    """Display feedback actions as readable action cards while preserving parseable labels."""
    value = markdown_table_to_report_text(str(text or ""))
    value = re.sub(r"^\s*#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"(?m)^\s*(?:\d+[.)]\s*){2,}", "", value)
    lines = [line.strip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]

    chunks: list[str] = []
    current: list[str] = []
    for raw_line in lines:
        line = re.sub(r"^(?:\d+[.)]\s*){2,}", "", raw_line).strip()
        line = re.sub(r"^[-•∙ㆍ·]\s*", "- ", line).strip()
        starts_item = bool(re.match(r"^\d+[.)]\s+", line))
        starts_item = starts_item or bool(re.match(r"^(?:관찰사항|환류과제)\s*[:：]", line))
        if starts_item and current:
            chunks.append("\n".join(current))
            current = [line]
        elif starts_item:
            current = [line]
        elif current:
            current.append(line)
        elif re.search(r"(관찰사항|환류과제|담당\s*주체|선정\s*사유|후속\s*확인자료)\s*[:：]", line):
            current = [line]
    if current:
        chunks.append("\n".join(current))

    if not chunks:
        chunks = [value]

    def clean_piece(value: str, limit: int = 260) -> str:
        cleaned = re.sub(r"^(?:\d+[.)]\s*)+", "", str(value or "")).strip()
        cleaned = re.sub(r"^[-•∙ㆍ·]\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ;")
        return short_text(cleaned, limit)

    def first_line(item: str) -> str:
        for line in item.splitlines():
            cleaned = clean_piece(line)
            if not cleaned:
                continue
            if re.match(r"^(관찰사항|담당\s*주체|선정\s*사유|우선순위|후속\s*확인자료)\s*[:：]", cleaned):
                continue
            return re.sub(r"^환류과제\s*[:：]\s*", "", cleaned).strip()
        return ""

    def field(item: str, labels: list[str], fallback: str = "", limit: int = 260) -> str:
        escaped = "|".join(re.escape(label).replace(r"\ ", r"\s*") for label in labels)
        stop = r"관찰사항|환류과제|담당\s*주체|담당주체|선정\s*사유|선정사유|우선순위|후속\s*확인자료|유관부서\s*의견"
        match = re.search(
            rf"(?:{escaped})\s*[:：]\s*(.*?)(?=(?:;|\n)\s*[-•∙ㆍ·]?\s*(?:{stop})\s*[:：]|$)",
            item,
            re.DOTALL,
        )
        return clean_piece(match.group(1) if match else fallback, limit)

    output: list[str] = []
    used: set[str] = set()
    for item in chunks:
        task_fallback = field(item, ["환류과제"], "", 220) or first_line(item)
        task = clean_piece(re.sub(r"^환류과제\s*[:：]\s*", "", task_fallback), 220)
        observation = field(item, ["관찰사항"], task, 260)
        if not task:
            task = clean_piece(f"{observation}에 대한 후속조치 계획 수립", 220)
        if not task or task in used:
            continue
        used.add(task)
        owner = field(item, ["담당 주체", "담당주체"], "사업담당부서/수행기관", 80)
        reason = field(item, ["선정 사유", "선정사유"], "평가결과 환류 및 후속 성과관리 강화 필요", 180)
        priority = field(item, ["우선순위"], "중", 20)
        evidence = field(item, ["후속 확인자료", "유관부서 의견"], "후속계획 및 이행 증빙", 160)
        output.extend([
            f"{len(used)}. {task}",
            f"   - 관찰사항: {observation}",
            f"   - 담당 주체: {owner}",
            f"   - 선정 사유: {reason}",
            f"   - 우선순위: {priority}",
            f"   - 후속 확인자료: {evidence}",
            "",
        ])
        if len(used) >= 6:
            break
    return normalize_korean_report_prose("\n".join(output)).strip()


def normalize_feedback_section(text: object) -> str:
    first = _normalize_feedback_section_once(text)
    second = _normalize_feedback_section_once(first)
    return short_text(second, 4200)


def normalize_lessons_section(text: object) -> str:
    """Normalize lesson body and checklist lines for both editor display and table extraction."""
    value = markdown_table_to_report_text(str(text or ""))
    value = re.sub(r"^\s*#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*[-•∙ㆍ·]\s*(?=체크리스트\s*질문\s*[:：])", "- ", value, flags=re.MULTILINE)
    lines: list[str] = []
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if re.match(r"^\(?2\)?\s*교훈\s*$", line):
            continue
        if re.match(r"^[-•∙ㆍ·]\s*(?!체크리스트\s*질문\s*[:：])", line):
            line = re.sub(r"^[-•∙ㆍ·]\s*", "- 체크리스트 질문: ", line)
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", normalize_korean_report_prose("\n".join(lines))).strip()


def sanitize_editor_part_response(content: str, part_id: str, user_request: str = "") -> str:
    if part_id == "cover":
        parsed_slots = parse_section1_cover_slots(content)
        if parsed_slots is None:
            parsed_slots = legacy_cover_text_to_slots(clean_evaluation_text(unwrap_editor_part_response(content)))
        title_override = cover_title_override_from_request(user_request)
        if title_override:
            parsed_slots["project_title"] = title_override
        return section1_cover_slots_to_json(parsed_slots)
    if part_id in STRUCTURED_SECTION_SCHEMAS and part_id != "cover":
        parsed_slots = parse_structured_section_slots(content, part_id)
        if parsed_slots is None:
            text_value = clean_evaluation_text(unwrap_editor_part_response(content))
            keys = STRUCTURED_SECTION_SLOT_KEYS.get(part_id) or ["raw_text"]
            parsed_slots = {keys[0]: text_value}
        if part_id == "summary-ko":
            parsed_slots = {
                key: value
                for key, value in parsed_slots.items()
                if key in SECTION5_SUMMARY_SLOT_KEYS
            }
        elif part_id == "project-background":
            parsed_slots = {
                key: value
                for key, value in parsed_slots.items()
                if key in SECTION6_PROJECT_BACKGROUND_SLOT_KEYS
            }
        elif part_id == "project-overview":
            parsed_slots = {
                key: value
                for key, value in parsed_slots.items()
                if key in SECTION7_PROJECT_OVERVIEW_SLOT_KEYS
            }
        elif part_id == "eval-matrix":
            parsed_slots = {
                key: value
                for key, value in parsed_slots.items()
                if key in SECTION10_EVAL_MATRIX_SLOT_KEYS
            }
        return structured_slots_to_json(part_id, parsed_slots)

    content = unwrap_editor_part_response(content)
    text = clean_evaluation_text(content)
    if part_id == "cover":
        stop_patterns = [
            r"\n\s*\(?2\)?\s*목차",
            r"\n\s*\(?3\)?\s*평가보고서",
            r"\n\s*\(?4\)?\s*평가등급",
            r"\n\s*I\.\s*평가결과",
            r"\n\s*II\.\s*대상사업",
            r"\n\s*III\.\s*평가개요",
            r"\n\s*IV\.",
            r"\n\s*V\.",
            r"\n\s*VI\.",
        ]
        cut = len(text)
        for pattern in stop_patterns:
            match = re.search(pattern, text)
            if match:
                cut = min(cut, match.start())
        text = text[:cut].strip()
        lines = [line.rstrip() for line in text.splitlines()]
        kept = []
        for line in lines:
            normalized = line.strip()
            if not normalized:
                if kept and kept[-1] != "":
                    kept.append("")
                continue
            if re.match(r"^\(?[2-9]\)?\s+", normalized):
                break
            kept.append(line)
            if sum(1 for item in kept if item.strip()) >= 5:
                # Cover should be only title, date, evaluator, institution.
                break
        lines = [line for line in kept if line.strip()]
        title_override = cover_title_override_from_request(user_request)
        if title_override:
            if lines:
                lines[0] = title_override
            else:
                lines = [title_override]
        if not any("종료평가 결과보고서" in line for line in lines[:2]):
            lines.insert(1, "종료평가 결과보고서")
        current_month = datetime.now().strftime("%Y. %m")
        date_index = next((index for index, line in enumerate(lines) if re.search(r"\d{4}\.\s*\d{1,2}", line)), None)
        if date_index is None:
            lines.insert(2, current_month)
        else:
            lines[date_index] = current_month
        if not any(line.startswith("평가책임자") for line in lines):
            lines.append("평가책임자 확인 필요")
        if not any(line.startswith("평가수행기관") for line in lines):
            lines.append("평가수행기관 확인 필요")
        text = "\n\n".join([
            "\n".join(lines[:2]),
            lines[2],
            "\n".join(lines[3:5]),
        ]).strip()
    else:
        text = strip_editor_part_headings(text, part_id)
        text = markdown_table_to_report_text(text)
        if part_id in CRITERIA_REPORT_PART_IDS:
            text = sanitize_criteria_report_prose(text)
        elif part_id == "feedback":
            text = normalize_feedback_section(text)
        elif part_id == "lessons":
            text = normalize_lessons_section(text)
    return text


def unwrap_editor_part_response(content: object) -> str:
    text = str(content or "").strip()
    if not text:
        return ""
    fence_match = re.fullmatch(r"```(?:json|text|markdown)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    if not (text.startswith("{") or text.startswith("[")):
        return text
    try:
        parsed = json.loads(text)
    except Exception:
        return text

    def stringify(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return "\n".join(stringify(item) for item in value if stringify(item)).strip()
        if isinstance(value, dict):
            for key in ("final_text", "section_text", "content", "body", "text", "output", "draft"):
                if key in value:
                    extracted = stringify(value.get(key))
                    if extracted:
                        return extracted
            if "replacements" in value and isinstance(value.get("replacements"), dict):
                return stringify(list(value["replacements"].values()))
            return "\n".join(
                f"{key}: {stringify(item)}"
                for key, item in value.items()
                if stringify(item)
            ).strip()
        return str(value).strip()

    return stringify(parsed) or text

