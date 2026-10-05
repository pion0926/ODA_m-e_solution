# K-ODAME

개발 원칙: [AGENTS.md](AGENTS.md) · [Playwright·MCP·문서 엔진 관리](docs/service/development-tooling.md)

프로젝트별 ODA 자료 등록, PDM 성과 모니터링, DAC 평가, 종료평가 보고서 작성 서비스입니다.
현재 소스 기준선은 **V2.4.23 (2026-10-06)**입니다. 운영 이미지 기준은 웹 V2.4.23 / API V2.4.21이며, 작업공간 수정이나 GitHub push만으로 운영 환경이 배포되지는 않습니다.

최근 변경과 검증 범위는 [변경 이력](CHANGELOG.md)을 참고합니다.

## 환경과 실행

| 환경 | Compose 프로젝트 | 주소 | 저장소 |
| --- | --- | --- | --- |
| 개발 | `docker-compose.yml` / `odame` | http://127.0.0.1:8002 | 기존 DB 볼륨, `data-redesign/` |
| 운영 | 고정 릴리스의 `compose.production.yml` / `odame-prod` | https://app.kodame.kr | 독립 DB·파일 볼륨 |
| 합성 QA | `compose.qa.yml` / `odame-qa` | http://127.0.0.1:8004 | QA 전용 DB·파일 볼륨 |

`.env.example`을 `.env`로 복사하고 개발용 설정을 채웁니다. 비밀번호·API 키는 Git에 저장하지 않습니다.

```powershell
docker compose up -d --build --wait --wait-timeout 180
./tools/ops/Test-Service.ps1
```

첫 명령은 개발 환경만 변경합니다. 초기 관리자는 `admin`이며 실제 비밀번호는 해당 환경 설정을 사용합니다.
공개 서비스에서는 예제 비밀번호를 사용하면 안 됩니다. 관리자가 프로젝트와 사용자 계정을 발급합니다.
운영 상태는 `./tools/ops/Server.ps1 -Environment production -Action status`로 확인합니다.

## 서비스 흐름

1. **사업계획서**와 **PDM**을 지정된 영역에 등록합니다. 사업개요는 사업계획서, 지표·목표는 PDM을 기준으로 만듭니다.
2. 두 기준 문서가 완료되면 일반 자료를 등록합니다. 원본 저장 → 텍스트 추출 → 성격 판단 → 역할·요약·원문 사실 추출 → PDM/DAC/보고서 매핑을 저장합니다.
3. **성과지표 분석**에서 신규 문서·신규 매핑 조합을 검토하고 실행합니다. 기존 평가와 신규 근거를 함께 검토합니다.
4. **DAC 평가진단**에서 질문별 대상 자료와 검토 범위를 확인하고 별도로 평가합니다. 등록 사실·매핑·저장된 PDM 결과를 활용합니다.
   저장된 평가 근거를 바탕으로 기준별 보완 팁을 제공하며, 팁 조회가 점수를 변경하지는 않습니다.
5. 평가 입력의 변경 여부를 확인하면서 보고서 섹션을 생성합니다. 중단 작업은 유효한 기존 섹션을 보존하고 이어서 실행합니다.
6. HWPX 생성 시 내용·표·쪽수·목차를 검증합니다. 생성된 초안은 평가자의 검토가 필요합니다.
   전체 보고서 미리보기는 화면에 맞춰 시작하며 필요한 페이지만 렌더링하고 원문 텍스트 선택·복사를 지원합니다.

일반 자료의 매칭 근거가 검증되지 않으면 해당 제안을 제외합니다. 실패·중지된 일반 자료가 프로젝트 전체를 잠그지 않습니다.
기준 문서 교체는 확인을 요구하며, 기존 보고서는 삭제하지 않고 최신 입력 반영 여부를 구분합니다.

## 코드와 서버 구성

Nginx, FastAPI, 업로드 워커, PDM·DAC 워커, 보고서·출력 워커, PostgreSQL, HWPX 변환 서비스를 분리합니다.
일회성 마이그레이션이 성공해야 API가 시작됩니다. 긴 AI 작업은 DB에 저장한 뒤 별도 워커에서 실행합니다.
일반 업로드는 최대 4건 동시 처리하고, 기준 문서 갱신은 기존 직렬화 규칙을 유지합니다.

| 역할 | 위치 |
| --- | --- |
| 화면 HTML | `frontend/index.html` |
| 스타일 / 기본 동작 / 서버 연결 | `assets/app-styles.css`, `app-shell.js`, `app-controller.js` |
| 기능별 UI | `assets/service-*.js`, `foundation-upload.js`, `*-analysis-review.js` |
| API 라우트·인증·시작/종료 | `redesign/backend/kodame_intake/api/` |
| AI 전송·스키마 처리 | `ai_gateway.py`, `structured_output.py`, `ai/request_limits.py` |
| 핵심 / 보고서 프롬프트 | `ai/prompts/`, 루트 `prompts/` |
| 영속 작업 / 워커 | `workflow_queue.py`, `workflow_worker.py`, `worker.py` |
| 보고서 분량 / 생성 / 조판 | `report_content_policy.py`, `report_generator.py`, `hwpx_layout/` |

이전 `0821_OoooDaon_v1.0.html`은 진입 안내입니다. `main.py`와 `openrouter.py`는 기존 import 호환용입니다.

## 문서와 QA

- [구조와 설계 결정](docs/service/architecture-20260925.md)
- [운영·배포·복구 절차](docs/service/operations-20260925.md)
- [QA 결과와 개선 과제](docs/service/qa-refactor-20260925.md)
- [범위와 시작 기준선](docs/service/refactor-plan-20260925.md)
- [기존 고정 릴리스 배포 안내](docs/service/deployment-v1.0.0.md)

자동 검사에는 외부 AI 키를 전달하지 않습니다. 실제 AI 검증은 합성 QA 전용
`tools/ops/Run-SyntheticQAProbe.ps1`로 단계별 실행하며 API 사용료가 발생합니다.
