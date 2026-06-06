# ODA M&E Solution Prototype

KOICA/ODA 종료평가 업무를 지원하기 위한 React + Python 기반 프로토타입입니다. DAC 평가기준별 증빙 문서 업로드, LLM 기반 평가 초안 생성, 참고문헌 관리, 평가보고서 패키지 다운로드 기능을 제공합니다.

## 주요 기능

- 메인 대시보드: DAC 평가기준별 1~4점 현황을 육각형 레이더 차트로 표시
- 평가항목 상세: 적절성, 일관성, 효과성, 효율성, 지속가능성 기준별 증빙 체크리스트와 평가결과 표시
- 문서 업로드: 개별 업로드 및 참고문헌 목록의 일괄 업로드 지원
- 분류 제안: 일괄 업로드 시 AI/휴리스틱 기반 분류 제안 후 사용자가 최종 확인
- LLM 평가: 신규 문서 확정 시 OpenRouter 기반 Gemini Flash-Lite 호출 구조로 평가결과 갱신
- 참고문헌: 업로드 문서 넘버링, 다운로드, 평가결과 내 각주 링크 지원
- 보고서 생성: 종료평가 보고서 패키지 ZIP 다운로드
  - 원본 HWP 양식 기반 보고서
  - DOCX 평가보고서
  - XLSX 등급 결과표
  - 참고문헌 목록 TXT

## 실행 방법

```powershell
$env:OPENROUTER_API_KEY="..."
$env:OPENROUTER_MODEL="google/gemini-3.1-flash-lite"
python backend/app.py
```

브라우저에서 다음 주소를 엽니다.

```text
http://127.0.0.1:8001/
```

## 프로젝트 구조

```text
.
├─ index.html
├─ assets/
│  ├─ app.jsx
│  └─ styles.css
├─ backend/
│  ├─ app.py
│  ├─ evaluation_specs.py
│  └─ hwp_report.ps1
└─ data/
   └─ .gitkeep
```

## 데이터 보관

업로드 문서, 추출 텍스트, 평가 JSON, 생성 보고서는 `data/` 아래에 로컬로 저장됩니다. 이 디렉터리의 실제 산출물은 개인정보와 원본문서 보호를 위해 Git에 포함하지 않습니다.

## HWP 보고서 생성

HWP 원본 양식 기반 보고서 생성은 Windows 한컴오피스 COM 자동화를 사용합니다. 한컴오피스가 설치되어 있지 않거나 COM 자동화가 차단된 환경에서는 HWP 대신 DOCX/XLSX 보고서만 생성될 수 있습니다.

## API 요약

- `GET /api/dashboard`
- `GET /api/criteria/{criterionId}`
- `POST /api/criteria/{criterionId}/documents`
- `DELETE /api/criteria/{criterionId}/documents/{documentId}`
- `GET /api/criteria/{criterionId}/documents/{documentId}/download`
- `POST /api/references/batch-upload`
- `POST /api/references/batch-confirm`
- `GET /api/reports/evaluation-package`
- `GET /api/ai/openrouter/status`
