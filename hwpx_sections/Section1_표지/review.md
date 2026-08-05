# Section 1 표지 슬롯 검수 초안

## 기준 파일

- 기준 HWPX: `samples/5-1. 종료평가 결과보고서 placeholder.hwpx`
- 섹션 XML: `Contents/section0.xml`
- 원본 XML 보관본: `hwpx_sections/Section1_표지/original.xml`
- 검수용 슬롯 파일: `hwpx_sections/Section1_표지/slots.review.json`
- 원본 XML SHA256: `8b5fb9aeb2fe6d5259bf935fd945b47e1d3676066e903f9b7afdba6163314f49`

## 구조 보존 원칙

섹션 1에서는 XML 양식을 그대로 유지하고, 지정된 `hp:t` 텍스트 노드의 문자열만 바꾼다.

금지:

- 문단 추가/삭제
- 런 추가/삭제
- `hp:lineBreak` 추가
- `hp:linesegarray` 수정
- 표/그림/섹션 속성 수정
- placeholder cleanup 같은 일괄 삭제

원본 구조 체크값:

| 항목 | 값 |
| --- | ---: |
| `hp:p` 문단 수 | 20 |
| `hp:tbl` 표 수 | 0 |
| `hp:t` 텍스트 노드 수 | 6 |
| `hp:lineseg` 수 | 20 |

## 문단별 원본 텍스트

| 문단 index | 원본 텍스트 | 판단 |
| ---: | --- | --- |
| 0 | 빈 문단/섹션 속성 포함 | 유지 |
| 1 | `{사업이름} ` | 사업명만 교체 |
| 2 | `종료평가 결과보고서` | 유지 |
| 3-4 | 빈 문단 | 유지 |
| 5 | `2023. 12` | 작성 연월 교체 |
| 6-14 | 빈 문단 | 유지 |
| 15 | `평가책임자 OOO` | 평가책임자 교체 |
| 16 | `평가수행기관 OOO(혹은 로고)` | 평가수행기관 텍스트 교체 |
| 17-19 | 빈 문단 | 유지 |

## 대체 후보

| slot id | 위치 | 원문 | 생성 주체 | 대체값 key | 비고 |
| --- | --- | --- | --- | --- | --- |
| `cover.project_title` | paragraph 1, text node 0 | `{사업이름} ` | LLM | `project_title` | paragraph 2의 `종료평가 결과보고서`는 유지 |
| `cover.report_date` | paragraph 5, text node 0 | `2023. 12` | 알고리즘 | `report_date` | `YYYY. MM` 형식 |
| `cover.evaluation_manager` | paragraph 15, text node 0 | `평가책임자 OOO` | LLM + 검수 | `evaluation_manager` | 근거 없으면 확인 대상 |
| `cover.evaluation_institution` | paragraph 16, text node 0 | `평가수행기관 OOO(혹은 로고)` | LLM + 검수 | `evaluation_institution` | 로고 삽입은 안전 치환 범위 제외 |

## LLM 역할

LLM은 HWPX/XML을 수정하지 않는다. 섹션 1에서는 아래 JSON 값만 생성한다.

```json
{
  "project_title": "사업명 추가 정보 필요",
  "evaluation_manager": "평가책임자 확인 대상",
  "evaluation_institution": "평가수행기관 확인 대상"
}
```

`report_date`는 LLM이 아니라 프로젝트 완료일 또는 생성 시점 기준으로 알고리즘이 만든다.

## 알고리즘 역할

알고리즘은 `slots.review.json`의 `replacement` 위치만 사용한다. 적용 전후로 구조 체크값이 같아야 하고, 선택된 `hp:t` 텍스트 내용 외 XML은 바뀌면 안 된다.
