"""Editable page contracts transcribed from the supplied reference PDFs.

source_pages is one-based. 30 pages condenses the 50-page Mozambique reference;
it is deliberately not a 50-page product option. Business facts never come from
the sample: only page purpose, ordering, and visual grammar are retained.
"""
from pydantic import BaseModel, ConfigDict
from typing import Literal


class PresentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slide_count: Literal[15, 30] = 15


def page(title, section, layout, source_pages, sources, columns=()):
    return dict(title=title, section=section, layout=layout,
                source_pages=list(source_pages), source_sections=list(sources), columns=list(columns))


BRIEF = [
    page("종료평가 결과보고", "", "cover", [1], ["cover", "summary-ko"]),
    page("목차", "", "toc", [2], ["summary-ko"]),
    page("평가 등급 결과", "Ⅰ. 평가 등급 결과", "table", [3], ["grade"], ["평가기준", "평점", "산정 이유"]),
    page("사업 개요", "Ⅱ. 대상사업 개요", "table", [4], ["project-overview", "project-background"], ["구분", "내용"]),
    page("PDM: 산출물과 성과", "Ⅱ. 대상사업 개요", "table", [5], ["pdm"], ["성과 구분", "검증지표", "검증수단", "가정"]),
    page("PDM: 투입과 활동", "Ⅱ. 대상사업 개요", "table", [6], ["pdm"], ["투입·활동", "주요 내용", "전제조건"]),
    page("평가 매트릭스", "Ⅲ. 평가 개요", "table", [7], ["eval-matrix"], ["평가기준", "핵심 질문", "지표·근거", "분석 방법"]),
    page("평가방법과 한계", "Ⅲ. 평가 개요", "table", [8], ["eval-methods", "eval-limitations", "eval-purpose"], ["단계", "평가 내용", "방법·근거", "한계"]),
    page("성과달성도", "Ⅳ. 성과달성도", "table", [9], ["achievement"], ["성과지표", "목표", "실적", "판단·근거"]),
    page("적절성과 일관성", "Ⅴ. 기준별 평가결과", "blocks", [10], ["criteria-relevance", "criteria-coherence"]),
    page("효율성", "Ⅴ. 기준별 평가결과", "blocks", [11], ["criteria-efficiency"]),
    page("효과성", "Ⅴ. 기준별 평가결과", "photo", [12], ["criteria-effectiveness"]),
    page("지속가능성과 범분야 이슈", "Ⅴ. 기준별 평가결과", "blocks", [13], ["criteria-sustainability", "criteria-crosscutting", "criteria-other"]),
    page("성공요인과 개선요인", "Ⅵ. 교훈 및 제언", "table", [14], ["working-factors", "nonworking-factors", "lessons"], ["구분", "요인", "교훈·개선 방향"]),
    page("제언 및 후속조치", "Ⅵ. 교훈 및 제언", "table", [15], ["feedback", "conclusion"], ["책임주체", "제언·확인자료", "시점", "우선순위"]),
]

DETAILED = [
    page("종료평가 최종보고", "", "cover", [1], ["cover", "summary-ko"]),
    page("목차", "", "toc", [2], ["summary-ko"]),
    page("사업 기본정보", "Ⅰ. 사업 개요", "table", [3, 4], ["project-overview"], ["구분", "내용"]),
    page("사업 배경 및 필요성", "Ⅰ. 사업 개요", "blocks", [4, 6], ["project-background"]),
    page("평가 배경 및 목적", "Ⅱ. 평가 개요", "blocks", [5, 6], ["eval-purpose"]),
    page("평가단 구성 및 역할", "Ⅱ. 평가 개요", "table", [7], ["eval-team"], ["역할", "책임·전문분야", "확인 근거"]),
    page("평가 절차 및 방법", "Ⅱ. 평가 개요", "table", [8], ["eval-methods"], ["단계", "수행 내용", "자료·방법"]),
    page("평가기준과 매트릭스", "Ⅱ. 평가 개요", "table", [9], ["eval-matrix"], ["평가기준", "질문", "판단 근거"]),
    page("평가 방향 및 한계", "Ⅱ. 평가 개요", "blocks", [10], ["eval-limitations", "eval-methods"]),
    page("변화이론과 성과경로", "Ⅱ. 평가 개요", "table", [11], ["theory", "pdm"], ["단계", "변화경로", "작동조건·검증"]),
    page("성과관리 프레임워크", "Ⅱ. 평가 개요", "table", [12], ["pdm"], ["성과 구분", "지표", "검증수단", "가정"]),
    page("평가 추진 경과", "Ⅱ. 평가 개요", "table", [13], ["eval-methods", "eval-team"], ["단계", "시점", "산출물·확인 상태"]),
    page("문헌조사와 근거자료", "Ⅲ. 평가 수행", "table", [14, 15], ["eval-methods", "eval-limitations"], ["자료 유형", "검토 내용", "확인 범위"]),
    page("현장·교육 운영자료 검토", "Ⅲ. 평가 수행", "photo", [16, 17], ["achievement", "project-overview"]),
    page("이해관계자·수혜자 근거", "Ⅲ. 평가 수행", "table", [18, 19, 20, 21], ["criteria-effectiveness", "eval-limitations"], ["대상", "확인된 내용", "근거 및 미확인 사항"]),
    page("종합성과 등급", "Ⅳ. 평가 결과", "table", [22, 23, 24], ["grade"], ["평가기준", "평점", "평가 판단"]),
    page("적절성", "Ⅳ. 평가 결과", "assessment", [25, 31], ["criteria-relevance"], ["평가항목", "판단·근거", "보완점"]),
    page("효율성", "Ⅳ. 평가 결과", "assessment", [26, 32], ["criteria-efficiency"], ["평가항목", "판단·근거", "보완점"]),
    page("효과성과 성과달성도", "Ⅳ. 평가 결과", "assessment", [27, 33], ["criteria-effectiveness", "achievement"], ["평가항목", "판단·근거", "보완점"]),
    page("지속가능성", "Ⅳ. 평가 결과", "assessment", [28, 34], ["criteria-sustainability"], ["평가항목", "판단·근거", "보완점"]),
    page("일관성", "Ⅳ. 평가 결과", "assessment", [29, 35], ["criteria-coherence"], ["평가항목", "판단·근거", "보완점"]),
    page("범분야 이슈", "Ⅳ. 평가 결과", "table", [30, 36], ["criteria-crosscutting", "criteria-other"], ["평가영역", "확인 결과", "근거 공백"]),
    page("성과지표 및 운영 적정성", "Ⅴ. 운영 및 성과 검토", "table", [37, 38, 39, 40], ["achievement", "criteria-efficiency"], ["지표·영역", "실적·판단", "한계·추가 확인"]),
    page("운영자료 확인 결과", "Ⅴ. 운영 및 성과 검토", "photo", [41, 42], ["achievement", "criteria-sustainability"]),
    page("운영 지속성 종합의견", "Ⅴ. 운영 및 성과 검토", "blocks", [43], ["conclusion", "criteria-sustainability"]),
    page("성공요인 및 제한요인", "Ⅵ. 교훈 및 제언", "table", [44, 45], ["working-factors", "nonworking-factors"], ["구분", "요인", "성과·한계에 미친 결과"]),
    page("작동요인·비작동요인과 교훈", "Ⅵ. 교훈 및 제언", "table", [46, 47], ["theory", "lessons"], ["요인", "검증 결과", "교훈"]),
    page("공여자 및 수행기관 제언", "Ⅵ. 교훈 및 제언", "table", [48], ["feedback"], ["책임주체", "실행 과제", "시점·확인자료"]),
    page("수원기관 및 후속 관리 제언", "Ⅵ. 교훈 및 제언", "table", [49], ["feedback", "conclusion"], ["책임주체", "실행 과제", "시점·확인자료"]),
    page("결론 및 후속 확인", "Ⅵ. 교훈 및 제언", "closing", [50], ["conclusion"]),
]


def table_widths(columns, width):
    if len(columns) == 2:
        fractions = [.24, .76]
    elif len(columns) == 3:
        fractions = [.18, .16, .66] if columns[1] == '평점' else [.22, .43, .35]
    elif columns[1] == '목표':
        fractions = [.31, .13, .13, .43]
    else:
        fractions = [.22, .30, .24, .24]
    return [width*f for f in fractions]


def get_profile(count: int) -> dict:
    if type(count) is not int or count not in (15, 30):
        raise ValueError("발표자료는 15페이지 또는 30페이지만 선택할 수 있습니다.")
    pages = BRIEF if count == 15 else DETAILED
    width = 720 if count == 15 else 780
    result = {"id": f"reference-{count}", "version": "2026-09-16.1", "slide_count": count,
            "reference_file": "south-africa-15.pdf" if count == 15 else "mozambique-50.pdf",
            "reference_page_count": 15 if count == 15 else 50,
            "width_pt": width, "height_pt": 540,
            "pages": [dict(p, slide_number=i) for i, p in enumerate(pages, 1)]}
    for p in result['pages']:
        if p['columns']:
            size = 16 if len(p['columns']) <= 3 else 15
            # Two full-width Korean lines per cell, leaving room for six rows.
            p['cell_char_limits'] = [max(8, int((w-14)/size)*2) for w in table_widths(p['columns'], width-56)]
    return result
