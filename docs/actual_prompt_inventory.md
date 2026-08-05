# 27개 섹션 실제 프롬프트 및 추가 데이터 인벤토리

본 문서는 `prompts/Section*.py`의 실제 `EDITOR_PROMPT` 전문과, 각 프롬프트에 주입되는 입력 데이터 및 증빙자료 목록을 한눈에 보기 위해 정리한 자료다.
특허 출원 검토 시에는 이 문서를 기준으로 섹션별 생성 목적, 입력 데이터, 출력 계약, 판단 기준을 설명할 수 있다.

## 1. 공통 추가 데이터 목록

| 데이터 키 | 역할 |
| --- | --- |
| reference_corpus | 업로드 문서, RAG 검색 결과, 샘플 보고서 등 원문 근거 묶음 |
| content_inputs.project | 사업명, 기간, 예산, 대상국가, 대상지역 등 프로젝트 기본정보 |
| content_inputs.criteria | DAC 기준별 평가질문, 점수, 핵심 판단, 증빙 공백 및 보완 필요사항 |
| content_inputs.overall | 종합점수, KOICA 평가등급, 국무조정실 평가등급 등 총괄 평가정보 |
| grade_score_rows | 평가등급 결과표에 투입되는 기준별·질문별 시스템 산정 점수 행 |
| prior_analysis_sections | 앞서 생성 또는 수정된 섹션 본문. 결론·작동요인·제언·교훈의 1차 근거 |
| sample_reference_for_this_section | 해당 섹션과 유사한 샘플 보고서 문체·표 구조·항목 구분 참조 |
| previous_text | 현재 HWPX 양식 또는 기존 생성본의 해당 섹션 내용 |
| user_request | 사용자가 해당 섹션에 직접 입력한 수정 지시 |

## 2. DAC 기준별 증빙자료 슬롯

### 적절성
- 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
- 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
- 사업개요서 또는 사업요청서 (PCP)
- 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
- 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
- 집행계획서 및 최신 PDM (Project Design Matrix)
- 변화이론(ToC) 도식도 및 문제나무 분석 자료
- 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
- 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
- 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록

### 일관성
- 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
- 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
- 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
- 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
- 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
- 국내 타 기관 및 KOICA 타 사업과의 협의 기록
- 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
- 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
- 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역

### 효과성
- 최신 PDM 및 성과지표 실적표
- 산출물 완료보고서 및 활동별 결과보고서
- 교육·서비스·시설·장비 제공 실적 자료
- 기준선/종료선 조사자료 (Baseline/Endline)
- 수혜자 만족도 조사 및 현장점검 기록
- 성과 기여도 분석 및 외부요인 검토 메모
- 성별·지역별·취약계층 분리 통계
- 사회적 소외계층 참여자 명단 및 지원 실적
- 수혜자 인터뷰 또는 사례 기록

### 효율성
- 예산 집행내역 및 집행률 분석표
- 예산 변경 내역 및 승인 문서
- 단가 비교 또는 비용 적정성 검토 자료
- 사업 일정표 및 마일스톤 이행 현황
- 조달 계획, 입찰·계약 문서
- 지연 사유 및 시정조치 기록
- 투입 대비 산출 분석표
- 인력 투입 계획 및 활동별 투입 기록
- 주요 활동 간 연계·조정 회의록

### 지속가능성
- 운영·유지관리 계획
- 지방정부 또는 파트너 기관 예산 확약서
- 인수인계 문서 및 운영 매뉴얼
- 현지 인력 역량강화 계획 및 교육 결과
- 리스크·위기대응 계획
- 운영 담당 조직의 역할분담 문서
- 정책·제도 반영 또는 공식 승인 문서
- 지역사회 참여 및 수용성 확인 자료
- 장기 재원조달 또는 수익모델 검토 자료

## 3. 섹션별 프롬프트 한눈에 보기

| No | 섹션 | 파트 ID | 파일 | 작성 대상 | 프롬프트 입력 | 추가 증빙 데이터 | 파이프라인 메모 | 출력 계약 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 표지 | `cover` | `prompts/Section1_표지.py` | 보고서 표지에 들어갈 슬롯 값을 작성한다. | previous_text: 현재 표지에 표시된 기존 문구 또는 이전 JSON 슬롯 값. 평가책임자와 평가수행기관이 이미 확정되어 있으면 유지한다.<br>content_inputs.project: 사업명, 기간, 예산, 개요 문서명 등 표지 판단에 필요한 최소 정보.<br>report_context.draft_date: 표지 기준 연월.<br>user_request: 사용자가 직접 입력한 수정 요청. 다른 입력보다 우선한다. | relevance: 사업개요서 또는 사업요청서 (PCP) | 사업명, 기간, 예산, 평가책임자/수행기관 확인 | JSON schema: `section1_cover_slots_v1` |
| 2 | 목차 | `toc` | `prompts/Section2_목차.py` | 목차 페이지 번호 슬롯은 LLM 생성 대상이 아니다. |  |  | 5-1 원본 양식과 최종 편집 문서 구조 참조 | JSON schema: `section2_toc_slots_v1` |
| 3 | 평가보고서 관련 공지 | `notice` | `prompts/Section3_공지.py` | 평가보고서 관련 공지 페이지의 placeholder 슬롯 값을 작성한다. | previous_text: 현재 공지 페이지 또는 이전 JSON 슬롯 값.<br>content_inputs.project: 사업명, 기간, 예산 등 사업 기본 정보.<br>reference_corpus: 평가책임자, 수행기관, 품질관리 관련 근거가 있을 때만 사용한다.<br>user_request: 사용자가 직접 입력한 수정 요청. |  | 5-1 원본 양식 공지 문구와 FAQ 참조 | JSON schema: `section3_notice_slots_v1` |
| 4 | 평가등급 결과표 | `grade` | `prompts/Section4_평가등급_결과표.py` | 평가등급 결과표에 들어갈 슬롯 값을 작성한다. | content_inputs.criteria: 기준별 평가점수와 판단 근거.<br>grade_score_rows: 시스템이 산정한 기준별 점수 행.<br>content_inputs.overall: 종합점수, KOICA 평가등급, 국무조정실 평가등급.<br>previous_text: 현재 등급표 또는 이전 JSON 슬롯 값.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 기준별 평가결과 JSON과 전체 업로드 증빙으로 점수/산정 이유 작성 | JSON schema: `section4_grade_slots_v1` |
| 5 | 국문 요약 | `summary-ko` | `prompts/Section5_국문_요약.py` | Section 5: I. 평가결과 요약 - 1. 국문 요약의 기존 placeholder 구조를 유지하면서, 각 입력 문단의 텍스트만 작성한다. |  | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 사업개요, PDM, 성과달성도, 기준별 평가결과, 결론/환류/교훈 종합 | JSON schema: `section5_summary_slots_v1` |
| 6 | 사업 추진배경 | `project-background` | `prompts/Section6_사업_추진배경.py` | Section 6: II. 대상사업개요 - 1. 사업 추진배경의 기존 placeholder 양식을 유지하면서, 다섯 개 배경 문단의 텍스트만 작성한다. |  | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서 | 수원국 수요, 정책 부합성, 사업 형성 배경 작성 | JSON schema: `section6_project_background_slots_v1` |
| 7 | 사업개요 | `project-overview` | `prompts/Section7_사업개요.py` | Section 7: II. 대상사업개요 - 2. 사업개요 표의 내용 셀만 작성한다. |  | relevance: 사업개요서 또는 사업요청서 (PCP) | 사업개요서 최종본 우선 사용 | JSON schema: `section7_project_overview_slots_v1` |
| 8 | 사업설계매트릭스(PDM) | `pdm` | `prompts/Section8_PDM.py` | Section 8: II. 대상사업개요 - 3. 사업설계매트릭스(PDM) 표의 placeholder 셀만 작성한다. |  | relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료<br>relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)<br>effectiveness: 최신 PDM 및 성과지표 실적표 | PDM, ToC, 문제나무, 역할분담 자료로 논리모형 작성 | JSON schema: `section8_pdm_slots_v1` |
| 9 | 평가의 목적과 범위 | `eval-purpose` | `prompts/Section9_평가_목적과_범위.py` | Section 9: III. 평가개요 - 1. 평가의 목적과 범위의 본문 슬롯만 작성한다. |  | relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix) | 평가 목적/범위는 사업개요와 양식/FAQ 기준으로 작성 | JSON schema: `section9_eval_purpose_slots_v1` |
| 10 | 평가매트릭스 | `eval-matrix` | `prompts/Section10_평가매트릭스.py` | Section 10: III. 평가개요 - 2. 평가매트릭스(Evaluation Matrix)의 원본 표 셀에 들어갈 값만 작성한다. |  | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 33개 | DAC 기준-평가질문-지표-자료출처-방법 매핑 | JSON schema: `section10_eval_matrix_slots_v1` |
| 11 | 평가방법 | `eval-methods` | `prompts/Section11_평가방법.py` | III. 평가개요 3. 평가 방법 본문을 작성한다. | reference_corpus: 평가계획, 인터뷰 기록, 설문 자료, 현장확인 자료, 문헌 목록.<br>content_inputs.criteria: 기준별로 사용한 자료와 분석 방법.<br>previous_text: 현재 양식.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 업로드 문헌 전체, 면담/설문/현장점검 기록을 방법론 자료원으로 사용 | 평가 방법 최종 텍스트만 반환한다. |
| 12 | 평가의 한계 | `eval-limitations` | `prompts/Section12_평가의_한계.py` | III. 평가개요 4. 평가의 한계 본문을 작성한다. | reference_corpus: 미확보 자료, 인터뷰 제약, 조사 범위 제한, 데이터 품질 관련 근거.<br>content_inputs.criteria: 기준별 자료 충분성 및 한계.<br>prior_analysis_sections: 이미 작성된 분석에서 확인된 공백.<br>previous_text: 현재 양식.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 미업로드 슬롯과 자료공백을 평가 한계로 정리 | 평가의 한계 최종 텍스트만 반환한다. |
| 13 | 평가팀 구성 및 시행체계 | `eval-team` | `prompts/Section13_평가팀_구성_및_시행체계.py` | III. 평가개요 5. 평가팀 구성 및 시행체계 본문을 작성한다. | reference_corpus: 평가자 명단, 역할분담표, 수행기관 정보, 품질관리 체계.<br>previous_text: 현재 양식.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 사업개요서 또는 사업요청서 (PCP) | 평가책임자, 수행기관, 품질관리 체계 확인 | 평가팀 구성 및 시행체계 최종 텍스트만 반환한다. |
| 14 | 성과 달성도 | `achievement` | `prompts/Section14_성과_달성도.py` | IV. 성과 달성도 표에 들어갈 성과지표별 내용을 작성한다. | reference_corpus: PDM, 성과지표, 산출물 실적, 종료보고서, 점검표, 인터뷰/설문 근거.<br>content_inputs.criteria: 성과달성도 관련 기준과 점수.<br>previous_text: 현재 성과달성도 표 양식.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>effectiveness: 최신 PDM 및 성과지표 실적표<br>effectiveness: 산출물 완료보고서 및 활동별 결과보고서<br>effectiveness: 교육·서비스·시설·장비 제공 실적 자료<br>effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)<br>effectiveness: 수혜자 만족도 조사 및 현장점검 기록<br>외 1개 | PDM 지표, 목표/실적, MOV, 성과자료 작성 | 아래 형식으로 3~5개 항목을 작성한다. 각 항목은 빈 줄로 구분한다. - 군립병원 인프라 개선: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ... - 보건의료 인력 역량 강화: 성과지표: ... /… |
| 15 | 적절성 | `criteria-relevance` | `prompts/Section15_적절성.py` | V. 기준별 평가결과 1. 적절성 본문을 작성한다. | reference_corpus: 사업요청서, PCP, 정책문서, 수요조사, 설계자료, 인터뷰 등 적절성 판단 근거.<br>content_inputs.criteria: 적절성 평가질문, 점수, 핵심 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 4개 | 적절성 10개 슬롯만 사용 | 적절성 평가결과 최종 본문만 반환한다. |
| 16 | 일관성 | `criteria-coherence` | `prompts/Section16_일관성.py` | V. 기준별 평가결과 2. 일관성을 작성한다. | reference_corpus: 정책/전략 문서, 타 공여기관 사업, KOICA 포트폴리오, 사업 설계·수행 자료.<br>content_inputs.criteria: 일관성 평가질문, 점수, 핵심 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)<br>coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)<br>coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)<br>coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서<br>coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록<br>coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록<br>외 3개 | 일관성 9개 슬롯만 사용 | 일관성 평가결과 최종 본문만 반환한다. |
| 17 | 효과성 | `criteria-effectiveness` | `prompts/Section17_효과성.py` | V. 기준별 평가결과 3. 효과성을 작성한다. | reference_corpus: PDM, 성과지표 실적, 산출물 점검, 인터뷰, 설문, 종료보고서 등 효과성 판단 근거.<br>content_inputs.criteria: 효과성 평가질문, 점수, 핵심 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | effectiveness: 최신 PDM 및 성과지표 실적표<br>effectiveness: 산출물 완료보고서 및 활동별 결과보고서<br>effectiveness: 교육·서비스·시설·장비 제공 실적 자료<br>effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)<br>effectiveness: 수혜자 만족도 조사 및 현장점검 기록<br>effectiveness: 성과 기여도 분석 및 외부요인 검토 메모<br>외 3개 | 효과성 9개 슬롯만 사용 | 효과성 평가결과 최종 본문만 반환한다. |
| 18 | 효율성 | `criteria-efficiency` | `prompts/Section18_효율성.py` | V. 기준별 평가결과 4. 효율성을 작성한다. | reference_corpus: 예산, 집행, 일정, 조달, 투입 대비 산출, 사업관리 문서.<br>content_inputs.criteria: 효율성 평가질문, 점수, 핵심 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | efficiency: 예산 집행내역 및 집행률 분석표<br>efficiency: 예산 변경 내역 및 승인 문서<br>efficiency: 단가 비교 또는 비용 적정성 검토 자료<br>efficiency: 사업 일정표 및 마일스톤 이행 현황<br>efficiency: 조달 계획, 입찰·계약 문서<br>efficiency: 지연 사유 및 시정조치 기록<br>외 3개 | 효율성 9개 슬롯만 사용 | 효율성 평가결과 최종 본문만 반환한다. |
| 19 | 지속가능성 | `criteria-sustainability` | `prompts/Section19_지속가능성.py` | V. 기준별 평가결과 5. 지속가능성을 작성한다. | reference_corpus: 운영·유지관리, 예산 확보, 인력 역량, 제도화, 현지 주인의식 관련 자료.<br>content_inputs.criteria: 지속가능성 평가질문, 점수, 핵심 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | sustainability: 운영·유지관리 계획<br>sustainability: 지방정부 또는 파트너 기관 예산 확약서<br>sustainability: 인수인계 문서 및 운영 매뉴얼<br>sustainability: 현지 인력 역량강화 계획 및 교육 결과<br>sustainability: 리스크·위기대응 계획<br>sustainability: 운영 담당 조직의 역할분담 문서<br>외 3개 | 지속가능성 9개 슬롯만 사용 | 지속가능성 평가결과 최종 본문만 반환한다. |
| 20 | 범분야 이슈 | `criteria-crosscutting` | `prompts/Section20_범분야_이슈.py` | V. 기준별 평가결과 6. 범분야 이슈를 작성한다. | reference_corpus: 성평등, 환경, 인권, 취약계층, 세이프가드, 갈등민감성 관련 근거.<br>content_inputs.criteria: 범분야 평가질문, 점수, 핵심 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서<br>coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서<br>effectiveness: 성별·지역별·취약계층 분리 통계<br>effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적<br>effectiveness: 수혜자 인터뷰 또는 사례 기록<br>sustainability: 지역사회 참여 및 수용성 확인 자료 | 젠더, 환경, 인권, 취약계층, 세이프가드 자료 중심 | 범분야 이슈 평가결과 최종 본문만 반환한다. |
| 21 | 그 외 평가기준 | `criteria-other` | `prompts/Section21_그_외_평가기준.py` | V. 기준별 평가결과 7. 그 외 평가기준을 작성한다. | reference_corpus: 위 기준으로 포착되지 않는 특수 이슈, 혁신성, 확장성, 위험관리 등 관련 근거.<br>prior_analysis_sections: 앞선 기준별 분석.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 사업 특수성, 혁신성, 확산 가능성은 전체 증빙에서 확인 | 그 외 평가기준 최종 본문만 반환한다. |
| 22 | 결론 | `conclusion` | `prompts/Section22_결론.py` | VI. 결론 1. 결론을 작성한다. | prior_analysis_sections: 앞서 작성된 사업개요, 평가개요, 성과달성도, 기준별 평가결과.<br>content_inputs.criteria: 기준별 점수와 핵심 판단.<br>reference_corpus: 결론 검증에 필요한 제한적 원문 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 기준별 평가결과와 성과달성도만 종합하고 새 사실 추가 금지 | 결론 최종 본문만 반환한다. |
| 23 | 작동요인 | `working-factors` | `prompts/Section23_작동요인.py` | VI. 결론 2. 작동요인을 작성한다. | prior_analysis_sections: 성과달성도와 기준별 평가결과.<br>reference_corpus: 성공 요인, 협력 구조, 현지 수요, 사업관리 관련 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 성과 달성에 기여한 설계·집행·환경 요인 추출 | 작동요인 최종 본문만 반환한다. |
| 24 | 비작동요인 | `nonworking-factors` | `prompts/Section24_비작동요인.py` | VI. 결론 2. 비작동요인을 작성한다. | prior_analysis_sections: 성과달성도와 기준별 평가결과.<br>reference_corpus: 지연, 미달, 운영상 제약, 설계상 한계 관련 근거.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 미달성 지표, 변경요청, 지연, 리스크, 증빙공백 추출 | 비작동요인 최종 본문만 반환한다. |
| 25 | 변화이론 분석 | `theory` | `prompts/Section25_변화이론_분석.py` | VI. 결론 2. 변화이론 분석을 작성한다. | reference_corpus: 사업 설계, PDM, 성과자료, 평가결과, 인터뷰 등 변화 경로 검토 근거.<br>prior_analysis_sections: 사업개요, 성과달성도, 기준별 평가결과, 작동/비작동요인.<br>previous_text: 현재 양식과 문체.<br>user_request: 사용자가 직접 입력한 수정 요청. | relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>effectiveness: 최신 PDM 및 성과지표 실적표<br>effectiveness: 산출물 완료보고서 및 활동별 결과보고서<br>effectiveness: 교육·서비스·시설·장비 제공 실적 자료<br>effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)<br>외 2개 | 투입-활동-산출-성과 경로와 작동/비작동 요인 연결 | 변화이론 분석 최종 본문만 반환한다. |
| 26 | 환류과제 | `feedback` | `prompts/Section26_환류과제.py` | VI. 결론 3. 환류과제(제언)를 작성한다. | prior_analysis_sections: 결론, 작동요인, 비작동요인, 변화이론 분석을 1차 근거로 사용한다.<br>content_inputs.criteria: 기준별 점수와 개선 필요 지점.<br>reference_corpus: 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, 사업변경·운영관리·기자재·인력 관련 근거.<br>sample_reference_for_this_section: 제언 표의 구분/제언/이해관계자 분리 방식과 문체.<br>previous_text: 현재 양식과 문체.<br>외 1개 | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | 비작동 요인과 리스크/지연/운영관리 자료를 실행 과제로 전환 | 환류과제 최종 텍스트만 반환한다. |
| 27 | 교훈 | `lessons` | `prompts/Section27_교훈.py` | VI. 결론 3. 교훈을 작성한다. | prior_analysis_sections: 작동요인, 비작동요인, 환류과제, 변화이론 분석, 결론을 1차 근거로 사용한다.<br>content_inputs.criteria: 기준별 평가결과와 개선 필요 지점.<br>reference_corpus: 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, 운영관리·기자재·인력 관련 근거.<br>sample_reference_for_this_section: 작동요인/비작동요인에서 교훈을 도출하는 방식과 문체.<br>previous_text: 현재 양식과 문체.<br>외 1개 | relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)<br>relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)<br>relevance: 사업개요서 또는 사업요청서 (PCP)<br>relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)<br>relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서<br>relevance: 집행계획서 및 최신 PDM (Project Design Matrix)<br>외 40개 | FAQ와 샘플 보고서 문체를 참조해 후속사업 체크리스트형 교훈 작성 | 교훈 최종 텍스트만 반환한다. |

## 4. 섹션별 요약 및 실제 프롬프트 전문

### 1. 표지 (cover)

- 원본 파일: `prompts/Section1_표지.py`
- 작성 대상: 보고서 표지에 들어갈 슬롯 값을 작성한다.
- 출력 계약: JSON schema: `section1_cover_slots_v1`
- 참조 평가기준: relevance
- 파이프라인 메모:
  - 사업명, 기간, 예산, 평가책임자/수행기관 확인
- 추가 증빙 데이터:
  - relevance: 사업개요서 또는 사업요청서 (PCP)

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 표지</summary>

````text
[작성 대상]
보고서 표지에 들어갈 슬롯 값을 작성한다.

[참고할 입력]
- previous_text: 현재 표지에 표시된 기존 문구 또는 이전 JSON 슬롯 값. 평가책임자와 평가수행기관이 이미 확정되어 있으면 유지한다.
- content_inputs.project: 사업명, 기간, 예산, 개요 문서명 등 표지 판단에 필요한 최소 정보.
- report_context.draft_date: 표지 기준 연월.
- user_request: 사용자가 직접 입력한 수정 요청. 다른 입력보다 우선한다.

[작성 규칙]
1. 표지는 아래 5개 슬롯만 작성한다.
   - project_title
   - report_title
   - report_date
   - evaluation_manager
   - evaluation_institution
2. project_title은 content_inputs.project.title을 우선 사용한다.
3. report_title은 반드시 "종료평가 결과보고서"로 고정한다.
4. report_date는 YYYY. MM 형식으로 쓴다.
5. evaluation_manager는 "평가책임자 "로 시작한다. 확인되지 않으면 "평가책임자 확인 중"로 쓴다.
6. evaluation_institution은 "평가수행기관 "으로 시작한다. 확인되지 않으면 "평가수행기관 확인 중"로 쓴다.
7. 모든 슬롯 값은 한 줄 문자열이어야 한다. 줄바꿈, markdown, XML, 설명, 근거, 파일명은 쓰지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section1_cover_slots_v1",
  "slots": {
    "project_title": "사업명",
    "report_title": "종료평가 결과보고서",
    "report_date": "YYYY. MM",
    "evaluation_manager": "평가책임자 확인 중",
    "evaluation_institution": "평가수행기관 확인 중"
  }
}
````

</details>

### 2. 목차 (toc)

- 원본 파일: `prompts/Section2_목차.py`
- 작성 대상: 목차 페이지 번호 슬롯은 LLM 생성 대상이 아니다.
- 출력 계약: JSON schema: `section2_toc_slots_v1`
- 파이프라인 메모:
  - 5-1 원본 양식과 최종 편집 문서 구조 참조

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 목차</summary>

````text
[작성 대상]
목차 페이지 번호 슬롯은 LLM 생성 대상이 아니다.

[처리 규칙]
1. Section 2의 제목/목차 항목 구조는 원본 HWPX 양식을 그대로 유지한다.
2. 페이지 번호는 LLM이 추정하지 않는다.
3. 실제 페이지 번호는 최종 문서를 PDF로 변환한 뒤 알고리즘이 산출한 data/reports/toc_page_map.json 또는 data/reports/toc_source.pdf에서만 가져온다.
4. PDF/페이지맵이 없으면 페이지 번호 슬롯은 비워 두고 원본 양식의 값을 유지한다.
5. 작업 안내문 제거용 remove_page_notice만 빈 문자열로 둔다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록, 설명문, 주석, markdown은 쓰지 않는다.

{
  "schema": "section2_toc_slots_v1",
  "slots": {
    "remove_page_notice": "",
    "page_numbers": {}
  }
}
````

</details>

### 3. 평가보고서 관련 공지 (notice)

- 원본 파일: `prompts/Section3_공지.py`
- 작성 대상: 평가보고서 관련 공지 페이지의 placeholder 슬롯 값을 작성한다.
- 출력 계약: JSON schema: `section3_notice_slots_v1`
- 파이프라인 메모:
  - 5-1 원본 양식 공지 문구와 FAQ 참조

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가보고서 관련 공지</summary>

````text
[작성 대상]
평가보고서 관련 공지 페이지의 placeholder 슬롯 값을 작성한다.

[참고할 입력]
- previous_text: 현재 공지 페이지 또는 이전 JSON 슬롯 값.
- content_inputs.project: 사업명, 기간, 예산 등 사업 기본 정보.
- reference_corpus: 평가책임자, 수행기관, 품질관리 관련 근거가 있을 때만 사용한다.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 원본 공지 문장 구조는 유지하고, placeholder 값만 작성한다.
2. 확인되지 않은 개인명, 소속, 날짜, 등급, 검토위원 정보는 "확인 중"로 쓴다.
3. 평가책임자/국가명/사업명처럼 사업개요에서 확인 가능한 값만 구체화한다.
4. 설명, 근거, XML, markdown은 쓰지 않는다.
5. 모든 값은 한 줄 문자열이어야 한다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section3_notice_slots_v1",
  "slots": {
    "responsible_evaluator_name_first": "확인 중",
    "country_name": "확인 중",
    "evaluated_project_name": "사업명 종료평가",
    "responsible_evaluator_name_second": "확인 중",
    "completion_date_value": "확인 중",
    "lead_evaluator_line": "책임평가자: 확인 중",
    "evaluation_expert_line": "평가 전문가: 확인 중",
    "sector_expert_line": "분야 전문가: 확인 중",
    "assistant_evaluator_line": "평가 보조원: 확인 중",
    "quality_review_date_value": "확인 중",
    "quality_grade_value": "확인 중",
    "review_chair_name": "확인 중",
    "review_member_1_name": "확인 중",
    "review_member_2_name": "확인 중",
    "review_member_3_name": "확인 중",
    "citation_lead": "확인 중"
  }
}
````

</details>

### 4. 평가등급 결과표 (grade)

- 원본 파일: `prompts/Section4_평가등급_결과표.py`
- 작성 대상: 평가등급 결과표에 들어갈 슬롯 값을 작성한다.
- 출력 계약: JSON schema: `section4_grade_slots_v1`
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 세부 판단/생성 기준 요약: 점수는 새로 계산하지 말고 시스템 입력값을 유지하되, 산정 이유는 아래 기준으로 "왜 해당 점수인지"를 설명한다.<br>4점 사유: 3점 조건을 충족하고, 추가 우수요건까지 근거문서와 핵심 판단에서 확인될 때만 그렇게 쓴다.<br>3점 사유: 주요 요건은 충족하지만 참여, 증빙, 품질, 달성범위, 제도화 등 일부 한계가 있을 때 그 한계를 함께 쓴다.<br>2점 사유: 일부 고려 또는 일부 달성은 있으나 분석방식, 조정근거, 실효성, 증빙, 성과연계가 부족한 점을 쓴다.<br>외 15개
- 파이프라인 메모:
  - 기준별 평가결과 JSON과 전체 업로드 증빙으로 점수/산정 이유 작성
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가등급 결과표</summary>

````text
[작성 대상]
평가등급 결과표에 들어갈 슬롯 값을 작성한다.

[참고할 입력]
- content_inputs.criteria: 기준별 평가점수와 판단 근거.
- grade_score_rows: 시스템이 산정한 기준별 점수 행.
- content_inputs.overall: 종합점수, KOICA 평가등급, 국무조정실 평가등급.
- previous_text: 현재 등급표 또는 이전 JSON 슬롯 값.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 점수는 시스템 입력의 기준별 점수와 종합점수를 그대로 사용한다.
2. 점수 형식은 "3점", 종합점수는 "14/20점" 형식으로 쓴다.
3. 사유는 표 셀에 들어갈 수 있게 한 줄, 90자 이내로 쓴다.
4. 점수는 시스템 입력값을 유지하고, 사유는 content_inputs.criteria의 평가질문별 점수와 핵심 판단을 최우선 근거로 작성한다.
5. 각 기준의 total_reason은 반드시 "{기준명} 종합 평가: ..." 형식으로 쓴다. "종합 평균"이라는 표현은 쓰지 않는다.
6. 효율성은 efficiency_timeliness, efficiency_balance, efficiency_total 세 행을 모두 작성한다. efficiency_total_reason도 반드시 "효율성 종합 평가: ..."로 채운다.
7. 근거 없는 일반론, 사업명만 바꾼 문장, 원본 placeholder 문장, "전반적으로 양호" 같은 추상 표현만 있는 사유는 금지한다.
8. XML, markdown, 설명, 주석은 쓰지 않는다.

[세부 점수 산정 및 산정 이유 작성 기준]
점수는 새로 계산하지 말고 시스템 입력값을 유지하되, 산정 이유는 아래 기준으로 "왜 해당 점수인지"를 설명한다.
- 4점 사유: 3점 조건을 충족하고, 추가 우수요건까지 근거문서와 핵심 판단에서 확인될 때만 그렇게 쓴다.
- 3점 사유: 주요 요건은 충족하지만 참여, 증빙, 품질, 달성범위, 제도화 등 일부 한계가 있을 때 그 한계를 함께 쓴다.
- 2점 사유: 일부 고려 또는 일부 달성은 있으나 분석방식, 조정근거, 실효성, 증빙, 성과연계가 부족한 점을 쓴다.
- 1점 사유: 핵심 요건이 미반영, 미달성, 미대응이거나 성과에 부정적 영향이 확인된 점을 쓴다.
- 각 사유는 "근거문서/핵심 판단 내용 + 점수 기준 충족 또는 미충족 이유" 구조로 작성한다.

평가질문별로 반드시 확인할 근거는 다음과 같다.
- relevance_policy: CPS/CAS, 협력국 정책, 사전·기초조사, PCP/RD, PDM, ToC·문제나무, 수혜자·이해관계자 수요조사에서 정책 부합성, 우선순위, 수요분석 방식, 현지 참여가 확인되는지 본다.
- relevance_adaptation: 정기 모니터링, 사업변경 요청, JSC/운영위원회 회의록, 리스크 대응, 변경 PDM에서 외부 변화 인지, 적기 대응, 실행 가능한 대안, 성과지표 달성 가능성이 확인되는지 본다.
- coherence_internal: KOICA 타 사업, 국내 기관 사업, SDGs·인권·젠더·환경 세이프가드, 국제규범과의 중복·충돌 여부 및 역할분담 근거를 본다.
- coherence_external: 타 공여기관, 수원국 정부, 현지 주체와의 MoU, 조정회의록, RACI, 유사사업 맵에서 중복 회피와 상호보완적 시너지가 입증되는지 본다.
- effectiveness_output: 최신 PDM, 산출물 완료보고서, 활동별 결과보고서, 교육·시설·장비 실적에서 계획 산출물의 수량, 품질, 일정 달성 여부를 본다.
- effectiveness_outcome: 기준선·종료선, 성과지표 실적, 수혜자 조사, 기여도 분석에서 성과목표 달성, 사업 기여, 외부요인 구분 여부를 본다.
- effectiveness_equity: 성별·지역별·취약계층 분리통계, 소외계층 참여 기록, 수혜자 사례에서 형평성과 포용 효과가 확인되는지 본다.
- efficiency_timeliness: 예산 집행, 단가·비용 적정성, 일정표, 조달·계약, 지연 및 시정조치에서 경제성과 시의성이 확인되는지 본다.
- efficiency_balance: 인력·예산 투입, 활동별 투입 기록, 활동 간 조정회의록, 투입 대비 산출 분석에서 투입·활동·산출의 균형과 중복·공백 여부를 본다.
- sustainability_capacity: 운영·유지관리 계획, 예산 확약, 인수인계, 운영 매뉴얼, 현지 인력 교육, 위기대응 계획에서 자립 운영역량과 장기 재원이 확인되는지 본다.
- sustainability_environment: 정책·제도 반영, 공식 승인, 지역사회 참여, 역할분담, 사회적 수용성 근거에서 편익의 장기 제도화 가능성을 본다.
- total_reason: 하위 질문 점수의 평균만 반복하지 말고, 해당 기준에서 점수를 좌우한 핵심 강점과 한계를 함께 쓴다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 코드블록(```), 설명문, 주석, 추가 키는 절대 쓰지 않는다.

{
  "schema": "section4_grade_slots_v1",
  "slots": {
    "project_label": "평가대상 사업명: 사업명(사업기간 / 예산)",
    "relevance_policy_score": "",
    "relevance_policy_reason": "",
    "relevance_adaptation_score": "",
    "relevance_adaptation_reason": "",
    "relevance_total_score": "",
    "relevance_total_reason": "",
    "coherence_internal_score": "",
    "coherence_internal_reason": "",
    "coherence_external_score": "",
    "coherence_external_reason": "",
    "coherence_total_score": "",
    "coherence_total_reason": "",
    "effectiveness_output_score": "",
    "effectiveness_output_reason": "",
    "effectiveness_outcome_score": "",
    "effectiveness_outcome_reason": "",
    "effectiveness_equity_score": "",
    "effectiveness_equity_reason": "",
    "effectiveness_total_score": "",
    "effectiveness_total_reason": "",
    "efficiency_timeliness_score": "",
    "efficiency_timeliness_reason": "",
    "efficiency_balance_score": "",
    "efficiency_balance_reason": "",
    "efficiency_total_score": "",
    "efficiency_total_reason": "",
    "sustainability_capacity_score": "",
    "sustainability_capacity_reason": "",
    "sustainability_environment_score": "",
    "sustainability_environment_reason": "",
    "sustainability_total_score": "",
    "sustainability_total_reason": "",
    "overall_score": "",
    "government_grade": "",
    "koica_grade": "",
    "remove_grade_notice_1": "",
    "remove_grade_notice_2": ""
  }
}
````

</details>

### 5. 국문 요약 (summary-ko)

- 원본 파일: `prompts/Section5_국문_요약.py`
- 작성 대상: Section 5: I. 평가결과 요약 - 1. 국문 요약의 기존 placeholder 구조를 유지하면서, 각 입력 문단의 텍스트만 작성한다.
- 출력 계약: JSON schema: `section5_summary_slots_v1`
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 사업개요, PDM, 성과달성도, 기준별 평가결과, 결론/환류/교훈 종합
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 국문 요약</summary>

````text
[작성 대상]
Section 5: I. 평가결과 요약 - 1. 국문 요약의 기존 placeholder 구조를 유지하면서, 각 입력 문단의 텍스트만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 문단 수, 순서, 글꼴, 표, XML 구조는 수정하지 않는다.
2. 단일 통합 요약 필드를 만들지 않는다. 아래 slots의 각 값이 원본 문서의 특정 문단 하나를 대체한다.
3. 기존 구조 표지를 값 안에 그대로 포함한다. 예: "가. 사업명 :", "ㅇ 추진배경", "- (평가목적)", "ㅇ 결론".
4. 각 slot 값은 문자열 하나이며 markdown, XML, 코드블록, 설명문을 넣지 않는다.
5. 미기재 안내 문구를 쓰지 말고 자료 기반 완성문으로 작성한다.
6. 정보가 직접적으로 부족해도 reference_corpus, content_inputs, prior_analysis_sections, criteria 평가결과, 사업개요/PDM/평가매트릭스/등급표를 최대한 종합해 가장 개연성 높은 보고서 문장으로 완성한다.
7. 불확실한 수치가 있으면 수치 없이 정성적으로 쓴다. 확인되지 않은 개인명만 피하고, 사업 배경·성과·평가판단은 주어진 자료 범위에서 합리적으로 요약한다.
8. 샘플 보고서 문장은 복사하지 말고 현재 평가 대상 사업에 맞춰 새로 작성한다.

[슬롯별 작성 기준]
- project_name_line: "가. 사업명 : 사업명(기간/예산)" 한 줄.
- business_background: 사업 필요성/추진배경을 "- ..." 한 문단으로 작성.
- business_overview: 사업개요를 "- (사업개요) ..." 한 문단으로 작성.
- evaluation_purpose: "- (평가목적) ..." 형식.
- evaluation_scope: "- (평가범위) ..." 형식.
- evaluation_method_overview: "ㅇ 평가방법: ..." 형식으로 방법 목록 요약.
- document_review_method: "- (문헌조사) ..." 형식.
- stakeholder_interview_method: "- (이해관계자 인터뷰) ..." 형식.
- field_survey_method: "- (현지실사) ..." 형식.
- evaluation_limitations: "ㅇ 평가의 한계: ..." 형식.
- achievement_summary: 성과 달성도 요약을 "ㅇ ..." 한 문단.
- relevance_summary/coherence_summary/effectiveness_summary/efficiency_summary/sustainability_summary: 기준별 평가 결과를 각각 "- ..." 한 문단.
- crosscutting_human_rights_gender: "- (인권 및 성 주류화) ..." 형식.
- crosscutting_environment: "- (환경영향) ..." 형식.
- conclusion_goal_achievement: "- (사업 목표 달성) ..." 형식.
- conclusion_dac_results: "- (DAC 6대 기준에 따른 평가결과) ..." 형식.
- conclusion_crosscutting_results: "- (범 분야 이슈 평가 결과) ..." 형식.
- lesson_working_factors: "- (작동요인) ..." 형식.
- lesson_nonworking_factors: "- (비작동요인) ..." 형식.
- recommendation_project_model: "- (사업모델 변경제언) ..." 형식.
- recommendation_project_management: "- (사업관리 개선제언) ..." 형식.
- recommendation_structural_limits: "- (개발환경 및 개입 특성상의 구조적 한계 분석 제언) ..." 형식.
- recommendation_other: "- (기타) ..." 형식.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section5_summary_slots_v1",
  "slots": {
    "project_name_line": "가. 사업명 : ...",
    "business_background": "- ...",
    "business_overview": "- (사업개요) ...",
    "evaluation_purpose": "- (평가목적) ...",
    "evaluation_scope": "- (평가범위) ...",
    "evaluation_method_overview": "ㅇ 평가방법: ...",
    "document_review_method": "- (문헌조사) ...",
    "stakeholder_interview_method": "- (이해관계자 인터뷰) ...",
    "field_survey_method": "- (현지실사) ...",
    "evaluation_limitations": "ㅇ 평가의 한계: ...",
    "achievement_summary": "ㅇ ...",
    "relevance_summary": "- ...",
    "coherence_summary": "- ...",
    "effectiveness_summary": "- ...",
    "efficiency_summary": "- ...",
    "sustainability_summary": "- ...",
    "crosscutting_human_rights_gender": "- (인권 및 성 주류화) ...",
    "crosscutting_environment": "- (환경영향) ...",
    "conclusion_goal_achievement": "- (사업 목표 달성) ...",
    "conclusion_dac_results": "- (DAC 6대 기준에 따른 평가결과) ...",
    "conclusion_crosscutting_results": "- (범 분야 이슈 평가 결과) ...",
    "lesson_working_factors": "- (작동요인) ...",
    "lesson_nonworking_factors": "- (비작동요인) ...",
    "recommendation_project_model": "- (사업모델 변경제언) ...",
    "recommendation_project_management": "- (사업관리 개선제언) ...",
    "recommendation_structural_limits": "- (개발환경 및 개입 특성상의 구조적 한계 분석 제언) ...",
    "recommendation_other": "- (기타) ..."
  }
}
````

</details>

### 6. 사업 추진배경 (project-background)

- 원본 파일: `prompts/Section6_사업_추진배경.py`
- 작성 대상: Section 6: II. 대상사업개요 - 1. 사업 추진배경의 기존 placeholder 양식을 유지하면서, 다섯 개 배경 문단의 텍스트만 작성한다.
- 출력 계약: JSON schema: `section6_project_background_slots_v1`
- 참조 평가기준: relevance
- 파이프라인 메모:
  - 수원국 수요, 정책 부합성, 사업 형성 배경 작성
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 사업 추진배경</summary>

````text
[작성 대상]
Section 6: II. 대상사업개요 - 1. 사업 추진배경의 기존 placeholder 양식을 유지하면서, 다섯 개 배경 문단의 텍스트만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 문단 수, 순서, 글꼴, 들여쓰기, XML 구조는 수정하지 않는다.
2. 단일 통합 본문 필드를 만들지 않는다. 아래 slots의 각 값이 원본 문서의 특정 `ㅇ` 문단 하나를 대체한다.
3. 모든 slot 값은 반드시 `ㅇ `로 시작한다.
4. 각 slot 값은 문자열 하나이며 markdown, XML, 코드블록, 설명문을 넣지 않는다.
5. 미기재 안내 문구를 쓰지 말고 자료 기반 완성문으로 작성한다.
6. 자료가 충분하지 않아 보이는 항목도 reference_corpus, 사업개요서, 사전조사, PCP, PDM, 국별협력전략, 기준별 평가결과를 최대한 종합해 완성된 보고서 문단으로 쓴다.
7. 확인된 수치·연도·정책명은 적극 활용하되, 특정 수치가 불확실하면 수치 없이 정성적 문장으로 작성한다.
8. 샘플 보고서 문장은 복사하지 말고 현재 평가 대상 사업에 맞춰 새로 작성한다.

[슬롯별 작성 기준]
- mdg_maternal_health_context: 국가/분야 배경, 보건·모자보건 문제, 격차, 서비스 접근성 문제.
- government_policy_context: 협력국 정부의 보건·모자보건 정책, 중기계획, 제도적 방향.
- target_region_need: 대상지역의 지리·사회경제적 취약성, 보건의료 인프라 부족, 사업 요청 배경.
- koica_policy_alignment: KOICA 국가/분야 전략, 개발목표, ODA 정책과의 부합성.
- project_selection_rationale: 왜 해당 사업이 신규 또는 후속 사업으로 추진되었는지에 대한 종합 판단.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section6_project_background_slots_v1",
  "slots": {
    "mdg_maternal_health_context": "ㅇ ...",
    "government_policy_context": "ㅇ ...",
    "target_region_need": "ㅇ ...",
    "koica_policy_alignment": "ㅇ ...",
    "project_selection_rationale": "ㅇ ..."
  }
}
````

</details>

### 7. 사업개요 (project-overview)

- 원본 파일: `prompts/Section7_사업개요.py`
- 작성 대상: Section 7: II. 대상사업개요 - 2. 사업개요 표의 내용 셀만 작성한다.
- 출력 계약: JSON schema: `section7_project_overview_slots_v1`
- 참조 평가기준: relevance
- 파이프라인 메모:
  - 사업개요서 최종본 우선 사용
- 추가 증빙 데이터:
  - relevance: 사업개요서 또는 사업요청서 (PCP)

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 사업개요</summary>

````text
[작성 대상]
Section 7: II. 대상사업개요 - 2. 사업개요 표의 내용 셀만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 표, 행/열, 병합, 글꼴, XML 구조는 절대 수정하지 않는다.
2. 아래 slots의 각 값은 원본 표의 특정 내용 셀 하나를 대체한다.
3. markdown 표, XML, HTML, 코드블록, 설명문을 쓰지 않는다.
4. 각 값은 셀 안에 들어갈 최종 텍스트만 작성한다.
5. 줄바꿈이 필요한 항목은 " / "로 구분한다. <br> 태그를 쓰지 않는다.
6. 자료가 직접 부족해도 사업개요서, reference_corpus, content_inputs.project, prior_analysis_sections를 종합해 최대한 작성한다.
7. 확인되지 않은 인명은 쓰지 말고, 사업명/기간/예산/지역/활동/산출물은 제공 자료 범위에서 보수적으로 작성한다.

[슬롯별 작성 기준]
- project_name_ko: "▣ 국문: ..." 형식.
- project_name_en: "▣ 영문: ..." 형식. 영문명이 없으면 사업명 의미를 자연스럽게 영문 번역한다.
- target_country_region: "▣ 네팔 무구군(Mugu District)"처럼 대상국가와 지역을 함께 쓴다.
- project_period_budget: "▣ 구분 : ... / ▣ 기간 : ... / ▣ 총 사업예산 : ..." 형식.
- project_sector: "▣ 프로젝트 / 보건(모자보건)"처럼 사업유형과 분야를 함께 요약한다.
- project_purpose: 사업 목적을 1~2개 "▣ ..." 항목으로 작성한다.
- pcp_feasibility_review: PCP, 수총기관 공문, 사전타당성조사 관련 핵심 검토사항을 "󰁯 ..." 항목으로 요약한다.
- korean_textbook_development: 우리정부 분담사항 중 교재개발/교육자료 관련 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- korean_equipment_support: 기자재 지원 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- korean_expert_dispatch: 전문가 파견/자문/모니터링 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- korean_invitation_training: 초청연수 또는 현지 교육·훈련 내용을 "▣ 소요예산 : ... / ▪ ..." 형식으로 작성한다.
- partner_contribution: 수원국 또는 파트너 분담사항을 "▣ ..." 형식으로 작성한다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section7_project_overview_slots_v1",
  "slots": {
    "project_name_ko": "▣ 국문: ...",
    "project_name_en": "▣ 영문: ...",
    "target_country_region": "▣ ...",
    "project_period_budget": "▣ 구분 : ... / ▣ 기간 : ... / ▣ 총 사업예산 : ...",
    "project_sector": "▣ ...",
    "project_purpose": "▣ ...",
    "pcp_feasibility_review": "󰁯 관계기관 PCP : ... / 󰁯 수총기관 공문 : ... / 󰁯 사전타당성조사 : ...",
    "korean_textbook_development": "▣ 소요예산 : ... / ▪ ...",
    "korean_equipment_support": "▣ 소요예산 : ... / ▪ ...",
    "korean_expert_dispatch": "▣ 소요예산 : ... / ▪ ...",
    "korean_invitation_training": "▣ 소요예산 : ... / ▪ ...",
    "partner_contribution": "▣ ..."
  }
}
````

</details>

### 8. 사업설계매트릭스(PDM) (pdm)

- 원본 파일: `prompts/Section8_PDM.py`
- 작성 대상: Section 8: II. 대상사업개요 - 3. 사업설계매트릭스(PDM) 표의 placeholder 셀만 작성한다.
- 출력 계약: JSON schema: `section8_pdm_slots_v1`
- 참조 평가기준: relevance, effectiveness
- 파이프라인 메모:
  - PDM, ToC, 문제나무, 역할분담 자료로 논리모형 작성
- 추가 증빙 데이터:
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - effectiveness: 최신 PDM 및 성과지표 실적표

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 사업설계매트릭스(PDM)</summary>

````text
[작성 대상]
Section 8: II. 대상사업개요 - 3. 사업설계매트릭스(PDM) 표의 placeholder 셀만 작성한다.

[구조 유지 규칙]
1. 원본 HWPX의 제목, 표, 행/열, 병합, 글꼴, XML 구조는 절대 수정하지 않는다.
2. 아래 slots의 각 값은 원본 PDM 표의 특정 셀 하나를 대체한다.
3. markdown 표, XML, HTML, 코드블록, 설명문을 쓰지 않는다.
4. 각 값은 셀 안에 들어갈 최종 텍스트만 작성한다.
5. 줄바꿈이 필요한 항목은 " / "로 구분한다. <br> 태그를 쓰지 않는다.
6. 한 셀은 가능한 1~4개 짧은 항목으로 압축한다. 긴 설명문을 쓰지 않는다.
7. 자료가 직접 부족해도 PDM, 사업개요서, 성과지표 실적표, reference_corpus를 종합해 최대한 작성한다.

[PDM 표 구조]
- 영향(Impact): impact_summary, impact_indicator, impact_mov, impact_assumption
- 성과(Outcome): outcome_summary, outcome_indicator, outcome_mov, outcome_assumption
- 산출물(Outputs): outputs_summary, outputs_indicator, outputs_mov, outputs_assumption
- 활동/투입/전제조건: activities, inputs, preconditions

[출력 형식]
아래 JSON 객체 하나만 반환한다. key를 추가/삭제/변경하지 않는다.

{
  "schema": "section8_pdm_slots_v1",
  "slots": {
    "impact_summary": "...",
    "impact_indicator": "...",
    "impact_mov": "...",
    "impact_assumption": "...",
    "outcome_summary": "...",
    "outcome_indicator": "...",
    "outcome_mov": "...",
    "outcome_assumption": "...",
    "outputs_summary": "...",
    "outputs_indicator": "...",
    "outputs_mov": "...",
    "outputs_assumption": "...",
    "activities": "...",
    "inputs": "...",
    "preconditions": "..."
  }
}
````

</details>

### 9. 평가의 목적과 범위 (eval-purpose)

- 원본 파일: `prompts/Section9_평가_목적과_범위.py`
- 작성 대상: Section 9: III. 평가개요 - 1. 평가의 목적과 범위의 본문 슬롯만 작성한다.
- 출력 계약: JSON schema: `section9_eval_purpose_slots_v1`
- 참조 평가기준: relevance
- 파이프라인 메모:
  - 평가 목적/범위는 사업개요와 양식/FAQ 기준으로 작성
- 추가 증빙 데이터:
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가의 목적과 범위</summary>

````text
[작성 대상]
Section 9: III. 평가개요 - 1. 평가의 목적과 범위의 본문 슬롯만 작성한다.

[작성 규칙]
1. 원본 HWPX의 제목과 양식은 수정하지 않는다.
2. evaluation_purpose_scope_body에 들어갈 최종 본문만 작성한다.
3. 평가 목적, 활용 주체, 평가 대상, 평가 범위, 기준, 기간, 결과 활용 계획을 공식 보고서 문체로 정리한다.
4. 평가방법 상세 내용은 Section 11에서 다루므로 여기서는 범위 수준으로만 언급한다.
5. markdown, XML, 설명문, 인접 섹션 내용은 쓰지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다.

{
  "schema": "section9_eval_purpose_slots_v1",
  "slots": {
    "evaluation_purpose_scope_body": "평가 목적과 범위 본문"
  }
}
````

</details>

### 10. 평가매트릭스 (eval-matrix)

- 원본 파일: `prompts/Section10_평가매트릭스.py`
- 작성 대상: Section 10: III. 평가개요 - 2. 평가매트릭스(Evaluation Matrix)의 원본 표 셀에 들어갈 값만 작성한다.
- 출력 계약: JSON schema: `section10_eval_matrix_slots_v1`
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - DAC 기준-평가질문-지표-자료출처-방법 매핑
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가매트릭스</summary>

````text
[작성 대상]
Section 10: III. 평가개요 - 2. 평가매트릭스(Evaluation Matrix)의 원본 표 셀에 들어갈 값만 작성한다.

[원본 표 구조]
열: 평가기준 | 평가질문 | 측정지표 | 자료출처 | 분석방법
행: 적절성, 일관성, 효과성, 효율성, 지속가능성, 인권/취약계층주류화, 성주류화, 환경주류화
평가기준명과 표 양식은 알고리즘이 보존하므로 출력하지 않는다.

[작성 규칙]
1. 원본 HWPX 표 구조, 제목, 기준명은 수정하지 않는다.
2. 각 slot 값은 해당 표 셀 하나에 들어갈 짧은 문장 또는 구문으로 작성한다.
3. 자료가 부족해도 "추가 정보 필요", "확인 필요", "자료 없음"이라고 쓰지 말고, 제공 자료·사업개요·PDM·평가기준 자료에서 추론 가능한 범위로 작성한다.
4. 평가질문은 질문형 한 문장으로 작성하고, 측정지표·자료출처·분석방법은 쉼표로 구분한 간결한 구문으로 작성한다.
5. 실제 수행하지 않은 조사 방법을 단정하지 말고, 가능한 분석방법은 문헌조사, 이해관계자 면담, 현장확인, 성과자료 검토 등 제공된 자료 기반 범위에서 작성한다.
6. markdown table, XML, 설명문, 본문 문단, 인접 섹션 내용은 절대 쓰지 않는다.

[출력 형식]
아래 JSON 객체 하나만 반환한다. 모든 key를 반드시 포함한다.

{
  "schema": "section10_eval_matrix_slots_v1",
  "slots": {
    "relevance_question": "사업은 수원국 정책과 수요에 적절히 부합하였는가?",
    "relevance_indicator": "정책 부합성, 수요 반영도, 설계 적절성",
    "relevance_source": "사업개요서, 사전조사 자료, 보건정책 자료",
    "relevance_method": "문헌조사, 설계논리 검토, 이해관계자 면담",
    "coherence_question": "타 공여기관 및 정부 사업과 중복 없이 상호보완적으로 연계되었는가?",
    "coherence_indicator": "조정체계, 역할 분담, 연계성",
    "coherence_source": "운영위원회 자료, 공여기관 관련 자료, 면담자료",
    "coherence_method": "문헌조사, 비교분석, 관계자 면담",
    "effectiveness_question": "계획된 산출물과 성과목표가 달성되었는가?",
    "effectiveness_indicator": "산출물 달성도, 성과지표 변화, 수혜자 접근성",
    "effectiveness_source": "PDM, 완료보고서, 성과자료, 종료선 조사 자료",
    "effectiveness_method": "성과자료 검토, 문헌조사, 면담",
    "efficiency_question": "투입 예산과 일정, 운영방식이 효율적으로 관리되었는가?",
    "efficiency_indicator": "예산 집행률, 일정 준수, 투입 대비 산출",
    "efficiency_source": "예산 집행자료, 사업 일정표, 조달·운영 자료",
    "efficiency_method": "투입·산출 비교, 문헌조사, 관계자 면담",
    "sustainability_question": "사업 종료 후 운영·유지관리 체계가 지속될 수 있는가?",
    "sustainability_indicator": "운영체계, 인력 수급, 예산 확보, 제도화 수준",
    "sustainability_source": "사후관리 자료, 운영자료, 기자재 관리대장, 면담자료",
    "sustainability_method": "문헌조사, 운영체계 검토, 면담",
    "human_rights_question": "취약계층의 접근성과 포용성이 사업 설계와 성과관리에서 고려되었는가?",
    "human_rights_indicator": "취약계층 접근성, 서비스 이용 형평성, 참여도",
    "human_rights_source": "사업계획서, 수혜자 자료, 현장·면담자료",
    "human_rights_method": "문헌조사, 수혜자 관점 검토, 면담",
    "gender_question": "여성의 수요와 편익이 사업 설계 및 성과분석에 반영되었는가?",
    "gender_indicator": "여성 수혜 정도, 모성보건 접근성, 성별 성과 차이",
    "gender_source": "성과자료, 보건통계, 수혜자·관계자 면담자료",
    "gender_method": "성별 자료 검토, 문헌조사, 면담",
    "environment_question": "환경 및 시설 운영 위험이 사업 수행과 사후관리에 고려되었는가?",
    "environment_indicator": "환경위험 검토, 의료폐기물 관리, 시설 운영관리",
    "environment_source": "사업계획서, 시설·기자재 자료, 현장확인 자료",
    "environment_method": "문헌조사, 현장확인, 관계자 면담"
  }
}
````

</details>

### 11. 평가방법 (eval-methods)

- 원본 파일: `prompts/Section11_평가방법.py`
- 작성 대상: III. 평가개요 3. 평가 방법 본문을 작성한다.
- 출력 계약: 평가 방법 최종 텍스트만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 세부 판단/생성 기준 요약: 문헌조사는 실제로 확인된 자료군을 1차, 2차, 3차 문헌으로 구분해 작성한다.<br>1차 문헌은 KOICA 정책 문서, 협력국 전략, 사업요청서, RD, 사업개요서, PDM, 사업집행계획, 연례보고서, 성과점검 보고서, 종료보고서, 사업변경 승인 내역, 예산계획 대비 집행내역, 성과관리 자료처럼 사업 설계와 집행을 직접 설명하는 자료를 우선한다.<br>2차 문헌은 협력국 국가정책, 부문별 전략, 인구·보건·경제통계, 대상지역 및 수혜인구 배경자료처럼 사업 맥락과 수요를 판단하는 자료를 우선한다.<br>3차 문헌은 국제기구, 타 공여기관, 유사 분야 연구, 경제성 분석, 운영관리 참고자료처럼 비교·해석·제언 도출에 필요한 자료를 우선한다.<br>외 2개
- 파이프라인 메모:
  - 업로드 문헌 전체, 면담/설문/현장점검 기록을 방법론 자료원으로 사용
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가방법</summary>

````text
[작성 대상]
III. 평가개요 3. 평가 방법 본문을 작성한다.

[참고할 입력]
- reference_corpus: 평가계획, 인터뷰 기록, 설문 자료, 현장확인 자료, 문헌 목록.
- content_inputs.criteria: 기준별로 사용한 자료와 분석 방법.
- previous_text: 현재 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 문헌조사, 정량자료 검토, 이해관계자 면담, 현장확인, 설문 등 제공 자료에서 확인되는 방법을 중심으로 작성한다.
2. 직접 근거가 약한 방법은 단정하지 말고 "자료 검토", "면담자료 확인", "성과자료 대조"처럼 보수적으로 표현한다.
3. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다. 자료가 제한적이면 가능한 근거를 종합해 방법론 문장으로 완성한다.
4. 각 방법이 평가기준과 평가질문 검토에 어떻게 기여했는지 연결한다.
5. 표, markdown, XML, 코드블록 없이 최종 보고서 본문으로 바로 들어갈 문단/목록만 작성한다.

[세부 생성 기준]
- 문헌조사는 실제로 확인된 자료군을 1차, 2차, 3차 문헌으로 구분해 작성한다.
- 1차 문헌은 KOICA 정책 문서, 협력국 전략, 사업요청서, RD, 사업개요서, PDM, 사업집행계획, 연례보고서, 성과점검 보고서, 종료보고서, 사업변경 승인 내역, 예산계획 대비 집행내역, 성과관리 자료처럼 사업 설계와 집행을 직접 설명하는 자료를 우선한다.
- 2차 문헌은 협력국 국가정책, 부문별 전략, 인구·보건·경제통계, 대상지역 및 수혜인구 배경자료처럼 사업 맥락과 수요를 판단하는 자료를 우선한다.
- 3차 문헌은 국제기구, 타 공여기관, 유사 분야 연구, 경제성 분석, 운영관리 참고자료처럼 비교·해석·제언 도출에 필요한 자료를 우선한다.
- 면담, 설문, 현장확인은 실시 근거가 있는 경우에만 쓰고, 각 방법이 적절성, 일관성, 효과성, 효율성, 지속가능성 판단에 어떤 증거를 제공했는지 연결한다.
- 이전 양식의 placeholder 문장과 동일한 내용을 그대로 반환하지 말고, 현재 reference_corpus와 content_inputs.criteria에 있는 문서명과 분석 목적을 반영한다.

[출력]
평가 방법 최종 텍스트만 반환한다.
````

</details>

### 12. 평가의 한계 (eval-limitations)

- 원본 파일: `prompts/Section12_평가의_한계.py`
- 작성 대상: III. 평가개요 4. 평가의 한계 본문을 작성한다.
- 출력 계약: 평가의 한계 최종 텍스트만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 미업로드 슬롯과 자료공백을 평가 한계로 정리
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가의 한계</summary>

````text
[작성 대상]
III. 평가개요 4. 평가의 한계 본문을 작성한다.

[참고할 입력]
- reference_corpus: 미확보 자료, 인터뷰 제약, 조사 범위 제한, 데이터 품질 관련 근거.
- content_inputs.criteria: 기준별 자료 충분성 및 한계.
- prior_analysis_sections: 이미 작성된 분석에서 확인된 공백.
- previous_text: 현재 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 한계는 "제약 내용 - 분석 영향 - 보완 방식"이 드러나도록 작성한다.
2. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다.
3. 자료가 부족한 경우에도 제공 자료에서 확인되는 데이터 공백, 현장 접근성, 성과지표 추적 한계, 이해관계자 기억 의존성 등을 평가 한계로 구체화한다.
4. 책임 회피가 아니라 해석 범위를 명확히 하는 톤으로 작성한다.
5. 표, markdown, XML, 코드블록 없이 최종 보고서 본문만 작성한다.

[출력]
평가의 한계 최종 텍스트만 반환한다.
````

</details>

### 13. 평가팀 구성 및 시행체계 (eval-team)

- 원본 파일: `prompts/Section13_평가팀_구성_및_시행체계.py`
- 작성 대상: III. 평가개요 5. 평가팀 구성 및 시행체계 본문을 작성한다.
- 출력 계약: 평가팀 구성 및 시행체계 최종 텍스트만 반환한다.
- 참조 평가기준: relevance
- 파이프라인 메모:
  - 평가책임자, 수행기관, 품질관리 체계 확인
- 추가 증빙 데이터:
  - relevance: 사업개요서 또는 사업요청서 (PCP)

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 평가팀 구성 및 시행체계</summary>

````text
[작성 대상]
III. 평가개요 5. 평가팀 구성 및 시행체계 본문을 작성한다.

[참고할 입력]
- reference_corpus: 평가자 명단, 역할분담표, 수행기관 정보, 품질관리 체계.
- previous_text: 현재 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 평가책임자, 평가자, 품질관리, 수행기관, 역할분담을 제공 자료에 근거해 정리한다.
2. 개인명·소속·직책 근거가 없으면 이름을 만들지 말고, 평가책임자/분야전문가/평가보조원 등 역할 중심으로 작성한다.
3. "추가 정보 필요", "자료 없음", "확인 필요", "확인 중" 같은 안내문을 쓰지 않는다.
4. 수행체계는 KOICA, 수행기관, 현지 이해관계자, 품질검토 절차의 관계가 보이도록 작성한다.
5. 개인정보나 연락처는 쓰지 않는다. 표, markdown, XML, 코드블록 없이 최종 본문만 작성한다.

[출력]
평가팀 구성 및 시행체계 최종 텍스트만 반환한다.
````

</details>

### 14. 성과 달성도 (achievement)

- 원본 파일: `prompts/Section14_성과_달성도.py`
- 작성 대상: IV. 성과 달성도 표에 들어갈 성과지표별 내용을 작성한다.
- 출력 계약: 아래 형식으로 3~5개 항목을 작성한다. 각 항목은 빈 줄로 구분한다. - 군립병원 인프라 개선: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ... - 보건의료 인력 역량 강화: 성과지표: ... /…
- 참조 평가기준: relevance, effectiveness
- 세부 판단/생성 기준 요약: 최신 PDM 또는 승인된 성과관리 자료를 우선 사용하고, 지표가 변경된 경우 변경 전후 지표를 혼합하지 않는다.<br>각 항목은 기초선, 목표치, 종료선 또는 현재 실적, 지표입증수단(MOV), 확인 문서를 기준으로 작성한다.<br>달성 여부는 단순히 "달성"이라고 쓰지 말고, 목표 대비 실적의 차이와 그 차이가 산출물·성과 판단에 미치는 의미를 함께 쓴다.<br>수치가 없는 지표는 종료보고서, 성과점검 보고서, 현장확인, 인터뷰 등 정성 근거로 대체하되 불확실성을 숨기지 않는다.<br>외 1개
- 파이프라인 메모:
  - PDM 지표, 목표/실적, MOV, 성과자료 작성
- 추가 증빙 데이터:
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 성과 달성도</summary>

````text
[작성 대상]
IV. 성과 달성도 표에 들어갈 성과지표별 내용을 작성한다.

[참고할 입력]
- reference_corpus: PDM, 성과지표, 산출물 실적, 종료보고서, 점검표, 인터뷰/설문 근거.
- content_inputs.criteria: 성과달성도 관련 기준과 점수.
- previous_text: 현재 성과달성도 표 양식.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 표 셀로 분해될 수 있도록 항목별 라벨 형식을 반드시 지킨다.
2. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다. 수치가 불확실하면 정성적 표현으로 대체한다.
3. 지표별로 목표, 실적, 달성 여부, 확인 근거, 미달 또는 초과 사유를 간결히 쓴다.
4. '평가점수 2/4' 같은 점수 라벨을 쓰지 않는다.
5. markdown table, XML, 코드블록, 장문 해설은 쓰지 않는다.

[세부 생성 기준]
- 최신 PDM 또는 승인된 성과관리 자료를 우선 사용하고, 지표가 변경된 경우 변경 전후 지표를 혼합하지 않는다.
- 각 항목은 기초선, 목표치, 종료선 또는 현재 실적, 지표입증수단(MOV), 확인 문서를 기준으로 작성한다.
- 달성 여부는 단순히 "달성"이라고 쓰지 말고, 목표 대비 실적의 차이와 그 차이가 산출물·성과 판단에 미치는 의미를 함께 쓴다.
- 수치가 없는 지표는 종료보고서, 성과점검 보고서, 현장확인, 인터뷰 등 정성 근거로 대체하되 불확실성을 숨기지 않는다.
- 미달성 또는 초과 달성은 지연, 외부환경, 예산·조달, 운영역량, 수요 변화 등 확인된 원인을 연결하여 작성한다.

[출력 형식]
아래 형식으로 3~5개 항목을 작성한다. 각 항목은 빈 줄로 구분한다.

- 군립병원 인프라 개선: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
- 보건의료 인력 역량 강화: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
- 지역사회 모자보건 서비스 이용 개선: 성과지표: ... / 기초선: ... / 목표치: ... / 종료선: ... / 대비 결과: ... / 지표입증수단(MOV): ... / 비고: ...
````

</details>

### 15. 적절성 (criteria-relevance)

- 원본 파일: `prompts/Section15_적절성.py`
- 작성 대상: V. 기준별 평가결과 1. 적절성 본문을 작성한다.
- 출력 계약: 적절성 평가결과 최종 본문만 반환한다.
- 참조 평가기준: relevance
- 세부 판단/생성 기준 요약: 정책·수요·우선순위 반영 여부는 협력국 국가개발전략 또는 부문별 정책, 한국 정부/KOICA CPS·CAS, 사전조사 및 기초조사, PCP/RD, 최신 PDM, ToC·문제나무, 수혜자·이해관계자 수요조사 자료를 함께 보고 판단한다.<br>높은 평가를 받은 경우에는 단순히 정책에 부합한다고 쓰지 말고, 정책 방향, 지역·수혜자 수요, 사업 산출물, PDM 지표, 변화이론이 어떤 논리로 연결되었는지 구체적으로 설명한다.<br>4점 수준의 판단은 협력국 정책과 KOICA 전략 부합, 사전 수요조사, 현지 이해관계자 참여, 문제나무 또는 ToC 기반 설계, 우선순위의 PDM 반영이 모두 확인될 때 작성한다.<br>3점 수준의 판단은 정책·수요와 대체로 부합하나 현지 참여, 취약계층 수요, 분석방식, PDM 연결근거 중 일부가 충분히 입증되지 않을 때 작성한다.<br>외 2개
- 파이프라인 메모:
  - 적절성 10개 슬롯만 사용
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 적절성</summary>

````text
[작성 대상]
V. 기준별 평가결과 1. 적절성 본문을 작성한다.

[참고할 입력]
- reference_corpus: 사업요청서, PCP, 정책문서, 수요조사, 설계자료, 인터뷰 등 적절성 판단 근거.
- content_inputs.criteria: 적절성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 세부 항목별 소제목을 두고, 각 항목은 최종 보고서 문체의 줄글 중심으로 분석한다.
2. 평가질문을 그대로 반복하거나 '평가점수 2/4'처럼 쓰지 않는다. 점수는 판단의 배경으로만 자연스럽게 반영한다.
3. 사업이 대상 지역 수요, 수원국 정책, KOICA 전략, 대상자 요구와 얼마나 부합했는지 근거 기반으로 설명한다.
4. "추가 정보 필요", "자료 없음", "확인 필요" 같은 안내문을 쓰지 않는다. 자료가 부족하면 제공 자료에서 확인되는 범위와 해석 한계를 문장 안에 녹인다.
5. 긍정 근거와 보완점을 균형 있게 쓰고, 샘플 문장은 복사하지 않는다.
6. markdown table, XML, 코드블록, 파일 경로는 쓰지 않는다.

[세부 판단 기준]
- 정책·수요·우선순위 반영 여부는 협력국 국가개발전략 또는 부문별 정책, 한국 정부/KOICA CPS·CAS, 사전조사 및 기초조사, PCP/RD, 최신 PDM, ToC·문제나무, 수혜자·이해관계자 수요조사 자료를 함께 보고 판단한다.
- 높은 평가를 받은 경우에는 단순히 정책에 부합한다고 쓰지 말고, 정책 방향, 지역·수혜자 수요, 사업 산출물, PDM 지표, 변화이론이 어떤 논리로 연결되었는지 구체적으로 설명한다.
- 4점 수준의 판단은 협력국 정책과 KOICA 전략 부합, 사전 수요조사, 현지 이해관계자 참여, 문제나무 또는 ToC 기반 설계, 우선순위의 PDM 반영이 모두 확인될 때 작성한다.
- 3점 수준의 판단은 정책·수요와 대체로 부합하나 현지 참여, 취약계층 수요, 분석방식, PDM 연결근거 중 일부가 충분히 입증되지 않을 때 작성한다.
- 상황변화 대응 여부는 정기 모니터링, 사업변경 요청, 운영위원회/JSC 회의록, 리스크 대응 기록, 변경 PDM, 일정·예산 변경 자료를 보고 판단한다.
- 외부 변화가 있었던 경우에는 변화의 내용, 사업의 대응 시점, 이해관계자 조정, 대안의 실행 가능성, 성과지표 달성에 미친 영향을 함께 설명한다.

[출력]
적절성 평가결과 최종 본문만 반환한다.
````

</details>

### 16. 일관성 (criteria-coherence)

- 원본 파일: `prompts/Section16_일관성.py`
- 작성 대상: V. 기준별 평가결과 2. 일관성을 작성한다.
- 출력 계약: 일관성 평가결과 최종 본문만 반환한다.
- 참조 평가기준: coherence
- 세부 판단/생성 기준 요약: 내적 일관성은 KOICA 타 사업, 국내 기관 사업, SDGs, 인권·젠더·환경 세이프가드, 국제규범, 사업 내부의 활동-산출-성과 논리를 함께 보고 판단한다.<br>높은 평가를 받은 경우에는 중복 또는 충돌이 없다는 표현에 그치지 말고, 어떤 기관·사업·규범과 어떤 방식으로 조정되어 시너지가 생겼는지 설명한다.<br>4점 수준의 판단은 국내 정책, KOICA 타 사업, 국제규범, 세이프가드 준수, 역할분담 근거가 모두 명확하고 중복 없이 부가가치가 확인될 때 작성한다.<br>3점 수준의 판단은 전반적 조화는 확인되나 구체적 조정회의, 역할분담, 세이프가드 적용 근거가 일부 제한될 때 작성한다.<br>외 2개
- 파이프라인 메모:
  - 일관성 9개 슬롯만 사용
- 추가 증빙 데이터:
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 일관성</summary>

````text
[작성 대상]
V. 기준별 평가결과 2. 일관성을 작성한다.

[참고할 입력]
- reference_corpus: 정책/전략 문서, 타 공여기관 사업, KOICA 포트폴리오, 사업 설계·수행 자료.
- content_inputs.criteria: 일관성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 내부 일관성(사업 설계 내부의 논리, 활동-산출-성과 연결)과 외부 일관성(수원국/KOICA/타 사업과의 연계)을 구분해 분석한다.
2. 평가질문이나 점수 라벨을 그대로 붙이지 말고, 보고서 문단으로 자연스럽게 작성한다.
3. 연계가 확인된 부분과 직접 근거가 제한적인 부분을 명확히 구분한다.
4. 다른 기준의 내용과 중복되면 일관성 관점으로 재정리한다.
5. 최종 본문만 반환한다.

[세부 판단 기준]
- 내적 일관성은 KOICA 타 사업, 국내 기관 사업, SDGs, 인권·젠더·환경 세이프가드, 국제규범, 사업 내부의 활동-산출-성과 논리를 함께 보고 판단한다.
- 높은 평가를 받은 경우에는 중복 또는 충돌이 없다는 표현에 그치지 말고, 어떤 기관·사업·규범과 어떤 방식으로 조정되어 시너지가 생겼는지 설명한다.
- 4점 수준의 판단은 국내 정책, KOICA 타 사업, 국제규범, 세이프가드 준수, 역할분담 근거가 모두 명확하고 중복 없이 부가가치가 확인될 때 작성한다.
- 3점 수준의 판단은 전반적 조화는 확인되나 구체적 조정회의, 역할분담, 세이프가드 적용 근거가 일부 제한될 때 작성한다.
- 외적 일관성은 타 공여기관, 수원국 정부, 현지 기관, 민간 주체와의 MoU, 조정회의록, RACI, 유사사업 맵을 보고 판단한다.
- 타 주체와의 조율은 중복 회피, 상호보완 역할, 공동 목표, 협의체 운영, 이슈 해소 기록이 확인되는 범위에서만 구체적으로 쓴다.

[출력]
일관성 평가결과 최종 본문만 반환한다.
````

</details>

### 17. 효과성 (criteria-effectiveness)

- 원본 파일: `prompts/Section17_효과성.py`
- 작성 대상: V. 기준별 평가결과 3. 효과성을 작성한다.
- 출력 계약: 효과성 평가결과 최종 본문만 반환한다.
- 참조 평가기준: effectiveness
- 세부 판단/생성 기준 요약: 산출물 달성은 최신 PDM, 산출물 완료보고서, 활동별 결과보고서, 교육·시설·장비 제공 실적, 현장점검 기록을 보고 판단한다.<br>산출물 평가는 수량 달성만 보지 말고 품질, 범위, 일정, 사용 가능성, 산출물이 성과로 연결된 근거를 함께 설명한다.<br>성과 및 목표 달성은 기준선·종료선 조사, 성과지표 실적표, 수혜자 만족도, 성과 기여도 분석, 외부요인 검토 자료를 보고 판단한다.<br>4점 수준의 판단은 목표 성과가 모두 달성되고 사업 개입에 따른 명확한 변화 또는 추가 긍정 성과가 확인될 때 작성한다.<br>외 3개
- 파이프라인 메모:
  - 효과성 9개 슬롯만 사용
- 추가 증빙 데이터:
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 효과성</summary>

````text
[작성 대상]
V. 기준별 평가결과 3. 효과성을 작성한다.

[참고할 입력]
- reference_corpus: PDM, 성과지표 실적, 산출물 점검, 인터뷰, 설문, 종료보고서 등 효과성 판단 근거.
- content_inputs.criteria: 효과성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 샘플 보고서처럼 산출물 달성, 성과 달성, 목표 달성 가능성, 수혜자 변화 등을 항목별로 분석한다.
2. '평가점수 2/4' 같은 라벨이나 표 내용을 그대로 복사하지 않는다.
3. 실적 수치가 있으면 목표 대비 의미를 설명하고, 수치가 없으면 확인 가능한 정성 근거를 중심으로 쓴다.
4. 긍정적 변화와 미달 요인을 모두 포함해 왜 해당 평가가 나왔는지 드러나게 한다.
5. 최종 보고서 문단으로 작성하고, 설명이나 파일 경로는 쓰지 않는다.

[세부 판단 기준]
- 산출물 달성은 최신 PDM, 산출물 완료보고서, 활동별 결과보고서, 교육·시설·장비 제공 실적, 현장점검 기록을 보고 판단한다.
- 산출물 평가는 수량 달성만 보지 말고 품질, 범위, 일정, 사용 가능성, 산출물이 성과로 연결된 근거를 함께 설명한다.
- 성과 및 목표 달성은 기준선·종료선 조사, 성과지표 실적표, 수혜자 만족도, 성과 기여도 분석, 외부요인 검토 자료를 보고 판단한다.
- 4점 수준의 판단은 목표 성과가 모두 달성되고 사업 개입에 따른 명확한 변화 또는 추가 긍정 성과가 확인될 때 작성한다.
- 3점 수준의 판단은 주요 산출물과 성과가 대체로 달성되었으나 일부 지표, 품질, 기여도 구분, 외부요인 통제에 한계가 있을 때 작성한다.
- 형평성은 성별·지역별·취약계층 분리통계, 소외계층 참여자 명단, 지원 실적, 수혜자 인터뷰 또는 사례 기록을 보고 판단한다.
- 취약계층 포용은 단순 언급이 아니라 설계, 집행, 성과관리 단계에서 실제로 어떻게 반영되었는지 써야 한다.

[출력]
효과성 평가결과 최종 본문만 반환한다.
````

</details>

### 18. 효율성 (criteria-efficiency)

- 원본 파일: `prompts/Section18_효율성.py`
- 작성 대상: V. 기준별 평가결과 4. 효율성을 작성한다.
- 출력 계약: 효율성 평가결과 최종 본문만 반환한다.
- 참조 평가기준: efficiency
- 세부 판단/생성 기준 요약: 경제성 및 시의성은 예산 집행내역, 집행률 분석표, 예산 변경 승인 문서, 단가 비교 또는 비용 적정성 검토, 사업 일정표, 조달·입찰·계약 문서, 지연 사유와 시정조치 기록을 보고 판단한다.<br>높은 평가를 받은 경우에는 단순히 예산이 집행되었다고 쓰지 말고, 예산 편차, 일정 지연, 조달 이슈, 보완조치가 산출물과 성과에 어떤 영향을 주었는지 설명한다.<br>4점 수준의 판단은 예산과 일정이 매우 효율적으로 관리되고 자원 절감, 추가 성과, 지연 최소화, 신속한 시정조치가 확인될 때 작성한다.<br>3점 수준의 판단은 주요 지연 또는 예산 편차가 관리되었으나 일부 조달 지연, 집행 조정, 비용 적정성 근거 부족이 남을 때 작성한다.<br>외 2개
- 파이프라인 메모:
  - 효율성 9개 슬롯만 사용
- 추가 증빙 데이터:
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 효율성</summary>

````text
[작성 대상]
V. 기준별 평가결과 4. 효율성을 작성한다.

[참고할 입력]
- reference_corpus: 예산, 집행, 일정, 조달, 투입 대비 산출, 사업관리 문서.
- content_inputs.criteria: 효율성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 예산 집행, 일정 관리, 조달·시공·운영관리, 투입 대비 산출의 관점에서 분석한다.
2. 점수 라벨이나 표 문구를 그대로 옮기지 않는다.
3. 지연, 비용 증가, 관리상 제약이 있으면 원인과 영향까지 설명한다.
4. 자료가 부족한 경우에도 근거 있는 범위에서 판단하고 한계를 짧게 밝힌다.
5. 최종 보고서 본문으로 작성한다.

[세부 판단 기준]
- 경제성 및 시의성은 예산 집행내역, 집행률 분석표, 예산 변경 승인 문서, 단가 비교 또는 비용 적정성 검토, 사업 일정표, 조달·입찰·계약 문서, 지연 사유와 시정조치 기록을 보고 판단한다.
- 높은 평가를 받은 경우에는 단순히 예산이 집행되었다고 쓰지 말고, 예산 편차, 일정 지연, 조달 이슈, 보완조치가 산출물과 성과에 어떤 영향을 주었는지 설명한다.
- 4점 수준의 판단은 예산과 일정이 매우 효율적으로 관리되고 자원 절감, 추가 성과, 지연 최소화, 신속한 시정조치가 확인될 때 작성한다.
- 3점 수준의 판단은 주요 지연 또는 예산 편차가 관리되었으나 일부 조달 지연, 집행 조정, 비용 적정성 근거 부족이 남을 때 작성한다.
- 투입·활동·산출의 균형은 인력 투입 계획, 활동별 투입 기록, 주요 활동 간 조정 회의록, 투입 대비 산출 분석표를 보고 판단한다.
- 투입 균형 판단은 중복 투입, 활동 공백, 특정 산출물 편중, 관리 비효율, 조정체계의 작동 여부를 구분하여 작성한다.

[출력]
효율성 평가결과 최종 본문만 반환한다.
````

</details>

### 19. 지속가능성 (criteria-sustainability)

- 원본 파일: `prompts/Section19_지속가능성.py`
- 작성 대상: V. 기준별 평가결과 5. 지속가능성을 작성한다.
- 출력 계약: 지속가능성 평가결과 최종 본문만 반환한다.
- 참조 평가기준: sustainability
- 세부 판단/생성 기준 요약: 운영역량·재정·위기대응은 운영·유지관리 계획, 지방정부 또는 파트너 기관 예산 확약서, 인수인계 문서, 운영 매뉴얼, 현지 인력 역량강화 계획 및 교육 결과, 리스크·위기대응 계획을 보고 판단한다.<br>높은 평가를 받은 경우에는 운영계획 존재만 쓰지 말고, 운영 주체, 예산 출처, 책임체계, 인력 역량, 위기대응 절차가 실제로 지속 가능한지 설명한다.<br>4점 수준의 판단은 현지 시스템과 조직이 자립 운영역량, 장기 재원, 책임체계, 위기대응능력을 명확히 확보한 경우에 작성한다.<br>3점 수준의 판단은 운영체계와 담당 조직 역량은 마련되었으나 예산 확약, 인수인계 완결성, 장기 운영재원, 위기대응 근거가 일부 제한될 때 작성한다.<br>외 2개
- 파이프라인 메모:
  - 지속가능성 9개 슬롯만 사용
- 추가 증빙 데이터:
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 지속가능성</summary>

````text
[작성 대상]
V. 기준별 평가결과 5. 지속가능성을 작성한다.

[참고할 입력]
- reference_corpus: 운영·유지관리, 예산 확보, 인력 역량, 제도화, 현지 주인의식 관련 자료.
- content_inputs.criteria: 지속가능성 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 제도적, 재정적, 조직·인력, 시설·기자재 유지관리, 지역사회 수용성 관점으로 분석한다.
2. 지속가능성이 높은 요소와 취약 요소를 구분해 쓴다.
3. 점수 라벨이나 질문 반복은 쓰지 않는다.
4. 후속 운영 가능성은 근거가 있는 범위에서만 판단한다.
5. 최종 보고서 본문만 반환한다.

[세부 판단 기준]
- 운영역량·재정·위기대응은 운영·유지관리 계획, 지방정부 또는 파트너 기관 예산 확약서, 인수인계 문서, 운영 매뉴얼, 현지 인력 역량강화 계획 및 교육 결과, 리스크·위기대응 계획을 보고 판단한다.
- 높은 평가를 받은 경우에는 운영계획 존재만 쓰지 말고, 운영 주체, 예산 출처, 책임체계, 인력 역량, 위기대응 절차가 실제로 지속 가능한지 설명한다.
- 4점 수준의 판단은 현지 시스템과 조직이 자립 운영역량, 장기 재원, 책임체계, 위기대응능력을 명확히 확보한 경우에 작성한다.
- 3점 수준의 판단은 운영체계와 담당 조직 역량은 마련되었으나 예산 확약, 인수인계 완결성, 장기 운영재원, 위기대응 근거가 일부 제한될 때 작성한다.
- 제도적·사회적 환경은 정책·제도 반영 또는 공식 승인 문서, 지역사회 참여 및 수용성 확인 자료, 운영 담당 조직의 역할분담 문서, 장기 재원조달 또는 수익모델 자료를 보고 판단한다.
- 제도화 가능성은 정책 반영, 현지 정부의 소유권, 지역사회 수용성, 사업 편익 확산 가능성을 구분하여 작성한다.

[출력]
지속가능성 평가결과 최종 본문만 반환한다.
````

</details>

### 20. 범분야 이슈 (criteria-crosscutting)

- 원본 파일: `prompts/Section20_범분야_이슈.py`
- 작성 대상: V. 기준별 평가결과 6. 범분야 이슈를 작성한다.
- 출력 계약: 범분야 이슈 평가결과 최종 본문만 반환한다.
- 참조 평가기준: coherence, effectiveness, sustainability
- 세부 판단/생성 기준 요약: 성평등은 성별 분리통계, 여성 참여, 모자보건 접근성, 성인지적 사업설계, 여성 수혜자 또는 종사자 역량강화 근거를 보고 판단한다.<br>취약계층·인권은 지역, 소득, 장애, 연령, 접근성 제약 등 소외요인을 고려한 대상자 선정과 서비스 접근 개선 근거를 보고 판단한다.<br>환경과 세이프가드는 환경영향, 의료폐기물, 기자재 운영, 시설 개선, 안전관리, 관련 체크리스트와 준수 근거를 보고 판단한다.<br>갈등민감성과 지역사회 수용성은 지역사회 참여, 현지 기관 협의, 민원 또는 갈등 대응, 문화적 수용성 근거를 보고 판단한다.<br>외 2개
- 파이프라인 메모:
  - 젠더, 환경, 인권, 취약계층, 세이프가드 자료 중심
- 추가 증빙 데이터:
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - sustainability: 지역사회 참여 및 수용성 확인 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 범분야 이슈</summary>

````text
[작성 대상]
V. 기준별 평가결과 6. 범분야 이슈를 작성한다.

[참고할 입력]
- reference_corpus: 성평등, 환경, 인권, 취약계층, 세이프가드, 갈등민감성 관련 근거.
- content_inputs.criteria: 범분야 평가질문, 점수, 핵심 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 자료에서 확인되는 범분야 이슈만 작성한다.
2. 성평등, 환경, 취약계층, 인권, 세이프가드 항목을 억지로 모두 채우지 않는다.
3. 확인되지 않는 항목은 '확인 가능한 근거가 제한적임' 정도로 간결히 처리한다.
4. 사업 설계와 수행에서 실제로 어떻게 반영되었는지, 부족한 점은 무엇인지 분석한다.
5. 최종 보고서 본문으로 작성한다.

[세부 판단 기준]
- 성평등은 성별 분리통계, 여성 참여, 모자보건 접근성, 성인지적 사업설계, 여성 수혜자 또는 종사자 역량강화 근거를 보고 판단한다.
- 취약계층·인권은 지역, 소득, 장애, 연령, 접근성 제약 등 소외요인을 고려한 대상자 선정과 서비스 접근 개선 근거를 보고 판단한다.
- 환경과 세이프가드는 환경영향, 의료폐기물, 기자재 운영, 시설 개선, 안전관리, 관련 체크리스트와 준수 근거를 보고 판단한다.
- 갈등민감성과 지역사회 수용성은 지역사회 참여, 현지 기관 협의, 민원 또는 갈등 대응, 문화적 수용성 근거를 보고 판단한다.
- 높은 평가를 받은 경우에는 단순히 고려했다고 쓰지 말고, 설계, 집행, 모니터링, 성과관리 중 어느 단계에서 어떻게 반영되었는지 설명한다.
- 근거가 제한적인 경우에는 범분야 이슈가 사업성과에 미친 영향과 향후 보완 필요 지점을 분리하여 작성한다.

[출력]
범분야 이슈 평가결과 최종 본문만 반환한다.
````

</details>

### 21. 그 외 평가기준 (criteria-other)

- 원본 파일: `prompts/Section21_그_외_평가기준.py`
- 작성 대상: V. 기준별 평가결과 7. 그 외 평가기준을 작성한다.
- 출력 계약: 그 외 평가기준 최종 본문만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 사업 특수성, 혁신성, 확산 가능성은 전체 증빙에서 확인
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 그 외 평가기준</summary>

````text
[작성 대상]
V. 기준별 평가결과 7. 그 외 평가기준을 작성한다.

[참고할 입력]
- reference_corpus: 위 기준으로 포착되지 않는 특수 이슈, 혁신성, 확장성, 위험관리 등 관련 근거.
- prior_analysis_sections: 앞선 기준별 분석.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 실제로 의미 있는 추가 평가기준이나 특수 이슈가 있을 때만 작성한다.
2. 쓸 내용이 없으면 억지로 새 기준을 만들지 말고, 해당 사항이 제한적임을 짧게 정리한다.
3. 앞 기준의 반복은 피하고, 추가적으로 보고서에 필요한 판단만 담는다.
4. 최종 보고서 본문으로 작성한다.

[출력]
그 외 평가기준 최종 본문만 반환한다.
````

</details>

### 22. 결론 (conclusion)

- 원본 파일: `prompts/Section22_결론.py`
- 작성 대상: VI. 결론 1. 결론을 작성한다.
- 출력 계약: 결론 최종 본문만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 기준별 평가결과와 성과달성도만 종합하고 새 사실 추가 금지
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 결론</summary>

````text
[작성 대상]
VI. 결론 1. 결론을 작성한다.

[참고할 입력]
- prior_analysis_sections: 앞서 작성된 사업개요, 평가개요, 성과달성도, 기준별 평가결과.
- content_inputs.criteria: 기준별 점수와 핵심 판단.
- reference_corpus: 결론 검증에 필요한 제한적 원문 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 결론은 원문을 처음부터 다시 분석하는 글이 아니라, 앞 섹션의 판단을 종합하는 글이다.
2. 사업의 의의, 주요 성과, 핵심 제약, 종합 평가를 균형 있게 정리한다.
3. 새로운 사실이나 새로운 점수를 만들지 않는다.
4. 기준별 내용을 단순 반복하지 말고, 보고서 전체 메시지가 드러나게 쓴다.
5. 최종 보고서 본문만 반환한다.

[출력]
결론 최종 본문만 반환한다.
````

</details>

### 23. 작동요인 (working-factors)

- 원본 파일: `prompts/Section23_작동요인.py`
- 작성 대상: VI. 결론 2. 작동요인을 작성한다.
- 출력 계약: 작동요인 최종 본문만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 성과 달성에 기여한 설계·집행·환경 요인 추출
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 작동요인</summary>

````text
[작성 대상]
VI. 결론 2. 작동요인을 작성한다.

[참고할 입력]
- prior_analysis_sections: 성과달성도와 기준별 평가결과.
- reference_corpus: 성공 요인, 협력 구조, 현지 수요, 사업관리 관련 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 작동요인은 사업 성과에 긍정적으로 기여한 설계·수행·협력·환경 요인을 정리한다.
2. 단순 성과 나열이 아니라 왜 작동했는지를 설명한다.
3. 앞 섹션의 근거와 충돌하지 않게 작성한다.
4. 확인되지 않은 성공 요인은 만들지 않는다.
5. 최종 보고서 본문으로 작성한다.

[출력]
작동요인 최종 본문만 반환한다.
````

</details>

### 24. 비작동요인 (nonworking-factors)

- 원본 파일: `prompts/Section24_비작동요인.py`
- 작성 대상: VI. 결론 2. 비작동요인을 작성한다.
- 출력 계약: 비작동요인 최종 본문만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 미달성 지표, 변경요청, 지연, 리스크, 증빙공백 추출
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 비작동요인</summary>

````text
[작성 대상]
VI. 결론 2. 비작동요인을 작성한다.

[참고할 입력]
- prior_analysis_sections: 성과달성도와 기준별 평가결과.
- reference_corpus: 지연, 미달, 운영상 제약, 설계상 한계 관련 근거.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 비작동요인은 사업 성과를 제한한 설계·수행·환경 요인을 정리한다.
2. 책임 추궁식 표현보다 개선 가능한 구조적 원인 중심으로 쓴다.
3. 앞 섹션에서 확인된 한계와 연결하되, 같은 문장을 반복하지 않는다.
4. 근거 없는 비판은 쓰지 않는다.
5. 최종 보고서 본문으로 작성한다.

[출력]
비작동요인 최종 본문만 반환한다.
````

</details>

### 25. 변화이론 분석 (theory)

- 원본 파일: `prompts/Section25_변화이론_분석.py`
- 작성 대상: VI. 결론 2. 변화이론 분석을 작성한다.
- 출력 계약: 변화이론 분석 최종 본문만 반환한다.
- 참조 평가기준: relevance, effectiveness
- 파이프라인 메모:
  - 투입-활동-산출-성과 경로와 작동/비작동 요인 연결
- 추가 증빙 데이터:
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 변화이론 분석</summary>

````text
[작성 대상]
VI. 결론 2. 변화이론 분석을 작성한다.

[참고할 입력]
- reference_corpus: 사업 설계, PDM, 성과자료, 평가결과, 인터뷰 등 변화 경로 검토 근거.
- prior_analysis_sections: 사업개요, 성과달성도, 기준별 평가결과, 작동/비작동요인.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 투입-활동-산출-성과-영향의 변화 경로를 정리하고, 각 단계가 어떻게 연결되었는지 분석한다.
2. 설계 당시의 핵심 가정이 실제 수행에서 유지되었는지 또는 약화되었는지 설명한다.
3. 단순 PDM 재작성에 그치지 말고, 평가결과를 바탕으로 변화 경로의 강점과 단절 지점을 분석한다.
4. 확인되지 않은 영향은 단정하지 않는다.
5. 최종 보고서 본문으로 작성한다.

[출력]
변화이론 분석 최종 본문만 반환한다.
````

</details>

### 26. 환류과제 (feedback)

- 원본 파일: `prompts/Section26_환류과제.py`
- 작성 대상: VI. 결론 3. 환류과제(제언)를 작성한다.
- 출력 계약: 환류과제 최종 텍스트만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - 비작동 요인과 리스크/지연/운영관리 자료를 실행 과제로 전환
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 환류과제</summary>

````text
[작성 대상]
VI. 결론 3. 환류과제(제언)를 작성한다.

[참고할 입력]
- prior_analysis_sections: 결론, 작동요인, 비작동요인, 변화이론 분석을 1차 근거로 사용한다.
- content_inputs.criteria: 기준별 점수와 개선 필요 지점.
- reference_corpus: 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, 사업변경·운영관리·기자재·인력 관련 근거.
- sample_reference_for_this_section: 제언 표의 구분/제언/이해관계자 분리 방식과 문체.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 샘플 보고서의 제언 표처럼 구분, 제언, 이해관계자 중심으로 작성한다.
2. 구분은 사업모델 변경제언, 사업관리 개선제언, 개발환경 및 개입 특성상의 구조적 한계 분석 제언 중에서 고른다.
3. 제언은 관찰된 문제를 반복하지 말고 이해관계자가 실행할 수 있는 조치와 산출물로 쓴다.
4. 이해관계자는 코이카 경영진, 코이카 사업 관계자, 코이카 사업 수행파트너, 수원국/수원기관, 사업의 성과관리·평가전문가 등으로 구체화한다.
5. 각 항목은 반드시 '구분:', '제언:', '이해관계자:', '선정 사유:', '후속 확인자료:' 필드를 포함한다.
6. 근거 없는 과제나 일반론적 권고는 피하고, 앞선 분석 또는 참고 문서명/evidenceName에 기반해 작성한다.

[출력]
환류과제 최종 텍스트만 반환한다.
````

</details>

### 27. 교훈 (lessons)

- 원본 파일: `prompts/Section27_교훈.py`
- 작성 대상: VI. 결론 3. 교훈을 작성한다.
- 출력 계약: 교훈 최종 텍스트만 반환한다.
- 참조 평가기준: relevance, coherence, effectiveness, efficiency, sustainability
- 파이프라인 메모:
  - FAQ와 샘플 보고서 문체를 참조해 후속사업 체크리스트형 교훈 작성
- 추가 증빙 데이터:
  - relevance: 예비/기획조사 결과보고서 및 기초조사서 (Baseline Survey)
  - relevance: 수혜자 및 이해관계자 수요조사서 (취약계층 분석 포함)
  - relevance: 사업개요서 또는 사업요청서 (PCP)
  - relevance: 협력국 국가개발전략 또는 부문별 정책 문서 (예: 국가보건전략)
  - relevance: 한국 정부/KOICA의 국별협력전략(CPS/CAS) 및 분야별 전략 문서
  - relevance: 집행계획서 및 최신 PDM (Project Design Matrix)
  - relevance: 변화이론(ToC) 도식도 및 문제나무 분석 자료
  - relevance: 부속서류: 이해관계자 간 역할 분담 협약서(MoU) 또는 ROD(협의의사록)
  - relevance: 정기 모니터링 보고서 (상황 변화 인지 및 대응 기록)
  - relevance: 사업 변경요청서(Change Log) 및 운영위원회(JSC) 의사결정 회의록
  - coherence: 유사 사업 및 타 공여 개입 맵 (Mapping 자료)
  - coherence: 타 공여자, 수원국 정부 및 민간 개입과의 조정 회의록 및 업무협약서(MoU)
  - coherence: 기존 유사사업 평가보고서 (중복 회피 및 시너지 창출 근거용)
  - coherence: 이해관계자 간 상호보완 및 역할분담(RACI) 명시 문서
  - coherence: 운영위원회(JSC) 등 협의체 참여 횟수 및 공동 의사결정 회의록
  - coherence: 국내 타 기관 및 KOICA 타 사업과의 협의 기록
  - coherence: 인권, 젠더, 환경 등 세이프가드 체크리스트 및 준수 근거 문서
  - coherence: 국제규범(SDGs 등) 및 기준 정합성 관련 평가 지침서
  - coherence: 중복·충돌 이슈 발생 건수 및 해소 상태를 기록한 변경 관리 내역
  - effectiveness: 최신 PDM 및 성과지표 실적표
  - effectiveness: 산출물 완료보고서 및 활동별 결과보고서
  - effectiveness: 교육·서비스·시설·장비 제공 실적 자료
  - effectiveness: 기준선/종료선 조사자료 (Baseline/Endline)
  - effectiveness: 수혜자 만족도 조사 및 현장점검 기록
  - effectiveness: 성과 기여도 분석 및 외부요인 검토 메모
  - effectiveness: 성별·지역별·취약계층 분리 통계
  - effectiveness: 사회적 소외계층 참여자 명단 및 지원 실적
  - effectiveness: 수혜자 인터뷰 또는 사례 기록
  - efficiency: 예산 집행내역 및 집행률 분석표
  - efficiency: 예산 변경 내역 및 승인 문서
  - efficiency: 단가 비교 또는 비용 적정성 검토 자료
  - efficiency: 사업 일정표 및 마일스톤 이행 현황
  - efficiency: 조달 계획, 입찰·계약 문서
  - efficiency: 지연 사유 및 시정조치 기록
  - efficiency: 투입 대비 산출 분석표
  - efficiency: 인력 투입 계획 및 활동별 투입 기록
  - efficiency: 주요 활동 간 연계·조정 회의록
  - sustainability: 운영·유지관리 계획
  - sustainability: 지방정부 또는 파트너 기관 예산 확약서
  - sustainability: 인수인계 문서 및 운영 매뉴얼
  - sustainability: 현지 인력 역량강화 계획 및 교육 결과
  - sustainability: 리스크·위기대응 계획
  - sustainability: 운영 담당 조직의 역할분담 문서
  - sustainability: 정책·제도 반영 또는 공식 승인 문서
  - sustainability: 지역사회 참여 및 수용성 확인 자료
  - sustainability: 장기 재원조달 또는 수익모델 검토 자료

<details>
<summary>실제 EDITOR_PROMPT 전문 보기: 교훈</summary>

````text
[작성 대상]
VI. 결론 3. 교훈을 작성한다.

[참고할 입력]
- prior_analysis_sections: 작동요인, 비작동요인, 환류과제, 변화이론 분석, 결론을 1차 근거로 사용한다.
- content_inputs.criteria: 기준별 평가결과와 개선 필요 지점.
- reference_corpus: 연차점검 보고서, 종료/최종보고서, 인터뷰·현장조사, PDM·성과관리 자료, 운영관리·기자재·인력 관련 근거.
- sample_reference_for_this_section: 작동요인/비작동요인에서 교훈을 도출하는 방식과 문체.
- previous_text: 현재 양식과 문체.
- user_request: 사용자가 직접 입력한 수정 요청.

[작성 규칙]
1. 작동요인은 확산 가능한 설계·수행 원칙으로, 비작동요인은 사전 점검·위험관리 교훈으로 전환한다.
2. 특정 사건 나열로 끝내지 말고 후속 유사 사업에서 재사용할 수 있는 판단 기준으로 쓴다.
3. 각 항목은 반드시 '교훈 N. (관찰사항 제목)', '교훈 내용:', '분야/일반 구분:', '이전년도 교훈 중복 여부:', '체크리스트 질문:' 필드를 포함한다.
4. 분야/일반 구분에는 일반 또는 분야만 쓰고, 이전년도 교훈 중복 여부에는 신규 또는 중복(연도/분야)처럼 짧게 쓴다.
5. 체크리스트 질문은 M&E 단계에서 바로 점검 가능한 질문 1문장으로 쓴다.
6. 샘플 문장을 복사하지 말고 현재 사업의 앞선 분석과 참고자료를 종합해 새로 작성한다.

[출력]
교훈 최종 텍스트만 반환한다.
````

</details>
