from __future__ import annotations

DAC_CRITERIA = {
    "relevance": "적절성: 정책·수요·우선순위, 대상자 요구, 사업 설계의 타당성",
    "coherence": "일관성: 국가전략·SDGs·타 사업과의 정합성, 중복·연계·조정",
    "effectiveness": "효과성: 산출물·성과지표 달성, 목표 대비 실적, 기여 요인",
    "efficiency": "효율성: 예산·일정·투입 대비 산출, 조달·운영과 비용 효과성",
    "impact": "영향: 중장기 변화, 의도·비의도 효과, 제도·사회적 파급",
    "sustainability": "지속가능성: 제도화, 재정·인력·운영 유지, 현지 소유권과 확산",
    "crosscutting": "범분야: 성평등, 인권, 환경, 취약계층, 디지털·기후 등",
}

SECTIONS = [
    (1, "cover", "표지", "사업명, 평가명, 국가, 기간, 발주·수행기관처럼 표지 식별정보를 제공하는 공식 문서"),
    (2, "toc", "목차", "보고서 구조나 장·절 목록을 직접 제공하는 문서"),
    (3, "notice", "평가보고서 관련 공지", "면책, 공개범위, 저작권, 개인정보, 활용상 주의사항"),
    (4, "grade", "평가등급 결과표", "DAC 기준별 점수, 등급, 산정근거 또는 종합평가 결과"),
    (5, "summary-ko", "국문 요약", "사업·평가 결과 전반을 요약하는 종합 자료; 단일 주제 자료는 보조 근거로만 분류"),
    (6, "project-background", "사업 추진배경", "개발문제, 수요조사, 정책환경, 사업 형성·기획 배경"),
    (7, "project-overview", "사업개요", "사업기간, 예산, 대상지, 수혜자, 수행체계, 주요 활동 등 기본정보"),
    (8, "pdm", "사업설계매트릭스(PDM)", "목표·성과·산출·활동·지표·가정의 논리모형 또는 PDM"),
    (9, "eval-purpose", "평가의 목적과 범위", "평가 목적, 대상, 기간, 범위, 핵심 평가질문"),
    (10, "eval-matrix", "평가매트릭스", "평가기준-질문-지표-자료원-조사방법의 연결표"),
    (11, "eval-methods", "평가방법", "문헌조사, 인터뷰, 설문, 표본, 현장조사, 분석방법"),
    (12, "eval-limitations", "평가의 한계", "자료 결측, 표본·접근 제약, 편향, 조사범위와 해석상 한계"),
    (13, "eval-team", "평가팀 구성 및 시행체계", "평가위원, 역할분담, 일정, 조사·검토·품질관리 체계"),
    (14, "achievement", "성과 달성도", "PDM 지표 기준선·목표·실적, 산출물 이행과 성과 측정자료"),
    (15, "criteria-relevance", "적절성", DAC_CRITERIA["relevance"]),
    (16, "criteria-coherence", "일관성", DAC_CRITERIA["coherence"]),
    (17, "criteria-effectiveness", "효과성", DAC_CRITERIA["effectiveness"]),
    (18, "criteria-efficiency", "효율성", DAC_CRITERIA["efficiency"]),
    (19, "criteria-sustainability", "지속가능성", DAC_CRITERIA["sustainability"]),
    (20, "criteria-crosscutting", "범분야 이슈", DAC_CRITERIA["crosscutting"]),
    (21, "criteria-other", "그 외 평가기준", "기본 DAC 기준 밖에서 발주처가 명시한 별도 평가기준에 직접 관련된 자료"),
    (22, "conclusion", "결론", "기준별 판단을 종합한 최종 결론; 원자료는 강한 종합성이 있을 때만 분류"),
    (23, "working-factors", "작동요인", "성과를 가능하게 한 인과요인, 성공조건, 촉진요인에 대한 근거"),
    (24, "nonworking-factors", "비작동요인", "성과 저해요인, 실패·지연 원인, 위험과 병목에 대한 근거"),
    (25, "theory", "변화이론 분석", "투입-활동-산출-성과-영향의 인과경로, 가정과 외부요인 검증"),
    (26, "feedback", "환류과제", "후속조치, 개선과제, 담당·기한·실행방안을 포함한 제언"),
    (27, "lessons", "교훈", "다른 사업에 적용 가능한 일반화된 교훈과 재현 조건"),
]

SECTION_BY_ID = {item[1]: item for item in SECTIONS}

def prompt_taxonomy() -> str:
    return "\n".join(f"{n}. {sid} | {title} | {rule}" for n, sid, title, rule in SECTIONS)
