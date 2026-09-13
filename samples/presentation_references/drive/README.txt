현재 발표자료 생성 기준 (2026-09-06)

- south-africa-15.pdf: 사용자가 제공한 남아공 DEEP 종료평가 발표자료 15페이지 원본
- mozambique-50.pdf: 사용자가 제공한 모잠비크 중앙병원 발표자료 50페이지 원본
- 화면 선택지는 15페이지 / 30페이지만 제공합니다.
- 30페이지형은 모잠비크 원본 50페이지의 중복 간지·평가 설명을 통합합니다.
- 원본 페이지와 생성 장표의 대응, 제목, 표 열 구성은 presentation_profiles.py에서 수정합니다.
- 내용 프롬프트는 presentation_reference_prompt.py, 조판은 presentation_reference_renderer.py에서 수정합니다.
- 원본 PDF의 사실·인명·사업 사진은 신규 사업 내용에 사용하지 않습니다.

이하 내용은 기존 12페이지 생성기의 Google Drive 참고자료 동기화 방식입니다.

1. config/presentation_reference_profile.json의 reference_folder URL에서 PPTX를 내려받습니다.
2. 이 폴더에 원본 PPTX를 그대로 둡니다.
3. 백엔드 이미지를 다시 빌드하면 슬라이드 비율, 도형/텍스트/표/이미지 밀도와 주요 글꼴만 추출됩니다.
4. 샘플의 본문, 국가, 기관, 사업명, 수치, 평가결과와 권고는 프롬프트에 전달하지 않습니다.
5. 참조 자료별 역할이나 제외 규칙은 config/presentation_reference_profile.json에서 직접 수정할 수 있습니다.
