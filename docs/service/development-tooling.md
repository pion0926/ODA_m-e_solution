# 개발 도구와 문서 엔진 관리

확인일: 2026-10-06. 개발 원칙은 루트 `AGENTS.md`를 따른다.

## 적용 구성

| 구성 | 고정 버전 / 설정 | 용도 |
|---|---|---|
| Playwright Test | 1.63.0 | 실제 Chromium DOM·화면 회귀 검사 |
| Playwright MCP | 0.0.83 | 개발용 독립 브라우저, headless·isolated |
| kordoc | 4.3.1 → 4.18.13 | HWPX 검증·구조 분석·SVG 서버 및 로컬 문서 MCP |
| rHWP Studio / core | 0.8.6 | 보고서 뷰어와 서버 오프라인 조판; 동일 자산 사용 |
| OpenAI Docs MCP | 공식 HTTP endpoint | AI API·Codex 설정 공식 문서 조회 |
| 웹검색 | 프로젝트 `web_search = "live"` | 최신 의존성·공식 문서 확인 |

Node 개발 의존성은 루트 `package-lock.json`, 문서 서버는 `redesign/kordoc/package-lock.json`으로 재현한다. 서버 조판의 Python Playwright 1.55.0 및 해당 Chromium은 이번 변경에서 유지했다. Node E2E 런타임과 별개이며, 기존 서버 런타임에서도 새 rHWP의 렌더링을 확인했다.

공식 자료: [Playwright](https://playwright.dev/docs/intro), [Playwright MCP](https://github.com/microsoft/playwright-mcp), [kordoc](https://github.com/chrisryugj/kordoc), [rHWP 0.8.6](https://github.com/edwardkim/rhwp/releases/tag/v0.8.6), [Codex MCP 설정](https://developers.openai.com/codex/mcp), [공식 문서 MCP](https://developers.openai.com/learn/docs-mcp). 버전은 공식 npm registry와 GitHub 릴리스에서 확인했다. Playwright/MCP는 Apache-2.0, kordoc/rHWP는 MIT이며 rHWP LICENSE를 자산에 포함했다. kordoc 배포본의 NOTICE·THIRD_PARTY도 유지한다.

## 설치와 실행

Node.js 26, Python 3.12 이상, Docker Compose를 사용한다. 저장소 루트에서:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
npx playwright install chromium
npm ci --prefix redesign/kordoc --omit=optional --ignore-scripts --no-audit --no-fund
npm run test:e2e
npm run test:frontend
node --test redesign/kordoc/test-compatibility.mjs
node tools/testing/check-mcp.mjs --docs
./tools/Setup-ProjectTools.ps1
```

Linux CI에서는 `npx playwright install --with-deps chromium`을 쓴다. `.github/workflows/service-checks.yml`에 독립 브라우저 검사 job을 추가했다. `tools/ops/Test-Service.ps1`도 기본적으로 브라우저 검사를 실행한다. 백엔드 위주 점검은 `-SkipBrowserTests`를 명시할 수 있다.

`npm run test:e2e:ui`로 테스트 UI, `npm run test:e2e:report`로 HTML 결과를 연다. 실패 시 trace·스크린샷을 남기며 CI는 실패 결과만 7일 보관한다. 결과와 `node_modules/`는 git/Docker 빌드 문맥에서 제외한다.

## 테스트 범위

- 테스트 전용 서버는 `127.0.0.1:8317`에서 실제 프런트 HTML과 `assets/`만 제공한다. DB·업로드·환경 설정은 제공하지 않는다.
- 로그인 검사는 모의 API로 세션 대기, 401, 일시적 503 및 재시도, 로그인 거절, bootstrap 로딩 실패를 검증한다. 외부 origin과 처리되지 않은 API 요청은 차단한다.
- rHWP 검사는 저장소의 빈 보고서 템플릿으로 문서 열기, 페이지 수, SVG 텍스트, 검색·필드 API, HWPX 재저장/재열기, 저장 단축키의 호스트 위임을 검증한다. 실제 사업 문서를 CI로 보내지 않는다.
- 각 시나리오는 데스크톱과 800px 화면에서 실행한다. 기본 E2E는 DB·유료 AI를 사용하는 전체 사업 흐름 검증을 대체하지 않는다.
- 실제 보고서 오프라인 조판은 `tools/qa_cover_profile.py`로 별도 수행한다. 실제 자료와 결과는 `.runtime/` 아래에 보관한다.

## MCP 운영

공유 원본은 `tools/codex-project.toml`이다. 설치기가 절대 경로를 해석해 `.codex/config.toml`에 기록하며, 기존의 다른 설정을 덮어쓰지 않는다. 설치 후 Codex에서 프로젝트를 다시 열어 서버 목록을 로드한다. 현재 대화에 즉시 추가되었다고 간주하지 않는다.

- `openaiDeveloperDocs`: 인증키 없는 공식 문서 endpoint. 외부에는 문서 검색어만 전달한다.
- `kodamePlaywright`: 개인 브라우저 세션/쿠키에 연결하지 않는다. 기본 요청 origin은 로컬 개발·QA·테스트 서버다. upstream origin 필터는 보안 격리 경계가 아니며 운영 접근 권한으로 해석하지 않는다. 현재 대화에 제공된 브라우저 도구 규칙을 우회하는 용도로 쓰지 않는다.
- `kodameKordoc`: `KORDOC_OFFLINE=1`, `KORDOC_ROOT=<저장소>`로 실행하고 읽기 도구만 활성화한다. 원본 변경·생성 도구는 노출하지 않는다. OCR 모델 자동 다운로드도 사용하지 않는다.

별도 검색 MCP·범용 파일시스템/DB MCP·추가 HWP 파서는 도입하지 않았다. 내장 검색과 기존 도구로 필요한 기능이 충족된다. 새 형식의 실패 사례가 생기면 라이선스·유지보수·격리·회귀 샘플을 검토해 추가한다.

## rHWP 업데이트 재현

`./tools/Build-Rhwp.ps1`의 고정 소스:

- Studio 태그 `v0.8.6`, 커밋 `f1f9c6ae58344ee9368996d3543f76b9345cf227`
- 공식 npm `@rhwp/core@0.8.6`의 JS/WASM 쌍
- upstream lockfile로 설치, TypeScript 검사 후 Vite 빌드
- HWP ActiveX 플러그인·외부 웹폰트 제외, base `/assets/rhwp/`

서비스 변경은 `tools/rhwp-service-bridge.ts`와 `assets/rhwp/service-host.js`로 분리했다. `tools/build_rhwp.py`가 버전·소스 마커 확인 후 반영한다. 삽입 위치가 바뀌면 실패시키며 minified 변수 이름에 의존하지 않는다. 과거 `tools/patch_rhwp_bundle.js`는 이전 번들용이므로 새 버전에 실행하지 않는다.

유지하는 계약: `rhwp-request`/`rhwp-response`, loadFile/pageCount/getPageSvg/exportHwpx, 검색·필드·본문 수정, 저장의 호스트 위임, 섹션 미리보기의 읽기 전용 origin/source 검사, 확대/축소와 조판 검사. PWA 캐시와 독립 앱의 첫 테마 선택은 사용하지 않는다. 샘플 문서·불필요한 public JS 복사본은 배포하지 않는다.

`assets/rhwp/version.json`에 소스 커밋·빌드 옵션·자산 SHA-256을 기록한다. 이전 해시 자산은 이미 열린 화면의 참조를 위해 유지할 수 있다. 새 자산 검증 후 개발 API·웹을 함께 빌드한다. 운영 배포는 별도 검증된 이미지 승격 절차를 따른다.

## 검증 기록

- Playwright: 12/12 통과(6개 시나리오 × 2개 화면).
- 기존 프런트: 17/17 통과. guard 분리에 맞춰 계약 테스트의 읽는 파일을 변경했다.
- HWPX/미리보기 백엔드: 130개 및 subtest 17개 통과.
- kordoc: 현재 서버가 호출하는 전체 라이브러리 API 호환성 통과.
- MCP 초기화: kordoc 17개, Playwright 25개, 공식 문서 5개 도구 반환. kordoc 템플릿 메타데이터 조회 통과.
- Playwright MCP 독립 브라우저 실제 기동·종료 통과.
- 교통대 기존 보고서 로컬 렌더링: 61쪽, 원본 SHA-256 `b9f6467a5f6462a426e988534916e341597dfe2b0a0c957444760a5a5cc65957`, 외부 네트워크/DB 없이 완료. 표지를 육안 확인했다. 한컴 데스크톱 검증은 포함하지 않는다.
- 동일 보고서 목차 최종 검증은 1회에 통과했고 파일 변경이 필요하지 않았다. 신규 엔진은 중간점 및 쪽 번호 표현·일부 줄의 페이지 배치를 달리한다. 공백·중간점·독립 숫자 행을 제외한 전체 본문 텍스트 비교는 일치했다.
- 개발 서버(8002)에 API·웹·모든 작업자·kordoc을 반영했다. 전체 healthcheck 통과, 실제 kordoc HTTP `/analyze`는 템플릿 23쪽·표 9개를 반환했다. 웹과 API의 rHWP 버전 모두 0.8.6, 실행 중 kordoc은 4.18.13으로 확인했다. 운영 서버는 이번 변경에서 배포하지 않았다.

운영 반영 여부는 배포 기록으로 별도 확인한다. 위 결과는 모든 사업 흐름·HWP 문서의 호환성 보증이 아니다.
