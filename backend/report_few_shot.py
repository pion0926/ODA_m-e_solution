from __future__ import annotations

import json
import re
from collections.abc import Iterable


EXPECTED_PART_IDS = (
    "cover", "toc", "notice", "grade", "summary-ko", "project-background",
    "project-overview", "pdm", "eval-purpose", "eval-matrix", "eval-methods",
    "eval-limitations", "eval-team", "achievement", "criteria-relevance",
    "criteria-coherence", "criteria-effectiveness", "criteria-efficiency",
    "criteria-sustainability", "criteria-crosscutting", "criteria-other",
    "conclusion", "working-factors", "nonworking-factors", "theory", "feedback",
    "lessons",
)


# These demonstrations intentionally contain no completed-report fact, sentence,
# number, institution, country, or judgement.  They are format blueprints derived
# from the completed-report library.  Runtime project evidence replaces every
# CURRENT_* token; the tokens themselves must never reach saved report text.
FORMAT_ONLY_DEMOS: dict[str, str] = {
    "cover": """{{CURRENT_PROJECT_TITLE}}
{{CURRENT_REPORT_TYPE}}
{{CURRENT_REFERENCE_DATE}}
평가책임자: {{CURRENT_EVALUATION_MANAGER}}
평가수행기관: {{CURRENT_EVALUATION_INSTITUTION}}""",
    "toc": """I. {{CURRENT_CHAPTER_TITLE}} ................................ {{CURRENT_PAGE}}
  1. {{CURRENT_SECTION_TITLE}} ............................. {{CURRENT_PAGE}}
    가. {{CURRENT_SUBSECTION_TITLE}} ....................... {{CURRENT_PAGE}}""",
    "notice": """ㅇ (평가 책임과 독립성)
- (평가 책임) {{CURRENT_PROJECT_EVIDENCE_BASED_NOTICE}}

ㅇ (사실확인 및 품질관리)
- (품질관리 범위) {{CURRENT_REVIEW_AND_DISCLOSURE_SCOPE}}""",
    "grade": """| 평가기준 | 핵심 질문 | 점수 | 산정 이유 |
|---|---|---:|---|
| {{CURRENT_DAC_CRITERION}} | {{CURRENT_EVALUATION_QUESTION}} | {{CURRENT_QUESTION_SCORE}}/4점 | {{CURRENT_EVIDENCE_BASED_REASON_FOR_THIS_QUESTION_ONLY}} |
| {{CURRENT_DAC_CRITERION}} 평점 |  | {{CURRENT_CRITERION_SCORE}}/4점 |  |

종합점수·등급: {{CURRENT_OFFICIAL_TOTAL_AND_GRADE}}""",
    "summary-ko": """(1) 대상사업개요

 ㅇ 사업 기본정보
- (사업명·유형) {{CURRENT_PROJECT_TITLE_AND_TYPE}}
- (대상지역·수혜자) {{CURRENT_COUNTRY_REGION_AND_BENEFICIARIES}}
- (기간·예산·수행체계) {{CURRENT_PERIOD_BUDGET_AND_ACTORS}}

 ㅇ 추진배경 및 주요내용
- {{CURRENT_DEVELOPMENT_PROBLEM_AND_NEED}}
- {{CURRENT_INTERVENTION_LOGIC_AND_MAIN_ACTIVITIES}}
- {{CURRENT_EXPECTED_RESULTS_AND_IMPLEMENTATION_SCOPE}}

(2) 평가개요

 ㅇ 평가 목적과 범위
- {{CURRENT_EVALUATION_PURPOSE}}
- {{CURRENT_EVALUATION_SCOPE}}

 ㅇ 평가 방법
- {{CURRENT_VERIFIED_DOCUMENT_REVIEW_METHOD}}
- {{CURRENT_VERIFIED_ANALYSIS_METHOD}}

 ㅇ 평가의 한계
- {{CURRENT_LIMITATION_AND_JUDGEMENT_EFFECT}}
- {{CURRENT_MITIGATION_AND_FOLLOW_UP}}

(3) 성과달성도

 ㅇ 주요 성과달성도
- (성과경로 범위) {{CURRENT_PDM_RESULT_CHAIN_SCOPE}}
- (산출 달성) {{CURRENT_VERIFIED_OUTPUT_ACHIEVEMENTS}}
- (성과 달성) {{CURRENT_VERIFIED_OUTCOME_ACHIEVEMENTS}}
- (미달·미산정 지표) {{CURRENT_UNDERACHIEVED_OR_UNSCORED_INDICATORS}}
- (근거 신뢰도) {{CURRENT_EVIDENCE_RELIABILITY_AND_LIMIT}}
- (후속 측정) {{CURRENT_FOLLOW_UP_MEASUREMENT_NEED}}

(4) 기준별 평가결과

 ㅇ 적절성
- {{CURRENT_RELEVANCE_JUDGEMENT}}
- {{CURRENT_RELEVANCE_EVIDENCE_AND_LIMIT}}

 ㅇ 일관성
- {{CURRENT_COHERENCE_JUDGEMENT}}
- {{CURRENT_COHERENCE_EVIDENCE_AND_LIMIT}}

 ㅇ 효과성
- {{CURRENT_EFFECTIVENESS_JUDGEMENT}}
- {{CURRENT_EFFECTIVENESS_EVIDENCE_AND_LIMIT}}

 ㅇ 효율성
- {{CURRENT_EFFICIENCY_JUDGEMENT}}
- {{CURRENT_EFFICIENCY_EVIDENCE_AND_LIMIT}}

 ㅇ 지속가능성
- {{CURRENT_SUSTAINABILITY_JUDGEMENT}}
- {{CURRENT_SUSTAINABILITY_EVIDENCE_AND_LIMIT}}

(5) 결론

 ㅇ 종합 결론
- {{CURRENT_SYNTHESIZED_CONCLUSION}}
- {{CURRENT_OVERALL_LIMIT_AND_MEANING}}

 ㅇ 작동요인
- {{CURRENT_WORKING_FACTORS}}
- {{CURRENT_WORKING_FACTOR_MECHANISM}}

 ㅇ 비작동요인
- {{CURRENT_NONWORKING_FACTORS}}
- {{CURRENT_NONWORKING_FACTOR_IMPLICATION}}

 ㅇ 환류과제 및 교훈
- {{CURRENT_FEEDBACK_AND_LESSONS}}
- {{CURRENT_IMPLEMENTATION_PRIORITY_AND_VERIFICATION}}""",
    "project-background": """**(개발문제와 구조적 취약성)**
{{CURRENT_PROBLEM_SCALE_CAUSE_AND_REMAINING_GAP}}

**(정책 대응과 사업 형성 논리)**
{{CURRENT_POLICY_RESPONSE_AND_INTERVENTION_RATIONALE}}""",
    "project-overview": """| 항목 | 현재 사업 확정 정보 |
|---|---|
| 사업명·대상지역·기간·예산 | {{CURRENT_PROJECT_FACTS}} |
| 목적·활동·산출 | {{CURRENT_OBJECTIVE_ACTIVITY_OUTPUT_LINK}} |
| 수행·협력기관·수혜자 | {{CURRENT_ACTORS_AND_BENEFICIARIES}} |""",
    "pdm": """| 구분 | 사업요약 | 검증지표(OVI) | 검증수단(MOV) | 중요가정 |
|---|---|---|---|---|
| {{CURRENT_RESULT_LEVEL}} | {{CURRENT_RESULT_STATEMENT}} | {{CURRENT_INDICATOR}} | {{CURRENT_MOV}} | {{CURRENT_ASSUMPTION}} |""",
    "eval-purpose": """ㅇ (평가 목적)
- (목적) {{CURRENT_EVALUATION_PURPOSE}}

ㅇ (대상·기간·공간 범위)
- (평가 범위) {{CURRENT_VERIFIED_SCOPE}}

ㅇ (핵심 판단영역과 결과 활용)
- (판단영역·활용) {{CURRENT_QUESTIONS_AND_USERS}}""",
    "eval-matrix": """| 평가기준 | 평가질문 | 측정지표·판단기준 | 자료출처 | 분석방법 |
|---|---|---|---|---|
| {{CURRENT_CRITERION}} | {{CURRENT_QUESTION}} | {{CURRENT_INDICATOR}} | {{CURRENT_AVAILABLE_SOURCE}} | {{CURRENT_VERIFIED_METHOD}} |""",
    "eval-methods": """ㅇ (자료수집)
- (자료수집 범위) {{CURRENT_VERIFIED_COLLECTION_METHOD_AND_SCOPE}}

ㅇ (분석 및 교차확인)
- (분석·교차확인) {{CURRENT_VERIFIED_ANALYSIS_AND_TRIANGULATION}}

ㅇ (품질관리)
- (검토 절차) {{CURRENT_REVIEW_PROCEDURE}}""",
    "eval-limitations": """ㅇ (자료 공백)
- (주요 제약) {{CURRENT_LIMITATION}}
- (판단 영향) {{CURRENT_EFFECT_ON_JUDGEMENT}}
- (보완·후속조치) {{CURRENT_MITIGATION_OR_FOLLOW_UP}}""",
    "eval-team": """ㅇ (구성 및 역할)
- (역할 분담) {{CURRENT_MEMBER_OR_INSTITUTION}}: {{CURRENT_VERIFIED_ROLE}}

ㅇ (검토·품질관리 체계)
- (검토·통제) {{CURRENT_DECISION_REVIEW_AND_CONFLICT_CONTROL}}""",
    "achievement": """| 성과지표 | 기초선 | 목표치 | 실적 | 달성률 | 검증수단 | 근거 위치 | 판단 |
|---|---|---|---|---|---|---|---|
| {{CURRENT_PDM_INDICATOR}} | {{CURRENT_BASELINE}} | {{CURRENT_TARGET}} | {{CURRENT_ACTUAL}} | {{CURRENT_RATE_OR_NOT_CALCULABLE}} | {{CURRENT_MOV}} | {{CURRENT_SOURCE_LOCATION}} | {{CURRENT_JUDGEMENT}} |

ㅇ (차이 원인과 함의)
- (차이 원인·함의) {{CURRENT_VARIANCE_CAUSE_AND_EVALUATIVE_IMPLICATION}}""",
    "criteria-relevance": """ㅇ (수요 적합성)
- (수요 반영) {{CURRENT_CLAIM_EVIDENCE_INTERPRETATION_LIMIT}}

ㅇ (정책 및 설계 적합성)
- (정책·설계 부합) {{CURRENT_CLAIM_EVIDENCE_INTERPRETATION_LIMIT}}""",
    "criteria-coherence": """ㅇ (내적 일관성)
- (내부 정합성) {{CURRENT_INTERNAL_COHERENCE_ARGUMENT}}

ㅇ (외적 일관성·조정)
- (외부 조정) {{CURRENT_EXTERNAL_COHERENCE_AND_COORDINATION_ARGUMENT}}""",
    "criteria-effectiveness": """ㅇ (산출 및 성과 달성)
- (산출·성과 진척) {{CURRENT_OUTPUT_OUTCOME_EVIDENCE_AND_JUDGEMENT}}

ㅇ (포용성·기여요인·대안설명)
- (포용성·기여요인) {{CURRENT_EQUITY_CONTRIBUTION_AND_ALTERNATIVE_EXPLANATION}}""",
    "criteria-efficiency": """ㅇ (예산·일정·조달)
- (계획 대비 집행) {{CURRENT_PLAN_ACTUAL_COMPARISON_AND_CAUSE}}

ㅇ (투입 대비 산출 및 관리)
- (자원 활용) {{CURRENT_RESOURCE_OUTPUT_AND_MANAGEMENT_JUDGEMENT}}""",
    "criteria-sustainability": """ㅇ (제도·조직·역량)
- (제도·역량 기반) {{CURRENT_INSTITUTION_ORGANISATION_CAPACITY_EVIDENCE}}

ㅇ (재원·유지관리·현지 소유권)
- (운영 지속 위험) {{CURRENT_FINANCE_MAINTENANCE_OWNERSHIP_RISK}}""",
    "criteria-crosscutting": """ㅇ (젠더·인권·취약계층)
- (포용적 설계) {{CURRENT_SUPPORTED_INCLUSIVE_DESIGN_AND_RESULT}} {{CURRENT_CONNECTED_INTERPRETATION}}
- (분리통계 한계) {{CURRENT_SUPPORTED_DISAGGREGATED_DATA_LIMITATION}}
- (이행체계 보완) {{CURRENT_EXECUTABLE_MONITORING_AND_MANAGEMENT_ACTION}}

ㅇ (환경·기후·세이프가드)
- (환경·세이프가드) {{CURRENT_SUPPORTED_SAFEGUARD_JUDGEMENT}}""",
    "criteria-other": """ㅇ (현재 사업에 적용되는 추가 기준)
- (추가 기준) {{CURRENT_ADDITIONAL_CRITERION_OR_NOT_APPLICABLE}}
- (판단·근거·한계) {{CURRENT_NON_DUPLICATIVE_ARGUMENT}}""",
    "conclusion": """ㅇ (종합 판단)
- (종합 평가) {{CURRENT_ACHIEVEMENT_AND_FIVE_DAC_SYNTHESIS}}

ㅇ (핵심 성과와 한계)
- (핵심 성과·한계) {{CURRENT_MOST_MATERIAL_STRENGTH_AND_LIMIT}}

ㅇ (후속 방향)
- (후속 과제) {{CURRENT_EVIDENCE_BASED_DIRECTION}}""",
    "working-factors": """ㅇ (작동요인: {{CURRENT_FACTOR_TITLE}})
- (원인) {{CURRENT_CAUSAL_CONDITION}}
- (작동경로) {{CURRENT_MECHANISM}}
- (관찰결과) {{CURRENT_SUPPORTED_RESULT}}""",
    "nonworking-factors": """ㅇ (비작동요인: {{CURRENT_FACTOR_TITLE}})
- (원인) {{CURRENT_CONSTRAINT}}
- (영향) {{CURRENT_EFFECT_ON_RESULT_PATH}}
- (대응·개선방향) {{CURRENT_RESPONSE_AND_IMPROVEMENT}}""",
    "theory": """ㅇ (성과경로)
- (성과경로) 투입 → 활동 → 산출 → 성과: {{CURRENT_CAUSAL_PATH}}

ㅇ (핵심 가정과 외부요인)
- (가정 검증) {{CURRENT_ASSUMPTION_TEST}}

ㅇ (작동·단절 지점)
- (작동·단절 분석) {{CURRENT_SUPPORTED_WORKING_AND_BROKEN_LINKS}}""",
    "feedback": """| 구분 | 관찰·근거 | 후속조치 | 책임주체 | 선정사유·우선순위 | 완료기한·점검주기·확인자료 |
|---|---|---|---|---|---|
| {{CURRENT_ACTION_CATEGORY}} | {{CURRENT_OBSERVATION}} | {{CURRENT_EXECUTABLE_ACTION}} | {{CURRENT_OWNER}} | {{CURRENT_REASON_AND_PRIORITY}} | {{CURRENT_DEADLINE_CYCLE_AND_EVIDENCE}} |""",
    "lessons": """| 교훈 제목 | 교훈 내용 | 일반화 조건·분야 | 중복 여부 | 후속 체크리스트 |
|---|---|---|---|---|
| {{CURRENT_LESSON_TITLE}} | {{CURRENT_GENERALISABLE_PRINCIPLE}} | {{CURRENT_SCOPE}} | {{CURRENT_DUPLICATION_STATUS}} | {{CURRENT_MONITORING_QUESTION}} |""",
}


SAMPLE_ISOLATION_POLICY = """[완성형 샘플보고서 격리 정책]
- 서버에 등록된 완성형 샘플보고서는 섹션의 제목 계층, 항목 분리, 표 열 구성, 문단 순서, 논증 밀도를 식별하는 데만 사용한다.
- 샘플 원문, 사업명, 국가·지역, 기관명, 인명, 날짜, 수치, 성과, 점수, 평가판단, 출처 문장은 모델 입력에 제공하지 않는다.
- 아래 예시의 {{CURRENT_*}} 토큰은 형식만 보여주는 자리표시자다. 실제 답변에서는 현재 사업의 근거로 모두 대체하고 토큰을 출력하지 않는다.
- 현재 사업 근거에 없는 값은 샘플로 채우거나 추정하지 않는다. 보유 근거 범위에서 보수적으로 서술한다.
- 문장 표현은 새로 작성한다. 샘플 문장을 복사하거나 유사하게 바꾸는 작업도 금지한다."""


def _example_payload(part_id: str, output_key: str, evidence_only: bool = False) -> dict:
    demo = FORMAT_ONLY_DEMOS[part_id]
    if evidence_only:
        demo = demo.replace("{{CURRENT_", "{{CURRENT_EVIDENCE_ONLY_")
    if output_key == "revised_content":
        return {
            "revised_content": demo,
            "quality_score": 95,
            "dimension_scores": {
                "grounding": 95,
                "analysis": 95,
                "specificity": 95,
                "structure": 95,
                "professional_style": 95,
                "completeness": 95,
            },
            "quality_issues": [],
            "evidence_coverage": [],
            "unresolved_evidence_gaps": [],
        }
    return {
        "content": demo,
        "used_evidence_ids": [],
        "key_claims": [],
        "evidence_gaps": [],
    }


def _example_message_content(part_id: str, output_key: str | None, evidence_only: bool) -> str:
    demo = FORMAT_ONLY_DEMOS[part_id]
    if evidence_only:
        demo = demo.replace("{{CURRENT_", "{{CURRENT_EVIDENCE_ONLY_")
    if output_key is None:
        return demo
    return json.dumps(_example_payload(part_id, output_key, evidence_only), ensure_ascii=False)


def build_format_only_few_shot_messages(
    part_id: str,
    *,
    structure_notes: str = "",
    sample_count: int = 0,
    output_key: str | None = "content",
) -> list[dict[str, str]]:
    """Build two safe demonstrations before the real section request.

    Completed reports are represented only by a structural profile.  No raw
    excerpt is accepted by this API, which keeps sample facts out of the model
    context by construction.
    """
    if part_id not in FORMAT_ONLY_DEMOS:
        raise KeyError(f"등록되지 않은 보고서 few-shot 섹션: {part_id}")
    profile = {
        "part_id": part_id,
        "completed_sample_reports_profiled": max(0, int(sample_count)),
        "raw_sample_content_in_prompt": False,
        "structure_notes": str(structure_notes or "").strip(),
    }
    return [
        {
            "role": "user",
            "content": (
                f"{SAMPLE_ISOLATION_POLICY}\n\n"
                "[Few-shot 예시 1: 형식과 구성]\n"
                f"{json.dumps(profile, ensure_ascii=False)}\n"
                + (
                    f"현재 사업 근거를 받았다고 가정하고 {output_key} JSON 구조의 형식 예시만 보여라."
                    if output_key else
                    "현재 사업 근거를 받았다고 가정하고 본문 형식 예시만 보여라. 실제 출력 계약은 이후 요청을 따른다."
                )
            ),
        },
        {
            "role": "assistant",
            "content": _example_message_content(part_id, output_key, False),
        },
        {
            "role": "user",
            "content": (
                f"{SAMPLE_ISOLATION_POLICY}\n\n"
                "[Few-shot 예시 2: 샘플 내용 차단]\n"
                "샘플에 있던 사실은 모두 사용할 수 없고 현재 사업 근거만 허용된다. "
                + (
                    f"같은 섹션 형식을 유지한 {output_key} JSON 예시를 보여라."
                    if output_key else
                    "같은 섹션의 본문 형식 예시를 보여라. 실제 출력 계약은 이후 요청을 따른다."
                )
            ),
        },
        {
            "role": "assistant",
            "content": _example_message_content(part_id, output_key, True),
        },
    ]


def format_only_sample_reference(
    part_id: str,
    *,
    structure_notes: str = "",
    sample_count: int = 0,
) -> str:
    """Return a legacy-editor-safe sample field without any sample prose."""
    profile = {
        "part_id": part_id,
        "completed_sample_reports_profiled": max(0, int(sample_count)),
        "raw_sample_content_in_prompt": False,
        "structure_notes": str(structure_notes or "").strip(),
        "format_only_demo": FORMAT_ONLY_DEMOS[part_id],
    }
    return SAMPLE_ISOLATION_POLICY + "\n\n" + json.dumps(profile, ensure_ascii=False, indent=2)


_PLACEHOLDER_PATTERN = re.compile(r"\{\{CURRENT(?:_EVIDENCE_ONLY)?_[A-Z0-9_]+\}\}")


def few_shot_artifact_issues(content: object) -> list[str]:
    value = str(content or "")
    if _PLACEHOLDER_PATTERN.search(value):
        return ["few-shot 형식 예시 자리표시자가 본문에 남음"]
    return []


def validate_format_only_few_shot_catalog(part_ids: Iterable[str] = EXPECTED_PART_IDS) -> None:
    requested = tuple(str(item) for item in part_ids)
    if len(requested) != 27 or len(set(requested)) != 27:
        raise RuntimeError("few-shot 대상 섹션은 중복 없이 정확히 27개여야 합니다.")
    if set(requested) != set(FORMAT_ONLY_DEMOS):
        missing = sorted(set(requested) - set(FORMAT_ONLY_DEMOS))
        extra = sorted(set(FORMAT_ONLY_DEMOS) - set(requested))
        raise RuntimeError(f"27개 섹션 few-shot 카탈로그 불일치: missing={missing}, extra={extra}")
    if len(set(FORMAT_ONLY_DEMOS.values())) != 27:
        raise RuntimeError("27개 섹션은 각각 고유한 형식 전용 few-shot 예시를 가져야 합니다.")
    for part_id, demo in FORMAT_ONLY_DEMOS.items():
        if not _PLACEHOLDER_PATTERN.search(demo):
            raise RuntimeError(f"현재 사업 전용 자리표시자가 없는 few-shot 예시: {part_id}")


validate_format_only_few_shot_catalog()
