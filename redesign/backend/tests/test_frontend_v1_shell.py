from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def assembled_shell():
    return (ROOT / 'frontend/index.html').read_text(encoding='utf-8') + '\n<style>' + (ROOT / 'assets/app-styles.css').read_text(encoding='utf-8') + '</style>\n<script>' + (ROOT / 'assets/app-shell.js').read_text(encoding='utf-8') + '</script>'


def api_source():
    return '\n'.join(p.read_text(encoding='utf-8') for p in sorted((ROOT / 'redesign/backend/kodame_intake/api').glob('*.py')))


def test_separate_files_v1_shell_is_the_deployed_index() -> None:
    dockerfile = (ROOT / "redesign" / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    html = assembled_shell()

    assert "COPY frontend/index.html /usr/share/nginx/html/index.html" in dockerfile
    assert "COPY assets/app-controller.js /usr/share/nginx/html/assets/app-controller.js" not in dockerfile
    assert '<script src="assets/app-controller.js' in html
    assert "COPY assets /usr/share/nginx/html/assets" in dockerfile
    assert "VIEW_ONLY_TEST8_SNAPSHOT" not in html
    assert "window.fetch = async" not in html


def test_v1_report_toolbar_keeps_live_export_actions() -> None:
    html = assembled_shell()
    required_ids = (
        'id="aiPrompt"',
        'id="rhwpPreview"',
        'id="hwpxExport"',
        'id="presentationExport"',
        'id="presentationProgress"',
    )
    for required_id in required_ids:
        assert html.count(required_id) == 1
    assert html.index('id="hwpxExport"') < html.index('id="presentationExport"')
    assert 'src="assets/app-controller.js' in html


def test_v1_brand_and_navigation_use_k_odame_names() -> None:
    html = assembled_shell()
    assert "K-ODAME v2.4" in html
    assert "오다:ON" not in html
    for label in (
        "증빙자료",
        "자료 업로드",
        "PDM 증빙",
        "DAC 증빙",
        "증빙 충족도",
        "성과 관리",
        "사업 개요",
        "성과지표 모니터링",
        "성과 리스크 예측 및 개선권고",
        "종료평가 준비도",
        "DAC 평가진단",
        "분석 결과",
        "보고서 자동작성",
    ):
        assert label in html
    assert "#/evidence/coverage" in html
    assert 'id="v-ev-coverage"' in html


def test_v1_live_layer_calls_current_report_apis() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    script += (ROOT / "assets" / "service-intake.js").read_text(encoding="utf-8")
    for endpoint in (
        "/api/v2/report/sections",
        "/api/v2/report/exports",
        "/api/v2/report/presentations",
        "/api/v2/evaluations",
        "/api/v2/intake/uploads",
    ):
        assert endpoint in script


def test_resolved_individual_report_sections_clear_stale_batch_error_message() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "const currentSectionsComplete = reportSections.length === 27" in script
    assert "const historicalErrorsResolved" in script
    assert "latestGenerationStatus = status" in script
    assert "if (latestGenerationStatus) renderGeneration(latestGenerationStatus);" in script
    assert "전체 보고서 생성 및 개별 보완 완료" in script
    assert "현재 27개 섹션이 모두 작성·보완되었습니다." in script


def test_dashboard_orders_scorecards_before_pdm_dac_insight_board() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "#v-dashboard .heroduo{order:1}" in html
    assert "#v-dashboard .daonbox{order:2}" in html
    assert ".insight-grid{display:grid;grid-template-columns:1fr 1fr" in html
    assert ".daonbox .avwrap{display:none!important}" in html
    assert "function renderDashboardInsights()" in script
    assert "PDM 관점" in script
    assert "DAC 관점" in script
    assert "#/project/gaps" in script
    assert "#/eval/results" in script


def test_dashboard_insights_are_short_prioritized_and_clickable() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    insight_renderer = script.split("function renderDashboardInsights()", 1)[1].split("function renderDashboard(data)", 1)[0]
    assert "function compactInsightText" in script
    assert ".slice(0, 3)" in insight_renderer
    assert "risk.recommendations" in insight_renderer
    assert "question.action_items" in insight_renderer
    assert 'data-go="${item.route}"' in insight_renderer
    assert "white-space:nowrap;overflow:hidden;text-overflow:ellipsis" in html


def test_empty_project_dashboard_clears_demo_metrics() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()

    assert "is_empty = total == 0 and not run and not overview_row" in backend
    assert '"code": "empty_project"' in backend
    assert "if (isEmpty)" in script
    assert "등록된 성과지표가 없습니다." in script
    assert "DAC 평가진단을 실행하면 종합점수가 표시됩니다" in script
    assert "renderDashboard({ is_empty: true, project: {} });" in script


def test_dashboard_does_not_show_empty_score_as_slash_twenty() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    dashboard_card = html.split('<div class="herocard dac">', 1)[1].split('</div>\n        </div>', 1)[0]
    assert "평가 전" in dashboard_card
    assert "17.5<small>/20</small>" not in dashboard_card
    assert "function syncDashboardDac(data)" in script
    assert "`${formatDacScore(overall.score)}<small>/20</small>`" in script
    assert "esc(tr('ui.dashboard.not_evaluated', '평가 전'))" in script
    assert "dacValue.innerHTML = '-<small>/20</small>'" not in script


def test_dashboard_dac_uses_the_same_evaluation_result_as_dac_diagnosis() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    evaluation_renderer = script.split("function renderEvaluation(data)", 1)[1].split("async function refreshEvaluation()", 1)[0]
    slot_renderer = script.split("function renderDacSlots()", 1)[1].split("function renderRecentUploads()", 1)[0]
    dashboard_renderer = script.split("function syncDashboardDac(data)", 1)[1].split("function renderEvaluation", 1)[0]
    assert "latestEvaluationData = data" in evaluation_renderer
    assert "syncDashboardDac(latestEvaluationData)" in evaluation_renderer
    assert "formatDacScore(data.overall.score)" in evaluation_renderer
    assert "overall.formula" in dashboard_renderer
    assert "#/eval/results" in dashboard_renderer
    assert "dacReady" not in slot_renderer


def test_empty_project_hides_demo_content_in_all_data_menus() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    for view_id in (
        "v-ev-pdm",
        "v-ev-dac",
        "v-ev-coverage",
        "v-proj-overview",
        "v-proj-indicators",
        "v-proj-gaps",
        "v-eval-overview",
        "v-eval-board",
        "v-eval-results",
        "v-eval-report",
    ):
        assert f"'{view_id}'" in script
    assert "function setEmptyProjectViews(isEmpty)" in script
    assert "child.dataset.emptyProjectHidden = 'true'" in script
    assert "projectIsEmpty ? { criteria: [], items: [] } : intake.slots" in script


def test_project_identity_uses_live_data_and_neutral_initial_markup() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    initial_markup = html.split("<script>", 1)[0]

    assert "베트남 뚜옌꽝성 라이프케어 사업" not in initial_markup
    assert 'data-viewfile="라이프케어_PDM.hwp"' not in initial_markup
    assert "currentProjectIdentity" in script
    assert "#drawer .fileinfo" in script
    assert "현재 선택한 사업" in script


def test_pdm_missing_optional_counter_does_not_abort_rendering() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "const pdmEvidenceCount = byId('pdmEvCnt');" in script
    assert "if (pdmEvidenceCount) pdmEvidenceCount.textContent" in script
    assert "byId('pdmEvCnt').textContent" not in script


def test_dac_progress_uses_dashboard_workflow_instead_of_demo_steps() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "function renderWorkflowSteps(steps)" in script
    assert "renderWorkflowSteps(data.steps || [])" in script
    assert "step.percent" in script
    assert "step.hint" in script


def test_live_shell_disables_stale_browser_cache() -> None:
    html = assembled_shell()
    nginx = (ROOT / "redesign" / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert 'http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate"' in html
    assert "location = /assets/app-controller.js" in nginx
    assert 'add_header Cache-Control "no-store, no-cache, must-revalidate" always;' in nginx


def test_empty_bootstrap_project_does_not_restore_legacy_project_information() -> None:
    backend = api_source()

    assert '"business_name": value("project_name", "")' in backend
    assert '"name": project_row["name"] if project_row else "새 ODA 평가 프로젝트"' in backend
    assert '"business_name": value("project_name", "")' in backend


def test_uploads_are_automatically_assigned_without_manual_review_ui() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    worker = (ROOT / "redesign" / "backend" / "kodame_intake" / "worker.py").read_text(encoding="utf-8")
    database = (ROOT / "redesign" / "backend" / "kodame_intake" / "db.py").read_text(encoding="utf-8")

    assert "it.badge&&pendingCount>0" in html
    assert "수동 배정 필요 리스트" not in html
    assert "request('/api/v2/intake/suggestions')" not in script
    assert "window.LIVE_PENDING_COUNT = 0" in script
    assert "review_status='approved',reviewed_at=now()" in worker
    assert "WHERE review_status='pending'" in database


def test_auto_assignment_copy_uses_formal_declarative_tone() -> None:
    html = assembled_shell()

    assert "문서의 역할과 사실을 정리하고 PDM · DAC · 보고서에 연결합니다." in html
    assert "알아서 배정해요" not in html
    assert "중복 배정해요" not in html


def test_explicit_login_always_opens_dashboard() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "function enterSession(data, forceDashboard = false)" in script
    assert "}), true);" in script
    assert "forceDashboard ? '#/dashboard'" in script
    assert "window.ServiceAuth.create({request, ready:enterSession, state:setAuthView})" in script


def test_project_overview_shows_plan_source_and_keeps_separate_latest_pdm() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()
    pdm = (ROOT / "redesign" / "backend" / "kodame_intake" / "pdm_monitoring.py").read_text(encoding="utf-8")

    assert "pdm_source_document" in backend
    assert "ORDER BY p.created_at DESC LIMIT 1" in backend
    assert "project_plan_source_document" in backend
    renderer = script.split("function renderProjectOverview(data)", 1)[1].split("async function refreshProjectOverview", 1)[0]
    assert "data.project_plan_source_document" in renderer
    assert "data.pdm_source_document" not in renderer
    assert "사업계획서 근거" in renderer
    assert "removeAttribute('data-i')" in renderer
    assert "uniqueSources.slice" not in script
    assert "-int(item.get(\"queue_position\") or 0)" in pdm


def test_project_overview_pdm_omits_monitoring_only_status_and_evidence_columns() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    overview_table = html.split('<tbody id="pdmBody">', 1)[0].rsplit('<table class="pdmtbl">', 1)[1]
    assert "상태" not in overview_table
    assert "증빙" not in overview_table
    assert 'colspan="5"' in script
    tier_row = script.split("const tierRows =", 1)[1].split("const sourceCells =", 1)[0]
    assert "documents.length" not in tier_row
    assert "pdmstat" not in tier_row


def test_project_overview_removes_duplicate_logic_flow_and_adds_pdm_support_rows() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert 'id="logicFlow"' not in html
    assert "PDM 논리구조</h3>" not in html
    renderer = script.split("function renderPdmData(data)", 1)[1].split("function renderProjectOverview", 1)[0]
    assert "sourceCells.activities" in renderer
    assert "sourceCells.inputs" in renderer
    assert "Activities(활동)" not in renderer  # label is composed from separate semantic fields
    assert "label: 'Activities', ko: tr('ui.overview.activity', '활동')" in renderer
    assert "label: 'Inputs', ko: tr('ui.overview.input', '투입')" in renderer


def test_monitoring_table_uses_pdm_tiers_and_collapsed_evidence_counts() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    renderer = script.split("function renderPerformanceIndicators(data)", 1)[1].split("function renderPdmData(data)", 1)[0]

    assert "groupPerformanceIndicators(indicators)" in renderer
    assert '<th>성과 구분</th>' in renderer
    assert '<colgroup>' in renderer
    assert "<th>프로그램</th>" not in renderer
    assert "최신 PDM 객관적 검증지표" in renderer
    assert "monitoringEvidenceFold(item)" in renderer
    assert '<details class="evidence-fold monitor-evidence">' in script
    assert "산출근거 ${evidenceCount}건 · 연결문서 ${documents.length}건" in script
    assert '<details class="evidence-fold monitor-evidence" open' not in script


def test_dashboard_and_monitoring_share_threshold_achievement_bars() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    renderer = script.split("function renderPerformanceIndicators(data)", 1)[1].split("function renderPdmData(data)", 1)[0]

    assert "function achievementBarMeta(rate)" in script
    assert "numeric >= 90 ? 'g' : numeric >= 70 ? 'w' : 'r'" in script
    assert "function achievementBarMarkup(rate, label)" in script
    assert 'class="achievement-cell">${achievementBarMarkup(item.achievement_rate, item.achievement_label)}' in renderer
    assert 'class="dash-kpi-row"' in script
    assert 'class="dash-kpi-name"' in script
    assert 'class="dash-kpi-chart">${achievementBarMarkup(item.achievement_rate, item.achievement_label)}' in script
    assert ".achievement-bar .pbar{height:9px" in html
    assert ".achievement-cell{min-width:156px}" in html
    assert ".monitor-evidence summary{margin-top:0" in html and "white-space:nowrap" in html
    assert ".dash-kpi-row{display:grid" in html


def test_dashboard_indicator_list_expands_from_five_to_all_pdm_indicators() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert 'id="dashIndToggle"' in html
    assert "let dashboardIndicatorsExpanded = false;" in script
    assert "function renderDashboardIndicatorList(indicators)" in script
    assert "dashboardIndicatorsExpanded ? ordered : ordered.slice(0, 5)" in script
    assert "groupPerformanceIndicators(visible)" in script
    assert 'class="dash-kpi-group-head"' in script
    assert '${esc(tier.label)}' in script
    assert ".dash-kpi-group-head{display:flex" in html
    assert "'전체 {count}개 펼치기 ▾', { count: ordered.length }" in script
    assert "'성과지표 접기 ▴'" in script
    assert "renderDashboardIndicatorList(intake.pdm?.performance_indicators || [])" in script


def test_performance_risks_are_grouped_and_open_full_detail_modal() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    renderer = script.split("function renderPerformanceIndicators(data)", 1)[1].split("function renderPdmData(data)", 1)[0]

    assert 'id="riskDetailModal"' in html
    assert "riskGroups = groupPerformanceIndicators(risks)" in renderer
    assert 'class="risk-group"' in renderer
    assert 'data-risk-open="${esc(id)}"' in renderer
    assert "function openRiskDetail" in script
    assert "function closeRiskDetail" in script
    for label in ("위험 분석", "원인", "전망", "개선권고", "추가 필요 근거"):
        assert label in script


def test_performance_refresh_renders_detailed_ai_risk_analysis() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()

    assert "AI가 목표·실적·달성도·산출근거를 종합" in html
    for label in ("위험 분석", "원인", "전망", "개선권고", "추가 근거"):
        assert label in script
    assert "증빙 내용·성과 분석 중" in script
    assert '"/api/v2/pdm/refresh/status"' in backend
    jobs = (ROOT / "redesign/backend/kodame_intake/pdm_jobs.py").read_text(encoding="utf-8")
    assert "refresh_pdm_model(analyze_risks=True, refresh_run_id=run_id, analysis_plan=row['analysis_plan'])" in jobs


def test_performance_risk_cards_do_not_force_horizontal_scroll() -> None:
    html = assembled_shell()

    assert ".gapgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in html
    assert ".gapgrid>.panel{min-width:0;max-width:100%;overflow:hidden}" in html
    assert "#v-proj-gaps{min-width:0;overflow-x:hidden}" in html
    assert "overflow-wrap:anywhere" in html


def test_evaluation_results_exclude_impact() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()

    evaluation_endpoint = backend.split('@router.get("/api/v2/evaluations")', 1)[1].split('@router.get("/api/v2/evaluations/status")', 1)[0]
    assert "impact_docs" not in evaluation_endpoint
    assert '"id": "impact"' not in evaluation_endpoint
    assert "DAC 5개 기준의 질문별 1~4점 평균 합산" in evaluation_endpoint
    assert "filter((item) => item.id !== 'impact')" in script


def test_evaluation_evidence_is_collapsed_until_expanded() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "function evidenceFold(documents)" in script
    assert '<details class="evidence-fold">' in script
    assert "증빙 자료 ${items.length}건 펼치기" in script
    assert ".evidence-fold[open] .fold-closed{display:none}" in html
    assert ".evidence-fold:not([open])>.csec-foot{display:none!important}" in html
    assert "<details class=\"evidence-fold\" open" not in script


def test_admin_console_and_account_menu_permissions_are_wired() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()
    database = (ROOT / "redesign" / "backend" / "kodame_intake" / "db.py").read_text(encoding="utf-8")

    assert 'id="v-admin"' in html
    assert 'id="adminAccountRows"' in html
    assert "window.KODAME_IS_ADMIN" in script
    assert "/api/v2/admin/accounts" in script
    assert '@router.get("/api/v2/admin/accounts")' in backend
    assert "require_admin(request.state.auth)" in backend
    assert "menu_permissions jsonb" in database
    assert "for number in (range(1, 11) if allow_seed else ())" in database
    assert "hash_password(BOOTSTRAP_ADMIN_PASSWORD, validate=False)" in database
    assert 'hash_password(f"KODAME-Test{number:02d}!2026")' in database


def test_report_access_uses_only_admin_console_permission() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()

    assert "function hasMenuPermission(menuKey)" in html
    assert "hasMenuPermission('evaluation_report')" in html
    assert "보고서 자동작성은 발주처·감리자 권한입니다" not in html
    assert "if(CURRENT_ROLE==='수행자')" not in html
    assert "role==='수행자'" not in html
    assert "프로젝트 역할과 관계없이 이 설정이 적용됩니다." in script
    assert "window.hasMenuPermission?.('evaluation_report')" in script
    assert 'request.url.path.startswith(REPORT_API_PREFIX)' in backend
    assert 'has_menu_permission(session, "evaluation_report")' in backend


def test_hash_refresh_and_reported_screen_regressions_are_guarded() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "if (typeof window.route === 'function') window.route();" in script
    assert "자료 목록을 불러오지 못했습니다." in script
    assert "화면 렌더링 실패" in script
    assert "아직 생성된 분석 결과가 없습니다." in script
    assert 'id="evalPeriodValue"' in html
    assert 'id="evalScopeText"' in html
    assert "business_name: value('project_name'), period: value('period')" in script
    assert "word-break:keep-all" in html
    assert 'src="assets/app-controller.js?v=' in html


def test_sample_forms_download_real_backend_files() -> None:
    html = assembled_shell()
    backend = api_source()

    assert "evaluation-report-hwpx" in html
    assert "/api/v2/samples/templates/${encodeURIComponent(f[3])}/download" in html
    assert "다운로드를 시작했습니다 (데모)" not in html
    assert '@router.get("/api/v2/samples/templates/{template_id}/download")' in backend
    assert '"evaluation-report-hwpx": "5-1. 종료평가 결과보고서 양식.hwpx"' in backend
    assert "root not in path.parents or not path.is_file()" in backend


def test_project_creation_and_database_backed_languages_are_wired() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    backend = api_source()
    database = (ROOT / "redesign" / "backend" / "kodame_intake" / "db.py").read_text(encoding="utf-8")

    assert 'id="adminCreateProject"' in html
    assert 'id="projectLanguageChecks"' in html
    assert 'id="projectDefaultLocale"' in html
    assert 'id="projectAccountChecks"' in html
    assert "renderLangSw').innerHTML" not in html
    assert "renderLangOpt()" not in html
    assert "window.configureProjectLanguages" in html
    assert "/api/v2/admin/projects" in script
    assert "/api/v2/project/i18n" in script
    assert '@router.post("/api/v2/admin/projects"' in backend
    assert '@router.get("/api/v2/project/i18n")' in backend
    assert "supported_locales text[]" in database
    assert "CREATE TABLE IF NOT EXISTS project_translations" in database
    assert "preferred_locale text" in database


def test_full_report_request_is_nonblocking_and_score_helper_uses_live_average() -> None:
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")

    assert "window.confirm('27개 섹션" not in script
    assert "timeoutMs: 15000" in script
    assert "전체 보고서 생성 요청을 접수했습니다." in script
    assert "scored.length === 5 ? `5대 기준 평균 ${average}점`" in script
    assert "나머지 판정보류" in script
    assert "} else {\n        await refreshReportSections(activeReportPart);" in script


def test_upload_labels_and_header_role_are_project_localized() -> None:
    html = assembled_shell()
    script = (ROOT / "assets" / "app-controller.js").read_text(encoding="utf-8")
    translations = (ROOT / "redesign" / "backend" / "kodame_intake" / "translations.py").read_text(encoding="utf-8")

    for key in ("files-common", "files-once", "all-upload-docs"):
        assert f'data-i="{key}"' in html
        assert f'"ui.{key}"' in translations
    assert "localizedRoleName" in script
    for key in ("ui.role.admin", "ui.role.owner", "ui.role.editor", "ui.role.viewer"):
        assert key in translations
