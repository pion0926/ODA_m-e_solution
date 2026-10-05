from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path


PROFILE_ENV = "REPORT_QUALITY_PROFILE_PATH"
CONTAINER_PATH = Path("/app/config/report_quality_profile.json")
REPOSITORY_PATH = Path(__file__).resolve().parents[1] / "config" / "report_quality_profile.json"


@lru_cache(maxsize=1)
def writing_profile() -> dict:
    configured = os.getenv(PROFILE_ENV, "").strip()
    path = Path(configured) if configured else (CONTAINER_PATH if CONTAINER_PATH.exists() else REPOSITORY_PATH)
    value = json.loads(path.read_text(encoding="utf-8"))
    profile = value.get("writing")
    if not isinstance(profile, dict):
        raise RuntimeError(f"writing 품질 프로필이 없습니다: {path}")
    return profile


def report_writing_policy_prompt() -> str:
    profile = writing_profile()
    generic_labels = ", ".join(str(item) for item in profile.get("forbidden_generic_detail_labels") or [])
    repetitive_phrases = ", ".join(str(item) for item in profile.get("forbidden_repetitive_phrases") or [])
    grade_sentences = profile.get("grade_reason_sentences") or [2, 3]
    feedback_items = profile.get("feedback_item_range") or [3, 6]
    lesson_items = profile.get("lesson_item_range") or [3, 5]
    narrative_layout = profile.get("narrative_detail_layout") or {}
    maximum_characters = int(narrative_layout.get("maximum_characters") or 360)
    maximum_sentences = int(narrative_layout.get("maximum_sentences") or 4)
    return f"""[편집 가능한 보고서 품질 정책]
- 괄호형 핵심어는 문단의 실제 판단을 요약할 때만 사용한다. `{generic_labels}` 같은 범용 라벨을 여러 문단에서 반복하지 않는다.
- 기본은 `- 본문`이며 큰 논거를 구분할 때만 소제목을 붙인다. 선두 괄호 소제목은 최대 1개이다. `(운영 자립) (현장 적용 효과 검증)`처럼 연속으로 쓰지 않는다. 관찰 성과와 향후 검증 과제를 구분하고, 본문이 검증 필요성이면 이를 자립 성과로 이름 붙이지 않는다.
- `{repetitive_phrases}` 같은 증거 유무 선언으로 판단을 대신하지 않는다. 확인한 사실, 그 의미, 남은 한계를 직접 쓴다.
- 평가등급 산정 이유는 질문별로 {grade_sentences[0]}~{grade_sentences[1]}개 완결 문장으로 작성하고, 성과·한계·점수 결론을 연결한다. 평점행 산정 이유는 비운다.
- 환류과제는 중요도 순 {feedback_items[0]}~{feedback_items[1]}건, 교훈은 {lesson_items[0]}~{lesson_items[1]}건으로 통합한다. 같은 조치를 말만 바꾸어 중복하지 않는다.
- 표 셀에 맞추려고 문장을 중간에서 자르지 않는다. 한 셀은 하나의 판단 또는 실행조치만 담아 짧고 완결되게 쓴다.
- 서술형 `- (핵심어) 본문` 한 문단은 서로 연결된 2~{maximum_sentences}개 문장, 약 {maximum_characters}자 이내를 기준으로 한다. 이를 넘으면 문장마다가 아니라 판단·근거·한계·조치의 의미 단위로 다음 `- (다른 핵심어)` 문단을 만든다.
- 영문 약어·기관명은 최초 1회 한글명과 함께 설명하고 이후 동일한 표기를 사용한다.""".strip()


def report_writing_policy_issues(content: object) -> list[str]:
    text = str(content or "")
    profile = writing_profile()
    issues: list[str] = []
    for label in profile.get("forbidden_generic_detail_labels") or []:
        count = len(re.findall(rf"\({re.escape(str(label))}\)", text))
        if count > 1:
            issues.append(f"범용 괄호 라벨 반복: {label} {count}회")
    for phrase in profile.get("forbidden_repetitive_phrases") or []:
        count = text.count(str(phrase))
        if count:
            issues.append(f"상투적 근거 문구 잔존: {phrase} {count}회")
    narrative_layout = profile.get("narrative_detail_layout") or {}
    maximum_characters = int(narrative_layout.get("maximum_characters") or 360)
    for line in text.replace("\r", "").splitlines():
        # Indexed PDM records are multiple table cells, not one prose paragraph.
        # Their row wrapping/splitting is validated by the HWPX table pipeline.
        if re.match(r'^\s*-\s*\[(?:outcome|outputs?)[-\s][\w.-]+\]\s*[:：]?\s*성과지표\s*[:：]', line, re.IGNORECASE):
            continue
        if line.lstrip().startswith("- ") and len(line.strip()) > maximum_characters:
            issues.append(
                f"서술형 세부 문단 시각 예산 초과: {len(line.strip())}자 > {maximum_characters}자"
            )
    return issues
