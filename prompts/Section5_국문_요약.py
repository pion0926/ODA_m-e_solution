from __future__ import annotations

from editor_prompt_runner import build_prompt_input as _build_editor_prompt_input
from editor_prompt_runner import main as _editor_prompt_main
from editor_prompt_runner import request_model


EDITOR_PROMPT = """[작성 대상]
Section 5: I. 평가결과 요약 - 1. 국문 요약의 제출용 본문을 작성한다.

[고정 상위 구조]
다음 다섯 항목을 제목·번호·순서까지 정확히 유지한다.
(1) 대상사업개요
(2) 평가개요
(3) 성과달성도
(4) 기준별 평가결과
(5) 결론

[문단 계층과 서식]
1. 각 상위 항목 아래의 논점을 `ㅇ` 문단으로 구분하고, 해당 논점의 설명·근거·평가판단은 `-` 문단에 쓴다.
2. `ㅇ` 앞에는 공백 1회를 두고, `-` 앞에는 공백을 두지 않는다. HWPX 문단 스타일이 하위 들여쓰기를 담당하므로 `-` 앞에 공백을 넣으면 안 되며, 내용은 표식 뒤에서 바로 시작한다.
3. `가. 사업명`, `나. 사업개요`, `다. 평가개요` 같은 한글 자모 상위 구조를 쓰지 않는다.
4. 사업명·대상국/지역·기간·예산·목적·주요내용은 `(1) 대상사업개요`의 `ㅇ 사업 기본정보` 아래에 배치한다.
5. Markdown 제목(`#`, `##`, `###`), 표, 굵게 표식, XML, 코드블록을 쓰지 않는다.
6. 각 `ㅇ`과 `-`는 독립 문단이며 한 줄 안에서 표식을 반복하지 않는다.
7. 전체 본문은 공백 포함 5,800~9,000자 수준으로 작성하여 HWPX 조판 기준 최소 4쪽을 확보한다.
8. 분량은 같은 말을 반복해서 늘리지 않고, 현재 사업의 확인 사실·평가판단·근거 한계·후속 함의를 서로 다른 문단으로 확장한다.
9. `-` 문단은 기본적으로 `- 본문`으로 작성한다. 같은 `ㅇ` 아래에서 3개 이상의 세부 논거가 실제로 큰 주제로 나뉘어 독자의 탐색을 돕는 경우에만 `- (2~15자 핵심어 요약) 본문`을 선택적으로 사용한다.
10. 모든 세부 본문 문장은 `~함.`, `~음.`, `~됨.`, `~평가됨.`, `~필요함.`으로 끝내고 `~다.`, `~이다.`, `~하였다.`를 쓰지 않는다.
11. `-`는 문장마다 붙이지 않는다. 같은 하위 논거의 판단·근거·해석·후속 문장은 2~4문장의 한 문단으로 묶고, 논거가 달라질 때만 새 `-` 문단을 만든다.
12. `(협력·조정)`, `(제도적 성과)`, `(핵심 판단)`, `(근거와 한계)`처럼 모든 문단에 기계적으로 괄호 요약을 붙이지 않는다. 괄호 요약을 쓰는 경우에만 같은 `ㅇ` 아래에서 중복하지 않는다.
13. `1. 국문 요약`, `(1)~(5)` 상위 항목, 각 `ㅇ` 논점 앞에는 한 줄을 비워 시각적으로 계층을 구분한다.

[항목별 내용 계약]
- (1) 대상사업개요: `ㅇ 사업 기본정보`, `ㅇ 추진배경 및 주요내용`을 포함하고, 두 논점 아래에 총 6개 이상의 `-` 문단을 둔다. 사업 식별정보, 개발문제, 개입논리, 주요 활동·대상, 기대 성과를 구분한다.
- (2) 평가개요: `ㅇ 평가 목적과 범위`, `ㅇ 평가 방법`, `ㅇ 평가의 한계`를 포함하고, 세 논점 아래에 총 6개 이상의 `-` 문단을 둔다. 등록 자료로 입증되지 않은 면담·현지조사·신규 설문을 수행했다고 쓰지 않는다.
- (3) 성과달성도: `ㅇ 주요 성과달성도` 아래 6개 이상의 `-` 문단으로 최신 PDM 1건의 Outcome·Output 지표 체계, 확인된 실적, 미달·미산정 지표, 자료 신뢰도와 평가적 의미를 구분한다.
- (4) 기준별 평가결과: `ㅇ 적절성`, `ㅇ 일관성`, `ㅇ 효과성`, `ㅇ 효율성`, `ㅇ 지속가능성`을 이 순서로 각각 작성하고, 각 기준마다 2개 이상의 `-` 문단으로 핵심 판단과 근거·한계를 분리한다. 영향/파급효과를 별도 점수 기준으로 추가하지 않는다.
- (5) 결론: `ㅇ 종합 결론`, `ㅇ 작동요인`, `ㅇ 비작동요인`, `ㅇ 환류과제 및 교훈`을 포함하고, 각 논점마다 2개 이상의 `-` 문단으로 종합판단과 실행 함의를 구분한다. 새로운 사실을 추가하지 말고 앞선 판단을 종합한다.

[근거 및 내용 규칙]
1. 현재 평가대상 사업의 사업개요, 최신 PDM 1건, 성과달성도, 5개 DAC 평가결과, 결론·작동/비작동요인·환류과제만 사용한다.
2. 완성형 샘플보고서는 항목 순서, 논점 분리, 문단 밀도, 전문 문체만 참고한다. 샘플의 국가·기관·수치·성과·문장·판단은 절대 가져오지 않는다.
3. `(1차년도 사업계획서, p. 7)`, `pp. 1-2`, `3쪽` 같은 문서명·페이지 괄호 인용을 요약에 쓰지 않는다.
4. 확인된 수치와 판단은 구체적으로 쓰되 근거가 없는 수치는 만들지 않는다.
5. project_status가 ongoing이면 사업이 종료됐다고 단정하지 말고 현재시점 판단과 후속 확인과제를 구분한다.
6. 영문 상태값 ongoing/ended, 내부 근거 ID, 원본 파일명, 샘플 사업 고유명사를 쓰지 않는다.

[Few-shot 예시 1 — 형식과 구성만 참고]
(1) 대상사업개요

 ㅇ 사업 기본정보
- (사업명) {{CURRENT_PROJECT_TITLE}}
- (대상국·지역) {{CURRENT_COUNTRY_AND_REGION}}
- (기간·예산) {{CURRENT_PERIOD_AND_BUDGET}}
- (수행·협력체계) {{CURRENT_IMPLEMENTATION_ARRANGEMENT}}

 ㅇ 추진배경 및 주요내용
- {{CURRENT_DEVELOPMENT_PROBLEM_AND_NEED}}
- {{CURRENT_INTERVENTION_LOGIC_AND_MAIN_ACTIVITIES}}

(2) 평가개요

 ㅇ 평가 목적과 범위
- {{CURRENT_EVALUATION_PURPOSE}}
- {{CURRENT_EVALUATION_SCOPE}}

 ㅇ 평가 방법
- {{CURRENT_VERIFIED_DOCUMENT_REVIEW_METHOD}}
- {{CURRENT_VERIFIED_ANALYTICAL_METHOD}}

 ㅇ 평가의 한계
- {{CURRENT_LIMITATION_AND_EFFECT_ON_JUDGEMENT}}
- {{CURRENT_MITIGATION_AND_FOLLOW_UP_VERIFICATION}}

(3) 성과달성도

 ㅇ 주요 성과달성도
- (성과경로 범위) {{CURRENT_PDM_RESULT_CHAIN_SCOPE}}
- (확인된 달성) {{CURRENT_VERIFIED_ACHIEVEMENTS}}
- (미달·미산정) {{CURRENT_UNDERACHIEVED_OR_UNSCORED_INDICATORS}}
- (근거 신뢰도) {{CURRENT_EVIDENCE_RELIABILITY}}
- (평가적 의미) {{CURRENT_ACHIEVEMENT_INTERPRETATION}}
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
- {{CURRENT_IMPLEMENTATION_PRIORITY_AND_VERIFICATION}}

[Few-shot 예시 2 — 논증 흐름만 참고]
`ㅇ 논점` 다음의 `-` 문단은 현재 사업에 관한 `판단 → 확인된 근거 → 의미 또는 한계` 순서로 쓴다.
샘플의 사실을 채우지 말고 {{CURRENT_PROJECT_EVIDENCE_ONLY}}로 완전히 교체한다.

[출력 형식]
위의 다섯 상위 항목으로 구성된 국문 요약 본문만 반환한다. JSON, Markdown 코드펜스, 설명문은 반환하지 않는다.
"""


def build_prompt_input() -> dict:
    return _build_editor_prompt_input(__file__, EDITOR_PROMPT)


def main() -> None:
    _editor_prompt_main(build_prompt_input, request_model)


if __name__ == "__main__":
    main()
