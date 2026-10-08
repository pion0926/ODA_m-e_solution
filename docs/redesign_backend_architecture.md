# KODAME redesign backend architecture

## Deployment boundary

- Redesign frontend: `kodame-redesign-web`, host port `8002`.
- Redesign backend: `kodame-redesign-api`, internal port `8100`, separate `data-redesign/` storage.
- Intake worker: `kodame-intake-worker`, PostgreSQL 큐에서 한 번에 한 문서만 처리.
- PostgreSQL: 문서 상태, 처리 이력, 분석 결과와 다중 슬롯 제안을 영속 저장.
- The browser uses only `http://localhost:8002`; Nginx proxies `/api/v2/*` to the redesign API.

## Target module boundaries

1. `api`: HTTP contracts, validation, authentication and serialization.
2. `application`: dashboard, document, evaluation and report use cases.
3. `domain`: projects, DAC criteria, evidence slots, evaluations and report sections.
4. `infrastructure`: storage, metadata database, extraction and LLM clients.
5. `workers`: asynchronous extraction, classification, evaluation and report jobs.

## Intake state machine

`queued → parsing → stored → analyzing → classifying → review`

- 워커는 `FOR UPDATE SKIP LOCKED`와 임대시간(lease)을 사용해 중복 처리를 방지한다.
- 원본은 UUID 디렉터리에 저장하고 SHA-256을 기록하며, 추출 본문은 별도 파일에 원자적으로 저장한다.
- OpenRouter 키가 없으면 `waiting_llm`으로 멈추고 파싱 결과를 보존한다.
- 일시 오류는 지수 백오프로 재시도하고 최대 횟수를 넘으면 `failed`로 전환한다.
- 모든 단계는 `processing_events`에 기록한다.

The API and worker live in `redesign/backend/kodame_intake`. Features can move into these layers without changing `/api/v2` browser contracts.

## Initial API contract

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Container health |
| GET | `/api/v2` | API discovery/version |
| GET | `/api/v2/dashboard` | Summary, progress and DAC scores |
| GET | `/api/v2/criteria` | Criteria and evidence coverage |
| GET | `/api/v2/documents` | Document list contract |
| GET | `/api/v2/reports/sections` | Report-section contract |

## Migration sequence

1. Replace in-memory dashboard arrays with dashboard and criteria APIs.
2. Add upload, extraction-job and evidence-slot assignment APIs.
3. Add evaluation drafts/versions with a separate human-approval transition.
4. Add report editing, generation jobs and export/download APIs.
5. Add production migrations, backups and observability before persistent rollout.
