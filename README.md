# Korea ODA M&E Solution (KODAME)

KODAME의 리디자인 프론트엔드와 전용 API 프로토타입입니다.

## 실행

```powershell
docker compose up -d --build
```

브라우저에서 `http://127.0.0.1:8002/`로 접속합니다. API는 동일한 호스트의 `/api/v2` 경로로 제공됩니다.

## 구성

- `kodame-redesign-web`: HTML 디자인 제공 및 API 프록시
- `kodame-redesign-api`: 대시보드·평가기준·문서·보고서용 v2 API
- `data-redesign/`: 새 시스템 전용 로컬 데이터 저장소

백엔드 확장 방향은 `docs/redesign_backend_architecture.md`를 참고하세요.
