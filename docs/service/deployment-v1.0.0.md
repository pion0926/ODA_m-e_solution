# V1.0.0 운영·개발 서버

## 환경 경계

| 항목 | 운영 | 개발 |
|---|---|---|
| 접속 | http://127.0.0.1:8000/ | http://127.0.0.1:8002/ |
| Compose 프로젝트 | `odame-prod` | `odame` (기존 이름 보존) |
| 소스 | `V1.0.0` 커밋의 Git archive | 현재 작업 디렉터리 |
| 이미지 | `odame-release/*:1.0.0` + 실제 `sha256` ID 고정 | `odame-dev/*:latest` |
| DB | `odame-prod_postgres-data` 신규 볼륨 | `odame_kodame-postgres-data` 기존 볼륨 |
| 문서/보고서 | `odame-prod_app-data` 신규 볼륨 | 기존 `data-redesign/` |
| 세션 쿠키 | `kodame_production_session` | `kodame_session` |
| 초기 데이터 | 관리자·빈 기본 프로젝트, 업무 자료 없음 | 기존 계정·자료·평가·보고서 유지 |

서로 다른 Compose 네트워크를 사용함. API/DB/문서 변환기는 운영 호스트 포트를 열지 않으며 웹만 공개함. 기본 바인딩은 두 환경 모두 `127.0.0.1`로 제한함. 웹사이트 2개이며 각 환경은 웹/API/작업자/DB/문서 변환기 5개 컨테이너로 구성됨.

## 현재 서버 제어

프로젝트 폴더에서 PowerShell로 실행함.

```powershell
# 운영 시작/상태/로그/정지 (개발에는 영향 없음)
./tools/ops/Server.ps1 production start
./tools/ops/Server.ps1 production status
./tools/ops/Server.ps1 production logs
./tools/ops/Server.ps1 production stop

# 개발 코드 수정 후 개발 서버만 재빌드
./tools/ops/Server.ps1 development start
```

`docker compose up -d --build`는 개발 전용임. 운영 시작 스크립트는 `.runtime/production-release.json`의 **릴리스 원본 Compose**를 읽고 `--no-build --pull never`로 저장된 이미지 ID만 실행함. 작업 디렉터리의 코드/양식/프롬프트 변경이나 `latest` 태그 교체는 운영에 반영되지 않음. 운영 이미지를 삭제하면 실행을 중단하며 개발 이미지로 대체하지 않음.

작업 디렉터리는 릴리스 저장 후 개발 브랜치 `codex/development`로 전환함. `V1.0.0` 브랜치는 고정 보존하고 이후 개발 커밋은 개발 브랜치에 추가함.

## 처음 설치하거나 새 호스트에 배포

```powershell
# V1.0.0 소스 및 Docker Desktop/Linux Docker가 준비된 상태
./tools/ops/New-ProductionEnvironment.ps1
./tools/ops/Build-Release.ps1 -Version V1.0.0 -GitRef V1.0.0
./tools/ops/Test-Deployment.ps1
./tools/ops/Server.ps1 production start
```

초기화는 기존 비밀 설정을 덮어쓰지 않음. 릴리스 빌드는 커밋된 파일만 사용하며 같은 릴리스 이미지 태그를 덮어쓰지 않음. Git에서 `backend/oda_me`, 프롬프트, 원본 서식, rHWP 정적 자산이 빠지면 빌드가 실패하도록 구성함. 다른 PC에 복제할 때 `.runtime`은 Git으로 전송되지 않으므로 그 호스트에서 별도 초기화해야 함. 위 스크립트는 PowerShell용임.

빌드는 당시 패키지 저장소를 사용할 수 있으므로 다른 날짜/호스트에서 같은 소스를 재빌드한 이미지가 바이트 단위로 동일하다는 보장은 없음. 현재 실행 중인 운영은 실제 이미지 ID에 고정되어 재빌드 영향이 없음. 동일 바이너리를 다른 서버로 이전하려면 릴리스 이미지를 `docker save`/`docker load` 또는 승인된 사설 레지스트리로 전달하고 ID를 대조해야 함.

## 관리자 및 비밀 설정

- 운영 관리자 아이디는 `admin`, 최초 비밀번호는 `.runtime/production.env`의 `PROD_BOOTSTRAP_PASSWORD`임.
- 운영 DB 비밀번호는 개발과 독립된 난수임. 계정 비밀번호는 DB에 해시로 저장되며 재시작이 기존 비밀번호를 초기화하지 않음.
- `.runtime/production.env`, DB 덤프, 업로드/생성 결과, 로그는 Git에 포함하지 않음. `docker compose config` 전체 결과에도 비밀값이 포함되므로 공유하지 않음.
- 생성 시 개발 `.env`에서 AI 키/모델 설정만 가져올 수 있음. DB·자료는 공유하지 않지만 같은 OpenRouter 키를 쓰면 과금 한도는 공유됨. 별도 과금이 필요하면 운영 설정에서 별도 키를 지정함.
- 공개 회원가입 및 시연 계정 생성은 꺼져 있음. 고객 계정은 관리자가 프로젝트를 생성한 후 발급함.

## 백업 및 복구

```powershell
./tools/ops/Backup-Environment.ps1 production
./tools/ops/Backup-Environment.ps1 development
```

백업 중 해당 환경의 웹/API/작업자가 잠시 멈추고 DB 덤프와 파일 압축을 함께 생성한 후 원래 컨테이너를 재시작함. 다른 환경은 중단하지 않음. `.runtime/backups/<환경>-<시간>/`에 `database.dump`, `files.tar.gz`, `checksums.json`이 생김. 장기 실행 중인 분석·보고서 작업이 없을 때 수행해야 함.

복구는 기존 볼륨을 지우고 즉시 덮어쓰는 명령을 제공하지 않음. 새 격리 환경에 PostgreSQL DB와 앱 역할을 초기화하고 덤프·파일을 같은 시점으로 복원한 뒤 계정/문서/보고서 접근을 확인하여 전환함. 스냅샷의 비밀정보도 별도로 안전하게 보관해야 함. `docker compose down -v`, 볼륨 prune, 운영 DB에 개발 덤프 덮어쓰기를 사용하지 말 것.

## 외부 공개 전 남은 운영 설정

이번 구성은 같은 컴퓨터에서 운영/개발 서비스를 독립 운용하는 단계임. 공인 도메인·원격 서버·HTTPS 인증서가 지정되지 않았으므로 인터넷 공개나 도메인 연결을 수행하지 않음. 외부 제공 시 운영 웹 앞에 HTTPS 리버스 프록시를 구성하고 `PROD_PUBLIC_URL`, `PROD_COOKIE_SECURE=true`를 설정한 뒤 로그인/업로드/긴 보고서 요청과 프록시 헤더를 검증해야 함. 개발은 외부에 공개하지 않음. 서버 절전 해제, Docker 자동 시작, 백업 외부 보관, 복원 훈련, 용량/오류 알림은 운영 정책에 맞게 추가해야 함.
