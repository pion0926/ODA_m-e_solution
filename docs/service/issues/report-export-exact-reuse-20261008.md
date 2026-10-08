# 동일 입력의 검증된 HWPX 재사용

## 문제

보고서 미리보기는 매번 `POST /api/v2/report/exports`를 요청했다. 27개 본문과 평가·자료가 그대로이고 완료 파일이 있어도 새로운 내보내기 작업을 등록해 다시 조판했다.

## 수정과 재사용 경계

POST의 기존 사전 점검, 보고서 현재성, 프로젝트 작업 잠금 및 진행 중 내보내기 차단을 유지한다. 이후 다음 조건을 모두 만족하는 완료 파일만 기존 ID·다운로드 주소로 반환한다. 재사용 시 새 작업·파일·DB 결과를 만들지 않는다.

- 현재 lifecycle의 문서 digest·workflow digest·검증된 canonical evaluation basis가 일치한다. 단순 run ID 변경을 수반한 검증된 전체 DAC 재사용은 허용하며, 실질 재평가는 허용하지 않는다.
- 저장된 27개 섹션의 내용·상태·갱신시각 digest가 일치한다.
- 선택된 AI 모델이 기존 변화이론 산출물의 모델과 같다.
- 조판 계약·의미 보존·사업명·목차·rHWP 최종 렌더와 geometry 검증이 모두 성공했다.
- 완료 파일이 내보내기 디렉터리 안에 실제로 존재하며, 매 요청에서 읽은 파일 SHA-256이 최종 검증 SHA-256과 일치한다.
- 생성 시작과 완료 시 동일한 runtime stamp를 확인했다. stamp는 API/kordoc의 immutable `sha256:<64자리>` 이미지 ID 및 Python 조판 코드·템플릿·정책/슬롯 설정·배포된 rHWP 자산의 실제 bytes digest로 구성한다. 이미지 ID는 폰트·브라우저·OS 의존성과 외부 kordoc 엔진까지 구분한다. 코드·파일 digest는 크기/mtime/ctime 키로 프로세스 안에서만 캐시하며, persisted identity는 실제 bytes 기반이다.

파일 검사 후 문서·섹션·runtime을 다시 확인한다. 재사용 stamp가 없는 과거 파일, 환경 revision이 없거나 mutable tag인 개발 환경, 파일 변경/누락, 잘못된 캐시 메타데이터는 재사용하지 않고 기존 생성 경로를 따른다. 기존 결과를 성공 처리하도록 stamp를 소급 기록하지 않는다.

## 회귀 검증

`test_report_export_cache.py`에서 동일 파일 재사용 및 검증된 DAC replay, 입력별 변경, 수동 본문 수정, 모델·조판/image revision 변경, 레거시 검증 누락, 파일 변조·삭제·경로 이탈, 검사 중 변경, 진행 중 작업·stale 보고서 차단, malformed 캐시의 안전한 무시를 확인한다. `test_report_export_freshness.py`, `test_evaluation_replay_freshness.py`와 함께 외부 AI 키 없는 격리 QA에서 검증한다.

운영 배포 및 실제 요청 재사용 확인은 별도 배포/QA 기록을 따른다. 이미지 버전이 바뀐 배포의 최초 요청은 새로 검증해야 하므로 이전 릴리스 파일은 재사용하지 않는다.
