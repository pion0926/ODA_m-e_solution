"""Prompt assets for KOICA-style final evaluation report generation.

The prompts are intentionally separated from route logic so each report part can
be refined without touching the editor or package-generation code.
"""

import ast
from pathlib import Path


REPORT_PART_PROMPTS = [
    {
        "id": "grade",
        "title": "평가 등급 결과표",
        "template_targets": ["평가대상 사업명", "평가 기준별 점수", "산정 이유", "종합점수", "KOICA 평가등급", "국무조정실 평가등급"],
        "required_inputs": [
            "사업명, 기간, 예산",
            "DAC 기준별 세부 질문 점수와 산정 근거",
            "업로드 문서별 증빙 요약",
            "미확인 항목 목록",
        ],
        "evidence_pipeline": [
            "criteria[*].evaluationResult.score 및 currentScore4를 기준으로 점수 초안 산정",
            "criteria[*].evaluationResult.summary/sections에서 산정 이유 추출",
            "documents classified by criterion을 근거자료로 연결",
            "근거가 부족한 세부 질문도 확인된 자료 범위에서 보수적으로 서술",
        ],
        "prompt": (
            "평가 등급 결과표를 작성한다. 각 DAC 기준의 핵심 질문별 점수는 /4점 구조를 유지하고, "
            "산정 이유는 1~2문장으로 구체적 근거와 부족 자료를 함께 적는다. 단순 안내문이나 양식 설명을 남기지 않는다. "
            "근거가 제한적이면 점수는 보수적으로 산정하고 사유는 확인된 자료와 사업 맥락 안에서 작성한다."
        ),
    },
    {
        "id": "summary",
        "title": "Ⅰ. 평가결과 요약",
        "template_targets": ["국문 요약", "사업개요 요약", "평가개요 요약", "성과달성도", "기준별 평가결과", "결론과 제언"],
        "required_inputs": [
            "사업개요서 또는 ROD",
            "PDM/ePDM",
            "성과지표 목표치와 종료선 자료",
            "기준별 평가결과",
            "환류과제와 교훈 초안",
        ],
        "evidence_pipeline": [
            "project metadata와 overview 문서에서 사업명/기간/예산/대상지역 추출",
            "achievement/criteria/conclusion 섹션을 3~5개 문단으로 압축",
            "샘플 보고서 문체를 참고하되 문장은 새로 작성",
            "제출 전 요약에서 본문에 없는 새로운 주장을 만들지 않음",
        ],
        "prompt": (
            "KOICA 종료평가 결과보고서의 국문 요약을 작성한다. 사업개요, 평가목적과 범위, 방법, 한계, "
            "성과달성도, DAC 기준별 주요 판단, 결론과 제언을 순서대로 요약한다. '~함', '~음', '~평가됨'의 "
            "공식 보고서 문체를 사용하고, 미확인 사항도 확인된 자료 범위에서 보수적으로 처리한다."
        ),
    },
    {
        "id": "project",
        "title": "Ⅱ. 대상사업 개요",
        "template_targets": ["사업 추진배경", "사업개요", "사업설계매트릭스(PDM)"],
        "required_inputs": [
            "사업개요서/기본계획/ROD",
            "수원국 정책 및 통계자료",
            "대상지역·수혜자 수요 자료",
            "PDM 또는 성과관리 계획",
            "예산 배분, 수행기관, 사업기간 변경 이력",
        ],
        "evidence_pipeline": [
            "reference documents에서 projectTitle, period, budget, target area 추출",
            "PDM 표의 impact/outcome/output/activity/indicator/MOV/assumption을 구조화",
            "정책·수요·문제분석 근거가 없으면 보완 필요 자료를 지정",
            "사업개요 표 셀에는 긴 설명 대신 표에 맞는 압축 문장 생성",
        ],
        "prompt": (
            "대상사업 개요를 작성한다. 추진배경은 수원국 개발과제, 정책 부합성, 대상지역 수요, KOICA 지원 논리를 "
            "근거 중심으로 서술한다. 사업개요는 사업명, 기간, 예산, 지역, 대상, 수행체계, 주요 투입과 산출을 표에 "
            "들어갈 수 있게 간결히 정리한다. PDM은 목표-성과-산출-활동-지표-MOV-가정의 논리 연결을 유지한다."
        ),
    },
    {
        "id": "evaluation_overview",
        "title": "Ⅲ. 평가개요",
        "template_targets": ["평가의 목적과 범위", "평가매트릭스", "평가 방법", "평가의 한계", "평가팀 구성 및 시행체계"],
        "required_inputs": [
            "평가 TOR 또는 과업지시서",
            "평가 질문 및 DAC 기준",
            "문헌조사 목록",
            "면담자/설문/현지조사 계획 및 결과",
            "평가팀 구성, 역할, 일정",
            "제약사항과 완화조치",
        ],
        "evidence_pipeline": [
            "criteria specs에서 기준별 평가질문 생성",
            "documents/evidence를 질문별 자료원으로 매핑",
            "방법론은 문헌검토, 면담, 설문, 현장확인, 삼각검증으로 분류",
            "한계는 자료 한계, 접근 제한, 회상 편향, 표본 한계를 완화조치와 함께 작성",
        ],
        "prompt": (
            "평가개요를 작성한다. 평가 목적과 활용 독자, 평가범위, 기준, 질문, 자료원, 방법, 한계, 품질관리 절차를 "
            "전문 평가자가 실제 수행계획을 설명하듯 작성한다. 평가매트릭스는 질문-자료원-방법-판단기준이 대응되게 한다."
        ),
    },
    {
        "id": "achievement_theory",
        "title": "Ⅳ. 성과달성도 및 사업 변화이론",
        "template_targets": ["성과달성 요약표", "사업 변화이론 분석"],
        "required_inputs": [
            "PDM 지표별 기초선/목표치/중간선/종료선",
            "성과조사·모니터링·최종보고서",
            "MOV 원자료",
            "산출물과 성과 간 인과경로",
            "외부요인과 가정 충족 여부",
        ],
        "evidence_pipeline": [
            "PDM 지표를 성과달성도 표 셀에 매핑",
            "수치가 있으면 달성률을 계산하고 없으면 필요한 원자료를 명시",
            "성과달성도 본문은 목표 대비 종료선, 원인, 자료 신뢰도 순서로 작성",
            "변화이론은 투입-활동-산출-성과-영향 경로와 끊어진 연결을 설명",
        ],
        "prompt": (
            "성과달성도와 변화이론을 작성한다. 지표별 목표 대비 실적을 표 형식으로 정리하고, 수치 근거가 부족한 경우 "
            "필요한 MOV를 정확히 적는다. 변화이론은 사업이 왜 성과를 냈는지 또는 왜 제약을 받았는지를 작동요인과 "
            "비작동요인으로 연결해 분석한다."
        ),
    },
    {
        "id": "criteria_findings",
        "title": "Ⅴ. 기준별 평가결과",
        "template_targets": ["적절성", "일관성", "효과성", "효율성", "지속가능성", "범분야 이슈"],
        "required_inputs": [
            "기준별 배점표",
            "문헌·성과자료·면담·설문 근거",
            "비교사업/정책/국제규범 자료",
            "경제성·효율성 자료",
            "지속가능성 예산·제도·운영 역량 자료",
        ],
        "evidence_pipeline": [
            "criterion별 evaluationResult.sections와 uploaded documents 결합",
            "각 기준은 샘플 보고서처럼 하위 소제목과 ㅇ 문단 중심의 최종 본문체로 작성",
            "평가점수, 판단:, 근거:, 한계:, 점수 산정 이유 같은 작업용 라벨은 본문에 쓰지 않음",
            "점수와 본문 판단은 정합화하되 점수는 등급표에서만 직접 표기",
        ],
        "prompt": (
            "DAC 기준별 평가결과를 작성한다. 각 기준은 샘플 보고서처럼 평가질문을 물음표로 반복하지 않고 "
            "하위 소제목과 줄글 평가문으로 전개한다. 근거, 한계, 보완 필요사항은 별도 메모 라벨이 아니라 문단 안에 자연스럽게 통합한다. "
            "점수는 등급표에서 관리하므로 기준별 본문 첫 줄에 평가점수를 쓰지 않는다."
        ),
    },
    {
        "id": "conclusion_lessons",
        "title": "Ⅵ. 결론, 교훈, 제언",
        "template_targets": ["결론", "작동요인", "비작동요인", "교훈", "제언/환류과제"],
        "required_inputs": [
            "기준별 평가결과 전체",
            "성과달성도와 변화이론 분석",
            "운영·관리상 제약",
            "이해관계자별 실행 가능 조치",
            "후속사업 설계에 반영할 교훈",
        ],
        "evidence_pipeline": [
            "결론은 본문에서 이미 분석한 내용만 종합",
            "작동요인은 성과달성에 기여한 설계·수행·환경 요인을 추출",
            "비작동요인은 지연, 자료공백, 제도·예산·인력 제약 등으로 분류",
            "제언은 관찰사항-환류과제-이행부서-선정사유-필요자료로 구조화",
            "교훈은 후속 사업 체크리스트 질문으로 변환",
        ],
        "prompt": (
            "결론, 교훈, 제언을 작성한다. 결론에는 새로운 사실을 넣지 않고 평가목적과 본문 분석을 종합한다. "
            "작동요인과 비작동요인은 변화이론 및 기준별 평가결과와 연결한다. 제언은 실행 주체와 조치가 분명해야 하며, "
            "교훈은 후속 사업에서 바로 점검 가능한 질문 형태로 변환한다."
        ),
    },
    {
        "id": "annexes",
        "title": "첨부",
        "template_targets": ["영문 요약", "현지조사 개요", "일별 활동내역", "면담자 목록 및 주요 질문", "설문 결과", "참고문헌"],
        "required_inputs": [
            "영문 요약 작성용 국문 요약",
            "출장/원격조사 일정",
            "면담자 목록과 질문지",
            "설문 원자료와 요약통계",
            "참고문헌 목록",
        ],
        "evidence_pipeline": [
            "본문에 사용된 자료만 참고문헌으로 정리",
            "현지조사/면담/설문 자료가 없으면 첨부별로 필요한 파일을 명시",
            "영문 요약은 국문 요약과 점수·판단이 일치하게 작성",
        ],
        "prompt": (
            "첨부자료를 작성한다. 영문 요약은 국문 요약과 동일한 판단을 유지한다. 현지조사, 면담, 설문, 참고문헌은 "
            "실제 제출 가능한 목록 형식으로 정리하고, 자료가 없으면 정확한 추가 필요 자료를 적는다."
        ),
    },
]


REPORT_MASTER_PROMPT = """너는 KOICA 종료평가 결과보고서 작성 책임자다.

작성 원칙:
- 5-1 종료평가 결과보고서 양식의 장·절 순서를 그대로 따른다.
- 양식의 파란 안내문, TIP, 작성 예시는 최종 산출물에 남기지 않는다.
- 샘플 결과보고서는 문체, 증거 밀도, 평가 논리, 섹션 커버리지를 참고하는 RAG 자료이며 문장을 복사하거나 가깝게 바꾸지 않는다.
- 모든 파트는 제출 가능한 공식 보고서 문체로 작성한다.
- 자료가 부족한 경우에도 빈칸을 두지 말고, 확인된 자료와 사업 맥락을 바탕으로 보수적으로 작성한다.
- 점수, 표, 본문 판단, 결론과 제언의 논리 일관성을 유지한다.
- 결론에서는 본문에서 다루지 않은 새로운 사실을 추가하지 않는다.
"""

RELEVANCE_SLOTS = [
    "예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)",
    "수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)",
    "사업개요서 또는 사업요청서 (PCP)",
    "협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)",
    "한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서",
    "집행계획서 및 최신 PDM (Project Design Matrix)",
    "변화이론(ToC) 도식도 및 문제나무 분석 자료",
    "부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)",
    "정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)",
    "사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록",
]

COHERENCE_SLOTS = [
    "유사 사업 및 타 공여 개입 맵 (Mapping 자료)",
    "타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)",
    "기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)",
    "이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서",
    "운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록",
    "국내 타 기관 및 KOICA 타 사업과의 협의 기록",
    "인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서",
    "국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서",
    "중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역",
]

EFFECTIVENESS_SLOTS = [
    "최신 PDM 및 성과지표 실적표",
    "산출물 완료보고서 및 활동별 결과보고서",
    "교육·서비스·시설·장비 제공 실적 자료",
    "기준선/종료선 조사자료 (Baseline/Endline)",
    "수혜자 만족도 조사 및 현장점검 기록",
    "성과 기여도 분석 및 외부요인 검토 메모",
    "성별·지역별·취약계층 분리 통계",
    "사회적 소외계층 참여자 명단 및 지원 실적",
    "수혜자 인터뷰 또는 사례 기록",
]

EFFICIENCY_SLOTS = [
    "예산 집행내역 및 집행률 분석표",
    "예산 변경 내역 및 승인 문서",
    "단가 비교 또는 비용 적정성 검토 자료",
    "사업 일정표 및 마일스톤 이행 현황",
    "조달 계획, 입찰·계약 문서",
    "지연 사유 및 시정조치 기록",
    "투입 대비 산출 분석표",
    "인력 투입 계획 및 활동별 투입 기록",
    "주요 활동 간 연계·조정 회의록",
]

SUSTAINABILITY_SLOTS = [
    "운영·유지관리 계획",
    "지방정부 또는 파트너 기관 예산 확약서",
    "인수인계 문서 및 운영 매뉴얼",
    "현지 인력 역량강화 계획 및 교육 결과",
    "리스크·위기대응 계획",
    "운영 담당 조직의 역할분담 문서",
    "정책·제도 반영 또는 공식 승인 문서",
    "지역사회 참여 및 수용성 확인 자료",
    "장기 재원조달 또는 수익모델 검토 자료",
]

ALL_DAC_SLOTS = {
    "relevance": RELEVANCE_SLOTS,
    "coherence": COHERENCE_SLOTS,
    "effectiveness": EFFECTIVENESS_SLOTS,
    "efficiency": EFFICIENCY_SLOTS,
    "sustainability": SUSTAINABILITY_SLOTS,
}

EDITOR_PART_REFERENCE_PIPELINES = {
    "cover": {"criteria": ["relevance"], "evidence": {"relevance": ["사업개요서 또는 사업요청서 (PCP)"]}, "notes": ["사업명, 기간, 예산, 평가책임자/수행기관 확인"]},
    "toc": {"criteria": [], "evidence": {}, "notes": ["5-1 원본 양식과 최종 편집 문서 구조 참조"]},
    "notice": {"criteria": [], "evidence": {}, "notes": ["5-1 원본 양식 공지 문구와 FAQ 참조"]},
    "grade": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["기준별 평가결과 JSON과 전체 업로드 증빙으로 점수/산정 이유 작성"]},
    "summary-ko": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["사업개요, PDM, 성과달성도, 기준별 평가결과, 결론/환류/교훈 종합"]},
    "project-background": {"criteria": ["relevance"], "evidence": {"relevance": RELEVANCE_SLOTS[:5]}, "notes": ["수원국 수요, 정책 부합성, 사업 형성 배경 작성"]},
    "project-overview": {"criteria": ["relevance"], "evidence": {"relevance": ["사업개요서 또는 사업요청서 (PCP)"]}, "notes": ["사업개요서 최종본 우선 사용"]},
    "pdm": {"criteria": ["relevance", "effectiveness"], "evidence": {"relevance": RELEVANCE_SLOTS[5:8], "effectiveness": EFFECTIVENESS_SLOTS[:1]}, "notes": ["PDM, ToC, 문제나무, 역할분담 자료로 논리모형 작성"]},
    "eval-purpose": {"criteria": ["relevance"], "evidence": {"relevance": ["사업개요서 또는 사업요청서 (PCP)", "집행계획서 및 최신 PDM (Project Design Matrix)"]}, "notes": ["평가 목적/범위는 사업개요와 양식/FAQ 기준으로 작성"]},
    "eval-matrix": {"criteria": list(ALL_DAC_SLOTS), "evidence": {**ALL_DAC_SLOTS, "effectiveness": EFFECTIVENESS_SLOTS[:2]}, "notes": ["DAC 기준-평가질문-지표-자료출처-방법 매핑"]},
    "eval-methods": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["업로드 문헌 전체, 면담/설문/현장점검 기록을 방법론 자료원으로 사용"]},
    "eval-limitations": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["미업로드 슬롯과 자료공백을 평가 한계로 정리"]},
    "eval-team": {"criteria": ["relevance"], "evidence": {"relevance": ["사업개요서 또는 사업요청서 (PCP)"]}, "notes": ["평가책임자, 수행기관, 품질관리 체계 확인"]},
    "achievement": {"criteria": ["relevance", "effectiveness"], "evidence": {"relevance": ["집행계획서 및 최신 PDM (Project Design Matrix)"], "effectiveness": EFFECTIVENESS_SLOTS[:6]}, "notes": ["PDM 지표, 목표/실적, MOV, 성과자료 작성"]},
    "criteria-relevance": {"criteria": ["relevance"], "evidence": {"relevance": RELEVANCE_SLOTS}, "notes": ["적절성 10개 슬롯만 사용"]},
    "criteria-coherence": {"criteria": ["coherence"], "evidence": {"coherence": COHERENCE_SLOTS}, "notes": ["일관성 9개 슬롯만 사용"]},
    "criteria-effectiveness": {"criteria": ["effectiveness"], "evidence": {"effectiveness": EFFECTIVENESS_SLOTS}, "notes": ["효과성 9개 슬롯만 사용"]},
    "criteria-efficiency": {"criteria": ["efficiency"], "evidence": {"efficiency": EFFICIENCY_SLOTS}, "notes": ["효율성 9개 슬롯만 사용"]},
    "criteria-sustainability": {"criteria": ["sustainability"], "evidence": {"sustainability": SUSTAINABILITY_SLOTS}, "notes": ["지속가능성 9개 슬롯만 사용"]},
    "criteria-crosscutting": {"criteria": ["coherence", "effectiveness", "sustainability"], "evidence": {"coherence": COHERENCE_SLOTS[6:8], "effectiveness": EFFECTIVENESS_SLOTS[6:9], "sustainability": ["지역사회 참여 및 수용성 확인 자료"]}, "notes": ["젠더, 환경, 인권, 취약계층, 세이프가드 자료 중심"]},
    "criteria-other": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["사업 특수성, 혁신성, 확산 가능성은 전체 증빙에서 확인"]},
    "conclusion": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["기준별 평가결과와 성과달성도만 종합하고 새 사실 추가 금지"]},
    "working-factors": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["성과 달성에 기여한 설계·집행·환경 요인 추출"]},
    "nonworking-factors": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["미달성 지표, 변경요청, 지연, 리스크, 증빙공백 추출"]},
    "theory": {"criteria": ["relevance", "effectiveness"], "evidence": {"relevance": ["변화이론(ToC) 도식도 및 문제나무 분석 자료", "집행계획서 및 최신 PDM (Project Design Matrix)"], "effectiveness": EFFECTIVENESS_SLOTS[:6]}, "notes": ["투입-활동-산출-성과 경로와 작동/비작동 요인 연결"]},
    "feedback": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["비작동 요인과 리스크/지연/운영관리 자료를 실행 과제로 전환"]},
    "lessons": {"criteria": list(ALL_DAC_SLOTS), "evidence": ALL_DAC_SLOTS, "notes": ["FAQ와 샘플 보고서 문체를 참조해 후속사업 체크리스트형 교훈 작성"]},
}

EDITOR_REPORT_PARTS = [
    {
        "id": "cover",
        "sectionId": "title",
        "title": "(1) 표지",
        "sampleHeadings": ["종료평가 결과보고서", "평가책임자", "평가수행기관"],
        "requiredInputs": ["사업명", "평가 기준월", "평가책임자", "평가수행기관", "KOICA/World Friends 로고 유지 여부"],
        "prompt": (
            "표지 영역만 수정한다. 기존 표지 문구는 'ㅇㅇ사업 종료평가 결과보고서', '2023. 12', "
            "'평가책임자 OOO', '평가수행기관 OOO(혹은 로고)'이다. "
            "ㅇㅇ사업은 사업개요서의 사업명으로 대체하고, 날짜는 현재 기준 연월로 작성한다. "
            "평가책임자와 평가수행기관은 사업개요서 또는 현재 자료에서 확인되는 경우만 반영하고, 없으면 '자료 기반 보수 작성'로 남긴다. "
            "사용자 입력값은 이 네 가지 표지 필드에만 반영한다. 목차, 공지, 평가등급표, 본문, 첨부 내용은 절대 작성하지 않는다. "
            "출력은 표지에 들어갈 텍스트만 다음 형식으로 반환한다: "
            "[사업명]\\n종료평가 결과보고서\\n\\n[YYYY. MM]\\n\\n평가책임자 [값]\\n평가수행기관 [값]"
        ),
    },
    {
        "id": "toc",
        "sectionId": "toc",
        "title": "(2) 목차 및 작성 쪽수",
        "sampleHeadings": ["목 차", "평가 등급 결과표", "평가결과 요약"],
        "requiredInputs": ["최종 문서 페이지 수", "본문/첨부 구성", "삭제된 안내문 및 예시 영역"],
        "prompt": "목차는 원본 양식의 항목 순서를 유지한다. 실제 쪽수는 편집 완료 후 갱신 대상으로 두고, 불필요한 TIP 문구나 작성자 안내문은 제거한다.",
    },
    {
        "id": "notice",
        "sectionId": "notice",
        "title": "(3) 평가보고서 관련 공지",
        "sampleHeadings": ["평가보고서 관련 공지", "평가자", "평가품질관리"],
        "requiredInputs": ["KOICA 평가보고서 고지 문구", "평가 책임 및 한계", "발간/제출 기준"],
        "prompt": "공지 문구는 제출용 문서의 공식 안내문으로 정리한다. 작성 예시, TIP, 삭제 지시는 남기지 않는다.",
    },
    {
        "id": "grade",
        "sectionId": "grade",
        "title": "(4) 평가등급 결과표",
        "sampleHeadings": ["평가 등급 결과표", "평가 기준", "종합 점수", "KOICA 평가등급"],
        "requiredInputs": ["DAC 기준별 점수", "세부 질문별 판단 근거", "증빙자료 목록", "종합점수 및 등급"],
        "prompt": "평가등급 결과표만 작성한다. /4점 칸은 보존하고 실제 점수는 왼쪽 빈 칸에 넣는다. 산정 이유는 근거 중심 1문장으로 쓰고, 증빙이 부족하면 '확인된 근거 범위 내 보수적 판단'로 쓴다. 평가자 안내문 두 줄은 제거한다.",
    },
    {
        "id": "summary-ko",
        "sectionId": "summary",
        "title": "(5) I. 평가결과 요약 1. 국문 요약",
        "sampleHeadings": ["Ⅰ. 평가결과 요약", "1. 국문 요약", "평가결과 요약"],
        "requiredInputs": ["사업개요", "평가목적/범위", "성과달성도", "기준별 평가결과", "결론/제언"],
        "prompt": "국문 요약은 완성본 샘플의 밀도와 문체를 참고하여 제출용 요약문으로 작성한다. 본문에 없는 새 사실을 만들지 말고, 부족한 근거는 확인된 자료 범위에서 명시한다.",
    },
    {
        "id": "project-background",
        "sectionId": "project-background",
        "title": "(6) II. 대상사업개요 1. 사업 추진배경",
        "sampleHeadings": ["Ⅱ. 대상사업 개요", "1. 사업 추진배경", "추진배경"],
        "requiredInputs": ["사업개요서", "수원국 개발수요", "정책/전략 부합성", "사업 형성 배경"],
        "prompt": "사업 추진배경은 수원국 수요, 정책적 필요, KOICA 지원 필요성을 근거 중심으로 서술한다. 샘플 보고서의 논리 구조만 참고하고 문장은 새로 쓴다.",
    },
    {
        "id": "project-overview",
        "sectionId": "project-overview",
        "title": "(7) II. 대상사업개요 2. 사업개요",
        "sampleHeadings": ["2. 사업 개요", "사업개요", "사업명", "사업기간"],
        "requiredInputs": ["사업개요서 최종본", "사업명", "기간", "예산", "대상지역", "수혜자", "수행기관"],
        "prompt": "사업개요서 최종본을 우선 근거로 삼아 사업명, 기간, 예산, 대상지역, 수혜자, 주요 활동과 산출물을 표/문단 형식에 맞게 채운다.",
    },
    {
        "id": "pdm",
        "sectionId": "pdm",
        "title": "(8) II. 대상사업개요 3. 사업설계매트릭스(PDM)",
        "sampleHeadings": ["사업설계매트릭스", "PDM", "Project Design Matrix"],
        "requiredInputs": ["PDM/ePDM", "성과관리계획", "지표", "MOV", "가정"],
        "prompt": "PDM은 투입-활동-산출-성과-상위목표의 논리 연결을 유지해 정리한다. 지표/MOV/가정이 없으면 필요한 자료명을 구체적으로 적는다.",
    },
    {
        "id": "eval-purpose",
        "sectionId": "eval-purpose",
        "title": "(9) III. 평가개요 1. 평가의 목적과 범위",
        "sampleHeadings": ["Ⅲ. 평가개요", "1. 평가의 목적과 범위", "평가 목적"],
        "requiredInputs": ["평가 TOR", "평가 대상 기간/범위", "평가 활용 목적"],
        "prompt": "평가의 목적, 대상, 범위, 활용 계획을 공식 평가보고서 문체로 정리한다.",
    },
    {
        "id": "eval-matrix",
        "sectionId": "eval-matrix",
        "title": "(10) III. 평가개요 2. 평가매트릭스",
        "sampleHeadings": ["평가매트릭스", "Evaluation Matrix", "평가질문"],
        "requiredInputs": ["DAC 기준", "평가질문", "지표", "자료출처", "평가방법"],
        "prompt": "평가매트릭스는 기준-질문-지표-자료출처-방법이 서로 맞물리게 작성한다. 현재 확보 자료와 부족 자료를 구분한다.",
    },
    {
        "id": "eval-methods",
        "sectionId": "eval-methods",
        "title": "(11) III. 평가개요 3. 평가방법",
        "sampleHeadings": ["3. 평가 방법", "문헌조사", "면담", "설문"],
        "requiredInputs": ["문헌조사 목록", "면담/설문/현지조사 계획", "분석 방법"],
        "prompt": "평가방법은 문헌검토, 정량/정성자료 분석, 이해관계자 면담, 삼각검증 절차를 실제 수행한 것처럼 구체화하되 근거 없는 수행 사실은 만들지 않는다.",
    },
    {
        "id": "eval-limitations",
        "sectionId": "eval-limitations",
        "title": "(12) III. 평가개요 4. 평가의 한계",
        "sampleHeadings": ["4. 평가의 한계", "제약", "한계"],
        "requiredInputs": ["자료 한계", "현장 접근성", "응답 편향", "기간 제약", "완화 조치"],
        "prompt": "평가 한계는 한계와 완화 조치를 함께 제시한다. 단순 변명이 아니라 결과 해석 시 주의사항으로 작성한다.",
    },
    {
        "id": "eval-team",
        "sectionId": "eval-team",
        "title": "(13) III. 평가개요 5. 평가팀 구성 및 시행체계",
        "sampleHeadings": ["5. 평가팀 구성", "시행체계", "평가팀"],
        "requiredInputs": ["평가책임자", "팀원 역할", "수행기관", "검토/품질관리 체계"],
        "prompt": "평가팀 구성과 역할, 수행체계, 품질관리 절차를 간결하게 작성한다. 미확정 인력은 확인된 자료 범위에서 표시한다.",
    },
    {
        "id": "achievement",
        "sectionId": "achievement",
        "title": "(14) IV. 성과 달성도",
        "sampleHeadings": ["Ⅳ. 성과달성도", "성과 달성도", "사업변화이론"],
        "requiredInputs": ["PDM 지표", "목표/실적", "성과자료", "MOV", "달성/미달성 원인"],
        "prompt": "성과 달성도는 지표별 목표 대비 실적과 근거, 달성 여부, 미달성 원인을 작성한다. 수치가 없으면 필요한 증빙을 명시한다.",
    },
    {
        "id": "criteria-relevance",
        "sectionId": "criteria-relevance",
        "title": "(15) V. 기준별 평가결과 1. 적절성",
        "sampleHeadings": ["1. 적절성", "Relevance", "적절성"],
        "requiredInputs": ["정책/수요 부합성", "사업설계 적절성", "대상자 수요", "점수 근거"],
        "prompt": "적절성은 수요, 정책, 사업설계의 부합성을 샘플 보고서식 소제목과 줄글 문단으로 평가한다. 평가점수, 판단:, 근거:, 한계:, 점수 이유 라벨은 쓰지 않는다.",
    },
    {
        "id": "criteria-coherence",
        "sectionId": "criteria-coherence",
        "title": "(16) V. 기준별 평가결과 2. 일관성",
        "sampleHeadings": ["2. 일관성", "Coherence", "내적 일관성", "외적 일관성"],
        "requiredInputs": ["KOICA/정부 정책 연계", "타 사업 중복/보완성", "공여기관 연계"],
        "prompt": "일관성은 내적 일관성과 외적 일관성을 구분하되, 샘플 보고서식 소제목과 문단으로 중복 회피, 보완성, 시너지 근거를 제시한다. 작업용 라벨과 점수 표기는 쓰지 않는다.",
    },
    {
        "id": "criteria-effectiveness",
        "sectionId": "criteria-effectiveness",
        "title": "(17) V. 기준별 평가결과 3. 효과성",
        "sampleHeadings": ["3. 효과성", "Effectiveness", "성과"],
        "requiredInputs": ["산출/성과 달성", "목표 대비 실적", "수혜자 변화", "성과 근거"],
        "prompt": "효과성은 산출물, 성과, 형평성/포용, 성과 기여요인을 샘플 보고서식 하위 소제목과 줄글로 평가한다. 평가질문을 물음표로 반복하거나 평가점수/판단/근거/한계 라벨을 쓰지 않는다.",
    },
    {
        "id": "criteria-efficiency",
        "sectionId": "criteria-efficiency",
        "title": "(18) V. 기준별 평가결과 4. 효율성",
        "sampleHeadings": ["4. 효율성", "Efficiency", "투입", "예산"],
        "requiredInputs": ["예산 집행", "일정", "투입 대비 산출", "관리 효율"],
        "prompt": "효율성은 예산, 일정, 조달·계약, 투입 대비 산출, 운영관리 측면을 샘플 보고서식 문단으로 평가한다. 경제성 근거의 한계는 문단 안에 자연스럽게 쓰고 점수 산정 메모로 쓰지 않는다.",
    },
    {
        "id": "criteria-sustainability",
        "sectionId": "criteria-sustainability",
        "title": "(19) V. 기준별 평가결과 5. 지속가능성",
        "sampleHeadings": ["5. 지속가능성", "Sustainability", "지속가능성 준비도"],
        "requiredInputs": ["제도/조직/재원 지속성", "역량 이전", "운영 주체", "위험요인"],
        "prompt": "지속가능성은 제도, 조직, 재원, 역량, 운영 체계를 기준으로 편익 지속 가능성을 샘플 보고서식 소제목과 줄글 문단으로 평가한다. 점수와 작업용 라벨은 본문에 쓰지 않는다.",
    },
    {
        "id": "criteria-crosscutting",
        "sectionId": "criteria-crosscutting",
        "title": "(20) V. 기준별 평가결과 6. 범분야 이슈",
        "sampleHeadings": ["범분야", "젠더", "환경", "인권", "취약계층"],
        "requiredInputs": ["젠더/환경/인권/취약계층 고려", "세이프가드", "포용성 근거"],
        "prompt": "범분야 이슈는 젠더, 환경, 인권, 취약계층 포용 여부를 근거가 있는 항목 중심으로 샘플 보고서식 문단으로 평가한다. 자료 한계는 평가 불가 메모가 아니라 본문 문장으로 처리한다.",
    },
    {
        "id": "criteria-other",
        "sectionId": "criteria-other",
        "title": "(21) V. 기준별 평가결과 7. 그 외 평가기준",
        "sampleHeadings": ["그 외 평가기준", "기타 평가기준"],
        "requiredInputs": ["사업 특수 기준", "혁신성", "확산 가능성", "디지털/ODA 특성"],
        "prompt": "그 외 평가기준은 본 사업의 특수성에 맞는 기준만 샘플 보고서식 문단으로 다룬다. 해당 없음이면 짧은 본문 문장으로 사유를 쓰고 임의 기준이나 점수 메모를 만들지 않는다.",
    },
    {
        "id": "conclusion",
        "sectionId": "conclusion",
        "title": "(22) VI. 결론 1. 결론",
        "sampleHeadings": ["Ⅵ. 결론", "1. 결론"],
        "requiredInputs": ["평가결과 종합", "성과/한계", "점수와 기준별 판단"],
        "prompt": "결론은 본문 평가결과를 종합한다. 새로운 사실을 추가하지 않고, 사업의 성과와 한계를 균형 있게 정리한다.",
    },
    {
        "id": "working-factors",
        "sectionId": "working-factors",
        "title": "(23) VI. 결론 2. 작동요인 및 비작동요인 (1) 작동 요인",
        "sampleHeadings": ["작동요인", "What worked"],
        "requiredInputs": ["성과 달성에 기여한 요인", "설계/집행/환경 요인", "근거"],
        "prompt": "작동요인은 성과 달성에 기여한 원인을 근거와 함께 제시한다.",
    },
    {
        "id": "nonworking-factors",
        "sectionId": "nonworking-factors",
        "title": "(24) VI. 결론 2. 작동요인 및 비작동요인 (2) 비작동 요인",
        "sampleHeadings": ["비작동요인", "What did not work"],
        "requiredInputs": ["성과 저해 요인", "자료/집행/제도 한계", "근거"],
        "prompt": "비작동요인은 성과 달성을 저해한 원인을 구체적으로 분석한다. 책임 추궁식 표현은 피하고 개선 관점으로 쓴다.",
    },
    {
        "id": "theory",
        "sectionId": "theory",
        "title": "(25) VI. 결론 2. 작동요인 및 비작동요인 (3) 변화이론 분석",
        "sampleHeadings": ["변화이론", "To-Be", "사업 종료단계"],
        "requiredInputs": ["투입-활동-산출-성과 경로", "가정 충족 여부", "작동/비작동 요인"],
        "prompt": "변화이론 분석은 사업의 성과 경로가 실제로 어떻게 작동했는지 설명한다.",
    },
    {
        "id": "feedback",
        "sectionId": "feedback",
        "title": "(26) VI. 결론 3. 환류과제 및 교훈 (1) 환류과제",
        "sampleHeadings": ["제언", "환류과제", "개선과제"],
        "requiredInputs": ["작동요인·비작동요인", "기준별 평가결과", "연차점검/종료보고서", "인터뷰·현장조사", "PDM·성과관리 자료"],
        "prompt": (
            "환류과제는 샘플 보고서의 '제언' 표처럼 작성한다. 우선 prior_analysis_sections의 결론, 작동요인, 비작동요인, 변화이론 분석과 "
            "저장된 기준별 평가결과를 검토하고, 부족한 근거는 reference_corpus의 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, "
            "사업변경·운영관리·기자재·인력 관련 문서로 보강한다. "
            "각 항목은 반드시 다음 필드를 반복한다: 구분: 사업모델 변경제언/사업관리 개선제언/개발환경 및 개입 특성상의 구조적 한계 분석 제언 중 하나, "
            "제언: 이해관계자가 실행할 수 있는 구체적 조치 1~2문장, 이해관계자: 코이카 경영진/코이카 사업 관계자/코이카 사업 수행파트너/수원국·수원기관/성과관리·평가전문가 등, "
            "선정 사유: 평가근거와 기대효과, 후속 확인자료: 이행 여부를 확인할 문서나 증빙. "
            "관찰된 문제를 그대로 반복하지 말고, 샘플처럼 번호가 붙은 공식 제언 문장으로 쓴다."
        ),
    },
    {
        "id": "lessons",
        "sectionId": "lessons",
        "title": "(27) VI. 결론 3. 환류과제 및 교훈 (2) 교훈",
        "sampleHeadings": ["교훈", "Lessons Learned", "체크리스트"],
        "requiredInputs": ["향후 사업에 적용할 교훈", "분야/일반 구분", "이전년도 교훈 중복 여부", "체크리스트 질문"],
        "prompt": (
            "교훈은 샘플 보고서의 작동요인·비작동요인 교훈처럼 작성한다. prior_analysis_sections의 작동요인, 비작동요인, 환류과제, 변화이론 분석을 먼저 보고, "
            "필요하면 reference_corpus의 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료를 보강 근거로 사용한다. "
            "각 항목은 반드시 다음 형식을 반복한다: 교훈 N. (짧은 관찰사항 제목) / 교훈 내용: 특정 사건 설명이 아니라 후속 유사 사업에 적용할 일반화된 원칙 1~2문장 / "
            "분야/일반 구분: 일반 또는 분야 / 이전년도 교훈 중복 여부: 신규 또는 중복(연도/분야) / 체크리스트 질문: M&E에서 바로 점검 가능한 질문 1문장. "
            "좋은 작동요인은 확산 가능한 설계 원칙으로, 비작동요인은 사전 점검·위험관리 교훈으로 전환한다. 좁은 칸인 분야/일반 구분과 중복 여부에는 긴 설명을 넣지 않는다."
        ),
    },
]


EDITOR_PART_DETAIL_PROMPTS = {
    "cover": [
        "사업명은 project.title을 최우선으로 사용하고, 평가책임자/수행기관은 원문 근거가 없으면 확인된 자료 범위에서 둔다.",
        "표지 외 목차·공지·등급표·본문 문장은 절대 생성하지 않는다.",
    ],
    "toc": [
        "5-1 종료평가 결과보고서 양식의 장·절 순서를 유지한다.",
        "실제 쪽수는 한글 최종 편집 단계에서 갱신 대상으로 표시한다.",
    ],
    "notice": [
        "공식 공지 문구만 남기고 작성 예시, TIP, 삭제 지시 문구를 제거한다.",
        "평가자·품질심의 정보가 없으면 확인된 자료 범위에서 표시한다.",
    ],
    "grade": [
        "content_inputs.criteria의 기준별 점수와 grade_score_rows의 점수를 그대로 사용한다.",
        "기준별 점수, 산정이유, 종합점수, 국무조정실 등급, KOICA 등급이 서로 일치해야 한다.",
        "점수가 존재하는 기준을 1점 기본값으로 되돌리지 않는다.",
    ],
    "summary-ko": [
        "사업개요, 평가개요, 성과달성도, 기준별 평가결과, 결론·교훈을 3~5개 문단으로 압축한다.",
        "본문에 없는 새 사실을 만들지 않고, 점수·등급과 핵심 보완사항을 함께 요약한다.",
    ],
    "project-background": [
        "수원국 보건·지역 맥락, 수혜자 수요, 정책 부합성, KOICA 지원 필요성을 근거 중심으로 연결한다.",
        "정책명·전략명·기초조사 근거가 확인되는 경우 문장 안에 반영한다.",
    ],
    "project-overview": [
        "사업명, 기간, 예산, 대상지역, 수혜자, 수행기관, 주요 산출물과 활동을 빠짐없이 정리한다.",
        "사업개요서와 PCP를 우선 근거로 사용하고 상충 정보는 추가 확인 필요로 표시한다.",
    ],
    "pdm": [
        "상위목표-성과-산출-활동-지표-MOV-가정의 논리 연결을 표처럼 정리한다.",
        "PDM/ToC/문제나무/역할분담 문서가 있으면 설계 타당성 판단과 연결한다.",
    ],
    "eval-purpose": [
        "평가 목적, 대상, 범위, 활용 주체, 평가기간과 기준을 공식 보고서 문체로 쓴다.",
        "평가 범위가 문서로 확인되지 않으면 추정하지 않는다.",
    ],
    "eval-matrix": [
        "DAC 기준별 평가질문, 판단지표, 자료출처, 방법, 한계를 한 세트로 맞춘다.",
        "등록된 자료목록과 기준별 평가결과를 자료출처에 반영한다.",
    ],
    "eval-methods": [
        "문헌검토, 인터뷰, 설문, 현장점검, 정량자료 분석, 삼각검증을 실제 근거와 연결한다.",
        "수행 근거가 없는 방법은 실행 사실처럼 쓰지 않고 계획/한계로 구분한다.",
    ],
    "eval-limitations": [
        "자료 공백, 접근 제약, 시간 제약, 표본 한계, 정량지표 한계를 결과 해석 영향과 함께 쓴다.",
        "각 한계마다 완화 조치 또는 보완 확인자료를 제시한다.",
    ],
    "eval-team": [
        "평가책임자, 분야전문가, 보조원, 품질관리·검토 체계를 역할 중심으로 정리한다.",
        "인명·소속이 확인되지 않으면 확인된 자료 범위에서 남긴다.",
    ],
    "achievement": [
        "PDM 지표별 목표-실적-달성여부-근거-MOV-미달성 원인을 구조화한다.",
        "성과자료가 충분하면 성과 달성 문장으로 쓰고, 수치가 없을 때만 보완자료를 요구한다.",
    ],
    "criteria-relevance": [
        "수요·정책·설계 타당성·상황변화 대응을 평가질문별로 판단한다.",
        "근거문서와 한계, 보완 필요사항은 샘플 보고서식 본문 문단 안에 자연스럽게 통합한다.",
        "평가질문을 그대로 묻거나 평가점수/판단/근거/한계 라벨로 닫지 않는다.",
    ],
    "criteria-coherence": [
        "내적 일관성과 외적 일관성을 분리하고, 중복 회피·보완성·조정 메커니즘을 평가한다.",
        "타 공여기관·국내 유사사업·국제규범과의 관계를 근거로 반영한다.",
    ],
    "criteria-effectiveness": [
        "산출물 달성, 성과 달성, 형평성/취약계층 포용, 성과 기여요인을 구분한다.",
        "정량 성과와 인터뷰 근거를 함께 쓰되, 성과 과장은 피한다.",
    ],
    "criteria-efficiency": [
        "예산 집행, 일정 준수, 조달·계약, 투입 대비 산출, 운영관리 효율성을 평가한다.",
        "경제성 분석 자료가 있으면 효율성 종합 판단의 근거 문장으로 반영한다.",
    ],
    "criteria-sustainability": [
        "재정, 제도, 조직, 인력, 유지관리, 지역사회 수용성을 기준으로 편익 지속 가능성을 판단한다.",
        "사후관리·기자재·현지 운영 주체 자료를 핵심 근거로 사용한다.",
    ],
    "criteria-crosscutting": [
        "젠더, 환경, 인권, 취약계층, 사회적 포용을 근거가 있는 항목만 평가한다.",
        "자료가 없으면 해당 항목을 평가 불가로 구분하고 필요한 증빙을 제시한다.",
    ],
    "criteria-other": [
        "사업 특수성상 추가 평가기준이 의미 있을 때만 작성한다.",
        "해당 없음이면 간단한 사유를 쓰고 장황한 임의 기준을 만들지 않는다.",
    ],
    "conclusion": [
        "앞선 성과달성도와 기준별 평가결과를 종합하되 새 사실을 추가하지 않는다.",
        "사업의 성과, 한계, 후속 조치 방향을 균형 있게 정리한다.",
    ],
    "working-factors": [
        "성과 달성에 기여한 설계·수행·협력·맥락 요인을 근거와 함께 정리한다.",
        "단순 칭찬이 아니라 왜 작동했는지 설명한다.",
    ],
    "nonworking-factors": [
        "성과를 저해한 자료·집행·제도·환경 요인을 개선 관점으로 분석한다.",
        "책임 추궁 표현보다 재발 방지와 설계 보완에 초점을 둔다.",
    ],
    "theory": [
        "투입-활동-산출-성과 경로가 실제로 어떻게 작동했는지 설명한다.",
        "성립한 가정과 깨진 가정을 작동요인/비작동요인과 연결한다.",
    ],
    "feedback": [
        "샘플 보고서의 제언 표처럼 구분, 제언, 이해관계자 중심으로 작성한다.",
        "참고 우선순위는 비작동요인, 작동요인, 변화이론 분석, 기준별 평가결과, 연차점검/종료보고서, 인터뷰·현장조사, PDM·성과관리 자료 순이다.",
        "구분은 사업모델 변경제언, 사업관리 개선제언, 개발환경 및 개입 특성상의 구조적 한계 분석 제언 중에서 고른다.",
        "제언은 관찰된 문제를 반복하지 말고 이해관계자가 실제 실행할 조치로 쓴다.",
        "각 항목은 '구분:', '제언:', '이해관계자:', '선정 사유:', '후속 확인자료:' 필드를 포함한다.",
    ],
    "lessons": [
        "작동요인은 확산 가능한 설계·수행 원칙으로, 비작동요인은 사전 점검·위험관리 교훈으로 정리한다.",
        "참고 우선순위는 작동요인, 비작동요인, 환류과제, 변화이론 분석, 기준별 평가결과, 연차점검/종료보고서, 인터뷰·현장조사, PDM·성과관리 자료 순이다.",
        "각 교훈은 '교훈 N. (관찰사항 제목)', '교훈 내용:', '분야/일반 구분:', '이전년도 교훈 중복 여부:', '체크리스트 질문:' 필드를 모두 포함한다.",
        "분야/일반 구분에는 '일반' 또는 '분야'만 쓰고, 이전년도 교훈 중복 여부에는 '신규' 또는 '중복(연도/분야)'처럼 짧게 쓴다.",
    ],
}


EDITOR_PROMPT_SECTION_NUMBER_BY_PART_ID = {
    "cover": 1,
    "toc": 2,
    "notice": 3,
    "grade": 4,
    "summary-ko": 5,
    "project-background": 6,
    "project-overview": 7,
    "pdm": 8,
    "eval-purpose": 9,
    "eval-matrix": 10,
    "eval-methods": 11,
    "eval-limitations": 12,
    "eval-team": 13,
    "achievement": 14,
    "criteria-relevance": 15,
    "criteria-coherence": 16,
    "criteria-effectiveness": 17,
    "criteria-efficiency": 18,
    "criteria-sustainability": 19,
    "criteria-crosscutting": 20,
    "criteria-other": 21,
    "conclusion": 22,
    "working-factors": 23,
    "nonworking-factors": 24,
    "theory": 25,
    "feedback": 26,
    "lessons": 27,
}


def prompt_file_for_part(part_id: str) -> Path | None:
    section_number = EDITOR_PROMPT_SECTION_NUMBER_BY_PART_ID.get(part_id)
    if not section_number:
        return None
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    matches = sorted(prompts_dir.glob(f"Section{section_number}_*.py"))
    return matches[0] if matches else None


def literal_from_prompt_file(path: Path, variable_name: str) -> str:
    module_ast = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in module_ast.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == variable_name for target in node.targets):
                value = ast.literal_eval(node.value)
                return str(value).strip()
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == variable_name:
            value = ast.literal_eval(node.value)
            return str(value).strip()
    return ""


def apply_editor_prompts_from_section_files() -> None:
    """Use prompts/Section*.py as the source of truth for editor generation prompts."""
    for part in EDITOR_REPORT_PARTS:
        part_id = str(part.get("id") or "")
        prompt_file = prompt_file_for_part(part_id)
        if not prompt_file:
            continue
        prompt = literal_from_prompt_file(prompt_file, "EDITOR_PROMPT")
        if not prompt:
            continue
        part["prompt"] = prompt
        part["promptSourceFile"] = str(prompt_file.relative_to(Path(__file__).resolve().parents[1]))


DETAILED_EVIDENCE_WRITING_PART_IDS = {
    "summary-ko",
    "project-background",
    "eval-purpose",
    "eval-methods",
    "eval-limitations",
    "eval-team",
    "achievement",
    "criteria-relevance",
    "criteria-coherence",
    "criteria-effectiveness",
    "criteria-efficiency",
    "criteria-sustainability",
    "criteria-crosscutting",
    "criteria-other",
    "conclusion",
    "working-factors",
    "nonworking-factors",
    "theory",
    "feedback",
    "lessons",
}


DETAILED_EVIDENCE_WRITING_PROMPT = """

[자료 기반 상세 서술 및 인용 지침]
- 이 파트는 단순 빈칸 채우기가 아니라 최종 보고서 본문이다. reference_corpus.documents, content_inputs.references, content_inputs.criteria, prior_analysis_sections, sample_reference_for_this_section를 먼저 확인한 뒤 자료에 근거해 충분히 상세하게 작성한다.
- 주요 주장마다 가능한 경우 근거 문서명 또는 evidenceName을 문장 안에 자연스럽게 언급한다. 예: "사업개요서(PCP)와 사전조사 결과에 따르면...", "PDM 및 종료보고서상 산출 실적은..."처럼 쓴다.
- 직접 인용은 짧게만 사용하고, 대부분은 자료 내용을 해석·종합해 보고서 문체로 재작성한다. 문서의 원문을 길게 복사하지 않는다.
- 서로 다른 자료가 같은 판단을 뒷받침하면 문서 간 교차근거를 연결해서 쓴다. 자료가 충돌하거나 추출 품질이 낮으면 단정하지 말고 "확인되는 범위에서는", "제시된 자료 기준으로는"처럼 보수적으로 쓴다.
- "추가 정보 필요", "자료 없음", "확인 필요" 같은 표식을 본문에 넣지 않는다. 자료가 제한적이면 현재 보유 자료에서 확인되는 사실, 합리적 해석, 판단의 한계를 한 문단 안에 함께 설명한다.
- 평가기준별 본문은 평가 질문을 그대로 나열하지 말고, 근거-해석-평가판단-한계/보완점의 흐름으로 2~4개 문단 수준의 완성된 설명을 작성한다.
- 결론, 작동/비작동요인, 변화이론, 환류과제, 교훈은 앞선 평가결과와 저장된 기준별 평가를 1차 근거로 삼고, 필요한 경우 참조문서명을 덧붙여 실행 가능한 시사점까지 연결한다.
""".strip()


def attach_editor_reference_pipelines() -> None:
    for part in EDITOR_REPORT_PARTS:
        pipeline = EDITOR_PART_REFERENCE_PIPELINES.get(part["id"], {"criteria": [], "evidence": {}, "notes": []})
        part["referenceCriteria"] = list(pipeline.get("criteria", []))
        part["referenceEvidence"] = {
            criterion_id: list(evidence_names)
            for criterion_id, evidence_names in pipeline.get("evidence", {}).items()
        }
        part["referenceNotes"] = list(pipeline.get("notes", []))
        detail_lines = EDITOR_PART_DETAIL_PROMPTS.get(part["id"], [])
        if detail_lines:
            detail_text = "\n세부 작성 기준:\n" + "\n".join(f"- {line}" for line in detail_lines)
            if "세부 작성 기준:" not in str(part.get("prompt", "")):
                part["prompt"] = str(part.get("prompt", "")).rstrip() + "\n" + detail_text
        if str(part.get("id") or "") in DETAILED_EVIDENCE_WRITING_PART_IDS:
            current_prompt = str(part.get("prompt", ""))
            if "[자료 기반 상세 서술 및 인용 지침]" not in current_prompt:
                part["prompt"] = current_prompt.rstrip() + "\n\n" + DETAILED_EVIDENCE_WRITING_PROMPT


apply_editor_prompts_from_section_files()
attach_editor_reference_pipelines()


def report_prompt_assets() -> dict:
    enabled_editor_parts = [
        {**part, "sectionNumber": EDITOR_PROMPT_SECTION_NUMBER_BY_PART_ID.get(str(part.get("id") or ""))}
        for part in EDITOR_REPORT_PARTS
    ]
    return {"master": REPORT_MASTER_PROMPT, "parts": enabled_editor_parts, "editorParts": enabled_editor_parts}


def report_prompt_text() -> str:
    lines = [REPORT_MASTER_PROMPT.strip(), "", "파트별 작성 프롬프트 및 자료 파이프라인"]
    for part in REPORT_PART_PROMPTS:
        lines.extend(
            [
                "",
                f"## {part['title']} ({part['id']})",
                "작성 대상: " + ", ".join(part["template_targets"]),
                "필요 자료:",
                *[f"- {item}" for item in part["required_inputs"]],
                "입력 파이프라인:",
                *[f"- {item}" for item in part["evidence_pipeline"]],
                "파트 프롬프트:",
                part["prompt"],
            ]
        )
    return "\n".join(lines)
