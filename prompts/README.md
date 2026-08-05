# Report Section Prompt Files

이 폴더의 `Section1_*.py`부터 `Section27_*.py`까지가 실제 보고서 에디터 생성 프롬프트의 원본이다.

## 실제 앱 연결

- 각 파일의 `EDITOR_PROMPT`가 실제 `평가보고서 작성` 및 우측 `AI 수정 요청`에서 사용된다.
- `backend/report_prompts.py`는 `Section번호_*.py`를 읽어 `EDITOR_REPORT_PARTS[*].prompt`에 주입한다.
- `hwpx_path`, `manifest_path`, XML 치환 정보는 LLM 작성 프롬프트가 아니라 라우팅/치환 메타데이터로만 사용한다.

## 직접 검수

```powershell
C:\Users\offic\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\prompts\Section1_표지.py --no-model
```

출력 구분:

- `PROMPT DEBUG`: 라우팅 메타데이터와 검수용 전체 구성. 라우팅 메타데이터는 모델 프롬프트로 보내지지 않는다.
- `ACTUAL LLM REQUEST PAYLOAD`: 실제 모델 요청에 들어가는 `model`, `messages`, `temperature`.
- `MODEL OUTPUT`: 모델 응답. `--no-model`을 빼면 호출한다.

## 수정 규칙

섹션별 작성 지시를 고칠 때는 해당 `Section*.py` 파일의 `EDITOR_PROMPT`를 수정한다. 실제 앱과 직접 실행 검수는 같은 값을 사용한다.
