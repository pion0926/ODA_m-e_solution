# 발표자료 생성 구조

현재 15·30페이지 생성은 이 문서 하단의 **2026-09-06: 15·30페이지 샘플 기반 생성**을 참고한다.
아래 12장 구조는 기존 파일 호환성을 위한 구버전 기록이다.

## 목적

보고서 HWPX 조판 전 27개 섹션 원문과 연결 근거자료를 기반으로, 평가 의사결정용 12장 PPTX를 생성한다. Claude는 내용 선별과 발표 서사를 담당하고, 코드 기반 렌더러는 글꼴·여백·배치·페이지 안전성을 통제한다.

## 모듈

- `redesign/backend/kodame_intake/presentation_prompt.py`
  - Claude 시스템 프롬프트, few-shot 예시, 12장 서사, JSON 스키마, 글자 수 계약을 관리한다.
  - 프롬프트를 직접 수정할 때는 이 파일만 변경하면 된다.
- `config/presentation_reference_profile.json`
  - Google Drive 예시 폴더, 양식·흐름 참고 원칙, 내용 복사 금지 규칙, 디자인 변형군과 품질 목표를 관리한다.
  - Drive 자료를 내려받아 `samples/presentation_references/drive/`에 두면 다음 이미지 빌드부터 형식 통계가 자동 반영된다.
- `redesign/backend/kodame_intake/presentation_reference.py`
  - 참조 PPTX에서 슬라이드 비율·도형/텍스트/표/이미지 밀도·주요 글꼴만 추출하고, 샘플 문장은 모델에 보내지 않는다.
  - 프로젝트와 export ID를 해시해 4개 안전 디자인 변형 중 하나를 재현 가능하게 선택한다.
- `redesign/backend/kodame_intake/presentation_source.py`
  - HWPX 변환 전 저장 본문 27개, 최신 PDM, 최신 DAC 평가결과, 연결 문서를 수집한다.
  - 외부 모델 전송 전 민감정보 비식별화를 적용한다.
- `redesign/backend/kodame_intake/presentation_exporter.py`
  - Claude Opus의 구조화 응답을 정규화하고 12개 독립 레이아웃으로 편집 가능한 PPTX를 만든다.
  - PDM 4단계와 권고 로드맵 형식을 코드에서 한 번 더 보정한다.
- `redesign/backend/kodame_intake/presentation_quality.py`
  - 슬라이드 수, 빈 장, 경계 이탈, 텍스트 넘침 가능성, 텍스트 상자 겹침, 16pt 미만 본문, 제목 누락을 검사한다.
  - LibreOffice와 Poppler로 실제 렌더링해 12장 이미지와 제목 보존을 확인한다.
  - 서사 20, 참조 양식 15, 시각 위계 20, 레이아웃 25, 출처 10, 디자인 다양성 10점으로 평가한다.

## 처리 흐름

1. 저장된 보고서 섹션과 근거자료를 수집한다.
2. 민감정보를 비식별화한다.
3. 참조 프로필에서 이번 export의 디자인 변형과 시드를 선택한다.
4. `OPENROUTER_PRESENTATION_MODEL`의 high reasoning으로 12장 발표 설계 JSON을 생성한다.
5. JSON 스키마와 실제 섹션·문서 식별자를 검증한다.
6. 코드 기반 레이아웃으로 PPTX를 생성하고 각 장에 `[Sources]` 발표자 노트를 기록한다.
7. 구조 검사와 실제 렌더 검사를 수행하고 100점 루브릭으로 평가한다.
8. 90점 미만 또는 하나라도 검증 이슈가 있으면 피드백을 넣어 최대 3회 다시 생성한다.
9. 90점 이상이면서 모든 하드 게이트를 통과한 파일만 다운로드 가능 상태로 바꾼다.

## 고정 품질 기준

- 정확히 12장, 인접 슬라이드 실루엣 중복 금지
- 표지 50pt, 제목 35pt, 중간 제목 24pt, 본문 16pt 이상
- 본문을 줄여 맞추지 않고 글자 수 계약과 레이아웃별 예산으로 제어
- PDM은 `투입·활동 → 산출물 → 성과 → 영향` 순서 보장
- 권고는 `과제명 | 책임주체 | 시점 | 확인자료`를 2×2 카드로 표시
- 보고서 본문에는 파일명·페이지 인용을 반복하지 않고 발표자 노트에 근거를 보존

## 설정

- 기본 모델: `anthropic/claude-opus-5`
- 환경변수: `OPENROUTER_PRESENTATION_MODEL`
- 참조 프로필: `PRESENTATION_REFERENCE_PROFILE_PATH`
- 최소 품질점수: `PRESENTATION_MIN_QUALITY_SCORE` (기본 90)
- 최대 재생성 횟수: `PRESENTATION_MAX_GENERATION_ATTEMPTS` (기본 3)
- 슬라이드 수와 역할: `presentation_prompt.py`의 `SLIDE_COUNT`, `ROLE_SEQUENCE`, `LAYOUT_SEQUENCE`
# 2026-09-06: 15·30페이지 샘플 기반 생성

현재 POST `/api/v2/report/presentations`는 `{"slide_count":15}` 또는 `{"slide_count":30}`을 받는다.
50, 12, 10 등 다른 분량은 HTTP 422로 거절한다. body를 생략한 이전 클라이언트는 15장으로 생성한다.
선택값은 `presentation_exports.slide_count`에 저장하여 대기/진행/완료 응답과 파일명이 일치하게 한다.
기존 파일은 실제 검증 메타데이터의 장수를 사용하고, 구버전 12장 파일도 다운로드할 수 있다.

## 책임별 편집 위치

| 파일 | 편집 대상 |
|---|---|
| `presentation_profiles.py` | 15·30장 각각의 제목, 순서, 원본 PDF 페이지 대응, 근거 섹션, 표 열 구성 |
| `presentation_reference_prompt.py` | few-shot, 내용 작성·압축, source 검증, 사진 선택 기준 |
| `presentation_reference_renderer.py` | 샘플별 화면비, 제목 띠/구분선, 편집 가능한 표, 행높이, 사진 비율 |
| `presentation_photos.py` | 현재 프로젝트 등록 증빙의 사진 추출 및 식별 |
| `presentation_reference_export.py` | 3장 단위 Claude 작성, 실패 피드백 재시도, 렌더 검증, 결과 저장 |
| `presentation_quality.py` | 실제 PDF 렌더 결과의 장수, 제목·표 셀·본문 누락 검사 |

남아공 PDF 15장은 같은 순서를 유지한다. 일관성 등 현재 사업의 평가기준을 해당 장표에 함께 반영한다.
모잠비크 PDF는 실제 50장이다. 모든 원본 페이지를 대응표에 포함하되 중복 간지와 종합/상세 평가를 통합하여
정확히 30장으로 만든다. DEA·현장조사 등 샘플 사업 특유의 분석을 현재 사업에서 수행한 것으로 생성하지 않는다.

PDF에는 PPT 마스터가 없으므로 샘플 디자인을 편집 가능한 네이티브 표·텍스트로 재구성한다.
기존 12장 생성기의 무작위 팔레트·대시보드형 레이아웃은 신규 15·30장 경로에 적용하지 않는다.
생성 계획 JSON도 PPTX와 함께 보존한다. 글자 크기를 자동 축소해 내용을 숨기지 않으며, 셀·본문이 넘치면
해당 생성 묶음을 피드백과 함께 다시 작성한다. 최종 렌더에서 본문 누락이 있으면 해당 장표를 재작성한다.

사진은 보고서에 연결된 현재 프로젝트 문서에서만 추출한다. 모델이 실제 후보 이미지를 보고 관련 사진을 선택하며
사진은 원래 비율을 유지하여 박스 안에 전체가 들어오게 배치한다. 원본 샘플 사업의 사진·로고는 사용하지 않는다.
API 서버의 내부 UUID는 외부 모델용 비식별화 문자열과 분리해 조회한다.

---

위의 12장 구조는 구버전 기록이며 신규 요청은 15·30장 경로로 실행된다.

## 2026-09-16 전용 모델과 가독성 갱신

- 신규 발표자료 API는 `OPENROUTER_PRESENTATION_MODEL`(기본 `openai/gpt-6-astra`)을 실시간 제공 목록으로 확인한 뒤 export 행과 background context에 고정한다. 일반 보고서/프로젝트의 모델 배정은 변경하지 않는다.
- 전용 환경변수가 과거 프로젝트 모델 통합 과정에서 무시되던 경로를 복구했다. 모델 제공이 확인되지 않으면 명시적으로 실패하며 다른 모델로 몰래 전환하지 않는다.
- 표 15~16pt, 설명 16pt, 평점 열 16% 폭, 테마 그림자 제거. `presentation_profiles.py`의 글자 수 계약도 새 글자 크기에 맞춘다.
- 상세 검증 및 미완료 항목은 `docs/qa/reports/FT-20260916-user-requests-review.md` 참고. 기존 내용으로 만든 재조판 검수본과 실제 Astra 신규 생성 시험을 구분한다.
