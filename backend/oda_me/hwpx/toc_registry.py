"""Every visible row in the report TOC, in document order."""
import re
import unicodedata

TOC_ROWS = (
    ('grade_page', '평가 등급 결과표', True),
    ('summary_chapter_page', 'Ⅰ. 평가결과 요약', True),
    ('summary_ko_page', '1. 국문 요약', False),
    ('project_chapter_page', 'Ⅱ. 대상사업 개요', True),
    ('project_background_page', '1. 사업 추진배경', False),
    ('project_overview_page', '2. 사업개요', False),
    ('pdm_page', '3. 사업설계매트릭스(PDM)', False),
    ('evaluation_chapter_page', 'Ⅲ. 평가개요', True),
    ('evaluation_purpose_page', '1. 평가의 목적과 범위', False),
    ('evaluation_matrix_page', '2. 평가매트릭스(Evaluation Matrix)', False),
    ('evaluation_methods_page', '3. 평가 방법', False),
    ('evaluation_limitations_page', '4. 평가의 한계', False),
    ('evaluation_team_page', '5. 평가팀 구성 및 시행체계', False),
    ('achievement_page', 'Ⅳ. 성과달성도', True),
    ('criteria_chapter_page', 'Ⅴ. 기준별 평가결과', True),
    ('criteria_relevance_page', '1. 적절성', False),
    ('criteria_coherence_page', '2. 일관성', False),
    ('criteria_effectiveness_page', '3. 효과성', False),
    ('criteria_efficiency_page', '4. 효율성', False),
    ('criteria_sustainability_page', '5. 지속가능성', False),
    ('criteria_crosscutting_page', '6. 범분야 이슈', False),
    ('criteria_other_page', '7. 그 외 평가기준', False),
    ('conclusion_chapter_page', 'Ⅵ. 결론', True),
    ('conclusion_page', '1. 결론', False),
    ('factors_page', '2. 작동요인 및 비작동요인', False),
    ('feedback_lessons_page', '3. 환류과제 및 교훈', False),
)
TOC_LABELS = {key: label for key, label, _ in TOC_ROWS}
TOC_CHAPTER_KEYS = frozenset(key for key, _, chapter in TOC_ROWS if chapter)


def normalized_title(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value))).casefold()


def destination_title(key, label):
    # The renderer may omit the optional English gloss on the matrix heading.
    return label.replace('(Evaluation Matrix)', '') if key == 'evaluation_matrix_page' else label
