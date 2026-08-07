# ODA ImpactOps AI - Flightbase 배포 및 외부 테스트 가이드

## 1. 결론

첨부된 Flightbase 사용자 매뉴얼 v1.5.1은 워크스페이스에 커스텀 Docker 이미지를 등록하는 방법으로 `Pull`, `Dockerfile Build`, `Tar`, `NGC`를 지원한다. 배포 단계에서는 Docker 이미지, 배포 코드가 있는 학습 프로젝트, 실행 명령, 코드 경로, GPU 수와 환경변수를 지정하고, 워커가 실행되면 배포 카드의 `API` 버튼에서 외부 호출 주소를 확인하도록 안내한다.

다만 이 매뉴얼의 “배포”는 일반 웹 호스팅이 아니라 모델 추론 코드를 워커로 실행하고 플랫폼 API 게이트웨이로 호출하는 MLOps 기능이다. 컨테이너가 임의 포트 `8001`에서 제공하는 React/Python 웹 화면을 그대로 외부 URL에 연결하는 기능은 매뉴얼에 명시되어 있지 않다. 따라서 아래 항목을 Flightbase 운영 관리자에게 먼저 확인해야 한다.

1. Custom Deployment가 컨테이너의 임의 HTTP 포트 `8001`을 서비스/Ingress에 연결할 수 있는가?
2. 컨테이너 `CMD` 또는 `/app/backend/app.py`를 장기 실행 프로세스로 사용할 수 있는가?
3. 읽기/쓰기 데이터셋 또는 영속 볼륨을 `/app/data`에 마운트할 수 있는가?
4. 생성된 외부 주소에서 WebSocket이 아닌 일반 HTTP GET/POST/DELETE와 파일 다운로드를 허용하는가?
5. 요청 본문 제한과 게이트웨이 타임아웃을 문서 일괄 업로드 및 LLM 처리 시간에 맞게 조정할 수 있는가?

위 다섯 항목이 지원되면 이 문서의 Flightbase 직접 배포 절차를 사용한다. 임의 포트 공개가 지원되지 않으면 Flightbase에는 향후 GPU 기반 로컬 LLM만 모델 워커로 배포하고, 현재 웹 애플리케이션은 일반 VM, Kubernetes 또는 컨테이너 서비스에 배포하는 구성이 적합하다.

## 2. 준비된 이미지의 운영 특성

이미지는 하나의 컨테이너에서 정적 React 화면과 Python API를 함께 제공한다. 기본 포트는 `8001`, 상태 확인 경로는 `/healthz`, 영속 데이터 경로는 `/app/data`이다. HWP/HWPX 텍스트 처리용 `rhwp` 실행 파일도 이미지에 포함한다.

외부 테스트 시에는 Basic 인증을 반드시 활성화한다. 브라우저가 최초 접속 시 사용자명과 비밀번호를 묻고, 같은 출처의 API 요청에도 인증정보를 재사용하므로 프런트엔드 수정 없이 보호할 수 있다. `/healthz`만 플랫폼 헬스체크를 위해 인증 없이 공개된다.

이 애플리케이션은 OpenRouter API를 호출하므로 자체적으로 GPU를 사용하지 않는다. 초기 테스트 권장 자원은 2 vCPU, RAM 4GB, 영속 디스크 20GB 이상이다. 다수 문서를 동시에 분석하거나 큰 보고서를 생성하면 RAM 8GB 이상을 권장한다. GPU 자원은 로컬 LLM을 별도 배포할 때만 필요하다.

## 3. 이미지 생성

Docker Desktop을 실행한 뒤 프로젝트 루트에서 다음 명령을 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_flightbase_image.ps1
```

스크립트는 `oda-impactops-flightbase:1.0.0` 이미지를 빌드하고 `output/docker/oda-impactops-flightbase-1.0.0.tar` 파일과 SHA-256 해시를 생성한다. 버전을 바꾸려면 다음과 같이 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_flightbase_image.ps1 -Tag 1.0.1
```

업로드 전에 로컬에서 다음과 같이 실행한다. 실제 키와 비밀번호는 명령 기록에 직접 쓰지 말고 PowerShell 환경변수나 `.env`를 사용한다.

```powershell
$env:OPENROUTER_API_KEY="발급받은 키"
$env:APP_BASIC_AUTH_USER="reviewer"
$env:APP_BASIC_AUTH_PASSWORD="충분히 긴 임의 비밀번호"
docker run --rm -p 8001:8001 `
  -e OPENROUTER_API_KEY `
  -e APP_BASIC_AUTH_USER `
  -e APP_BASIC_AUTH_PASSWORD `
  -v oda-impactops-test-data:/app/data `
  oda-impactops-flightbase:1.0.0
```

다른 창에서 `http://127.0.0.1:8001/healthz`가 HTTP 200을 반환하는지 확인하고, 브라우저에서 `http://127.0.0.1:8001`에 접속해 Basic 인증 후 대시보드, 자료 등록, AI 상태 조회, 보고서 섹션 생성과 다운로드를 점검한다.

## 4. Flightbase에 TAR로 등록

레지스트리 계정 없이 전달하려면 TAR 방식이 가장 단순하다.

1. Flightbase 로그인 후 대상 워크스페이스로 이동한다.
2. `도커 이미지` 메뉴에서 `새 도커 이미지 생성`을 누른다.
3. 이미지 이름을 `oda-impactops-flightbase-1.0.0`으로 지정한다.
4. 생성 방식을 `Tar`로 선택하고 `output/docker/oda-impactops-flightbase-1.0.0.tar`를 업로드한다.
5. 공개 범위는 우선 해당 워크스페이스만 선택한다.
6. 이미지 설치 로그가 성공했는지 확인한 뒤 상세 화면에서 Python 버전과 이미지 정보를 확인한다.

TAR 파일이 플랫폼 업로드 제한을 초과하거나 반복 배포가 필요하면 아래 Pull 방식을 사용한다.

## 5. 컨테이너 레지스트리 Pull 방식

조직에서 허용한 Docker Hub, GHCR 또는 사설 레지스트리에 이미지를 올린다. `REGISTRY/PROJECT`는 실제 경로로 변경한다.

```powershell
docker tag oda-impactops-flightbase:1.0.0 REGISTRY/PROJECT/oda-impactops-flightbase:1.0.0
docker login REGISTRY
docker push REGISTRY/PROJECT/oda-impactops-flightbase:1.0.0
```

Flightbase의 `새 도커 이미지 생성`에서 생성 방식을 `Pull`로 선택하고 `REGISTRY/PROJECT/oda-impactops-flightbase:1.0.0`을 입력한다. 비공개 레지스트리라면 Flightbase 관리자가 제공하는 Registry Secret 기능을 사용하고 계정 비밀번호를 이미지 이름이나 Dockerfile에 기록하지 않는다.

## 6. Flightbase 워커 설정

임의 웹 포트 공개가 지원된다는 운영 관리자 확인을 받은 경우 다음 값으로 새 배포를 만든다.

| 항목 | 권장값 |
|---|---|
| Docker 이미지 | `oda-impactops-flightbase-1.0.0` |
| 실행 명령 | 이미지 `CMD` 유지 또는 `python3 /app/backend/app.py` |
| 컨테이너 포트 | `8001` |
| 헬스체크 | `GET /healthz`, HTTP 200 |
| GPU | `0` |
| CPU/RAM | 최소 2 vCPU / 4GB, 권장 4 vCPU / 8GB |
| 데이터 볼륨 | 읽기/쓰기 영속 볼륨을 `/app/data`에 마운트 |
| 워커 수 | 최초 1개. 현재 로컬 파일 저장 구조에서는 여러 워커 동시 실행 금지 |

환경변수는 Flightbase 워커 설정 화면에서 입력한다.

| 환경변수 | 필수 | 설명 |
|---|---:|---|
| `HOST=0.0.0.0` | 예 | 외부 서비스가 컨테이너에 연결할 수 있도록 바인딩 |
| `PORT=8001` | 예 | 애플리케이션 포트 |
| `DATA_DIR=/app/data` | 예 | 업로드 문서, 평가 결과, 보고서 저장 위치 |
| `OPENROUTER_API_KEY` | AI 기능 사용 시 | Secret으로 등록 |
| `OPENROUTER_MODEL` | 아니요 | 기본값 `google/gemini-3.1-flash-lite` |
| `OPENROUTER_REFERER` | 권장 | 최종 외부 HTTPS 주소 |
| `APP_BASIC_AUTH_USER` | 외부 공개 시 | 테스트 사용자명 |
| `APP_BASIC_AUTH_PASSWORD` | 외부 공개 시 | 길고 임의적인 비밀번호, Secret으로 등록 |
| `MAX_REQUEST_BYTES` | 아니요 | 기본 128MiB. 게이트웨이 제한보다 작게 설정 |

워커가 정상 실행되면 시스템 로그에서 `ODA ImpactOps Python backend running at http://0.0.0.0:8001`을 확인한다. 플랫폼이 제공한 외부 URL의 `/healthz`가 200인지 확인한 후 루트 URL에 접속한다.

## 7. 일반 VM 또는 Kubernetes 대안

Flightbase가 임의 웹 포트 공개를 지원하지 않으면 일반 Linux VM에서 `docker-compose.production.yml`을 사용하는 것이 가장 빠르다.

```bash
export ODA_IMAGE=REGISTRY/PROJECT/oda-impactops-flightbase:1.0.0
export OPENROUTER_API_KEY='...'
export APP_BASIC_AUTH_USER='reviewer'
export APP_BASIC_AUTH_PASSWORD='...'
export OPENROUTER_REFERER='https://oda.example.org'
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml ps
curl -fsS http://127.0.0.1:8001/healthz
```

공인 인터넷에는 컨테이너 포트 `8001`을 직접 노출하지 않고 Nginx, Caddy, ALB 또는 Kubernetes Ingress를 앞에 두어 HTTPS를 종료한다. 방화벽에서는 80/443만 허용하고 8001은 내부 네트워크에서만 접근시킨다.

## 8. 데이터와 운영 주의사항

`/app/data`에는 원본 문서, 추출 텍스트, 평가 결과와 생성 보고서가 저장된다. 이 경로가 영속 볼륨이 아니면 워커 재생성 때 모든 운영 데이터가 사라진다. 매일 볼륨 스냅샷 또는 별도 저장소 백업을 수행하고, 개인정보가 포함된 원본 문서는 보존기간과 접근권한을 별도로 관리한다.

현재 저장소는 공유 파일시스템과 데이터베이스 잠금 없이 로컬 파일을 사용한다. 따라서 한 데이터 볼륨을 여러 워커가 동시에 쓰게 하면 상태 파일 충돌 위험이 있다. 운영 초기에는 워커를 1개로 유지한다. 다중 워커와 무중단 확장이 필요하면 문서 원본은 객체 저장소, 상태는 PostgreSQL 같은 외부 데이터베이스로 이전해야 한다.

새 버전은 `1.0.1`, `1.0.2`처럼 변경 불가능한 태그로 등록하고, 정상 검증 전 기존 이미지를 삭제하지 않는다. 장애 시 이전 이미지 태그로 워커를 되돌린다. `latest` 태그만 사용하는 배포는 재현성과 롤백이 어려우므로 피한다.

## 9. 외부 테스트 체크리스트

1. `/healthz` 응답이 200이고 `dataDirectoryReady`가 `true`인가?
2. 루트 URL이 인증 없이 열리지 않고 HTTP 401을 반환하는가?
3. 인증 후 대시보드와 정적 자산이 정상 표시되는가?
4. OpenRouter 상태 화면에서 키와 모델이 정상으로 표시되는가?
5. 작은 PDF/HWPX 한 개와 여러 문서 일괄등록이 모두 성공하는가?
6. 컨테이너 또는 워커를 재시작해도 업로드 문서와 설정이 유지되는가?
7. 보고서 개별 섹션 생성과 HWPX/XLSX/PPTX 다운로드가 동작하는가?
8. 애플리케이션 로그에 API 키, Basic 인증 비밀번호 또는 원문 전체가 출력되지 않는가?
9. 외부 HTTPS 인증서와 도메인이 정상이고 8001 포트가 인터넷에 직접 열려 있지 않은가?
