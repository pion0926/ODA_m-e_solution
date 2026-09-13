from __future__ import annotations

import re
from collections.abc import Iterable

from report_writing_policy import writing_profile


# Tables and fixed-cell sections retain their own reviewed layouts.  These
# sections are reader-facing narrative blocks and therefore share one visual
# hierarchy from authoring through HWPX rendering.
NARRATIVE_OUTLINE_PART_IDS = frozenset(
    {
        "eval-purpose",
        "eval-methods",
        "eval-limitations",
        "eval-team",
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
    }
)


NARRATIVE_OUTLINE_DEFAULT_LABELS = {
    "eval-purpose": "평가 목적과 범위",
    "eval-methods": "평가 방법과 수행절차",
    "eval-limitations": "주요 한계와 대응",
    "eval-team": "평가 수행체계",
    "criteria-relevance": "적절성 평가결과",
    "criteria-coherence": "일관성 평가결과",
    "criteria-effectiveness": "효과성 평가결과",
    "criteria-efficiency": "효율성 평가결과",
    "criteria-sustainability": "지속가능성 평가결과",
    "criteria-crosscutting": "범분야 평가결과",
    "criteria-other": "추가 평가 관점",
    "conclusion": "종합 결론",
    "working-factors": "주요 작동요인",
    "nonworking-factors": "주요 비작동요인",
    "theory": "변화경로 분석",
}


# These labels are supplied by the fixed HWPX template.  They are never
# reader-facing body bullets.  LLM drafts occasionally repeat one of them as
# ``ㅇ 7. 그 외 평가기준`` (or as a Markdown/numbered heading), which leaves
# two visually identical titles after the template heading is rendered.
NARRATIVE_OUTLINE_OUTER_LABELS = {
    "eval-purpose": ("평가의 목적과 범위", "평가 목적과 범위"),
    "eval-methods": ("평가방법", "평가 방법"),
    "eval-limitations": ("평가의 한계", "평가의 한계 및 보완 조치"),
    "eval-team": ("평가팀 구성 및 시행체계",),
    "criteria-relevance": ("적절성",),
    "criteria-coherence": ("일관성",),
    "criteria-effectiveness": ("효과성",),
    "criteria-efficiency": ("효율성",),
    "criteria-sustainability": ("지속가능성",),
    "criteria-crosscutting": ("범분야 이슈",),
    "criteria-other": ("그 외 평가기준", "기타 평가기준"),
    "conclusion": ("결론",),
    "working-factors": ("작동요인", "작동 요인"),
    "nonworking-factors": ("비작동요인", "비작동 요인"),
    "theory": ("변화이론 분석",),
}


NARRATIVE_OUTLINE_PROMPT = """
[전 서술형 섹션 공통 문단 양식]
- 표·고정 셀 섹션을 제외한 서술형 본문은 국문 요약과 같은 `ㅇ → -` 두 단계 문단 계층으로 작성한다.
- 각 논점 제목은 독립 문단인 ` ㅇ 논점 제목`으로 작성하고, 그 아래에는 서로 다른 하위 논거만 `  - 세부 내용`으로 구분한다.
- `-`는 문장마다 붙이는 표식이 아니다. 하나의 하위 논거는 2~4개의 서로 연결된 문장을 한 문단으로 묶고, 같은 판단의 설명·근거·후속 문장은 기존 `-` 문단에 이어 쓴다.
- 세부 문단은 `  - 본문`으로 작성한다. 맥락이 크게 구분될 때만 `(핵심어 요약)`을 선택적으로 붙이며, 모든 문단에 기계적으로 라벨을 붙이지 않는다.
- 한 문단의 선두 괄호 소제목은 최대 1개만 쓴다. `(운영 자립) (현장 적용 효과 검증)`처럼 포괄 라벨 뒤에 다시 소제목을 붙이지 않는다. 본문이 검증 필요성을 설명하면 소제목도 그 판단을 정확히 나타내거나 생략한다.
- 같은 `ㅇ` 아래에서 동일한 괄호 요약어를 두 번 사용하지 않는다. 같은 역할의 문단은 하나로 합치고, 다른 역할이면 `포용적 설계`, `분리통계 한계`, `이행체계 보완`처럼 실제 논거를 구별하는 요약어를 쓴다.
- 세부 본문은 개조식 종결을 사용한다. 문장 끝은 `~함.`, `~음.`, `~됨.`, `~평가됨.`, `~필요함.` 중 의미에 맞는 형태로 쓰고, `~다.`, `~이다.`, `~하였다.` 서술형 종결을 쓰지 않는다.
- `ㅇ` 앞에는 공백 1회, `-` 앞에는 공백 2회를 둔다. 내용은 표식 다음 한 칸 뒤에서 시작한다.
- 한 문단 안에 `ㅇ` 또는 `-` 표식을 반복하거나, 제목과 본문을 같은 줄에 이어 쓰지 않는다.
- Markdown 제목(`#`, `##`, `###`), `가./나./다.` 하위 제목, 탭, 굵게 표식은 사용하지 않는다. 장·절 번호와 제목은 HWPX 양식이 담당한다.
- HWPX가 넣는 현재 섹션 제목을 본문 첫 줄의 `ㅇ` 문단으로 다시 쓰지 않는다. 예를 들어 `7. 그 외 평가기준` 아래에 `ㅇ 7. 그 외 평가기준`을 반복하지 않는다.
- 각 `ㅇ` 아래에는 내용이 중복되지 않는 `-` 문단을 두되, 논거가 하나뿐이면 문장 수를 맞추기 위해 억지로 나누지 않는다. 긴 내용은 문장 수가 아니라 판단·근거·한계·후속조치의 의미 단위에서만 나눈다.
- 한 `- (핵심어)` 문단은 서로 연결된 2~4문장, 약 360자 이내를 기준으로 한다. 이를 넘으면 문장을 자르지 말고 판단·근거·한계·후속조치 중 달라지는 의미부터 새로운 `- (다른 핵심어)` 문단으로 분리한다.
""".strip()


_DETAIL_LABEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:사업명|사업기간|총사업비|대상\s*지역|수행\s*기간).{0,100}(?:사업|프로그램|수행|구성)"), "사업 범위"),
    (re.compile(r"(?:평가\s*목적|평가\s*범위|평가\s*대상|평가\s*기준일)"), "평가 범위"),
    (re.compile(r"(?:별도\s*면담|현지\s*조사|신규\s*설문).{0,100}(?:없이|없어|제외|제한|실시하지)"), "평가자료 범위"),
    (re.compile(r"(?:종합\s*점수|정부\s*평가\s*등급|ODA\s*기준\s*[A-E]\s*등급)"), "종합 등급"),
    (re.compile(r"(?:담당|역할\s*분담|주관|지원).{0,100}(?:기관|대학|부처|파트너)"), "역할 분담"),
    (re.compile(r"(?:우선순위|완료기한|점검주기|확인자료)"), "실행계획"),
    (re.compile(r"(?:졸업생|자격시험|취업률).{0,80}(?:산출|집계|배출|대기|유보)"), "성과 산정시점"),
    (re.compile(r"(?:공식\s*문헌|공문서|자체평가|진도보고서|사업계획서).{0,120}(?:검토|대조|기반|분석|검증)"), "문헌 교차검토"),
    (re.compile(r"(?:국가\s*인력\s*양성\s*정책|정책\s*방향).{0,90}(?:부합|정합|연계)"), "정책 부합성"),
    (re.compile(r"(?:타\s*공여기관|공여기관).{0,100}(?:조율|조정|역할\s*분담|연계)"), "공여기관 조정"),
    (re.compile(r"(?:자체\s*예산|재정적\s*자립|유지보수\s*계획|장기\s*재원)"), "재정 자립조건"),
    (re.compile(r"(?:투입\s*(?:및|·)\s*활동|재원|전문인력).{0,30}경로"), "투입·활동 경로"),
    (re.compile(r"(?:산출\s*(?:및|·)\s*성과|산출|성과).{0,24}경로"), "산출·성과 경로"),
    (re.compile(r"(?:포용|취약계층|소외계층|접근성|형평).{0,80}(?:설계|반영|고려)|(?:설계|반영|고려).{0,80}(?:포용|취약계층|소외계층|접근성|형평)"), "포용적 설계"),
    (re.compile(r"(?:성별|계층별|장애|취약계층별).{0,40}(?:분리\s*통계|분리\s*자료|참여\s*현황)|(?:분리\s*통계|분리\s*자료).{0,40}(?:성별|계층별|장애|취약계층별)"), "분리통계 관리"),
    (re.compile(r"(?:분리\s*통계|정량적\s*지표|수혜\s*비율).{0,50}(?:미명시|명시되어\s*있지|부족|제한|부재)"), "분리통계 한계"),
    (re.compile(r"(?:운영\s*지침|차별적\s*요소|동등한\s*(?:실습|참여)\s*기회|형평성\s*지표).{0,70}(?:정비|보완|보장|배제|필요|관리)"), "운영지침 보완"),
    (re.compile(r"(?:관리\s*체계|관리\s*서식|서식\s*정비|연도별.{0,20}기록|이행\s*계획)"), "이행체계 보완"),
    (re.compile(r"(?:후속\s*검증|추적\s*(?:조사|검증|모니터링)|장기\s*모니터링)"), "후속 검증"),
    (re.compile(r"(?:산출|성과).{0,30}(?:달성|진척)|(?:달성|진척).{0,30}(?:산출|성과)"), "산출·성과 진척"),
    (re.compile(r"(?:마스터\s*트레이너|CPCR|MCI\s*Triage).{0,100}(?:교육|확산|연계|이수)"), "교육·확산 연계"),
    (re.compile(r"(?:거점\s*학과|앵커\s*기관|지역\s*거점).{0,80}(?:육성|기능|역할|비전)"), "거점학과 비전"),
    (re.compile(r"(?:학과\s*승인|직무\s*코드|법적\s*승인|제도적\s*승인)"), "제도적 지속성"),
    (re.compile(r"(?:평가\s*대상\s*영역|평가\s*항목|평가\s*기준).{0,80}(?:적절성|일관성|효과성|효율성|지속가능성)"), "평가 대상영역"),
    (re.compile(r"(?:공식\s*문서|등록된\s*문서|제공된\s*문서).{0,80}(?:한정|범위|기반|중심)"), "근거자료 범위"),
    (re.compile(r"(?:수혜자|참여자|졸업생).{0,60}(?:분리\s*자료|분리\s*통계|교차\s*검증|추적)"), "수혜지표 검증"),
    (re.compile(r"(?:PDM|사업설계매트릭스).{0,80}(?:연차|자체평가|계획|일치|정합)"), "PDM 정합성"),
    (re.compile(r"(?:장기\s*성과|영향\s*지표|생존율|취업률).{0,80}(?:공식\s*통계|추적|검증|측정)"), "영향지표 추적"),
    (re.compile(r"(?:지표\s*목록|성과지표|검증지표).{0,80}(?:관리|갱신|체계|모니터링)"), "지표 관리체계"),
    (re.compile(r"(?:PDM|산출|성과).{0,80}(?:미도래|유보|향후\s*확인|검증\s*시점)"), "성과 검증시점"),
    (re.compile(r"(?:수요|요구|needs).{0,80}(?:설계|반영|조사|진단)"), "현지수요 반영"),
    (re.compile(r"(?:유사\s*사업|타\s*사업|국가협력전략|CPS).{0,90}(?:연계|상호보완|시너지|정합)"), "사업 간 연계"),
    (re.compile(r"(?:교육과정|현지\s*강사|교원|교재).{0,90}(?:자립|내재화|운영\s*역량|지속)"), "운영 자립기반"),
    (re.compile(r"(?:비용\s*편익|비용\s*효율|단가|예산\s*대비).{0,80}(?:분석|근거|성과|검토)"), "비용효율 근거"),
    (re.compile(r"(?:연차별|자체평가|정기\s*점검).{0,80}(?:환류|조정|개선|관리)"), "관리 환류체계"),
    (re.compile(r"(?:자료\s*공백|측정\s*한계|검증\s*제약|근거\s*부족)"), "성과측정 제약"),
    (re.compile(r"목표.{0,24}(?:실적|대비)|(?:실적|대비).{0,24}목표"), "목표 대비 실적"),
    (re.compile(r"(?:문헌\s*검토|문서\s*(?:검토|분석)|검토.{0,12}문서)"), "문헌 검토"),
    (re.compile(r"(?:증빙|자료).{0,36}(?:교차\s*검증|교차\s*대조)|(?:교차\s*검증|교차\s*대조).{0,36}(?:증빙|자료)"), "증빙 교차검증"),
    (re.compile(r"(?:한계|미흡|부족|공백|제약|미달)"), "한계 및 보완"),
    (re.compile(r"(?:후속|향후|권고|추적|보완).{0,24}(?:필요|과제|조치|관리)"), "후속 과제"),
    (re.compile(r"(?:승인|직무\s*코드|법적\s*기반|제도화|제도적)"), "제도적 성과"),
    (re.compile(r"(?:강사|교원|연수|교육과정|교재|역량\s*강화)"), "교육역량 강화"),
    (re.compile(r"(?:기자재|시뮬레이션|실습실|센터|시설|장비)"), "교육 인프라"),
    (re.compile(r"(?:취약계층|성별|포용|형평|인권)"), "포용성 검토"),
    (re.compile(r"(?:예산|재정|집행|비용)"), "재정·집행"),
    (re.compile(r"(?:일정|지연|조달|기간)"), "일정·조달"),
    (re.compile(r"(?:협력|거버넌스|조정|역할\s*분담|파트너)"), "협력·조정"),
    (re.compile(r"(?:근거|자료|문헌|확인|검증)"), "근거 기반 판단"),
)

_FALLBACK_DETAIL_LABELS = ("핵심 판단", "근거 및 분석", "한계 및 보완", "후속 과제")
_EDITABLE_GENERIC_DETAIL_LABELS = tuple(
    str(item).strip()
    for item in writing_profile().get("forbidden_generic_detail_labels", ())
    if str(item).strip()
)
_GENERIC_DETAIL_LABELS = frozenset((*_FALLBACK_DETAIL_LABELS, *_EDITABLE_GENERIC_DETAIL_LABELS))
_DETAIL_LABEL_RE = re.compile(r"^\((?P<label>[^()]{2,80})\)\s*(?P<body>.+)$")


_NARRATIVE_DETAIL_LAYOUT = writing_profile().get("narrative_detail_layout") or {}
NARRATIVE_DETAIL_MAX_CHARACTERS = int(
    _NARRATIVE_DETAIL_LAYOUT.get("maximum_characters") or 360
)
NARRATIVE_DETAIL_MAX_SENTENCES = int(
    _NARRATIVE_DETAIL_LAYOUT.get("maximum_sentences") or 4
)
def nominalize_report_sentences(value: object) -> str:
    """Convert common final-report declaratives to Korean bullet endings."""

    text = _clean_text(value)
    replacements = (
        (r"필요가\s*있다\.", "필요가 있음."),
        (r"할\s*수\s*있다\.", "할 수 있음."),
        (r"수\s*있다\.", "수 있음."),
        (r"하여야\s*한다\.", "하여야 함."),
        (r"해야\s*한다\.", "해야 함."),
        (r"필요하다\.", "필요함."),
        (r"요구된다\.", "요구됨."),
        (r"확인된다\.", "확인됨."),
        (r"판단된다\.", "판단됨."),
        (r"평가된다\.", "평가됨."),
        (r"기대된다\.", "기대됨."),
        (r"나타난다\.", "나타남."),
        (r"드러난다\.", "드러남."),
        (r"두드러진다\.", "두드러짐."),
        (r"보인다\.", "보임."),
        (r"보여준다\.", "보여줌."),
        (r"나타났다\.", "나타났음."),
        (r"있었다\.", "있었음."),
        (r"없었다\.", "없었음."),
        (r"않았다\.", "않았음."),
        (r"높다\.", "높음."),
        (r"낮다\.", "낮음."),
        (r"많다\.", "많음."),
        (r"않는다\.", "않음."),
        (r"않다\.", "않음."),
        (r"따른다\.", "따름."),
        (r"가진다\.", "가짐."),
        (r"이룬다\.", "이룸."),
        (r"이루었다\.", "이루었음."),
        (r"크다\.", "큼."),
        (r"적다\.", "적음."),
        (r"어렵다\.", "어려움."),
        (r"같다\.", "같음."),
        (r"하였습니다\.", "하였음."),
        (r"되었습니다\.", "되었음."),
        (r"이었습니다\.", "이었음."),
        (r"했습니다\.", "했음."),
        (r"됐습니다\.", "됐음."),
        (r"있습니다\.", "있음."),
        (r"없습니다\.", "없음."),
        (r"않았습니다\.", "않았음."),
        (r"졌습니다\.", "졌음."),
        (r"쳤습니다\.", "쳤음."),
        (r"합니다\.", "함."),
        (r"됩니다\.", "됨."),
        (r"입니다\.", "임."),
        (r"하였다\.", "하였음."),
        (r"되었다\.", "되었음."),
        (r"이었다\.", "이었음."),
        (r"했다\.", "했음."),
        (r"됐다\.", "됐음."),
        (r"삼았다\.", "삼았음."),
        (r"밝힌다\.", "밝힘."),
        (r"남는다\.", "남음."),
        (r"남긴다\.", "남김."),
        (r"냈다\.", "냈음."),
        (r"겼다\.", "겼음."),
        (r"졌다\.", "졌음."),
        (r"였다\.", "였음."),
        (r"([가-힣]+)하다\.", r"\1함."),
        (r"한다\.", "함."),
        (r"된다\.", "됨."),
        (r"이다\.", "임."),
        (r"있다\.", "있음."),
        (r"없다\.", "없음."),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def _detail_label_candidates(value: object, parent_label: object = "", ordinal: int = 1) -> list[str]:
    text = _clean_text(value)
    candidates = [name for pattern, name in _DETAIL_LABEL_RULES if pattern.search(text)]
    parent = _plain_outline_label(parent_label)
    parent_text = str(parent_label).strip().strip("()")
    if parent and 2 <= len(parent_text) <= 15 and ordinal == 1:
        candidates.append(parent_text)
    return list(dict.fromkeys(label for label in candidates if 2 <= len(label) <= 15))


_PARENT_FALLBACK_LABELS = (
    (re.compile(r"추진배경|주요내용"), ("사업 추진맥락", "개입 방향", "실행 범위", "역할 연계")),
    (re.compile(r"평가.*(?:목적|범위)"), ("평가 범위", "근거 범위", "판단 범위", "결과 활용")),
    (re.compile(r"평가.*방법"), ("자료수집 절차", "분석 절차", "교차검증", "품질관리")),
    (re.compile(r"평가.*한계|자료 공백"), ("자료 제약", "판단 영향", "보완 조치", "후속 확인")),
    (re.compile(r"성과달성|성과 달성"), ("성과 현황", "지표 관리", "성과 검증", "후속 측정")),
    (re.compile(r"적절성|수요 적합"), ("수요 적합성", "정책 부합성", "설계 타당성", "보완 방향")),
    (re.compile(r"일관성|정합성|조정"), ("내부 정합성", "외부 조정", "연계 수준", "조정 과제")),
    (re.compile(r"효과성|포용성|기여요인"), ("성과 기여", "포용성 검토", "대안 설명", "검증 과제")),
    (re.compile(r"효율성|예산|조달"), ("자원 활용", "집행 효율", "일정 관리", "비용 검증")),
    (re.compile(r"지속가능|자립|유지관리"), ("제도 기반", "운영 자립", "재원 조건", "유지관리")),
    (re.compile(r"범분야|환경|세이프가드"), ("포용적 설계", "환경 검토", "세이프가드", "이행 보완")),
    (re.compile(r"비작동요인"), ("제약 원인", "성과 영향", "대응 방향", "후속 관리")),
    (re.compile(r"작동요인"), ("작동 조건", "기여 경로", "관찰 성과", "확산 조건")),
    (re.compile(r"변화이론|성과경로|가정"), ("성과 경로", "가정 검증", "단절 지점", "후속 추적")),
    (re.compile(r"결론|종합"), ("종합 평가", "핵심 성과", "핵심 한계", "후속 방향")),
)
_SAFE_FALLBACK_LABELS = ("쟁점 검토", "증빙 해석", "제약 요인", "개선 방향")


def _fallback_detail_label(parent_label: object, ordinal: int, used: set[str]) -> str:
    """Create a natural role label without exposing truncated parent text."""

    parent = _plain_outline_label(parent_label)
    pools = [labels for pattern, labels in _PARENT_FALLBACK_LABELS if pattern.search(parent)]
    pools.append(_SAFE_FALLBACK_LABELS)
    start = max(ordinal, 1) - 1
    for labels in pools:
        for offset in range(len(labels)):
            label = labels[(start + offset) % len(labels)]
            if label not in used and label not in _GENERIC_DETAIL_LABELS:
                return label
    suffix = max(ordinal, 1)
    while True:
        label = f"검토 쟁점 {suffix}"
        if label not in used:
            return label
        suffix += 1


def _mechanical_detail_label(label: object, parent_label: object = "") -> bool:
    """Detect legacy labels made by truncating a parent heading plus a role.

    Examples such as ``추진배경및주요내 제약`` and
    ``평가목적과범위 판단`` satisfy the length contract but expose an
    implementation artifact to the reader.  Natural labels with a spaced
    noun phrase (for example ``근거 기반 판단``) remain valid.
    """

    text = _clean_text(label)
    match = re.fullmatch(r"(?P<stem>.+?)\s+(?:판단|근거|제약|개선)", text)
    if not match:
        return False
    stem = match.group("stem").strip()
    compact_stem = re.sub(r"\s+", "", stem)
    compact_parent = re.sub(r"\s+", "", _plain_outline_label(parent_label))
    if compact_parent and compact_stem == compact_parent[: len(compact_stem)]:
        return True
    return " " not in stem and (len(compact_stem) >= 7 or "및" in compact_stem)


def format_narrative_detail(
    value: object,
    parent_label: object = "",
    ordinal: int = 1,
    used_labels: Iterable[str] = (),
) -> str:
    """Preserve an optional authored label; never invent one from a parent.

    Longer labels used to miss the 15-character regex and receive an unrelated
    fallback in front. Formatting must not make a new semantic judgment.
    """

    text = _clean_text(value)
    existing = _DETAIL_LABEL_RE.match(text)
    existing_label = existing.group("label").strip() if existing else ""
    body = existing.group("body") if existing else text
    labeled = re.match(r"^([^:：]{2,24})\s*[:：]\s*(.+)$", text)
    if not existing and labeled:
        existing_label = labeled.group(1).strip()
        body = labeled.group(2)

    automatic_labels = {
        *_GENERIC_DETAIL_LABELS, *_SAFE_FALLBACK_LABELS,
        *(name for _, names in _PARENT_FALLBACK_LABELS for name in names),
        *(name for _, name in _DETAIL_LABEL_RULES),
    }
    # Collapse adjacent Korean *headings*, not acronym/unit parentheses such
    # as '(교육기관) (ASMI)' or '(예산) (2026년 기준)'. Keep those in the body.
    while existing_label:
        nested = _DETAIL_LABEL_RE.match(body.strip())
        if not nested or not re.search(r'[가-힣]', nested['label']) or re.search(r'\d', nested['label']):
            break
        inner = nested['label'].strip()
        existing_label = inner if existing_label in automatic_labels or existing_label == inner else f'{existing_label}·{inner}'
        body = nested['body']
    used = {_clean_text(label) for label in used_labels if _clean_text(label)}
    if not existing_label or existing_label in used or existing_label in _GENERIC_DETAIL_LABELS or _mechanical_detail_label(existing_label, parent_label):
        return nominalize_report_sentences(body)
    return f"({existing_label}) {nominalize_report_sentences(body)}"


def _append_outline_detail(
    output: list[str],
    value: object,
    parent_label: object,
    ordinal: int,
    used_labels: set[str],
) -> None:
    for offset, chunk in enumerate(_semantic_detail_chunks(value)):
        formatted = format_narrative_detail(
            chunk,
            parent_label,
            ordinal + offset,
            used_labels,
        )
        parsed = _DETAIL_LABEL_RE.match(formatted)
        if parsed:
            used_labels.add(parsed.group("label").strip())
        output.append(f"  - {formatted}")


def _semantic_detail_chunks(value: object) -> list[str]:
    """Split overlong details only at complete report-sentence boundaries.

    The first chunk keeps an existing parenthetical label. Later chunks are
    labelled from their own content by ``format_narrative_detail``. No
    sentence is shortened, and a single long sentence remains intact so a
    metric, proper noun, or quotation is never cut in half.
    """

    text = _clean_text(value)
    existing = _DETAIL_LABEL_RE.match(text)
    existing_label = existing.group("label").strip() if existing else ""
    body = existing.group("body").strip() if existing else text
    if len(body) <= NARRATIVE_DETAIL_MAX_CHARACTERS:
        return [text]
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?。])\s+", body)
        if item.strip()
    ]
    if len(sentences) <= 1:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_characters = 0
    for sentence in sentences:
        candidate_characters = current_characters + len(sentence) + (1 if current else 0)
        should_flush = bool(current) and (
            len(current) >= NARRATIVE_DETAIL_MAX_SENTENCES
            or candidate_characters > NARRATIVE_DETAIL_MAX_CHARACTERS
        )
        if should_flush:
            chunks.append(" ".join(current))
            current = [sentence]
            current_characters = len(sentence)
        else:
            current.append(sentence)
            current_characters = candidate_characters
    if current:
        chunks.append(" ".join(current))
    if len(chunks) <= 1:
        return [text]
    if existing_label:
        chunks[0] = f"({existing_label}) {chunks[0]}"
    return chunks


def _append_detail_continuation(output: list[str], value: object) -> bool:
    """Append an unmarked wrapped line to the preceding detail paragraph."""

    if not output or not output[-1].startswith("  - "):
        return False
    continuation = nominalize_report_sentences(value)
    if not continuation:
        return True
    output[-1] = f"{output[-1].rstrip()} {continuation}"
    return True


_BULLET_RE = re.compile(r"^(?:[•●○◦❍∙ㆍㅇ])\s*(?P<body>\S.*)$")
_DETAIL_RE = re.compile(r"^(?:[-–—▪■◆◇])\s*(?P<body>\S.*)$")
_OUTLINE_HEADING_RE = re.compile(
    r"^(?:[가-하]\s*[.)]|\(?\d+(?:\.\d+)*\s*[.)]|[①-⑳])\s*(?P<body>\S.*)$"
)
_PAREN_HEADING_RE = re.compile(r"^[\(（](?P<body>[^()（）]{2,90})[\)）]\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s*(?P<body>\S.*)$")


def _clean_text(value: object) -> str:
    text = str(value or "").replace("\t", " ")
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _as_heading(value: str) -> str:
    text = _clean_text(value)
    match = (
        _MARKDOWN_HEADING_RE.match(text)
        or _OUTLINE_HEADING_RE.match(text)
        or _PAREN_HEADING_RE.match(text)
    )
    return _clean_text(match.group("body")) if match else ""


def _plain_outline_label(value: object) -> str:
    """Normalize nested bullet/number prefixes for exact label comparison."""

    text = _clean_text(value)
    previous = None
    while text and text != previous:
        previous = text
        text = re.sub(r"^(?:[•●○◦❍∙ㆍㅇ]|[-–—▪■◆◇])\s*", "", text).strip()
        text = re.sub(
            r"^(?:[가-하]\s*[.)]|\(?\d+(?:\.\d+)*\s*[.)]|[①-⑳])\s*",
            "",
            text,
        ).strip()
        text = re.sub(
            r"^(?:(?:[IVXLCDM]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*[.)]?)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        text = re.sub(r"^#{1,6}\s*", "", text).strip()
    return re.sub(r"[\s·ㆍ_-]+", "", text).strip(".:：()[]【】").casefold()


def is_redundant_narrative_outer_heading(part_id: str, value: object) -> bool:
    """Return whether a body line repeats the fixed template section title."""

    normalized = _plain_outline_label(value)
    return bool(normalized) and any(
        normalized == _plain_outline_label(label)
        for label in NARRATIVE_OUTLINE_OUTER_LABELS.get(part_id, ())
    )


def canonical_narrative_outline_lines(part_id: str, lines: Iterable[object]) -> list[str]:
    """Return deterministic `ㅇ`/`-` paragraphs for a narrative section.

    The generator owns the words; this function owns only paragraph hierarchy.
    It never summarizes, truncates, or rewrites a claim.
    """

    if part_id not in NARRATIVE_OUTLINE_PART_IDS:
        return [str(item) for item in lines]

    output: list[str] = []
    has_parent = False
    default_label = NARRATIVE_OUTLINE_DEFAULT_LABELS[part_id]
    parent_label = ""
    detail_ordinal = 0
    used_detail_labels: set[str] = set()
    paragraph_break = False

    def ensure_parent() -> None:
        nonlocal has_parent, parent_label, detail_ordinal, used_detail_labels
        if not has_parent:
            output.append(f" ㅇ {default_label}")
            has_parent = True
            parent_label = default_label
            detail_ordinal = 0
            used_detail_labels = set()

    for raw in lines:
        text = _clean_text(raw)
        if not text:
            paragraph_break = True
            continue
        if is_redundant_narrative_outer_heading(part_id, text):
            continue
        bullet = _BULLET_RE.match(text)
        if bullet:
            bullet_body = _clean_text(bullet.group("body"))
            # Do not render two competing outline tokens such as
            # ``ㅇ 가. 사업 특수성``.  The fixed report hierarchy owns the
            # visible ``ㅇ``; a nested generated heading number is metadata.
            nested_heading = _as_heading(bullet_body)
            parent_label = nested_heading or bullet_body
            output.append(f" ㅇ {parent_label}")
            has_parent = True
            detail_ordinal = 0
            used_detail_labels = set()
            paragraph_break = False
            continue
        detail = _DETAIL_RE.match(text)
        if detail:
            ensure_parent()
            detail_ordinal += 1
            _append_outline_detail(
                output,
                detail.group("body"),
                parent_label,
                detail_ordinal,
                used_detail_labels,
            )
            paragraph_break = False
            continue
        heading = _as_heading(text)
        if heading:
            output.append(f" ㅇ {heading}")
            has_parent = True
            parent_label = heading
            detail_ordinal = 0
            used_detail_labels = set()
            paragraph_break = False
            continue
        ensure_parent()
        if not paragraph_break and _append_detail_continuation(output, text):
            paragraph_break = False
            continue
        detail_ordinal += 1
        _append_outline_detail(output, text, parent_label, detail_ordinal, used_detail_labels)
        paragraph_break = False
    return output


def canonical_narrative_outline_text(part_id: str, value: object) -> str:
    return "\n".join(
        canonical_narrative_outline_lines(
            part_id,
            str(value or "").replace("\r", "").splitlines(),
        )
    ).strip("\n")


def narrative_outline_issues(part_id: str, value: object) -> list[str]:
    """Validate that stored narrative text is ready for deterministic HWPX layout."""

    if part_id not in NARRATIVE_OUTLINE_PART_IDS:
        return []
    lines = [line for line in str(value or "").replace("\r", "").splitlines() if line.strip()]
    issues: list[str] = []
    if not lines:
        return ["서술형 본문이 비었습니다."]
    if any(is_redundant_narrative_outer_heading(part_id, line) for line in lines):
        issues.append("HWPX 고정 섹션 제목이 본문 ㅇ 문단으로 중복됨")
    if re.search(r'(?m)^\s*-\s+\([^()\n]+\)\s*\([^()\n]*[가-힣][^()\n]*\)', str(value or '')):
        issues.append("한 문단 선두에 괄호 소제목이 연속됨: 본문 의미에 맞는 소제목 하나만 사용")
    if any(not re.match(r"^\s*(?:ㅇ|-)\s+\S", line) for line in lines):
        issues.append("모든 서술형 문단은 독립된 ㅇ 또는 - 계층이어야 함")
    if any(
        line.lstrip().startswith("- ") and re.search(r"(?:다|습니다)\.", line)
        for line in lines
    ):
        issues.append("- 세부 문단은 ~함·~음·~됨의 개조식 종결이어야 함")
    if any(
        line.lstrip().startswith("- ")
        and len(line.strip()) > NARRATIVE_DETAIL_MAX_CHARACTERS
        for line in lines
    ):
        issues.append(
            f"- 세부 문단은 약 {NARRATIVE_DETAIL_MAX_CHARACTERS}자 이내의 의미 단위로 분리해야 함"
        )
    parent_seen = False
    labels_for_parent: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("ㅇ "):
            parent_seen = True
            labels_for_parent = set()
        elif stripped.startswith("- ") and not parent_seen:
            issues.append("상위 ㅇ 문단보다 먼저 나온 - 세부 문단이 있음")
            break
        elif stripped.startswith("- "):
            detail = re.match(r"^-\s+\(([^()]{2,15})\)\s+", stripped)
            if detail:
                label = detail.group(1).strip()
                if label in labels_for_parent:
                    issues.append(f"같은 ㅇ 문단에서 요약어 '{label}'이 중복됨")
                labels_for_parent.add(label)
    if re.search(r"(?m)^\s*(?:#{1,6}\s+|[가-하]\s*[.)]\s+)|\t|\*\*|__", str(value or "")):
        issues.append("Markdown·한글 자모 제목·탭·굵게 표식이 남아 있음")
    return issues
