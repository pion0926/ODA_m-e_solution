# KODAME redesign backend architecture

## Deployment boundary

- Redesign frontend: `kodame-redesign-web`, host port `8002`.
- Redesign backend: `kodame-redesign-api`, internal port `8100`, separate `data-redesign/` storage.
- The browser uses only `http://localhost:8002`; Nginx proxies `/api/v2/*` to the redesign API.

## Target module boundaries

1. `api`: HTTP contracts, validation, authentication and serialization.
2. `application`: dashboard, document, evaluation and report use cases.
3. `domain`: projects, DAC criteria, evidence slots, evaluations and report sections.
4. `infrastructure`: storage, metadata database, extraction and LLM clients.
5. `workers`: asynchronous extraction, classification, evaluation and report jobs.

The prototype starts with a dependency-free contract in `redesign/backend/app.py`. Features can move into these layers without changing `/api/v2` browser contracts.

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
