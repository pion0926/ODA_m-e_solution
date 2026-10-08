(function () {
  'use strict';
  if (!window.ReportSectionFlow?.createFlow || !window.ReportSectionPreview?.create || !window.ServiceAdminUI?.create || !window.ServiceAuth?.create) {
    window.reportModuleUnavailable?.();
    return;
  }

  const byId = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
  const downloadUrl = (id) => `/api/v2/intake/jobs/${encodeURIComponent(id)}/download`;
  const roleNames = { owner: '발주처', editor: '수행자', viewer: '수행자' };
  const reportNames = { draft: '초안', generating: '생성 중', failed: '오류', empty: '비어 있음' };
  const PRESENTATION_SLIDE_COUNT = 15;
  const criterionNames = {
    relevance: '적절성', coherence: '일관성', effectiveness: '효과성',
    efficiency: '효율성', sustainability: '지속가능성'
  };

  let authMode = 'login';
  let started = false;
  let currentRole = 'viewer';
  const localizedRoleName = () => {
    const key = window.KODAME_IS_ADMIN ? 'admin' : currentRole === 'editor' ? 'viewer' : currentRole;
    const fallback = window.KODAME_IS_ADMIN ? '관리자' : (roleNames[currentRole] || currentRole);
    return typeof window.projectText === 'function' ? window.projectText(`ui.role.${key}`, fallback) : fallback;
  };
  window.refreshLiveLocalizedLabels = () => {
    const label = localizedRoleName();
    if (byId('roleName')) byId('roleName').textContent = label;
    if (byId('roleAv')) byId('roleAv').textContent = label.charAt(0);
    for (const id of ['logout', 'compactLogout']) if (byId(id)) byId(id).textContent = ({ko:'로그아웃',en:'Log out',vi:'Đăng xuất',ru:'Выйти',uz:'Chiqish'})[window.KODAME_LOCALE || 'ko'] || 'Log out';
  };
  let reportSections = [];
  let activeReportPart = null;
  const reportFlow = window.ReportSectionFlow.createFlow();
  const reportInstructions = new Map();
  const reportRenderTimes = [];
  let sectionLoadPending = null;
  const sectionPreview = window.ReportSectionPreview.create({ request });
  let reportBatchSubmitting = false;
  let reportLifecycle = null;
  let reportLifecycleCheckedAt = 0;
  let reportLifecyclePromise = null;
  let allowProjectReload = false;
  window.reportSectionDiagnostics = () => ({ sections: reportFlow.diagnostics(), renderMs: [...reportRenderTimes] });
  let intake = { jobs: [], slots: { criteria: [], items: [] }, pdm: { tiers: [], assignments: [], performance_indicators: [] } };
  let projectOverview = null;
  let dacCoverage = { filled: 0, total: 0, assigned: 0 };
  let latestEvaluationData = { status: 'not_run', criteria: [], overall: null };
  let evaluationLoaded = false;
  let evaluationLoadError = '';
  let latestEvaluationStatus = null;
  let latestWorkflowSteps = [];
  let pdmCoverage = { filled: 0, total: 0, complete_tiers: 0, tier_total: 0 };
  let reportTimer = null;
  let generationTimer = null;
  let generationPollRevision = 0;
  let latestGenerationStatus = null;
  let exportTimer = null;
  let presentationTimer = null;
  let exportStarted = 0;
  let presentationStarted = 0;
  let evaluationWasActive = false;
  let fileFilter = 'all';
  let fileQuery = '';
  let fileShowAll = false;
  let uploadBusy = false;
  let uploadFailures = [];
  let intakeRefreshPromise = null;
  const foundationUpload = window.FoundationUpload.create({ request, escapeHtml: esc, refresh: refreshIntake, notify });
  window.ServiceReview?.create({request, escapeHtml:esc, notify});
  let projectIsEmpty = true;
  let adminAccounts = [];
  let adminProjects = [];
  let adminLanguages = {};
  let selectedAdminAccountId = null;
  let accountProjectChoices = [];
  const projectAI = window.ProjectAIUI.create({ request, escapeHtml: esc, refresh: refreshAdmin, notify });
  const serviceAdmin = window.ServiceAdminUI.create({ request, escapeHtml: esc, refresh: refreshAdmin,
    accounts: () => adminAccounts, projects: () => adminProjects,
    selected: (id) => id === undefined ? selectedAdminAccountId : (selectedAdminAccountId = id), notify });
  let currentProjectIdentity = {};
  const serviceScope = window.ServiceScope.create(showWorkspaceChanged);
  const sessionStartup = window.ServiceAuth.create({request, ready:enterSession, state:setAuthView});
  window.KODAME_REQUEST = request;
  let riskDetailItems = new Map();
  let riskModalTrigger = null;
  let dashboardIndicatorsExpanded = false;
  let localizedViewsBundle = null;
  let localizedViewsPromise = null;
  let localizedViewsRefreshTimer = null;

  const currentLocale = () => String(window.KODAME_LOCALE || document.documentElement.lang || 'ko').toLowerCase();
  function tr(key, fallback, variables = {}) {
    const template = typeof window.projectText === 'function'
      ? window.projectText(key, fallback)
      : (fallback || key);
    return String(template).replace(/\{([a-z_]+)\}/gi, (match, name) => (
      Object.prototype.hasOwnProperty.call(variables, name) ? String(variables[name]) : match
    ));
  }

  function localizedViewSignature(name, value) {
    if (!value) return '';
    if (name === 'dashboard') return JSON.stringify([
      value.document_count, value.processing_document_count, value.updated_at,
      value.workflow_status?.code, value.progress, value.alerts?.length
    ]);
    if (name === 'project_overview') return JSON.stringify([value.status, value.id, value.run_id, value.created_at]);
    if (name === 'pdm') return JSON.stringify([
      value.status, value.id, value.created_at, value.performance_indicators?.length,
      value.risk_analysis?.status, value.risk_analysis?.analyzed_count
    ]);
    if (name === 'evaluation') return JSON.stringify([value.status, value.run_id, value.completed_at]);
    return '';
  }

  function scheduleLocalizedViewsRefresh() {
    if (localizedViewsRefreshTimer || localizedViewsPromise) return;
    localizedViewsRefreshTimer = setTimeout(() => {
      localizedViewsRefreshTimer = null;
      refreshLocalizedProjectViews(currentLocale(), true).catch((error) => {
        console.error('변경된 화면 데이터 번역 갱신 실패', error);
      });
    }, 250);
  }

  function localizedView(name, fallback) {
    const translated = localizedViewsBundle?.locale === currentLocale()
      ? localizedViewsBundle.views?.[name]
      : null;
    if (translated) {
      if (localizedViewSignature(name, translated) !== localizedViewSignature(name, fallback)) {
        scheduleLocalizedViewsRefresh();
      }
      // Keep the last complete translation visible until the changed data has
      // been translated as one bundle. This prevents a mixed-language screen.
      return translated;
    }
    return fallback;
  }

  async function prepareLocalizedProjectViews(locale = currentLocale(), force = false) {
    const normalized = String(locale || 'ko').toLowerCase();
    if (!force && localizedViewsBundle?.locale === normalized && !['queued','running'].includes(localizedViewsBundle.translation_status)) return localizedViewsBundle;
    if (localizedViewsPromise?.locale === normalized) return localizedViewsPromise.promise;
    const promise = request(`/api/v2/project/i18n/views?locale=${encodeURIComponent(normalized)}`, { timeoutMs: 180000 })
      .finally(() => { if (localizedViewsPromise?.promise === promise) localizedViewsPromise = null; });
    localizedViewsPromise = { locale: normalized, promise };
    return promise;
  }

  async function applyLocalizedProjectViews(bundle) {
    if (!bundle?.views || bundle.locale !== currentLocale()) return;
    localizedViewsBundle = bundle;
    if (['queued','running'].includes(bundle.translation_status)) {
      clearTimeout(localizedViewsRefreshTimer);
      localizedViewsRefreshTimer=setTimeout(async()=>{localizedViewsRefreshTimer=null;try{await applyLocalizedProjectViews(await prepareLocalizedProjectViews(currentLocale(),true));}catch(e){notify(e.message);}},5000);
    }
    const views = bundle.views;
    if (views.dashboard?.project?.name) currentProjectIdentity.name = views.dashboard.project.name;
    if (views.dashboard) renderDashboard(views.dashboard);
    if (views.pdm) renderPdmData(views.pdm);
    if (views.evaluation) renderEvaluation(views.evaluation);
    if (views.project_overview) renderProjectOverview(views.project_overview);
  }

  async function refreshLocalizedProjectViews(locale = currentLocale(), force = false) {
    const bundle = await prepareLocalizedProjectViews(locale, force);
    if (String(locale).toLowerCase() === currentLocale()) await applyLocalizedProjectViews(bundle);
    return bundle;
  }

  window.prepareLocalizedProjectViews = prepareLocalizedProjectViews;
  window.applyLocalizedProjectViews = applyLocalizedProjectViews;
  window.refreshLocalizedProjectViews = refreshLocalizedProjectViews;

  const menuLabels = {
    dashboard: '대시보드', evidence_upload: '자료 업로드', evidence_pdm: 'PDM 증빙',
    evidence_dac: 'DAC 증빙', evidence_coverage: '증빙 충족도', project_overview: '사업 개요',
    project_indicators: '성과지표 모니터링', project_gaps: '성과 리스크·개선권고',
    evaluation_overview: '종료평가 준비도', evaluation_board: 'DAC 평가진단',
    evaluation_results: '분석 결과', evaluation_report: '보고서 자동작성'
  };

  const emptyProjectViewIds = [
    'v-ev-pdm', 'v-ev-dac', 'v-ev-coverage',
    'v-proj-overview', 'v-proj-indicators', 'v-proj-gaps',
    'v-eval-overview', 'v-eval-board', 'v-eval-results', 'v-eval-report'
  ];

  async function request(path, options = {}) {
    const { timeoutMs = 0, ...fetchOptions } = options;
    fetchOptions.headers = serviceScope.headers(path, fetchOptions.headers);
    const controller = timeoutMs > 0 && !fetchOptions.signal ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const response = await fetch(path, controller ? { ...fetchOptions, signal: controller.signal } : fetchOptions);
      let body = null;
      try { body = await response.json(); } catch (_) { /* empty response */ }
      serviceScope.check(path, response, body);
      if (!response.ok) {
        const detail = Array.isArray(body?.detail) ? body.detail.map((item) => `${(item.loc || []).filter((key) => key !== 'body').join('.')}: ${item.msg || '입력값 확인 필요'}`).join(' · ') : body?.detail;
        const error = new Error(detail || body?.error || `요청 실패 (${response.status})`);
        error.status = response.status;
        throw error;
      }
      return body;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('요청 접수 확인 시간이 초과되었습니다. 생성 상태를 다시 확인합니다.');
      throw error;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  function showWorkspaceChanged(problem) {
    if (byId('workspaceChangedDialog')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'workspaceChangedDialog'; dialog.className = 'service-account-dialog';
    dialog.setAttribute('aria-labelledby', 'workspaceChangedTitle');
    const retained = new Map(reportInstructions);
    if (byId('aiPrompt')?.value) retained.set(activeReportPart || '현재 수정 요청', byId('aiPrompt').value);
    const drafts = [...retained.entries()].filter(([, text]) => text.trim()).map(([part, text]) => `${reportSections.find(section => section.part_id === part)?.title || part}\n${text}`);
    dialog.innerHTML = `<h2 id="workspaceChangedTitle">작업 공간 확인이 필요합니다</h2><p>${esc(problem.message)}</p><p>프로젝트: <b>${esc(currentProjectIdentity.name || '관리자')}</b></p>${drafts.length ? '<p>아직 실행하지 않은 수정 요청은 아래에서 복사해 보관할 수 있습니다.</p><textarea aria-label="보관할 수정 요청" readonly style="width:100%;min-height:140px"></textarea>' : ''}<p>서버에 저장된 문서·평가·보고서는 유지됩니다.</p><button class="btn primary" type="button">${problem.status === 401 ? '로그인 화면 열기' : '현재 작업 공간 다시 열기'}</button>`;
    if (drafts.length) dialog.querySelector('textarea').value = drafts.join('\n\n');
    dialog.addEventListener('cancel', event => event.preventDefault());
    dialog.querySelector('button').onclick = () => { allowProjectReload = true; location.reload(); };
    document.body.appendChild(dialog); dialog.showModal();
  }

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else window.alert(message);
  }

  function replaceNode(id) {
    const node = byId(id);
    if (!node) return null;
    const clone = node.cloneNode(true);
    node.replaceWith(clone);
    return clone;
  }

  function detachDemoHandlers() {
    ['logout', 'uploadBtn', 'dropzone', 'spDrop', 'runBtn', 'runBtn2', 'seclist',
      'repGenAll', 'aiGen', 'fileSearch', 'fileMore', 'assignList', 'optcards',
      'fixList', 'daonFold', 'indRefresh']
      .forEach(replaceNode);
    document.querySelectorAll('.fchipb').forEach((button) => {
      const clone = button.cloneNode(true);
      button.replaceWith(clone);
    });
  }

  function setAuthMode(mode) {
    authMode = mode;
    const registering = mode === 'register';
    byId('nameField').hidden = !registering;
    byId('authIdentityLabel').textContent = registering ? '이메일' : '아이디 또는 이메일';
    byId('codeInput').placeholder = registering ? 'name@organization.org' : 'test1 또는 name@organization.org';
    byId('codeInput').type = registering ? 'email' : 'text';
    byId('authPassword').placeholder = registering ? '10자 이상' : '비밀번호';
    byId('authPassword').autocomplete = registering ? 'new-password' : 'current-password';
    byId('codeBtn').textContent = registering ? '계정 만들기' : '로그인';
    byId('authSwitch').textContent = registering ? '기존 계정으로 로그인' : '새 계정 만들기';
    byId('codeErr').textContent = '';
  }

  async function authenticate() {
    const button = byId('codeBtn');
    button.disabled = true;
    byId('codeErr').textContent = '';
    try {
      const payload = {
        email: byId('codeInput').value.trim(),
        password: byId('authPassword').value
      };
      if (authMode === 'register') payload.display_name = byId('authName').value.trim();
      const endpoint = authMode === 'register' ? '/api/v2/auth/register' : '/api/v2/auth/login';
      enterSession(await request(endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      }), true);
    } catch (error) {
      byId('codeErr').textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = authMode === 'register' ? '계정 만들기' : '로그인';
    }
  }

  function setProjectIdentity(data) {
    const project = data.project || {};
    const incomingName = project.name || project.project_name;
    currentProjectIdentity = Object.fromEntries(Object.entries({
      ...currentProjectIdentity,
      ...project,
      name: project.id || !currentProjectIdentity.name ? (incomingName || currentProjectIdentity.name) : currentProjectIdentity.name
    }).filter(([, value]) => value != null && value !== ''));
    const projectName = currentProjectIdentity.name || '배정된 사업';
    const chip = document.querySelector('#projChip .pn');
    if (chip) chip.textContent = projectName;
    byId('reportProjectTitle').textContent = `보고서 자동작성 · ${projectName}`;
    const drawerInfo = document.querySelector('#drawer .fileinfo');
    if (drawerInfo) {
      const businessName = currentProjectIdentity.business_name || projectName;
      const region = [currentProjectIdentity.country, currentProjectIdentity.location].filter(Boolean).join(' · ');
      const operator = [currentProjectIdentity.donor, currentProjectIdentity.implementer].filter(Boolean).join(' · ');
      drawerInfo.innerHTML = [
        ['사업명', businessName], ['기간', currentProjectIdentity.period || '자료 분석 전'],
        ['예산', currentProjectIdentity.budget || '자료 분석 전'], ['국가 · 지역', region || '자료 분석 전'],
        ['시행', operator || '자료 분석 전'], ['평가 단계', currentProjectIdentity.stage || '종료평가 준비']
      ].map(([label, value]) => `<div class="k">${esc(label)}</div><div>${esc(value)}</div>`).join('');
    }
    renderProjectChoices();
    setEvaluationProjectInfo(projectName, currentProjectIdentity.period || projectOverview?.overview?.period?.text);
    document.title = `K-ODAME v${document.querySelector('meta[name="application-version"]')?.content || '2.3'} · ${projectName}`;
  }

  function renderProjectChoices() {
    const target = byId('projList');
    if (!target) return;
    const choices = accountProjectChoices.length ? accountProjectChoices : currentProjectIdentity.id ? [currentProjectIdentity] : [];
    target.innerHTML = choices.map((project) => `<button type="button" class="projrow ${project.id === currentProjectIdentity.id ? 'cur' : ''}" data-select-project="${esc(project.id)}" ${project.id === currentProjectIdentity.id ? 'disabled' : ''} style="width:100%;text-align:left"><span style="flex:1;min-width:0"><span class="pt2">${esc(project.name)}</span><span class="pm2" style="display:block">${project.id === currentProjectIdentity.id ? '현재 선택한 사업' : '이 사업으로 전환'}</span></span>${project.id === currentProjectIdentity.id ? '<span class="tag i">현재</span>' : ''}</button>`).join('') || '<div class="empty">배정된 프로젝트가 없습니다. 관리자가 프로젝트를 배정하면 여기에 표시됩니다.</div>';
  }

  async function refreshProjectChoices() {
    try { accountProjectChoices = (await request('/api/v2/account/projects', { timeoutMs: 15000 })).projects || []; renderProjectChoices(); }
    catch (error) { console.error('프로젝트 목록 조회 실패', error); }
  }

  async function refreshProjectLanguages() {
    try {
      const data = await request('/api/v2/project/i18n');
      if (typeof window.configureProjectLanguages === 'function') window.configureProjectLanguages(data);
      await refreshLocalizedProjectViews(data.preferred_locale || data.default_locale || 'ko');
    } catch (error) { console.error('프로젝트 언어 설정을 불러오지 못했습니다.', error); }
  }

  function setEvaluationProjectInfo(projectName, period) {
    const safeName = String(projectName || '배정된 사업');
    const safePeriod = String(period || '사업 전 기간');
    const periodNode = byId('evalPeriodValue');
    const scopeNode = byId('evalScopeText');
    if (periodNode) periodNode.textContent = `${safePeriod} · 사업 전 기간`;
    if (scopeNode) scopeNode.innerHTML = `본 평가는 <b style="color:var(--ink)">${esc(safeName)}</b>의 성과를 OECD DAC 5대 기준으로 판단하고, KOICA 평가등급과 국무조정실 등급 산정의 근거를 마련하는 것을 목적으로 합니다. 평가 범위는 ${esc(safePeriod)}의 투입·활동·산출물·성과이며, 판단은 <b style="color:var(--ink)">증빙자료와 PDM 실적</b>에만 근거합니다.`;
  }

  function setEmptyProjectViews(isEmpty) {
    projectIsEmpty = isEmpty;
    document.body.classList.toggle('empty-project', isEmpty);
    emptyProjectViewIds.forEach((id) => {
      const view = byId(id);
      if (!view) return;
      let state = view.querySelector(':scope > .live-empty-project');
      if (!state) {
        state = document.createElement('div');
        state.className = 'panel empty live-empty-project';
        state.innerHTML = '<b>아직 등록된 자료가 없습니다.</b><br>자료 업로드에서 문서를 등록하면 이 메뉴의 분석 결과가 생성됩니다.<div style="margin-top:14px"><button class="btn primary" data-go="#/evidence">자료 업로드</button></div>';
        view.appendChild(state);
      }
      [...view.children].forEach((child) => {
        if (child === state) return;
        if (isEmpty) {
          child.dataset.emptyProjectHidden = 'true';
          child.hidden = true;
        } else if (child.dataset.emptyProjectHidden === 'true') {
          delete child.dataset.emptyProjectHidden;
          child.hidden = false;
        }
      });
      state.hidden = !isEmpty;
    });

    if (isEmpty) {
      window.LIVE_PENDING_COUNT = 0;
      if (typeof window.renderNav === 'function') window.renderNav();
      const sidePending = byId('spPend');
      if (sidePending) sidePending.hidden = true;
      byId('statPdm').innerHTML = '0<span>/0</span>';
      byId('statPdmBar').style.width = '0%';
      byId('statDac').innerHTML = '0<span>/0</span>';
      byId('statDacBar').style.width = '0%';
      byId('statFiles').textContent = '0';
      const assignCount = byId('assignCount');
      const assignList = byId('assignList');
      if (assignCount) assignCount.textContent = '';
      if (assignList) assignList.innerHTML = '';
      byId('fileRows').innerHTML = '<tr><td colspan="4"><div class="empty" style="border:none">등록된 문서가 없습니다.</div></td></tr>';
      byId('cntAll').textContent = '0건';
    }
  }

  function enterSession(data, forceDashboard = false) {
    if (!data.has_project && !data.account?.is_admin) {
      setAuthView('unassigned', '로그인되어 있지만 배정된 프로젝트가 없습니다. 관리자에게 프로젝트 배정을 요청해 주세요.');
      return;
    }
    serviceScope.bind(data);
    window.KODAME_IS_ADMIN = Boolean(data.account?.is_admin);
    window.KODAME_MENU_PERMISSIONS = data.account?.menu_permissions || {};
    currentRole = data.project?.role || 'viewer';
    const roleLabel = localizedRoleName();
    if (typeof window.applyRole === 'function') window.applyRole(roleLabel);
    byId('roleName').textContent = roleLabel;
    byId('roleAv').textContent = roleLabel.charAt(0);
    setProjectIdentity(data);
    if (window.KODAME_IS_ADMIN) document.title = `K-ODAME v${document.querySelector('meta[name="application-version"]')?.content || '2.3'} · 프로젝트·사용자 관리`;
    byId('logout').textContent = '로그아웃';
    if (typeof window.configureProjectLanguages === 'function') {
      window.configureProjectLanguages({
        supported_locales: data.project?.supported_locales || ['ko'],
        default_locale: data.project?.default_locale || 'ko',
        preferred_locale: data.project?.preferred_locale || data.project?.default_locale || 'ko'
      });
    }
    byId('gate').style.display = 'none';
    byId('app').style.display = 'grid';
    const hash = data.account?.is_admin ? '#/admin/projects' : forceDashboard ? '#/dashboard' : (location.hash && location.hash !== '#/' ? location.hash : '#/dashboard');
    if (typeof window.go === 'function') window.go(hash);
    if (typeof window.route === 'function') window.route();
    if (data.has_project && !window.KODAME_IS_ADMIN) { startData(); refreshProjectLanguages(); refreshProjectChoices(); }
    if (window.KODAME_IS_ADMIN) refreshAdmin();
  }

  function formatAdminDate(value) {
    return value ? new Date(value).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' }) : '기록 없음';
  }

  function renderAdminSummary() {
    const users = adminAccounts.filter((account) => !account.is_admin);
    const active = users.filter((account) => account.is_active).length;
    const totalTokens = adminAccounts.reduce((sum, account) => sum + Number(account.usage?.total_tokens || 0), 0);
    const projects = adminProjects.length;
    byId('adminSummary').innerHTML = [
      ['전체 사용자', `${users.length}명`], ['활성 계정', `${active}명`],
      ['할당 프로젝트', `${projects}개`], ['누적 토큰', totalTokens.toLocaleString('ko-KR')]
    ].map(([label, value]) => `<div class="panel"><span>${label}</span><b class="num">${value}</b></div>`).join('');
  }

  function renderAdminProjects() {
    const target = byId('adminProjectList');
    if (!target) return;
    const query = (byId('adminProjectSearch')?.value || '').trim().toLowerCase();
    const matches = adminProjects.filter(project => project.name.toLowerCase().includes(query));
    const filter = byId('adminUserProject');
    const current = filter.value;
    filter.innerHTML = '<option value="">전체 프로젝트</option>' + adminProjects.map(project => `<option value="${esc(project.id)}">${esc(project.name)}</option>`).join('');
    filter.value = current;
    target.innerHTML = matches.length ? matches.map((project) => `
      <article class="admin-project-card"><b title="${esc(project.name)}">${esc(project.name)}</b>
      <small>${Number(project.member_count || 0)}명 · ${esc(project.default_locale.toUpperCase())} 기본</small>
      <small>문서 ${Number(project.document_count || 0)}건 · 평가 ${Number(project.evaluation_count || 0)}회 · 작성 섹션 ${Number(project.written_sections || 0)}/27</small>${projectAI.card(project)}
      <div class="locale-tags">${(project.supported_locales || []).map((locale) => `<span>${esc(adminLanguages[locale]?.native_name || locale.toUpperCase())}</span>`).join('')}</div><button class="btn sm primary" data-issue-project="${esc(project.id)}">이 프로젝트 계정 발급</button><button class="btn sm" data-project-users="${esc(project.id)}">사용자 관리</button><button class="btn sm" style="color:var(--bad-t)" data-delete-project="${esc(project.id)}">프로젝트 삭제</button></article>`).join('')
      : '<div class="empty">표시할 프로젝트가 없습니다. 새 프로젝트를 생성하거나 검색어를 확인해 주세요.</div>';
  }

  function syncDefaultLocaleOptions() {
    const checked = [...byId('projectLanguageChecks').querySelectorAll('input:checked')].map((input) => input.value);
    const select = byId('projectDefaultLocale');
    const previous = select.value;
    select.innerHTML = checked.map((locale) => `<option value="${esc(locale)}">${esc(adminLanguages[locale]?.native_name || locale.toUpperCase())}</option>`).join('');
    if (checked.includes(previous)) select.value = previous;
  }

  function openProjectCreator() {
    const languageEntries = Object.entries(adminLanguages);
    byId('projectLanguageChecks').innerHTML = languageEntries.map(([locale, meta]) => `<label><input type="checkbox" value="${esc(locale)}" ${locale === 'ko' ? 'checked' : ''}><span>${esc(meta.native_name)}<small style="display:block;color:var(--muted)">${esc(meta.name)}</small></span></label>`).join('');
    byId('projectAccountChecks').innerHTML = '';
    byId('projectCreateName').value = '';
    byId('projectCreateState').textContent = '';
    syncDefaultLocaleOptions();
    byId('projectCreateSubmit').disabled = false;
    if (typeof window.openLayer === 'function') window.openLayer('projectCreateOv');
  }

  async function submitProjectCreate(event) {
    event.preventDefault();
    if (byId('projectCreateSubmit').disabled) return;
    const supported_locales = [...byId('projectLanguageChecks').querySelectorAll('input:checked')].map((input) => input.value);
    const account_ids = [...byId('projectAccountChecks').querySelectorAll('input:checked')].map((input) => input.value);
    if (!supported_locales.length) { byId('projectCreateState').textContent = '제공 언어를 하나 이상 선택해 주세요.'; return; }
    const button = byId('projectCreateSubmit');
    button.disabled = true; byId('projectCreateState').textContent = '프로젝트를 생성하는 중…';
    try {
      const created = await request('/api/v2/admin/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        name: byId('projectCreateName').value.trim(), supported_locales,
        default_locale: byId('projectDefaultLocale').value, account_ids
      }) });
      if (typeof window.closeLayer === 'function') window.closeLayer('projectCreateOv');
      location.hash = '#/admin/projects';
      await refreshAdmin();
      notify('빈 프로젝트를 생성했습니다. 연결할 사용자 계정을 발급해 주세요.');
      serviceAdmin.openAccountForm(null, created.id);
    } catch (error) { byId('projectCreateState').textContent = error.message; button.disabled = false; }
  }

  function renderAdminRows() {
    const query = (byId('adminUserSearch')?.value || '').trim().toLowerCase();
    const projectId = byId('adminUserProject')?.value || '';
    const matches = adminAccounts.filter(account => !account.is_admin && `${account.username} ${account.display_name}`.toLowerCase().includes(query) && (!projectId || (account.projects || []).some(project => project.id === projectId)));
    if (!matches.some(account => account.id === selectedAdminAccountId)) {
      selectedAdminAccountId = matches[0]?.id || null;
      renderAdminDetail(matches[0]);
    }
    byId('adminAccountRows').innerHTML = matches.map((account) => `
      <tr data-admin-account="${account.id}" class="${account.id === selectedAdminAccountId ? 'selected' : ''}">
        <td><div class="admin-user"><i>${esc(account.username.charAt(0).toUpperCase())}</i><span><b>${esc(account.username)}</b><small>${esc(account.display_name)}</small></span></div></td>
        <td><b>${(account.projects || []).map(project => esc(project.name)).join('<br>') || '미배정'}</b><br><span class="tag ${account.is_active ? 'g' : 'w'}">${account.is_active ? '활성' : '중지'}</span></td>
        <td class="num"><b>${Number(account.usage?.total_tokens || 0).toLocaleString('ko-KR')}</b><br><small style="color:var(--muted)">입력 ${Number(account.usage?.prompt_tokens || 0).toLocaleString('ko-KR')} · 출력 ${Number(account.usage?.completion_tokens || 0).toLocaleString('ko-KR')}</small></td>
        <td>${formatAdminDate(account.last_login_at)}<br><small style="color:var(--muted)">${esc(account.last_login_ip || '-')}</small></td>
      </tr>`).join('') || '<tr><td colspan="4">조건에 맞는 사용자가 없습니다.</td></tr>';
  }

  async function renderAdminDetail(account) {
    byId('adminDetail').innerHTML = '<div class="empty">' + (account ? '선택 계정 정보를 불러오는 중입니다.' : '표시할 사용자가 없습니다. 검색 조건을 확인하거나 계정을 발급해 주세요.') + '</div>';
    if (!account) return;
    let history = [];
    try { history = (await request(`/api/v2/admin/accounts/${encodeURIComponent(account.id)}/login-history`)).items || []; } catch (_) { /* summary remains usable */ }
    if (account.id !== selectedAdminAccountId) return;
    const checks = Object.entries(menuLabels).map(([key, label]) => `<label class="menu-check"><input type="checkbox" data-menu-key="${key}" ${account.menu_permissions?.[key] !== false ? 'checked' : ''} ${account.is_admin ? 'disabled' : ''}><span>${label}</span></label>`).join('');
    byId('adminDetail').innerHTML = `
      <div class="admin-detail-head"><span class="avatar">${esc(account.username.charAt(0).toUpperCase())}</span><div><h2>${esc(account.username)} ${account.is_admin ? '<span class="tag i">관리자</span>' : ''}</h2><p>${esc(account.email)} · ${esc(account.display_name)}</p></div></div>
      <div class="admin-facts"><div class="admin-fact"><span>소속 프로젝트</span><b title="${esc((account.projects || []).map(project => project.name).join(' · ') || '미배정')}">${esc((account.projects || []).map(project => project.name).join(' · ') || '미배정')}</b></div><div class="admin-fact"><span>프로젝트 역할</span><b>${account.is_admin ? '시스템 관리자' : esc([...new Set((account.projects || []).map(project => roleNames[project.role] || project.role))].join(' · ') || '-')}</b></div><div class="admin-fact"><span>누적 토큰</span><b class="num">${Number(account.usage?.total_tokens || 0).toLocaleString('ko-KR')}</b></div><div class="admin-fact"><span>최근 로그인</span><b>${formatAdminDate(account.last_login_at)}</b></div></div>
      ${serviceAdmin.detail(account)}
      <div class="menu-permissions"><h3>메뉴 및 기능 권한</h3><p class="state">체크한 메뉴의 조회·작성·생성 기능을 허용합니다. 프로젝트 역할과 관계없이 이 설정이 적용됩니다.</p><div class="menu-checks">${checks}</div><div class="admin-save"><span class="state" id="adminSaveState">${account.is_admin ? '관리자 계정은 전체 메뉴와 기능이 고정 허용됩니다.' : '변경 후 저장해 주세요.'}</span>${account.is_admin ? '' : '<button class="btn primary" id="adminSaveMenus">권한 설정 저장</button>'}</div></div>
      <div class="login-history"><h3>로그인 기록</h3>${history.length ? history.map((item) => `<div class="login-row"><b>${formatAdminDate(item.logged_in_at)}</b><span class="num">${esc(item.ip_address)}</span><small title="${esc(item.user_agent)}">${esc(item.user_agent)}</small></div>`).join('') : '<div class="empty" style="padding:16px">아직 로그인 기록이 없습니다.</div>'}</div>`;
  }

  async function refreshAdmin() {
    if (!window.KODAME_IS_ADMIN || !byId('adminAccountRows')) return;
    byId('adminAccountRows').innerHTML = '<tr><td colspan="4">계정 정보를 불러오는 중입니다.</td></tr>';
    try {
      const [data, projectData] = await Promise.all([request('/api/v2/admin/accounts'), request('/api/v2/admin/projects')]);
      adminAccounts = data.accounts || [];
      adminProjects = projectData.projects || [];
      adminLanguages = projectData.languages || {};
      selectedAdminAccountId = selectedAdminAccountId || adminAccounts.find(account => !account.is_admin)?.id || null;
      renderAdminSummary(); renderAdminProjects(); renderAdminRows();
      await renderAdminDetail(adminAccounts.find((account) => account.id === selectedAdminAccountId));
    } catch (error) {
      byId('adminAccountRows').innerHTML = `<tr><td colspan="4" style="color:var(--bad-t)">${esc(error.message)}</td></tr>`;
    }
  }

  async function saveAdminMenus() {
    const account = adminAccounts.find((item) => item.id === selectedAdminAccountId);
    if (!account || account.is_admin) return;
    const menu_permissions = {};
    byId('adminDetail').querySelectorAll('[data-menu-key]').forEach((input) => { menu_permissions[input.dataset.menuKey] = input.checked; });
    byId('adminSaveState').textContent = '저장 중…';
    try {
      const saved = await request(`/api/v2/admin/accounts/${encodeURIComponent(account.id)}/menus`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ menu_permissions }) });
      account.menu_permissions = saved.menu_permissions;
      byId('adminSaveState').textContent = '권한 설정을 저장했습니다.';
    } catch (error) { byId('adminSaveState').textContent = error.message; }
  }

  function setAuthView(state, message = '') {
    byId('gate').style.display = 'flex';
    byId('app').style.display = 'none';
    byId('authForm').hidden = state !== 'login';
    byId('authStatus').hidden = state === 'login';
    byId('authStatusMessage').textContent = message || '접속 상태를 확인하고 있습니다…';
    byId('authRetry').hidden = !['error','unassigned'].includes(state);
    byId('authSignOut').hidden = state !== 'unassigned';
    if (state === 'login') byId('codeInput').focus();
  }

  function confirmDocumentAction(title, message, reason = null) {
    if (byId('documentActionDialog')) return Promise.resolve(null);
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.id = 'documentActionDialog'; dialog.className = 'service-account-dialog';
      dialog.setAttribute('aria-labelledby', 'documentActionTitle');
      dialog.innerHTML = `<form><h2 id="documentActionTitle">${esc(title)}</h2><p style="margin:14px 0">${esc(message)}</p>${reason !== null ? '<label>변경 사유<textarea aria-label="변경 사유" required maxlength="1000" style="display:block;width:100%;min-height:90px"></textarea></label>' : ''}<div class="report-ai-actions"><button type="button" class="btn" data-action-cancel>취소</button><button type="submit" class="btn primary">확인</button></div></form>`;
      let result = null;
      const input = dialog.querySelector('textarea');
      if (input) input.value = reason;
      dialog.querySelector('[data-action-cancel]').onclick = () => dialog.close();
      dialog.querySelector('form').onsubmit = event => {
        event.preventDefault();
        if (input && !input.value.trim()) { input.focus(); return; }
        result = input ? input.value.trim() : true;
        dialog.close();
      };
      dialog.addEventListener('close', () => { dialog.remove(); resolve(result); }, {once:true});
      document.body.appendChild(dialog); dialog.showModal();
      dialog.querySelector('[data-action-cancel]').focus();
    });
  }

  function initializeAuth() { return sessionStartup.start(); }

  function formatSize(bytes) {
    const number = Number(bytes || 0);
    return number < 1048576 ? `${Math.max(1, Math.round(number / 1024))}KB` : `${(number / 1048576).toFixed(1)}MB`;
  }

  function compactInsightText(value, maxLength = 78) {
    const text = String(value || '')
      .replace(/\([^)]*(?:p\.|쪽)\s*\d+[^)]*\)/gi, '')
      .replace(/^[\s•·\-–—]+/, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!text) return '';
    return text.length > maxLength ? `${text.slice(0, Math.max(1, maxLength - 1)).trim()}…` : text;
  }

  function renderDashboardInsights() {
    const target = byId('fixList');
    const footer = byId('fixFoot');
    if (!target || !footer) return;
    const localizedStatusMeta = statusMetaForLocale();

    const priorityOrder = { under: 0, unset: 1, watch: 2, ok: 3 };
    const pdmRisks = [...(intake.pdm?.performance_indicators || [])]
      .filter((item) => item.status !== 'ok')
      .sort((a, b) => (priorityOrder[a.status] ?? 9) - (priorityOrder[b.status] ?? 9));
    const pdmItems = pdmRisks.slice(0, 3).map((item) => {
      const risk = item.risk_analysis || {};
      const status = localizedStatusMeta[item.status] || localizedStatusMeta.unset;
      const detail = (risk.recommendations || [])[0] || risk.forecast || risk.risk_analysis
        || tr('ui.dashboard.check_indicator', '{indicator}의 목표·실적 및 산출근거를 확인합니다.', {
          indicator: item.indicator || tr('ui.dashboard.indicator', '성과지표')
        });
      return {
        title: compactInsightText(risk.risk_title || item.indicator || tr('ui.dashboard.indicator_risk', '성과지표 위험'), 48),
        detail: compactInsightText(detail),
        tagClass: status[0], tagText: status[1], route: '#/project/gaps',
      };
    });

    const dacItems = [...(latestEvaluationData.criteria || [])]
      .filter((criterion) => criterion.id !== 'impact')
      .sort((a, b) => Number(a.score ?? 4) - Number(b.score ?? 4))
      .map((criterion) => {
        const questions = [...(criterion.question_assessments || [])].sort((a, b) => {
          const aIssue = Number(Boolean(a.evidence_gaps?.length || a.action_items?.length));
          const bIssue = Number(Boolean(b.evidence_gaps?.length || b.action_items?.length));
          return bIssue - aIssue || Number(a.score ?? 4) - Number(b.score ?? 4);
        });
        const question = questions[0] || {};
        const detail = (question.action_items || [])[0] || (question.evidence_gaps || [])[0]
          || question.finding || criterion.score_reason || criterion.summary
          || tr('ui.dashboard.check_detail', '세부 판단 근거를 확인합니다.');
        const score = Number(criterion.score);
        return {
          title: compactInsightText(`${criterion.name} · ${question.question || tr('ui.dashboard.general_judgement', '종합 판단')}`, 48),
          detail: compactInsightText(detail),
          tagClass: score < 3 ? 'b' : score < 4 ? 'w' : 'g',
          tagText: `${formatDacScore(criterion.score)}/4`, route: '#/eval/results',
        };
      }).slice(0, 3);

    const rows = (items, emptyText) => items.length ? items.map((item, index) => `
      <div class="insight-row" data-go="${item.route}" role="button" tabindex="0">
        <span class="insight-rank">${index + 1}</span>
        <span class="insight-copy"><span class="insight-title">${esc(item.title)}</span><span class="insight-detail">${esc(item.detail)}</span></span>
        <span class="insight-meta"><span class="tag ${item.tagClass}">${esc(item.tagText)}</span><span class="go2">›</span></span>
      </div>`).join('') : `<div class="insight-empty">${esc(emptyText)}</div>`;

    target.innerHTML = `
      <section class="insight-lane pdm">
        <div class="insight-lane-head" data-go="#/project/gaps" role="button" tabindex="0">
          <span class="tag g">${esc(tr('ui.dashboard.pdm_perspective', 'PDM 관점'))}</span><h3>${esc(tr('ui.dashboard.pdm_risk_title', '성과 리스크·개선권고'))}</h3><span class="insight-count">${esc(tr('ui.dashboard.group_count', '{count}개', { count: pdmRisks.length }))} ›</span>
        </div>
        <div class="insight-list">${rows(pdmItems, tr('ui.dashboard.no_pdm_risk', '현재 확인된 PDM 성과 리스크가 없습니다.'))}</div>
      </section>
      <section class="insight-lane dac">
        <div class="insight-lane-head" data-go="#/eval/results" role="button" tabindex="0">
          <span class="tag i">${esc(tr('ui.dashboard.dac_perspective', 'DAC 관점'))}</span><h3>${esc(tr('ui.dashboard.dac_result_title', '종료평가 분석 결과'))}</h3><span class="insight-count">${esc(tr('ui.dashboard.criteria_count', '{count}개 기준', { count: (latestEvaluationData.criteria || []).filter((item) => item.id !== 'impact').length }))} ›</span>
        </div>
        <div class="insight-list">${rows(dacItems, tr('ui.dashboard.no_dac_result', '아직 생성된 DAC 분석 결과가 없습니다.'))}</div>
      </section>`;
    footer.textContent = tr('ui.dashboard.footer', 'PDM 성과 리스크 {risks}건 · DAC 분석 {criteria}개 기준 · 항목을 누르면 상세 화면으로 이동합니다.', {
      risks: pdmRisks.length,
      criteria: (latestEvaluationData.criteria || []).filter((item) => item.id !== 'impact').length,
    });
  }

  function renderDashboard(data) {
    const project = data.project || {};
    setProjectIdentity({ project });
    const projectName = currentProjectIdentity.name || '배정된 사업';

    // A delayed dashboard/translation response must not erase freshly uploaded files.
    const isEmpty = data.is_empty === true && intake.jobs.length === 0;
    setEmptyProjectViews(isEmpty);
    byId('emptyProjectStart').hidden = !isEmpty;
    const pdmSubtitle = document.querySelector('#v-dashboard .herocard.pdm .psub');

    if (isEmpty) {
      byId('updTime').textContent = '자료 등록 전';
      byId('achievePct').textContent = tr('ui.dashboard.not_evaluated', '평가 전');
      byId('achieveBar').style.width = '0%';
      byId('daonHello').textContent = tr('ui.dashboard.insight_title', '핵심 리스크·분석 요약');
      byId('daonSub').textContent = tr('ui.dashboard.insight_empty_subtitle', '성과 관리와 종료평가의 최신 분석에서 우선 확인할 항목만 표시합니다.');
      renderDashboardInsights();
      byId('pdmBig').innerHTML = '0<small>/0</small>';
      byId('pdmKl').textContent = tr('ui.dashboard.no_indicators', '등록된 성과지표가 없습니다.');
      dashboardIndicatorsExpanded = false;
      renderDashboardIndicatorList([]);
      if (pdmSubtitle) pdmSubtitle.textContent = tr('ui.dashboard.not_evaluated', '평가 전');
      syncDashboardDac(latestEvaluationData);
      renderWorkflowSteps([]);
      return;
    }

    const progress = Math.max(0, Math.min(100, Number(data.progress || 0)));
    byId('achievePct').textContent = `${progress}%`;
    byId('achieveBar').style.width = `${progress}%`;
    byId('daonHello').textContent = tr('ui.dashboard.insight_title', '핵심 리스크·분석 요약');
    byId('daonSub').textContent = tr('ui.dashboard.insight_project_subtitle', '{project}의 PDM 성과 리스크와 DAC 분석 결과를 우선순위별로 요약했습니다.', { project: projectName });
    renderDashboardInsights();

    syncDashboardDac(latestEvaluationData);
    if (data.updated_at) byId('updTime').textContent = tr('ui.dashboard.updated', '업데이트 {value}', {
      value: new Date(data.updated_at).toLocaleString(currentLocale()),
    });
    else byId('updTime').textContent = tr('ui.dashboard.not_evaluated', '평가 전');
    renderWorkflowSteps(data.steps || []);
  }

  function renderWorkflowSteps(steps) {
    latestWorkflowSteps = steps;
    steps = window.DacScoringUI.evaluationSteps(steps, latestEvaluationData, latestEvaluationStatus);
    const target = byId('stepline');
    if (!target) return;
    if (!steps.length) {
      target.innerHTML = `<div class="empty" style="border:none">${esc(tr('ui.dashboard.workflow_empty', '자료 등록 후 진행상황이 표시됩니다.'))}</div>`;
      return;
    }
    const currentIndex = steps.findIndex((step) => Number(step.percent || 0) < 100);
    target.innerHTML = steps.map((step, index) => {
      const percent = Math.max(0, Math.min(100, Number(step.percent || 0)));
      const completed = !step.active && percent >= 100;
      const current = step.active || (!completed && index === currentIndex);
      const state = completed ? 'done' : current ? 'run' : 'wait';
      const icon = completed ? '✓' : current ? '●' : '·';
      const chip = step.active ? '새 평가 진행 중' : step.historical ? '이전 결과' : completed
        ? tr('ui.dashboard.complete', '완료')
        : current
          ? (percent > 0 ? tr('ui.dashboard.in_progress', '진행 중 {percent}%', { percent }) : tr('ui.dashboard.action_required', '진행 필요'))
          : tr('ui.dashboard.waiting', '대기');
      return `<div class="stepitem ${current ? 'cur' : ''}"><span class="si ${state}">${icon}</span><div style="flex:1;min-width:0"><div class="sn2">${esc(step.name)}</div><div class="sd2">${esc(step.hint || '')}</div></div><span class="st2 ${state}">${chip}</span></div>`;
    }).join('');
  }

  async function refreshDashboard() {
    try {
      const data = await request('/api/v2/dashboard');
      renderDashboard(localizedView('dashboard', data));
    } catch (error) { console.error(error); }
  }

  function renderFiles() {
    const summaryExpanded = new Set([...byId('fileRows').querySelectorAll('details[data-document-summary][open]')].map(el => el.dataset.documentSummary));
    const expanded = new Set([...byId('fileRows').querySelectorAll('details[data-document-matches][open]')].map(el => el.dataset.documentMatches));
    const triageExpanded = new Set([...byId('fileRows').querySelectorAll('details[data-triage][open]')].map(el => el.dataset.triage));
    const jobs = intake.jobs.filter((job) => {
      const linked = intake.slots.items.some((item) => item.document_id === job.id)
        || (intake.pdm.assignments || []).some((item) => item.document_id === job.id)
        || ['pdm', 'dac_slots', 'report_sections'].some(axis => job.matches?.[axis]?.length);
      const filterMatch = fileFilter === 'excluded' ? job.evaluation_excluded
        : !job.evaluation_excluded && (fileFilter === 'all' || (fileFilter === 'linked' ? linked : !linked));
      return filterMatch && (!fileQuery || String(job.file_name || '').toLowerCase().includes(fileQuery));
    });
    const shown = fileShowAll ? jobs : jobs.slice(0, 8);
    byId('fileRows').innerHTML = shown.length ? shown.map((job) => {
      const dac = intake.slots.items.filter((item) => item.document_id === job.id);
      const pdm = job.matches?.pdm?.length
        ? job.matches.pdm.map(item => ({ requirement_title: item.indicator || item.indicator_id }))
        : (intake.pdm.assignments || []).filter((item) => item.document_id === job.id);
      const slotMarkup = [
        ...dac.map((item) => `<div><span class="tag i" style="font-size:9px;padding:1px 6px">DAC</span> ${esc(item.criterion_name)} · ${esc(item.slot_title)}</div>`),
        ...pdm.map((item) => `<div><span class="tag g" style="font-size:9px;padding:1px 6px">PDM</span> ${esc(item.requirement_title)}</div>`),
        ...(job.matches?.report_sections || []).map(item => `<div><span class="tag n" style="font-size:9px;padding:1px 6px">보고서</span> ${esc(item.section_title || item.section_id)}</div>`)
      ];
      const matchingDetails = slotMarkup.length ? `<details data-document-matches="${esc(job.id)}" ${expanded.has(job.id) ? 'open' : ''}><summary style="cursor:pointer">매칭 ${slotMarkup.length}건 · 상세 보기</summary><div style="margin-top:8px;max-height:320px;overflow:auto">${slotMarkup.join('')}</div></details>` : '';
      const purposeProfiles = (job.document_profiles || []).map(profile => `<p><b>문서 목적</b> ${esc(profile.purpose)}<br><b>사업 내 역할</b> ${esc(profile.project_role)}${profile.interview_purpose ? `<br><b>인터뷰 목적</b> ${esc(profile.interview_purpose)}<br><b>응답 대상</b> ${esc(profile.interview_subject)}` : ''}</p>`).join('');
      const modeLabel = job.intake_mode === 'artifact' ? '산출물 등록' : job.intake_mode === 'evidence' ? '일반 자료 분석' : job.status === 'awaiting_review' ? '처리 방식 선택 필요' : job.triage ? 'AI 사전 판단 완료' : job.status === 'completed' ? '일반 자료 분석 (기존)' : 'AI 사전 판단 예정';
      const eligibility = job.evaluation_scope || {};
      const scopeMarkup = job.upload_role === 'evidence' ? `<div style="margin-top:8px"><span class="tag ${job.evaluation_excluded ? 'w' : 'n'}">${job.evaluation_excluded ? '평가 대상에서 제외' : '평가 대상'}</span>${job.evaluation_excluded ? `<p>${esc(eligibility.reason || '')}</p>${eligibility.reference_name ? `<p>대조 문서: ${esc(eligibility.reference_name)}</p>` : ''}<small>원본은 보관하며 성과지표·DAC 평가·보고서 분석에는 사용하지 않습니다.</small>` : ''}${job.status !== 'processing' ? `<p><button class="btn sm" data-evaluation-scope="${job.evaluation_excluded ? 'include' : 'exclude'}" data-scope-document="${esc(job.id)}">${job.evaluation_excluded ? '평가 대상에 포함' : '평가 대상에서 제외'}</button></p>` : ''}</div>` : '';
      const triageMarkup = job.upload_role === 'evidence' ? `<details data-triage="${esc(job.id)}" ${job.status==='awaiting_review'||triageExpanded.has(job.id)?'open':''} style="margin-top:8px"><summary style="cursor:pointer">${esc(modeLabel)} · 판단/변경</summary><p>${esc(job.triage?.reason || '일부 본문을 확인해 처리 방식을 추천합니다.')}</p>${job.triage ? `<p>${esc(job.triage.title || '')} · ${esc(job.triage.artifact_type || '')}${job.triage.is_excerpt==='yes'?' · 일부 발췌본':''}</p><small>사전 판단은 일부 본문만 확인합니다.</small>`:''}${job.intake_mode==='artifact'?`<p>${esc(job.registration?.limitation || '산출물 제출만 확인하며 제작·배포·효과는 별도 증빙이 필요합니다.')}</p>${(job.intake_warnings||[]).slice(1).map(w=>`<p>${esc(w)}</p>`).join('')}`:''}<p>${job.status==='processing'?'분석 중에는 작업 트레이에서 중지한 뒤 변경할 수 있습니다.':`<button class="btn sm" data-intake-mode="artifact" data-mode-document="${esc(job.id)}">산출물로 등록</button> <button class="btn sm" data-intake-mode="evidence" data-mode-document="${esc(job.id)}">일반 자료로 분석</button>`}</p></details>` : '';
      return `
      <tr>
        <td><a class="filechip" href="${downloadUrl(job.id)}" download><span class="t">${esc(job.file_name)}</span></a>${scopeMarkup}${job.summary ? `<details data-document-summary="${esc(job.id)}" ${summaryExpanded.has(job.id) ? 'open' : ''} style="margin-top:8px"><summary style="cursor:pointer">문서 요약${job.registration_fact_count ? ` · 등록 사실 ${Number(job.registration_fact_count)}건` : ''}</summary><p style="white-space:pre-wrap;overflow-wrap:anywhere;max-width:560px">${esc(job.summary)}</p>${purposeProfiles}</details>` : ''}${job.evaluation_excluded ? '' : triageMarkup}${job.status==='completed' && !job.evaluation_excluded?`<p>검토 깊이: ${job.review_depth==='sample_only'?'표본 검토':'추출 원문 전체'}${job.registration?.deeper_review_suggested?' · 성과 근거 후보가 있어 일반 자료 분석을 권장합니다.':''}</p><button class="btn sm" data-document-source="${esc(job.id)}">원문·사실 위치 보기</button>`:''}</td>
        <td>${job.evaluation_excluded ? '<span class="tag n">보관 완료 · 평가 분석 제외</span>' : ['failed', 'waiting_llm', 'cancelled'].includes(job.status) ? `<span class="tag w">${job.status === 'failed' ? '분석 실패' : job.status === 'cancelled' ? '사용자 중지' : 'AI 연결 대기'}</span><p style="overflow-wrap:anywhere">${esc(job.error_message || '작업 상태를 확인한 뒤 필요하면 다시 요청해 주세요.')}</p><button class="btn sm" data-retry-document="${esc(job.id)}">분석 재시도</button>` : matchingDetails || `<span class="tag ${job.status === 'completed' ? 'n' : 'w'}">${job.status === 'completed' ? '미분류 · 직접 매핑 가능' : job.status === 'awaiting_review' ? '처리 방식 선택 필요' : esc(job.stage || job.status)}</span>`}</td>
        <td class="meta2 num">${formatSize(job.size_bytes)}</td>
        <td class="meta2 num">${job.uploaded_at ? new Date(job.uploaded_at).toLocaleDateString('ko-KR') : '-'}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="4"><div class="empty" style="border:none">등록된 문서가 없습니다.</div></td></tr>';
    byId('fileMore').style.display = jobs.length > 8 ? 'block' : 'none';
    byId('fileMore').textContent = fileShowAll ? '접기 ▴' : `전체 ${jobs.length}건 모두 보기 ▾`;
    byId('statFiles').textContent = intake.jobs.length;
    byId('cntAll').textContent = `${intake.jobs.length}건`;
    let health = byId('intakeHealth');
    if (!health) { health = document.createElement('div'); health.id = 'intakeHealth'; health.setAttribute('role', 'status'); byId('dropzone').after(health); }
    const failed = intake.jobs.filter(job => ['failed', 'waiting_llm', 'cancelled'].includes(job.status));
    const completed = intake.jobs.filter(job => job.status === 'completed').length;
    const excludedCount = intake.jobs.filter(job => job.evaluation_excluded).length;
    const awaitingReview = intake.jobs.filter(job => job.status === 'awaiting_review').length;
    health.innerHTML = `<p style="margin:12px 0">전체 ${intake.jobs.length}건 · 처리 완료 ${completed}건(평가 제외 ${excludedCount}건 포함) · 처리 중 ${intake.jobs.length - completed - failed.length - awaitingReview}건 · 확인 필요 ${failed.length}건 · 처리 방식 선택 ${awaitingReview}건</p>${awaitingReview ? '<p>판단이 불확실한 문서는 아래에서 산출물 등록 또는 일반 자료 분석을 선택해 주세요.</p>' : ''}${failed.length ? '<p>실패·중지한 일반 자료는 제외하고 다음 분석을 진행할 수 있습니다. 처리 중·연결 대기 자료와 기준 문서는 먼저 완료해 주세요.</p>' : ''}`;
  }

  function clearManualAssignmentState() {
    window.LIVE_PENDING_COUNT = 0;
    if (typeof window.renderNav === 'function') window.renderNav();
    const count = byId('assignCount');
    const list = byId('assignList');
    if (count) count.textContent = '';
    if (list) list.innerHTML = '';
    const sideCount = byId('spPend');
    if (sideCount) sideCount.hidden = true;
  }

  const lineText = (value) => esc(value || '').replace(/\n/g, '<br>');
  const statusMetaForLocale = () => ({
    ok: ['g', tr('ui.status.achieved', '달성')],
    watch: ['w', tr('ui.status.warning', '주의')],
    under: ['b', tr('ui.status.below', '미달')],
    unset: ['n', tr('ui.status.missing', '실적 미확인')]
  });

  function achievementBarMeta(rate) {
    if (rate == null || rate === '' || !Number.isFinite(Number(rate))) {
      return { css: '', width: 0, label: tr('ui.dashboard.achievement_unavailable', '미산정'), unset: true };
    }
    const numeric = Number(rate);
    const display = Number.isInteger(numeric) ? String(numeric) : String(Math.round(numeric * 10) / 10);
    return {
      css: numeric >= 90 ? 'g' : numeric >= 70 ? 'w' : 'r',
      width: Math.max(0, Math.min(100, numeric)),
      label: `${display}%`,
      unset: false,
    };
  }

  function achievementBarMarkup(rate, label) {
    if (label) return `<span class="tag ${label === '충족' ? 'g' : 'b'}">${esc(label)}</span>`;
    const meta = achievementBarMeta(rate);
    const ariaLabel = tr('ui.dashboard.achievement_label', '달성도 {value}', { value: meta.label });
    return `<div class="achievement-bar${meta.unset ? ' unset' : ''}" aria-label="${esc(ariaLabel)}"><div class="pbar"><i class="${meta.css}" style="width:${meta.width}%"></i></div><span class="pv num">${esc(meta.label)}</span></div>`;
  }

  function renderDashboardIndicatorList(indicators) {
    const statusOrder = { under: 0, unset: 1, watch: 2, ok: 3 };
    const ordered = [...(indicators || [])].sort((left, right) => (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9));
    const visible = dashboardIndicatorsExpanded ? ordered : ordered.slice(0, 5);
    const target = byId('dashInd');
    const toggle = byId('dashIndToggle');
    if (!target || !toggle) return;

    target.className = 'dash-kpi-list';
    target.innerHTML = visible.length
      ? groupPerformanceIndicators(visible).map(({ tier, items }) => `<section class="dash-kpi-group"><div class="dash-kpi-group-head"><span class="tier ${tier.css}">${esc(tier.label)}</span><span>${esc(tr('ui.dashboard.group_count', '{count}개', { count: items.length }))}</span></div>${items.map((item) => `<div class="dash-kpi-row" data-go="#/project/indicators" role="button" tabindex="0"><span class="dash-kpi-name">${esc(item.indicator)}</span><span class="dash-kpi-chart">${achievementBarMarkup(item.achievement_rate, item.achievement_label)}</span></div>`).join('')}</section>`).join('')
      : `<div class="empty" style="border:none">${esc(tr('ui.dashboard.no_indicators', '등록된 성과지표가 없습니다.'))}</div>`;
    toggle.hidden = ordered.length <= 5;
    toggle.setAttribute('aria-expanded', String(dashboardIndicatorsExpanded));
    toggle.textContent = dashboardIndicatorsExpanded
      ? tr('ui.dashboard.collapse_indicators', '성과지표 접기 ▴')
      : tr('ui.dashboard.expand_indicators', '전체 {count}개 펼치기 ▾', { count: ordered.length });
  }

  const performanceTierOrder = ['impact', 'outcome', 'outputs', 'activities', 'inputs'];
  const performanceTierLabels = {
    impact: { label: 'Impact(영향)', ko: '영향', en: 'Impact', css: 'impact' },
    outcome: { label: 'Outcome(성과)', ko: '성과', en: 'Outcome', css: 'outcome' },
    outputs: { label: 'Output(산출물)', ko: '산출물', en: 'Output', css: 'output' },
    activities: { label: 'Activities(활동)', ko: '활동', en: 'Activities', css: 'activity' },
    inputs: { label: 'Inputs(투입)', ko: '투입', en: 'Inputs', css: 'input' },
  };

  function performanceTierMeta(item = {}) {
    let id = String(item.tier_id || '').toLowerCase();
    if (id === 'output') id = 'outputs';
    if (id === 'activity') id = 'activities';
    if (id === 'input') id = 'inputs';
    const fallbackKo = item.tier_name || item.program || '미분류';
    const fallbackLabel = item.tier_label || fallbackKo;
    const known = performanceTierLabels[id];
    if (known) {
      const localizedName = item.tier_name || item.program || known.ko;
      return {
        id,
        ...known,
        ko: localizedName,
        label: currentLocale() === 'ko' ? known.label : (currentLocale() === 'en' ? known.en : `${known.en} (${localizedName})`),
      };
    }
    return {
      id: id || 'other',
      ...{ label: fallbackLabel, ko: fallbackKo, en: '', css: 'input' },
    };
  }

  function groupPerformanceIndicators(items) {
    const groups = new Map();
    items.forEach((item) => {
      const tier = performanceTierMeta(item);
      if (!groups.has(tier.id)) groups.set(tier.id, { tier, items: [] });
      groups.get(tier.id).items.push(item);
    });
    return [...groups.values()].sort((left, right) => {
      const leftIndex = performanceTierOrder.indexOf(left.tier.id);
      const rightIndex = performanceTierOrder.indexOf(right.tier.id);
      return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
    });
  }

  function monitoringEvidenceFold(item) {
    const documents = item.evidence_documents || [];
    const evidence = String(item.evidence || '').trim();
    const evidenceCount = evidence && evidence !== 'PDM에 검증수단 미기재' ? 1 : 0;
    const summary = `산출근거 ${evidenceCount}건 · 연결문서 ${documents.length}건`;
    const documentMarkup = documents.length
      ? documents.map((document) => `<a class="filechip" href="${downloadUrl(document.id)}" download><span class="t">${esc(document.file_name)}</span></a>`).join('')
      : '<span class="miss">연결 문서 없음</span>';
    const measurements = (item.measurement_sources || []).map((source) => {
      const selected=item.selected_measurements?.[source.kind];
      const applied=selected && selected.document_id===source.document_id && selected.value===source.value && selected.period===source.period;
      return `<div><b>${source.kind === 'actual' ? '실적' : '목표'} ${esc(source.value)}</b> ${applied?'<span class="tag g">현재 반영</span>':''} · ${esc(source.period || '측정기간 확인 필요')}<p>${esc(source.quote || (source.previous_result?'이전 평가에 저장된 값':''))}</p>${source.document_id?`<a href="${downloadUrl(source.document_id)}" download>${esc(source.file_name)}</a>`:esc(source.file_name)}</div>`;
    }).join('');
    return `<details class="evidence-fold monitor-evidence"><summary><span>${summary}</span><span class="fold-closed">펼치기</span><span class="fold-open">접기</span></summary><div class="monitor-evidence-body"><div><b>PDM 산출근거</b><p>${esc(evidence || '산출근거 미기재')}</p></div><div><b>연결문서 ${documents.length}건</b><div class="csec-foot">${documentMarkup}</div></div>${measurements}</div></details>`;
  }

  function riskListMarkup(values, ordered = false, fallback = '추가 확인이 필요합니다.') {
    const items = (values || []).filter(Boolean);
    if (!items.length) return `<p>${esc(fallback)}</p>`;
    const tag = ordered ? 'ol' : 'ul';
    return `<${tag}>${items.map((value) => `<li>${esc(value)}</li>`).join('')}</${tag}>`;
  }

  function riskItemKey(item) {
    return String(item.id || `${performanceTierMeta(item).id}:${item.pdm_code || item.indicator || 'risk'}`);
  }

  function openRiskDetail(id, trigger) {
    const item = riskDetailItems.get(id);
    const modal = byId('riskDetailModal');
    if (!item || !modal) return;
    const tier = performanceTierMeta(item);
    const risk = item.risk_analysis || {};
    const sourceLabel = risk.analysis_source === 'openrouter' ? 'AI 상세분석' : '기본 분석';
    riskModalTrigger = trigger || document.activeElement;
    byId('riskDetailTier').textContent = tier.label;
    byId('riskDetailTier').className = `tier ${tier.css}`;
    byId('riskDetailTitle').textContent = risk.risk_title || item.indicator || '성과 리스크 상세';
    byId('riskDetailMeta').textContent = `${item.pdm_code ? `${item.pdm_code} · ` : ''}목표 ${item.target || '-'} · 실적 ${item.actual || '-'} · 달성도 ${item.achievement_rate == null ? '산정 불가' : `${item.achievement_rate}%`} · ${sourceLabel}`;
    byId('riskDetailBody').innerHTML = `
      <section class="risk-modal-section"><h3>위험 분석</h3><p>${esc(risk.risk_analysis || '지표 갱신을 실행해 상세 분석을 생성해 주세요.')}</p></section>
      <section class="risk-modal-section"><h3>원인</h3>${riskListMarkup(risk.root_causes)}</section>
      <section class="risk-modal-section"><h3>전망</h3><p>${esc(risk.forecast || '후속 측정 결과에 따라 갱신합니다.')}</p></section>
      <section class="risk-modal-section"><h3>개선권고</h3>${riskListMarkup(risk.recommendations, true, '책임자·기한·확인자료를 포함한 개선계획을 수립합니다.')}</section>
      <section class="risk-modal-section"><h3>추가 필요 근거</h3>${riskListMarkup(risk.evidence_needed, false, '추가 근거를 확인합니다.')}</section>`;
    modal.hidden = false;
    document.body.classList.add('risk-modal-open');
    modal.querySelector('button[data-risk-close]')?.focus();
  }

  function closeRiskDetail() {
    const modal = byId('riskDetailModal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove('risk-modal-open');
    riskModalTrigger?.focus?.();
    riskModalTrigger = null;
  }

  function renderEvidenceCoverage() {
    const pdmMissing = Math.max(0, pdmCoverage.total - pdmCoverage.filled);
    const dacMissing = Math.max(0, dacCoverage.total - dacCoverage.filled);
    const pdmPercent = Math.round(pdmCoverage.filled / Math.max(1, pdmCoverage.total) * 100);
    const dacPercent = Math.round(dacCoverage.filled / Math.max(1, dacCoverage.total) * 100);
    byId('coveragePdmValue').innerHTML = `${pdmCoverage.filled}<span>/${pdmCoverage.total}</span>`;
    byId('coveragePdmBar').style.width = `${pdmPercent}%`;
    byId('coverageDacValue').innerHTML = `${dacCoverage.filled}<span>/${dacCoverage.total}</span>`;
    byId('coverageDacBar').style.width = `${dacPercent}%`;
    byId('coverageDocumentValue').textContent = intake.jobs.length;
    byId('coverageGapList').innerHTML = `<div class="minirow" data-go="#/evidence/pdm"><span class="tag g">PDM</span><span class="mn">검증수단 미확보 항목</span><span class="mv num">${pdmMissing}건</span><span class="go2">확인 ›</span></div><div class="minirow" data-go="#/evidence/dac"><span class="tag i">DAC</span><span class="mn">평가기준 증빙 미확보 항목</span><span class="mv num">${dacMissing}건</span><span class="go2">확인 ›</span></div>`;
  }

  function renderPerformanceIndicators(data) {
    const indicators = data.performance_indicators || [];
    const localizedStatusMeta = statusMetaForLocale();
    const groupedIndicators = groupPerformanceIndicators(indicators);
    const counts = { ok: 0, watch: 0, under: 0, unset: 0 };
    indicators.forEach((item) => { counts[item.status] = (counts[item.status] || 0) + 1; });
    byId('indSummary').innerHTML = `<div class="stat"><div class="sl">전체 지표</div><div class="sv num">${indicators.length}</div><div class="ss">최신 PDM 객관적 검증지표</div></div><div class="stat"><div class="sl">달성</div><div class="sv good">${counts.ok}</div><div class="ss">목표 대비 100% 이상</div></div><div class="stat"><div class="sl">주의</div><div class="sv warn">${counts.watch}</div><div class="ss">목표 대비 70~99%</div></div><div class="stat"><div class="sl">미달</div><div class="sv bad">${counts.under}</div><div class="ss">목표 대비 70% 미만</div></div><div class="stat"><div class="sl">실적 미확인</div><div class="sv mut">${counts.unset}</div><div class="ss">추가 실적자료 필요</div></div>`;
    const source = data.performance_source_document;
    const monitoring = data.monitoring || {};
    const riskMeta = data.risk_analysis || {};
    const riskStatus = riskMeta.status === 'completed'
      ? ` · AI 상세분석 ${Number(riskMeta.analyzed_count || 0)}건 반영`
      : riskMeta.status === 'fallback' ? ' · AI 호출 실패로 구체적 기본 권고 반영' : '';
    const matchedCount = Number(monitoring.matched_reported_metric_count || 0);
    byId('indSummaryNote').innerHTML = `목록은 최신 PDM의 객관적 검증지표 ${indicators.length}건만 사용합니다.`
      + (source ? ` <a href="${downloadUrl(source.id)}" download><b>${esc(source.file_name)}</b></a>에서 목표·실적 ${matchedCount}건을 연결했습니다.` : monitoring.evidence_analysis ? ' 연결 문서의 원문을 기준으로 목표·실적을 검토했습니다.' : ' 성과지표 분석을 실행하면 연결 문서에서 목표·실적을 검토합니다.')
      + (monitoring.evidence_analysis ? ` 이번 검토 문서 ${Number(monitoring.evidence_analysis.mapped_document_count || 0)}건 · 누적 측정값 ${Number(monitoring.evidence_analysis.observation_count || 0)}건.` : '')
      + (monitoring.evidence_analysis?.incomplete_indicator_count ? ` 분석 미완료 지표 ${Number(monitoring.evidence_analysis.incomplete_indicator_count)}건: 재갱신이 필요합니다.` : '')
      + riskStatus;
    const monitoringRows = groupedIndicators.map(({ tier, items }) => items.map((item, index) => {
      const meta = localizedStatusMeta[item.status] || localizedStatusMeta.unset;
      const tierCell = index === 0 ? `<td rowspan="${items.length}" class="tiercell"><div class="monitor-tier"><span class="tier ${tier.css}">${esc(tier.label)}</span><small>${items.length}개 지표</small></div></td>` : '';
      return `<tr data-tier="${esc(tier.label)}" class="${index === 0 ? 'tier-first' : ''}">${tierCell}<td class="sum">${item.pdm_code ? `<b>${esc(item.pdm_code)}</b> ` : ''}${esc(item.indicator)}</td><td class="num">${esc(item.target || '-')}${item.target_review_required ? '<br><span class="tag b" title="활성 참고자료에서 보고한 목표입니다. PDM 공식 목표와 대조가 필요합니다.">참고자료 목표</span>' : ''}</td><td class="num">${esc(item.actual || '-')}</td><td class="achievement-cell">${achievementBarMarkup(item.achievement_rate, item.achievement_label)}</td><td>${monitoringEvidenceFold(item)}</td><td><span class="tag ${meta[0]}">${meta[1]}</span>${item.note ? `<details class="monitoring-note"><summary>판단 근거 보기</summary><p>${esc(item.note)}</p></details>` : ''}</td></tr>`;
    }).join('')).join('');
    byId('narrList').innerHTML = indicators.length ? `<div class="panel" style="padding:0;overflow:hidden"><div style="overflow-x:auto"><table class="pdmtbl monitoring-table"><colgroup><col style="width:10%"><col style="width:30%"><col style="width:7%"><col style="width:7%"><col style="width:14%"><col style="width:19%"><col style="width:13%"></colgroup><thead><tr><th>성과 구분</th><th>객관적 검증지표(OVI)</th><th>목표</th><th>실적</th><th>달성도</th><th>산출근거·연결문서</th><th>상태</th></tr></thead><tbody>${monitoringRows}</tbody></table></div></div>` : '<div class="empty"><b>PDM 객관적 검증지표가 없습니다.</b><br>최신 PDM 원본을 확인해 주세요.</div>';

    const risks = indicators.filter((item) => item.status !== 'ok');
    riskDetailItems = new Map(risks.map((item) => [riskItemKey(item), item]));
    byId('gapCount').textContent = `${risks.length}건`;
    const riskGroups = groupPerformanceIndicators(risks);
    byId('gapList').innerHTML = risks.length ? riskGroups.map(({ tier, items }) => `<section class="risk-group"><div class="risk-group-head"><span class="tier ${tier.css}">${esc(tier.label)}</span><h2>${esc(tier.ko)} 리스크</h2><span>${items.length}건</span></div><div class="risk-group-grid">${items.map((item) => {
      const id = riskItemKey(item);
      const meta = localizedStatusMeta[item.status] || localizedStatusMeta.unset;
      const risk = item.risk_analysis || {};
      const recommendations = risk.recommendations || [];
      const priority = { high: ['b', '높음'], medium: ['w', '중간'], low: ['g', '낮음'] }[risk.priority] || ['w', '중간'];
      const sourceLabel = risk.analysis_source === 'openrouter' ? 'AI 상세분석' : '기본 분석';
      return `<article class="panel risk-card"><button class="risk-expand" type="button" data-risk-open="${esc(id)}" aria-label="${esc(risk.risk_title || item.indicator)} 전체 내용 보기" title="전체 내용 보기">⤢</button><div class="ph"><h3>${esc(risk.risk_title || item.indicator)}</h3><div style="display:flex;gap:6px"><span class="tag ${priority[0]}">우선순위 ${priority[1]}</span><span class="tag ${meta[0]}">${meta[1]}</span></div></div><div class="psub">${item.pdm_code ? `${esc(item.pdm_code)} · ` : ''}목표 ${esc(item.target || '-')} · 실적 ${esc(item.actual || '-')} · 달성도 ${item.achievement_rate == null ? '산정 불가' : `${item.achievement_rate}%`} · ${sourceLabel}</div><div class="callout" style="margin-top:12px"><span class="ci">!</span><p class="risk-preview"><b>위험 분석</b><br>${esc(risk.risk_analysis || '지표 갱신을 실행해 상세 분석을 생성해 주세요.')}</p></div><div class="minilist" style="margin-top:12px"><div class="minirow" style="align-items:flex-start"><span class="tag g">개선권고</span><span class="mn">${recommendations.length ? recommendations.slice(0, 2).map((value, index) => `${index + 1}. ${esc(value)}`).join('<br>') : '책임자·기한·확인자료를 포함한 개선계획을 수립합니다.'}</span></div></div></article>`;
    }).join('')}</div></section>`).join('') : '<div class="empty" style="grid-column:1/-1"><b>현재 확인된 성과 리스크가 없습니다.</b><br>모든 PDM 지표가 목표를 달성했습니다.</div>';

    renderDashboardIndicatorList(indicators);
    byId('pdmBig').innerHTML = `${counts.ok}<small>/${indicators.length}</small>`;
    byId('pdmKl').textContent = tr('ui.dashboard.indicator_status', '지표 달성 · 미달 {under} · 주의 {watch} · 실적 미확인 {unset}', counts);
    renderDashboardInsights();
  }

  function renderPdmData(data) {
    intake.pdm = data || { tiers: [], assignments: [], performance_indicators: [] };
    const tiers = intake.pdm.tiers || [];
    pdmCoverage = intake.pdm.coverage || { filled: 0, total: 0, complete_tiers: 0, tier_total: 0 };
    const percent = Math.round(pdmCoverage.filled / Math.max(1, pdmCoverage.total) * 100);
    byId('statPdm').innerHTML = `${pdmCoverage.filled}<span>/${pdmCoverage.total}</span>`;
    byId('statPdmBar').style.width = `${percent}%`;
    const pdmEvidenceCount = byId('pdmEvCnt');
    if (pdmEvidenceCount) pdmEvidenceCount.textContent = `${pdmCoverage.filled}/${pdmCoverage.total}`;
    byId('covPdm').innerHTML = `<div class="stat"><div class="sl">검증수단 확보</div><div class="sv num">${pdmCoverage.filled}<span>/${pdmCoverage.total}</span></div><div class="ss">전체 대비 ${percent}%</div></div><div class="stat"><div class="sl">미확보</div><div class="sv bad">${Math.max(0, pdmCoverage.total - pdmCoverage.filled)}</div><div class="ss">지표 실적 인정 근거 보완</div></div><div class="stat"><div class="sl">완전 충족 계층</div><div class="sv num">${pdmCoverage.complete_tiers || 0}<span>/${pdmCoverage.tier_total || tiers.length}</span></div><div class="ss">영향 · 성과 · 산출물</div></div>`;
    byId('covPdmNote').innerHTML = intake.pdm.source_document
      ? `최신 PDM 원본 <a href="${downloadUrl(intake.pdm.source_document.id)}" download><b>${esc(intake.pdm.source_document.file_name)}</b></a>의 검증수단을 그대로 사용합니다.`
      : 'PDM 원본 표를 아직 찾지 못했습니다.';
    byId('slotSecPdm').innerHTML = tiers.length ? tiers.map((tier) => {
      const sorted = [...tier.indicators].sort((a, b) => Number(Boolean(a.evidence_documents?.length)) - Number(Boolean(b.evidence_documents?.length)));
      const have = tier.indicators.filter((item) => item.evidence_documents?.length).length;
      return `<div class="slotsec"><div class="slotsec-h"><div class="nm">${esc(tier.name)}</div><div class="cov"><span>확보 ${have}/${tier.indicators.length}</span></div></div><div class="slotbody">${sorted.map((indicator) => {
        const documents = indicator.evidence_documents || [];
        return `<div class="slotrow ${documents.length ? '' : 'missrow'}"><span class="ck ${documents.length ? 'on' : 'off'}">${documents.length ? '✓' : '·'}</span><span class="sn"><b>${esc(indicator.code)}</b> ${esc(indicator.mov)}<small style="display:block;color:var(--muted)">${esc(indicator.text)}</small></span>${documents.length ? documents.map((doc) => `<a class="filechip" href="${downloadUrl(doc.id)}" download><span class="t">${esc(doc.file_name)}</span></a>`).join('') : '<span class="miss">미확보</span><button class="up" data-live-upload>업로드</button>'}</div>`;
      }).join('')}</div></div>`;
    }).join('') : '<div class="empty"><b>PDM 원본 표가 아직 분석되지 않았습니다.</b><br>PDM PDF를 등록하면 검증수단별 증빙이 표시됩니다.</div>';

    const tierRows = tiers.map((tier) => tier.indicators.map((indicator, index) => {
      return `<tr class="${index === 0 ? 'tier-first' : ''}">${index === 0 ? `<td rowspan="${tier.indicators.length}" class="tiercell"><span class="tiername">${esc(tier.name)}</span><span class="tieren">${esc(tier.id)}</span></td>` : ''}<td class="sum">${index === 0 ? lineText(tier.summary) : ''}</td><td class="ind"><b>${esc(indicator.code)}</b> ${esc(indicator.text)}</td><td class="mov">${esc(indicator.mov)}</td><td class="asm">${index === 0 ? lineText(tier.assumption) : ''}</td></tr>`;
    }).join('')).join('');
    const sourceCells = intake.pdm.source_cells || {};
    const supportRows = (sourceCells.activities || sourceCells.inputs) ? [
      { label: 'Activities', ko: tr('ui.overview.activity', '활동'), css: 'activity', value: sourceCells.activities, assumption: sourceCells.preconditions },
      { label: 'Inputs', ko: tr('ui.overview.input', '투입'), css: 'input', value: sourceCells.inputs, assumption: '' },
    ].map((item) => `<tr class="tier-first support-tier-row"><td class="tiercell"><span class="tier ${item.css}">${currentLocale() === 'en' ? item.label : `${item.label}(${esc(item.ko)})`}</span></td><td class="sum">${lineText(item.value || tr('ui.overview.source_text_required', 'PDM 원문에서 확인 필요'))}</td><td class="ind">—</td><td class="mov">—</td><td class="asm">${lineText(item.assumption || '—')}</td></tr>`).join('') : '';
    const pdmRows = `${tierRows}${supportRows}`;
    byId('pdmBody').innerHTML = pdmRows || `<tr><td colspan="5"><div class="empty">${esc(tr('ui.overview.pdm_empty', 'PDM 데이터가 없습니다.'))}</div></td></tr>`;
    const overviewView = byId('v-proj-overview');
    if (overviewView) {
      const actions = overviewView.querySelector('.vhead .acts');
      if (actions) {
        actions.innerHTML = intake.pdm.source_document
          ? `<a class="btn" href="${downloadUrl(intake.pdm.source_document.id)}" download>${esc(tr('ui.overview.download_pdm', 'PDM 원본 다운로드'))}</a>`
          : '';
      }
      const readinessPanel = overviewView.querySelector('.grid.g2 .panel:nth-child(2)');
      const readinessSubtitle = readinessPanel?.querySelector('.psub');
      if (readinessSubtitle) readinessSubtitle.textContent = tr('ui.overview.pdm_connection', '지표 · 검증수단 · 증빙 연결 상태');
      const readiness = overviewView.querySelector('.grid.g2 .panel:nth-child(2) .minilist');
      if (readiness) readiness.innerHTML = `<div class="minirow"><span class="mn">${esc(tr('ui.overview.ovi_count', 'PDM 객관적 검증지표'))}</span><span class="mv num">${pdmCoverage.total}</span></div><div class="minirow"><span class="mn">${esc(tr('ui.overview.evidence_secured', '검증수단 증빙 확보'))}</span><div class="pbar" style="max-width:140px"><i class="${percent >= 70 ? 'g' : 'w'}" style="width:${percent}%"></i></div><span class="mv num">${pdmCoverage.filled}/${pdmCoverage.total}</span></div><div class="minirow"><span class="mn">${esc(tr('ui.overview.evidence_missing', '미확보 검증수단'))}</span><span class="mv num">${Math.max(0, pdmCoverage.total - pdmCoverage.filled)}</span></div>`;
      const readinessCallout = readinessPanel?.querySelector('.callout p');
      if (readinessCallout) readinessCallout.textContent = tr(
        'ui.overview.readiness_note',
        '미확보 검증수단 {count}건은 성과 리스크 분석에서 상세를 확인할 수 있습니다.',
        { count: Math.max(0, pdmCoverage.total - pdmCoverage.filled) }
      );
    }
    renderPerformanceIndicators(intake.pdm);
    renderEvidenceCoverage();
  }

  function renderProjectOverview(data) {
    projectOverview = data;
    const view = byId('v-proj-overview');
    if (!view) return;
    const panel = view.querySelector('.grid.g2 .panel:first-child');
    if (!panel) return;
    // This subtitle contains a document link; static translation must not replace it.
    panel.querySelector('.psub').removeAttribute('data-i');
    if (!data || data.status !== 'completed' || !data.overview) {
      panel.querySelector('.psub').textContent = tr('ui.overview.plan_analysis_wait', '사업계획서 분석 후 사업 기본정보가 표시됩니다.');
      panel.querySelector('.fileinfo').innerHTML = `<div class="empty" style="grid-column:1/-1">${esc(tr('ui.overview.generation_wait', '사업개요 생성 대기 중입니다.'))}</div>`;
      return;
    }
    const overview = data.overview;
    const value = (key) => overview[key]?.text || tr('ui.overview.confirm_required', '확인 필요');
    const planSource = data.project_plan_source_document;
    panel.querySelector('.psub').innerHTML = planSource
      ? `${esc(tr('ui.overview.plan_basis', '사업계획서 근거'))} <a href="${downloadUrl(planSource.id)}" download><u>${esc(planSource.file_name)}</u></a>`
      : esc(tr('ui.overview.plan_missing', '사업 기본정보의 근거 사업계획서를 아직 찾지 못했습니다.'));
    panel.querySelector('.fileinfo').innerHTML = [
      [tr('ui.overview.project_name', '사업명'), value('project_name')],
      [tr('ui.overview.project_manager', '사업책임자'), value('project_manager')],
      [tr('ui.overview.lead_implementer', '주관 수행기관'), value('lead_implementer')],
      [tr('ui.overview.country_region', '국가 · 지역'), `${value('country')} · ${value('location')}`],
      [tr('ui.overview.period_budget', '기간 · 예산'), `${value('period')} · ${value('budget')}`],
      [tr('ui.overview.donor', '지원기관'), value('donor')],
      [tr('ui.overview.implementer', '수행기관'), value('implementer')],
      [tr('ui.overview.partner', '협력기관'), value('partner')],
      [tr('ui.overview.objective', '사업목적'), value('objective')],
      [tr('ui.overview.beneficiaries', '주요 수혜자'), value('beneficiaries')],
      [tr('ui.overview.activities', '주요 활동'), value('activities')],
      [tr('ui.overview.outputs_outcomes', '주요 산출물·성과'), `${value('outputs')}\n${value('outcomes')}`]
    ].map(([label, text]) => `<div class="k">${esc(label)}</div><div>${lineText(text)}</div>`).join('');
    const conflictCount = (data.conflicts || []).length;
    const callout = view.querySelector(':scope > .callout:last-child');
    if (callout) callout.innerHTML = `<span class="ci">i</span><p>${esc(tr('ui.overview.plan_source_note', '사업 기본정보는 사업계획서만을 근거로 작성합니다. 성과지표와 검증수단은 PDM을 기준으로 표시합니다.'))}${conflictCount ? ` ${esc(tr('ui.overview.source_conflicts', '문서 간 충돌 {count}건은 원문 확인이 필요합니다.', { count: conflictCount }))}` : ''}</p>`;
    setProjectIdentity({ project: {
      business_name: value('project_name'), period: value('period'), budget: value('budget'),
      country: value('country'), location: value('location'), donor: value('donor'),
      implementer: value('implementer')
    } });
  }

  async function refreshProjectOverview() {
    try {
      const data = await request('/api/v2/project-overview');
      renderProjectOverview(localizedView('project_overview', data));
    }
    catch (error) { console.error(error); }
  }

  function renderDacSlots() {
    const source = projectIsEmpty ? { criteria: [], items: [] } : intake.slots;
    const { criteria = [], items = [] } = source;
    const assigned = new Set(items.map((item) => item.document_id)).size;
    const required = criteria.reduce((sum, item) => sum + (item.slots || []).length, 0);
    const filled = criteria.reduce((sum, criterion) => sum + new Set(items.filter((item) => item.criterion === criterion.id).map((item) => item.slot_id)).size, 0);
    const percent = Math.round(filled / Math.max(1, required) * 100);
    dacCoverage = { filled, total: required, assigned };
    byId('statDac').innerHTML = `${filled}<span>/${required}</span>`;
    byId('statDacBar').style.width = `${percent}%`;
    byId('boardEv').innerHTML = `${filled}<small>/${required}</small>`;
    byId('covDac').innerHTML = `<div class="stat"><div class="sl">필수 슬롯 확보</div><div class="sv num">${filled}<span>/${required}</span></div><div class="ss">전체 대비 ${percent}%</div></div><div class="stat"><div class="sl">미확보</div><div class="sv bad">${Math.max(0, required - filled)}</div><div class="ss">분석 보완 필요</div></div><div class="stat"><div class="sl">연결 문서</div><div class="sv num">${assigned}</div><div class="ss">중복 제외</div></div>`;
    byId('covDacNote').innerHTML = `미확보 슬롯은 <b data-go="#/eval/results">분석 결과</b>의 근거 부족 항목과 연결됩니다`;
    byId('slotSecDac').innerHTML = criteria.map((criterion) => {
      const criterionItems = items.filter((item) => item.criterion === criterion.id);
      const slots = criterion.slots.map((slot) => {
        const docs = criterionItems.filter((item) => item.slot_id === slot.id);
        return `<div class="slotrow ${docs.length ? '' : 'missrow'}"><span class="ck ${docs.length ? 'on' : 'off'}">${docs.length ? '✓' : '·'}</span><span class="sn">${esc(slot.title)}</span>${docs.length ? docs.map((doc) => `<a class="filechip" href="${downloadUrl(doc.document_id)}" download><span class="t">${esc(doc.original_name)}</span></a>`).join('') : '<span class="miss">미확보</span><button class="up" data-live-upload>업로드</button>'}</div>`;
      }).join('');
      return `<div class="slotsec"><div class="slotsec-h"><div class="nm">${esc(criterion.name)}</div><div class="cov"><span>연결 ${criterionItems.length}건</span></div></div><div class="slotbody">${slots}</div></div>`;
    }).join('') || '<div class="empty"><b>등록된 DAC 증빙이 없습니다.</b><br>자료 업로드 후 자동 분류 결과가 표시됩니다.</div>';
    renderEvidenceCoverage();
  }

  function renderRecentUploads() {
    const recent = intake.jobs.slice(0, 5);
    byId('spRecent').innerHTML = recent.length ? recent.map((job) => `<div class="uprow"><span class="ext">${esc(String(job.file_name || '').split('.').pop().toUpperCase())}</span><span class="fn2">${esc(job.file_name)}</span><span class="stt">${job.status === 'awaiting_review' ? '처리 방식 선택 필요' : esc(job.stage || job.status)}</span></div>`).join('') : '<div class="empty" style="padding:16px">아직 없습니다. 파일을 올리면 여기에 처리 상태가 표시됩니다.</div>';
  }

  const pdmRefresh = window.ServicePdmRefresh.create({
    request, notify,
    update: (job) => window.ServiceJobTray?.update('pdm', {...job,restored:true}),
    button: (active) => { const el=byId('indRefresh'); el.disabled=active; el.textContent=active ? '증빙 내용·성과 분석 중…' : '✦ 성과지표 분석'; },
    refreshViews: async () => {
      const pdm = await request('/api/v2/pdm', {timeoutMs:15000});
      intake.pdm = pdm;
      renderPdmData(pdm);
      await refreshLocalizedProjectViews(currentLocale(), true);
    }
  });

  const performanceReview = window.PerformanceAnalysisReview.create({
    request, start: review => pdmRefresh.start(review), refreshIntake, notify, escapeHtml: esc
  });

  async function refreshIntake() {
    if (intakeRefreshPromise) return intakeRefreshPromise;
    intakeRefreshPromise = loadIntake();
    try { return await intakeRefreshPromise; } finally { intakeRefreshPromise = null; }
  }

  window.ServiceJobTray?.configure(async (id, action) => {
    if (id.startsWith('translation:')) {
      try {
        await request(`/api/v2/project/translations/${encodeURIComponent(id.slice(12))}/${action}`, {method:'POST'});
        localizedViewsBundle=null;
        notify(action==='cancel'?'화면 번역 중지를 요청했습니다.':'화면 번역을 재요청했습니다.');
      } catch(error) { notify(error.message); }
      return;
    }
    if (action === 'review') {
      fileFilter='all'; fileQuery=''; fileShowAll=true; location.hash='#/evidence'; renderFiles();
      const details = [...document.querySelectorAll('[data-triage]')].find(el=>el.dataset.triage===id);
      if (details) { details.open=true; details.scrollIntoView({block:'center'}); }
      return;
    }
    try {
      await request(`/api/v2/intake/jobs/${encodeURIComponent(id)}/${action}`, {method:'POST'});
      await refreshIntake();
      notify(action === 'cancel' ? '문서 분석 중지를 요청했습니다.' : '최신 연결 모델로 분석을 재요청했습니다.');
    } catch (error) { notify(error.message); }
  });

  async function loadIntake() {
    try {
      const [jobs, slots, pdm, foundation] = await Promise.all([
        window.ServiceIntake.listAll(request).then(jobs => { window.ServiceJobTray?.syncIntake(jobs.items || []); return jobs; }), request('/api/v2/intake/document-slots'),
        request('/api/v2/pdm'), request('/api/v2/intake/foundation')
      ]);
      foundationUpload.render(foundation);
      const displayPdm = localizedView('pdm', pdm);
      intake = { jobs: jobs.items || [], slots, pdm: displayPdm };
      if (intake.jobs.length) setEmptyProjectViews(false);
      clearManualAssignmentState();
      const renderers = [
        ['업로드 문서', renderFiles], ['최근 업로드', renderRecentUploads],
        ['PDM 증빙', () => renderPdmData(displayPdm)], ['DAC 증빙', renderDacSlots]
      ];
      renderers.forEach(([label, renderer]) => {
        try { renderer(); } catch (error) { console.error(`${label} 화면 렌더링 실패`, error); }
      });
    } catch (error) {
      console.error('자료 목록 조회 실패', error);
      foundationUpload.render(null);
      console.error('자료 목록을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.');
    }
  }

  async function uploadFiles(files) {
    if (!files || !files.length) return;
    if (!foundationUpload.canUpload()) return;
    if (uploadBusy) { notify('현재 선택한 파일을 접수하고 있습니다. 완료 후 추가해 주세요.'); return; }
    uploadBusy = true;
    const dropzone = byId('dropzone');
    dropzone.classList.add('drag');
    let panel = byId('uploadResult');
    if (!panel) { panel = document.createElement('section'); panel.id = 'uploadResult'; panel.className = 'panel'; panel.setAttribute('aria-live', 'polite'); panel.style.cssText = 'margin-top:12px;padding:16px;overflow-wrap:anywhere'; dropzone.after(panel); }
    byId('uploadBtn').disabled = true;
    try {
      const result = await window.ServiceIntake.uploadBatch(request, files, (index, total, name) => { panel.textContent = `파일 접수 ${index}/${total} · ${name}`; });
      uploadFailures = result.failed;
      const summary = `새로 접수 ${result.accepted}건 · 기존 동일 파일 ${result.duplicates}건 · 미접수 ${result.failed.length}건`;
      panel.innerHTML = `<b>업로드 결과</b><p>${summary}</p>${result.failed.length ? `<ul>${result.failed.map(item => `<li><b>${esc(item.file.name)}</b> — ${esc(item.error)}</li>`).join('')}</ul><button class="btn sm" data-retry-upload>미접수 파일만 다시 업로드</button>` : '<p>접수한 파일은 순서대로 분석합니다. 분석 상태는 아래 목록에서 확인할 수 있습니다.</p>'}`;
      notify(summary);
    } catch (error) {
      panel.textContent = error.message;
    } finally {
      uploadBusy = false;
      byId('uploadBtn').disabled = false;
      dropzone.classList.remove('drag');
      byId('bulkFileInput').value = '';
      await refreshIntake();
    }
  }

  function drawLiveRadar(items) {
    const criteria = ['relevance', 'coherence', 'effectiveness', 'efficiency', 'sustainability'].map((id) => {
      const found = items.find((item) => item.id === id);
      return { id, name: found?.name || criterionNames[id], score: found?.score == null ? null : Number(found.score) };
    });
    ['radar', 'radar2'].forEach((id) => {
      const svg = byId(id);
      if (!svg) return;
      const cx = 200, cy = 155, radius = 106, count = criteria.length;
      const point = (index, r) => {
        const angle = (-90 + index * 360 / count) * Math.PI / 180;
        return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
      };
      const polygon = (r) => criteria.map((_, index) => point(index, r).join(',')).join(' ');
      let markup = '';
      for (let grid = 1; grid <= 4; grid += 1) markup += `<polygon points="${polygon(radius * grid / 4)}" fill="none" stroke="#E4EAF1"/>`;
      criteria.forEach((_, index) => { const [x, y] = point(index, radius); markup += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#E4EAF1"/>`; });
      if (criteria.every(item => Number.isFinite(item.score))) {
        markup += `<polygon points="${criteria.map((item, index) => point(index, radius * item.score / 4).join(',')).join(' ')}" fill="rgba(79,179,232,.18)" stroke="#4FB3E8" stroke-width="2"/>`;
      } else {
        criteria.forEach((item, index) => { if (Number.isFinite(item.score)) { const [x, y] = point(index, radius * item.score / 4); markup += `<circle cx="${x}" cy="${y}" r="4" fill="#1173A8"/>`; } });
      }
      criteria.forEach((item, index) => { const [x, y] = point(index, radius + 21); markup += `<text x="${x}" y="${y + 4}" font-size="11.5" font-weight="600" fill="#63788C" text-anchor="${Math.abs(x - cx) < 6 ? 'middle' : x < cx ? 'end' : 'start'}">${esc(item.name)} <tspan font-weight="800" fill="#1173A8">${item.score ?? '보류'}</tspan></text>`; });
      svg.innerHTML = markup;
    });
  }

  function evidenceLinks(documents) {
    return documents?.length ? documents.map((doc) => `<a class="filechip" href="${downloadUrl(doc.id)}" download><span class="t">${esc(doc.file_name)}</span></a>`).join('') : '<span class="miss">연결 문서 없음</span>';
  }

  function evidenceFold(documents) {
    const items = documents || [];
    return `<details class="evidence-fold"><summary><span class="fold-closed">증빙 자료 ${items.length}건 펼치기</span><span class="fold-open">증빙 자료 ${items.length}건 접기</span></summary><div class="csec-foot">${evidenceLinks(items)}</div></details>`;
  }

  function formatDacScore(value) {
    if (value === null || value === undefined || value === '') return '보류';
    const score = Number(value);
    if (!Number.isFinite(score)) return '-';
    return Number.isInteger(score) ? String(score) : score.toFixed(1);
  }

  function syncDashboardDac(data) {
    // A status/dashboard response cannot establish that no evaluation exists.
    if (!evaluationLoaded) return;
    const items = (data?.criteria || []).filter((item) => item.id !== 'impact');
    const overall = data?.overall || {};
    const provisional = overall.assessment_basis === 'provisional_document_review';
    const isHeld = data?.status === 'completed' && items.some(item => item.score == null);
    const hasScore = overall.score !== null && overall.score !== undefined && overall.score !== '' && Number.isFinite(Number(overall.score));
    const dacValue = document.querySelector('#v-dashboard .herocard.dac .hckpi > b');
    const dacLabel = document.querySelector('#v-dashboard .herocard.dac .hckpi .hkl');
    const dacSubtitle = document.querySelector('#v-dashboard .herocard.dac .psub');
    if (dacValue) dacValue.innerHTML = hasScore
      ? `${formatDacScore(overall.score)}<small>/20</small>`
      : (isHeld ? '판정보류' : esc(tr('ui.dashboard.not_evaluated', '평가 전')));
    if (dacLabel) dacLabel.innerHTML = hasScore
      ? (provisional ? `내부 잠정 진단 · 환산등급 <span class="grade">${esc(overall.koica_grade || '-')}</span>` : `${esc(tr('ui.dashboard.overall_score', '종합점수'))} · KOICA <span class="grade">${esc(overall.koica_grade || '-')}</span> · ${esc(tr('ui.dashboard.government_grade', '국무조정실'))} ${esc(overall.government_grade || '-')}`)
      : (isHeld ? '자료 보완이 필요한 항목이 있어 종합점수 판정을 보류합니다' : tr('ui.dashboard.evaluation_prompt', 'DAC 평가진단을 실행하면 종합점수가 표시됩니다'));
    if (dacSubtitle) dacSubtitle.textContent = hasScore
      ? (provisional ? overall.notice : (overall.formula || 'DAC 5개 기준의 질문별 1~4점 평균 합산'))
      : tr('ui.dashboard.evaluation_source', '등록 자료를 기준으로 DAC 평가진단을 실행합니다');
    const evaluationState = window.DacScoringUI.evaluationState(data, latestEvaluationStatus);
    if (evaluationState.title && dacSubtitle) dacSubtitle.textContent = `${evaluationState.title} · ${evaluationState.detail}`;
    const target = byId('dacReady');
    if (target) target.innerHTML = items.length ? items.map((item) => `
      <div class="minirow" data-go="#/eval/results">
        <span class="mn">${esc(item.name)}</span>
        <span class="mv num">${formatDacScore(item.score)}<small>/4</small></span>
      </div>`).join('') : `<div class="empty" style="border:none">${esc(tr('ui.dashboard.evaluation_empty', '아직 생성된 DAC 평가진단 결과가 없습니다.'))}</div>`;
    drawLiveRadar(items);
  }

  function syncEvaluationState() {
    const state = window.DacScoringUI.evaluationState(latestEvaluationData, latestEvaluationStatus);
    if (!evaluationLoaded || evaluationLoadError) {
      state.title = evaluationLoadError ? (evaluationLoaded ? '평가 결과 갱신 실패' : '평가 결과 조회 실패') : '평가 결과 불러오는 중';
      state.detail = evaluationLoadError
        ? `${evaluationLoaded ? '마지막으로 확인한 결과를 표시합니다. ' : ''}${evaluationLoadError} · 새로고침해 주세요.`
        : '저장된 점수와 근거를 확인하고 있습니다.';
    }
    for (const id of ['dacEvaluationState', 'dacResultState']) {
      const node = byId(id);
      if (!node) continue;
      node.hidden = !state.title;
      node.textContent = `${state.title} · ${state.detail}`;
    }
    const provisional = latestEvaluationData.overall?.assessment_basis === 'provisional_document_review';
    const labels = document.querySelectorAll('#v-eval-board .statrow .sl');
    const names = provisional ? ['내부 잠정 종합점수', '참고 환산등급 (잠정)', '참고 판정 (잠정)']
      : ['종합점수', 'KOICA 평가등급', '국무조정실 평가등급'];
    names.forEach((name, index) => { if (labels[index]) labels[index].textContent = `${state.historical ? '이전 완료 평가 · ' : ''}${name}`; });
    const basis = byId('dacScoreBasis');
    if (basis) basis.textContent = evaluationLoaded
      ? `${state.historical ? '이전 완료 평가 점수' : '마지막 완료 평가 점수'} · 목표 4점 대비 · 칩을 누르면 분석 결과로 이동`
      : '저장된 평가 결과를 확인한 뒤 기준별 점수를 표시합니다.';
    renderWorkflowSteps(latestWorkflowSteps);
  }

  function dacQuestionEvidence(question) {
    const review = question.document_review;
    const pdm = question.pdm_context;
    const pdmCoverage = pdm?.status === 'completed'
      ? `<div class="meta2">PDM 지표 ${Number(pdm.indicator_count || 0)}건 함께 검토 · 이 질문에 활용한 지표 ${(pdm.used_indicator_ids || []).length}건</div>` : '';
    const coverage = review?.method === 'fulltext_chunks'
      ? `<div class="meta2">관련 문서 ${Number(review.document_count || 0)}건의 본문 전체 검토</div>` : '';
    return window.DacScoringUI.render(question, esc) + coverage + pdmCoverage + evidenceFold(question.evidence_documents);
  }

  function renderEvaluation(data) {
    evaluationLoaded = true;
    evaluationLoadError = '';
    byId('dacScoreSummary')?.setAttribute('aria-busy', 'false');
    latestEvaluationData = data || { status: 'not_run', criteria: [], overall: null };
    data = latestEvaluationData;
    const items = (data.criteria || []).filter((item) => item.id !== 'impact');
    syncDashboardDac(latestEvaluationData);
    const scored = items.filter((item) => item.scored);
    const total = scored.reduce((sum, item) => sum + Number(item.score || 0), 0);
    const average = scored.length ? (total / scored.length).toFixed(1) : '-';
    const stats = document.querySelectorAll('#v-eval-board .statrow .sv');
    const provisional = data.overall?.assessment_basis === 'provisional_document_review';
    const statLabels = document.querySelectorAll('#v-eval-board .statrow .sl');
    if (statLabels[0]) statLabels[0].textContent = provisional ? '내부 잠정 종합점수' : '종합점수';
    if (statLabels[1]) statLabels[1].textContent = provisional ? '참고 환산등급 (잠정)' : 'KOICA 평가등급';
    if (statLabels[2]) statLabels[2].textContent = provisional ? '참고 판정 (잠정)' : '국무조정실 평가등급';
    const hasOverallScore = data.overall?.score !== null && data.overall?.score !== undefined && data.overall?.score !== '' && Number.isFinite(Number(data.overall?.score));
    if (stats[0]) stats[0].innerHTML = hasOverallScore ? `${formatDacScore(data.overall.score)}<span>/20</span>` : (data.status === 'completed' ? '판정보류' : '평가 전');
    if (stats[1]) stats[1].textContent = data.overall?.koica_grade || '-';
    if (stats[2]) stats[2].textContent = data.overall?.government_grade || '-';
    const statNotes = document.querySelectorAll('#v-eval-board .statrow .ss');
    if (statNotes[0]) statNotes[0].textContent = 'DAC 5대 기준 합산';
    if (statNotes[1]) statNotes[1].textContent = scored.length === 5 ? `5대 기준 평균 ${average}점` : `점수 판정 ${scored.length}/5개 기준 · 나머지 판정보류`;
    if (statNotes[2]) statNotes[2].textContent = '종합 정성 등급';
    byId('scorechips2').innerHTML = items.filter((item) => item.id !== 'impact').map((item) => `<button class="schip" data-go="#/eval/results"><div class="nm">${esc(item.name)}</div><div class="sc num">${item.score == null ? '판정보류' : `${formatDacScore(item.score)}<small>/4</small>`}</div></button>`).join('');
    byId('critSections').innerHTML = items.length ? items.map((criterion) => `<div class="csec"><div class="csec-h"><div class="nm">${esc(criterion.name)}</div><div class="hbar"><div class="pbar"><i class="${Number(criterion.score || 0) < 3 ? 'w' : 'g'}" style="width:${Math.round(Number(criterion.score || 0) / 4 * 100)}%"></i></div></div><span class="tag ${Number(criterion.score || 0) < 3 ? 'w' : 'g'}">${criterion.scored ? '근거 평가 완료' : '자료보완 · 판정보류'}</span><span class="scr num">${criterion.score ?? '-'}<small> /4</small></span></div><div class="csec-b">${window.DacScoringUI.renderImprovements(criterion, esc)}${(criterion.question_assessments || []).map((question, index) => `<div class="qrow"><span class="qno">Q${index + 1}</span><div class="qbody"><div class="qq">${esc(question.question)}</div><div class="qa"><b>근거 판단</b> · ${esc(question.finding)}</div>${question.evidence_gaps?.length ? `<div class="qlost w">${question.evidence_gaps.map(esc).join(' · ')}</div>` : ''}${dacQuestionEvidence(question)}</div><div class="qmeta"><span class="qscore num">${question.score ?? '보류'}<small> /4</small></span></div></div>`).join('') || `<div class="qrow"><div class="qbody">${esc(criterion.score_reason || criterion.summary || '분석 내용이 없습니다.')}${evidenceFold(criterion.evidence_documents)}</div></div>`}</div></div>`).join('') : '<div class="panel empty evaluation-empty"><b>아직 생성된 분석 결과가 없습니다.</b><br>등록 문서의 처리가 끝난 뒤 재평가를 실행하면 DAC 기준별 점수와 판단 근거가 표시됩니다.<div style="margin-top:14px"><button class="btn primary" data-go="#/eval/board">DAC 평가진단으로 이동</button></div></div>';
    renderDashboardInsights();
    syncEvaluationState();
  }

  async function refreshEvaluation() {
    try {
      const data = await request('/api/v2/evaluations');
      renderEvaluation(localizedView('evaluation', data));
    } catch (error) {
      evaluationLoadError = error.message;
      byId('dacScoreSummary')?.setAttribute('aria-busy', 'false');
      if (!evaluationLoaded) {
        document.querySelectorAll('#v-eval-board .statrow .ss').forEach((note, index) => {
          if (index < 3) note.textContent = '평가 결과 조회 실패';
        });
        byId('critSections').innerHTML = `<div class="empty">${esc(error.message)}</div>`;
      }
      syncEvaluationState();
    }
  }

  async function refreshEvaluationStatus() {
    try {
      const status = await request('/api/v2/evaluations/status');
      latestEvaluationStatus = status;
      syncEvaluationState();
      syncDashboardDac(latestEvaluationData);
      const dacStage = {overview:'사업개요 확인',evidence:'선택 원문 검토·자동 복구',questions:'질문별 근거 판정',saving:'검증 결과 저장',needs_retry:'일부 항목 재시도 필요'}[status.current_stage] || '평가 준비';
      const active = Boolean(status.active);
      window.ServiceJobTray?.update('dac', { name: 'DAC 평가', active, failed: status.status === 'failed', completed: status.completed_criteria, total: status.total_criteria,
        detail: active ? `${dacStage} · ${status.completed_criteria}/${status.total_criteria}단계 · 검증 질문 ${status.completed_questions || 0}개(재사용 ${status.reused_questions || 0}개) · 원본 ${status.document_count}개` : status.status === 'failed' ? `${status.error_message || '평가 미완료'} · 검증 완료 질문 ${status.completed_questions || 0}개와 완료 원문 구간 보존. 재평가 시 입력이 같은 질문은 재사용하고 변경·미완료 질문을 검토합니다.` : `평가 결과 저장 완료 · 검증 결과 재사용 ${status.reused_questions || 0}개` });
      [byId('runBtn'), byId('runBtn2')].forEach((button) => {
        if (!button) return;
        button.disabled = active || (!active && !status.can_start && Number(status.processing_document_count || 0) === 0);
        button.textContent = active ? `✦ 분석 단계 ${status.completed_criteria}/${status.total_criteria}` : '✦ DAC 근거 분석·평가';
      });
      const message = active ? `${status.document_count}개 문서 분석 중` : status.status === 'failed' ? `평가 중단 · ${status.error_message || '다시 평가해 주세요.'}` : Number(status.processing_document_count || 0) > 0 ? `문서 처리 ${status.completed_document_count}/${status.document_count}` : status.completed_at ? `최근 완료 ${new Date(status.completed_at).toLocaleString('ko-KR')}` : '분석 실행 대기';
      byId('pendAnalyze').textContent = message;
      byId('stPend').textContent = message;
      if (!active && evaluationWasActive) {
        await refreshLocalizedProjectViews(currentLocale(), true);
        await Promise.all([refreshEvaluation(), refreshDashboard()]);
      }
      evaluationWasActive = active;
    } catch (error) {
      byId('pendAnalyze').textContent = error.message;
    }
  }

  let dacReviewDialog;
  async function startEvaluation() {
    dacReviewDialog ||= window.DacAnalysisReview.create({request, start:submitEvaluation, refreshIntake:async()=>{}, notify, escapeHtml:esc});
    await dacReviewDialog.open();
  }
  async function submitEvaluation(review) {
    try {
      const job = await request('/api/v2/evaluations', { method: 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(review) });
      evaluationWasActive = true;
      await refreshEvaluationStatus();
      return job;
    } catch (error) { notify(error.message); return null; }
  }

  function renderReportList() {
    byId('seclist').innerHTML = reportSections.map((section) => {
      const state = ['generating', 'failed'].includes(section.status) ? section.status : String(section.content || '').trim() ? section.status : 'empty';
      const badge = ['generating', 'failed', 'empty'].includes(state) ? `<span class="st ${state === 'generating' ? 'draft' : 'rev'}">${reportNames[state]}</span>` : '';
      return `<button type="button" class="it ${section.part_id === activeReportPart ? 'active' : ''}" data-id="${esc(section.part_id)}" aria-current="${section.part_id === activeReportPart ? 'true' : 'false'}" title="${esc(section.title)}"><span class="no num">${section.section_number}</span><span>${esc(section.title.replace(/^\(\d+\)\s*/, ''))}</span>${badge}</button>`;
    }).join('');
    renderReportSummary();
  }

  async function refreshReportLifecycle(force = false) {
    if (reportLifecyclePromise) return reportLifecyclePromise;
    if (!force && Date.now() - reportLifecycleCheckedAt < 12000) return;
    reportLifecyclePromise = request('/api/v2/project/lifecycle', { timeoutMs: 15000 }).then((value) => {
      reportLifecycle = value;
      reportLifecycleCheckedAt = Date.now();
      const target = byId('reportLifecycle');
      target.hidden = false;
      target.dataset.state = value.evaluation_stale ? 'uncertain' : value.phase;
      const action = value.phase === 'evaluation_required' ? '<button class="btn sm" data-go="#/eval/board" style="margin-left:10px">DAC 재평가로 이동</button>' : value.phase === 'empty_project' ? '<button class="btn sm" data-go="#/evidence" style="margin-left:10px">자료 업로드</button>' : '';
      target.innerHTML = `<b>자료 → 평가 → 보고서</b><br>${esc(value.message)}${action}${value.stale_section_ids?.length ? `<br>최신 자료 반영이 필요한 섹션 ${value.stale_section_ids.length}개 · 이전 초안은 보존됩니다.` : ''}`;
      renderSectionAssistant(reportSections.find((item) => item.part_id === activeReportPart));
    }).catch((error) => {
      byId('reportLifecycle').hidden = false;
      byId('reportLifecycle').textContent = `자료·평가 최신 상태를 확인하지 못했습니다. 서버에서 생성 가능 여부를 다시 검증합니다. ${error.message}`;
    }).finally(() => { reportLifecyclePromise = null; });
    return reportLifecyclePromise;
  }

  function renderSectionAssistant(section) {
    if (!section || section.part_id !== activeReportPart) return;
    const state = reportFlow.state(section.part_id);
    const busy = reportFlow.busy(section.part_id) || sectionLoadPending === section.part_id;
    const batchActive = reportBatchSubmitting || ['queued', 'running'].includes(latestGenerationStatus?.status);
    const allowed = window.hasMenuPermission?.('evaluation_report') !== false;
    const hasContent = Boolean(String(section.content || '').trim());
    const blocked = window.ReportSectionFlow.generationBlock({ allowed, loading: sectionLoadPending === section.part_id, batchActive, status: state.status, lifecycle: reportLifecycle });
    byId('reportAiTarget').textContent = `선택한 섹션 ${section.section_number || ''} · ${section.title}`;
    byId('aiGen').disabled = Boolean(blocked);
    byId('aiGen').title = blocked?.reason || '현재 선택한 섹션에 수정 요청을 반영합니다.';
    byId('aiGen').textContent = state.status === 'submitting' ? '요청 접수 중…' : state.status === 'generating' ? '✦ AI 작성 중…' : state.status === 'failed' ? '✦ 이 섹션 다시 시도' : hasContent ? '✦ 수정 요청 반영' : '✦ 이 섹션 초안 생성';
    byId('aiPrompt').disabled = busy || batchActive;
    byId('aiCheckStatus').hidden = !blocked && state.status !== 'failed';
    const next = byId('reportAiNextStep');
    next.hidden = !blocked?.action;
    if (blocked?.action) { next.textContent = blocked.action.label; next.dataset.go = blocked.action.href; }
    else delete next.dataset.go;
    const status = byId('reportAiStatus');
    status.dataset.state = blocked ? 'blocked' : state.status;
    status.textContent = blocked ? `수정 요청 대기: ${blocked.reason}` : state.status === 'failed' ? `작성에 실패했습니다. 기존 본문과 수정 요청은 유지됩니다. 오류: ${state.error || '상세 오류를 확인해 주세요.'}` : state.elapsedMs != null ? 'AI 수정이 저장되었습니다. 오른쪽 한글 미리보기에서 결과를 확인해 주세요.' : hasContent ? '현재 본문을 바탕으로 요청한 부분만 수정합니다. 완료하면 저장하고 오른쪽 한글 미리보기를 갱신합니다.' : '요청을 비워 두면 등록된 사업 자료와 섹션 작성 기준에 따라 내용을 생성합니다.';
    const timing = [];
    if (state.acceptedMs != null) timing.push(`접수 ${(state.acceptedMs / 1000).toFixed(1)}초`);
    if (state.elapsedMs != null) timing.push(`완료 확인까지 ${(state.elapsedMs / 1000).toFixed(1)}초`);
    else if (state.startedAt != null && busy) timing.push(`경과 ${Math.max(0, Math.round((performance.now() - state.startedAt) / 1000))}초`);
    byId('reportAiTiming').textContent = timing.join(' · ');
    byId('repGenAll').disabled = Boolean(blocked) || reportSections.some((item) => item.status === 'generating') || busy;
  }

  async function loadReportSection(id, replace = true) {
    const changed = activeReportPart !== id;
    if (changed) sectionPreview.clear();
    if (changed && activeReportPart) reportInstructions.set(activeReportPart, byId('aiPrompt').value);
    activeReportPart = id;
    sectionLoadPending = id;
    byId('aiGen').disabled = true;
    reportFlow.select(id);
    if (changed) byId('aiPrompt').value = reportInstructions.get(id) || '';
    clearTimeout(reportTimer);
    const readToken = reportFlow.beginRead(id);
    renderReportList();
    let section;
    try { section = await request(`/api/v2/report/sections/${encodeURIComponent(id)}`, { timeoutMs: 15000 }); }
    catch (error) {
      if (reportFlow.isCurrent(id, readToken)) {
        // Failed reads must leave a visible retry path, not a silently locked button.
        byId('reportAiStatus').textContent = `섹션을 불러오지 못했습니다. 진행 상태 다시 확인을 눌러 주세요. ${error.message}`;
        byId('reportAiStatus').dataset.state = 'failed';
        byId('aiCheckStatus').hidden = false;
      }
      throw error;
    }
    if (!reportFlow.isCurrent(id, readToken)) return;
    sectionLoadPending = null;
    const renderStarted = performance.now();
    reportFlow.observe(section);
    window.ServiceJobTray?.update(`section:${section.part_id}`, {name:`보고서 섹션 · ${section.title}`, active:section.status==='generating', failed:section.status==='failed', detail:section.error_message || (section.status==='generating' ? 'AI가 본문을 작성·검토하고 있습니다.' : '본문 저장 완료')});
    const sectionIndex = reportSections.findIndex((item) => item.part_id === id);
    if (sectionIndex >= 0) reportSections[sectionIndex] = { ...reportSections[sectionIndex], ...section };
    const metadata = section.generation_metadata || {};
    const lastRequest = String(metadata.user_request || '').trim();
    const qualityIssues = Array.isArray(section.quality_report?.quality_issues) ? [...section.quality_report.quality_issues] : [];
    if (section.quality_score != null && Number(section.quality_score) < 70) qualityIssues.unshift('AI 품질점수가 70점 미만이므로 근거와 서술을 검토해 주세요. 내용 품질 권고와 한글 파일 형식 검증은 별개입니다.');
    byId('reportQualityWarnings').hidden = qualityIssues.length === 0;
    byId('reportQualitySummary').textContent = `내용 검토 권고 ${qualityIssues.length}건 · 파일 형식 검증과 구분`;
    byId('reportQualityBody').textContent = qualityIssues.map((item) => `• ${item}`).join('\n');
    if (section.status !== 'generating' && location.hash === '#/eval/report') {
      sectionPreview.select(id, section.content || '', section.title);
    }
    byId('reportPrompt').textContent = `작성 프롬프트\n${section.prompt || ''}\n\n필수 입력\n${(section.required_inputs || []).map((item) => `• ${item}`).join('\n')}${lastRequest ? `\n\n최근 사용자 수정 요청\n${lastRequest}` : ''}`;
    const documents = section.documents || [];
    byId('reportDocsSummary').textContent = `관련 문서 ${documents.length}건 보기`;
    byId('reportDocs').innerHTML = documents.length ? documents.map((doc) => `<a class="filechip" href="${downloadUrl(doc.id)}" download><span class="t">${esc(doc.original_name)}</span></a>`).join('') : '직접 배정된 관련 문서가 없습니다.';
    byId('reportState').textContent = '';
    renderReportList();
    renderSectionAssistant(section);
    if (latestGenerationStatus) renderGeneration(latestGenerationStatus);
    reportRenderTimes.push(performance.now() - renderStarted);
    if (reportRenderTimes.length > 30) reportRenderTimes.shift();
    if (section.status === 'generating') reportTimer = setTimeout(() => {
      if (activeReportPart === id) loadReportSection(id, false).catch((error) => {
        if (activeReportPart !== id) return;
        byId('reportAiStatus').textContent = `상태 조회 연결이 지연되었습니다. 생성 작업은 계속될 수 있습니다. ${error.message}`;
        byId('aiCheckStatus').hidden = false;
      });
    }, document.hidden ? 10000 : 2500);
  }

  async function refreshReportSections(select) {
    const selectedAtStart = activeReportPart;
    try {
      const response = await request('/api/v2/report/sections');
      reportSections = response.items || [];
      reportSections.forEach(section => window.ServiceJobTray?.update(`section:${section.part_id}`, {name:`보고서 섹션 · ${section.title}`, active:section.status==='generating', failed:section.status==='failed', detail:section.error_message || (section.status==='generating' ? 'AI가 본문을 작성·검토하고 있습니다.' : '본문 저장 완료')}));
      if (location.hash === '#/eval/report') refreshReportLifecycle();
      const selected = select || activeReportPart || reportSections[0]?.part_id;
      renderReportList();
      if (latestGenerationStatus) renderGeneration(latestGenerationStatus);
      // A background save/status refresh must not navigate back over a newer
      // section click made while the list request was in flight.
      if (selected && activeReportPart === selectedAtStart) await loadReportSection(selected, false);
    } catch (error) { byId('reportState').textContent = error.message; }
  }

  async function generateSection() {
    if (!activeReportPart) return;
    const partId = activeReportPart;
    const selected = reportSections.find(item => item.part_id === partId);
    const blocked = window.ReportSectionFlow.generationBlock({ allowed: window.hasMenuPermission?.('evaluation_report') !== false,
      loading: sectionLoadPending === partId, batchActive: reportBatchSubmitting || ['queued', 'running'].includes(latestGenerationStatus?.status),
      status: reportFlow.state(partId).status, lifecycle: reportLifecycle });
    if (!selected || blocked) { renderSectionAssistant(selected); return; }
    if (!reportFlow.begin(partId)) return;
    const instruction = byId('aiPrompt').value.trim();
    const currentContent = selected.content || '';
    reportInstructions.set(partId, instruction);
    byId('reportState').textContent = '현재 본문과 수정 요청을 전달하는 중…';
    renderSectionAssistant(reportSections.find((item) => item.part_id === partId));
    try {
      await refreshReportLifecycle(true);
      if (reportLifecycle?.can_generate_report === false) {
        const error = new Error(reportLifecycle.message);
        error.status = 409;
        throw error;
      }
      await request(`/api/v2/report/sections/${encodeURIComponent(partId)}/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instruction, current_content: currentContent }), timeoutMs: 15000
      });
      reportFlow.accepted(partId);
      window.ServiceJobTray?.update(`section:${partId}`, {name:`보고서 섹션 · ${selected.title}`, active:true, detail:'AI가 본문을 작성·검토하고 있습니다.'});
      const section = reportSections.find((item) => item.part_id === partId);
      if (section) section.status = 'generating';
      if (activeReportPart === partId) await loadReportSection(partId, false);
    } catch (error) {
      reportFlow.rejected(partId, error.message, !error.status || error.status >= 500);
      if (error.status === 409) await refreshReportLifecycle(true);
      if (activeReportPart === partId) {
        byId('reportState').textContent = error.message;
        renderSectionAssistant(reportSections.find((item) => item.part_id === partId));
      }
    }
  }

  function renderGeneration(status) {
    const active = ['queued', 'running'].includes(status.status);
    renderReportSummary(status);
    let cancel = byId('reportCancel');
    if (!cancel) {
      cancel = document.createElement('button');
      cancel.id = 'reportCancel';
      cancel.className = 'btn';
      cancel.type = 'button';
      byId('reportGenerationMessage').after(cancel);
      cancel.addEventListener('click', async () => {
        if (!latestGenerationStatus?.id) return;
        generationPollRevision += 1;
        clearTimeout(generationTimer);
        cancel.disabled = true;
        try {
          latestGenerationStatus = await request(`/api/v2/report/generation/${encodeURIComponent(latestGenerationStatus.id)}/cancel`, {method:'POST'});
          updateGenerationTray(latestGenerationStatus);
          renderGeneration(latestGenerationStatus);
        } catch (error) { cancel.disabled = false; notify(error.message); }
        pollGeneration();
      });
    }
    cancel.hidden = !active;
    cancel.disabled = Boolean(status.cancel_requested);
    cancel.textContent = status.cancel_requested ? '중단 요청됨 · AI 응답 정리 중' : '보고서 생성 중단';
    let resume = byId('reportResume');
    if (!resume) {
      resume = document.createElement('button');
      resume.id = 'reportResume';
      resume.className = 'btn primary';
      resume.type = 'button';
      resume.textContent = '남은 섹션 이어서 생성';
      cancel.after(resume);
      resume.addEventListener('click', async () => {
        if (!latestGenerationStatus?.id || reportBatchSubmitting) return;
        reportBatchSubmitting = true;
        resume.disabled = true;
        try {
          const result = await request(`/api/v2/report/generation/${encodeURIComponent(latestGenerationStatus.id)}/resume`, {method:'POST'});
          notify(`저장된 ${result.preserved_sections}개 섹션을 보존하고 이어서 생성합니다.`);
        } catch (error) { notify(error.message); }
        finally { reportBatchSubmitting = false; resume.disabled = false; pollGeneration(); }
      });
    }
    resume.hidden = active || !status.can_resume;
    const total = Number(status.total_sections || 27);
    const completed = Number(status.completed_sections || 0);
    const percent = Math.round(completed / Math.max(1, total) * 100);
    const currentSectionsComplete = reportSections.length === 27 && reportSections.every((section) =>
      String(section.content || '').trim() && !['generating', 'failed'].includes(section.status)
    );
    const historicalErrorsResolved = !active && Number(status.failed_sections || 0) > 0 && currentSectionsComplete;
    const history = byId('reportGenerationHistory');
    history.hidden = status.status === 'not_started';
    // Keep the server's historical result intact, but only running work gets
    // an expanded progress view. Repeated reads preserve a user's expansion.
    if (active || history.dataset.active !== 'false') history.open = active;
    history.dataset.active = String(active);
    byId('reportGenerationHistorySummary').textContent = active
      ? `전체 보고서 작성 진행 중 · ${completed}/${total}`
      : `이전 전체 작성 기록 · ${['failed','cancelled'].includes(status.status) ? '중단' : status.status === 'completed_with_errors' ? '일부 보완 필요' : '완료'}`;
    byId('reportGenerationProgress').hidden = status.status === 'not_started';
    byId('reportGenerationBar').parentElement.hidden = !active;
    byId('reportGenerationPercent').hidden = !active;
    byId('reportGenerationBar').style.width = `${percent}%`;
    byId('reportGenerationPercent').textContent = `${percent}%`;
    byId('reportGenerationStage').textContent = active
      ? `보고서 생성 ${completed}/${total}`
      : ['failed','cancelled'].includes(status.status)
        ? '최근 전체 작성 실행 중단'
        : historicalErrorsResolved
          ? '전체 보고서 생성 및 개별 보완 완료'
          : status.status === 'completed_with_errors'
            ? '전체 보고서 일부 섹션 보완 필요'
            : '전체 보고서 생성 완료';
    byId('reportGenerationMessage').textContent = historicalErrorsResolved
      ? '현재 27개 섹션이 모두 작성·보완되었습니다.'
      : [status.cancel_requested && active ? '중단 요청 접수 · 현재 AI 응답을 정리한 뒤 중단합니다. 저장된 본문은 보존됩니다.' : status.error_message || status.message || '', active && !status.cancel_requested ? '한 섹션의 작성·검토 동안 진행률은 유지됩니다.' : '', !active && status.status === 'failed' && currentSectionsComplete ? '저장된 27개 섹션의 본문은 보존되어 있습니다. 최신 자료 반영 여부는 상단 안내를 확인해 주세요.' : ''].filter(Boolean).join(' ');
    byId('repGenAll').disabled = active;
    renderSectionAssistant(reportSections.find((item) => item.part_id === activeReportPart));
  }

  function updateGenerationTray(status) {
    // Only a new server response may update the global tray. Section reads
    // also render cached generation history, which may precede a newer run.
    const active = ['queued', 'running'].includes(status.status);
    const total = Number(status.total_sections || 27);
    const completed = Number(status.completed_sections || 0);
    const historicalErrorsResolved = !active && Number(status.failed_sections || 0) > 0
      && reportSections.length === 27 && reportSections.every((section) =>
        String(section.content || '').trim() && !['generating', 'failed'].includes(section.status));
    window.ServiceJobTray?.update('report', {name:'보고서 전체 작성', active,
      cancelled:status.status === 'cancelled',
      failed:!historicalErrorsResolved && ['failed','completed_with_errors'].includes(status.status),
      completed:historicalErrorsResolved ? total : completed, total,
      detail:historicalErrorsResolved ? '이전 실행의 실패 섹션을 개별 보완하여 현재 27개 섹션 작성 완료' : status.error_message || status.message || `${completed}/${total}개 섹션`});
  }

  function renderReportSummary(generation = latestGenerationStatus) {
    const counts = { saved: 0, complete: 0, generating: 0, attention: 0 };
    for (const section of reportSections) {
      const hasContent = Boolean(String(section.content || '').trim());
      if (hasContent) counts.saved += 1;
      if (section.status === 'generating') counts.generating += 1;
      else if (section.status === 'failed' || !hasContent) counts.attention += 1;
      else counts.complete += 1;
    }
    if (['queued', 'running'].includes(generation?.status)) {
      const total = Number(generation.total_sections || reportSections.length || 27);
      const completed = Number(generation.completed_sections || 0);
      const failed = Number(generation.failed_sections || 0);
      byId('repStat').textContent = `${reportSections.length}개 섹션 · 저장된 본문 ${counts.saved} · 이번 생성 ${completed}/${total}${generation.status === 'queued' ? ' · 대기 중' : ''}${failed ? ` · 이번 실패 ${failed}` : ''}`;
    } else {
      byId('repStat').textContent = `${reportSections.length}개 섹션 · 작성 ${counts.complete} · 생성 중 ${counts.generating} · 확인 필요 ${counts.attention}`;
    }
  }

  async function pollGeneration() {
    clearTimeout(generationTimer);
    const revision = ++generationPollRevision;
    try {
      const status = await request('/api/v2/report/generation/latest');
      if (revision !== generationPollRevision) return;
      latestGenerationStatus = status;
      updateGenerationTray(status);
      renderGeneration(status);
      if (['queued', 'running'].includes(status.status)) {
        await refreshReportSections(activeReportPart);
        if (revision !== generationPollRevision) return;
        generationTimer = setTimeout(pollGeneration, 2500);
      } else {
        await refreshReportSections(activeReportPart);
      }
    } catch (error) {
      if (revision !== generationPollRevision) return;
      byId('reportState').textContent = `진행 상태 연결을 다시 시도합니다. ${error.message}`;
      generationTimer = setTimeout(pollGeneration, 5000);
    }
  }

  async function generateAllReport() {
    if (reportBatchSubmitting || ['queued', 'running'].includes(latestGenerationStatus?.status) || reportSections.some((item) => reportFlow.busy(item.part_id) || item.status === 'generating')) return;
    if (reportSections.some((item) => String(item.content || '').trim()) && !await confirmDocumentAction('전체 보고서 다시 작성', '현재 사업 자료로 전체 보고서의 초안을 다시 작성합니다. 기존 본문이 바뀔 수 있습니다. 특정 부분만 수정하려면 취소 후 AI 섹션 수정 요청을 사용하세요. 전체 재작성을 진행할까요?')) return;
    reportBatchSubmitting = true;
    const button = byId('repGenAll');
    button.disabled = true;
    byId('reportState').textContent = '전체 보고서 생성 요청을 전송하고 있습니다.';
    notify('전체 보고서 생성 요청을 접수했습니다.');
    try {
      await request('/api/v2/report/generate-all', { method: 'POST', timeoutMs: 15000 });
    } catch (error) {
      byId('reportState').textContent = error.message;
    } finally {
      reportBatchSubmitting = false;
      pollGeneration();
    }
  }

  function renderExport(status) {
    const percent = Math.max(0, Math.min(100, Number(status.progress || 0)));
    byId('hwpxProgress').hidden = false;
    byId('hwpxBar').style.width = `${percent}%`;
    byId('hwpxPercent').textContent = `${percent}%`;
    byId('hwpxStage').textContent = status.status === 'completed' ? 'HWPX 생성 완료' : status.status === 'failed' ? 'HWPX 생성 실패' : status.stage || '내보내기';
    byId('hwpxMessage').textContent = status.error_message || status.message || '';
    byId('hwpxExport').disabled = ['queued', 'running'].includes(status.status);
    byId('rhwpPreview').disabled = byId('hwpxExport').disabled;
  }

  async function pollExport(id, preview = false) {
    clearTimeout(exportTimer);
    try {
      const status = await request(`/api/v2/report/exports/${encodeURIComponent(id)}`);
      renderExport(status);
      if (status.status === 'completed') {
        location.assign(preview ? `/assets/rhwp/?reportPreview=1&url=${encodeURIComponent(status.download_url)}&filename=${encodeURIComponent(status.file_name || 'KODAME.hwpx')}` : status.download_url); return;
      }
      if (status.status === 'failed') return;
      exportTimer = setTimeout(() => pollExport(id, preview), 1000);
    } catch (error) { renderExport({ status: 'failed', error_message: error.message }); }
  }

  async function exportHwpx(preview = false) {
    preview = preview === true;
    renderExport({ status: 'queued', stage: '현재 저장된 보고서 조판 요청 중' });
    try {
      const response = await request('/api/v2/report/exports', { method: 'POST' });
      exportStarted = Date.now();
      pollExport(response.id, preview);
    } catch (error) { renderExport({ status: 'failed', error_message: error.message }); }
  }

  async function previewRhwp() {
    // Use the current saved sections, never silently open an older export.
    return exportHwpx(true);
  }

  function renderPresentation(status) {
    const percent = Math.max(0, Math.min(100, Number(status.progress || 0)));
    const active = ['queued', 'running'].includes(status.status);
    window.ServiceJobTray?.update('presentation', {name:'AI 발표자료 작성', active, failed:status.status==='failed', completed:percent, total:100, detail:status.error_message || status.message || status.stage || '발표자료 구성'});
    const slideCount = Number(status.slide_count || status.validation?.slide_count || PRESENTATION_SLIDE_COUNT);
    byId('presentationProgress').hidden = status.status === 'not_started';
    byId('presentationBar').style.width = `${percent}%`;
    byId('presentationPercent').textContent = `${percent}%`;
    byId('presentationStage').textContent = status.status === 'completed' ? `${slideCount}장 발표자료 생성 완료` : status.status === 'failed' ? '발표자료 생성 실패' : status.stage || 'AI 발표자료 구성';
    byId('presentationMessage').textContent = status.error_message || status.message || `${status.model || '프로젝트 배정 AI'}가 보고서와 근거자료를 ${slideCount}장으로 구성합니다.`;
    byId('presentationExport').disabled = active;
    if (byId('presentationSlideCount')) {
      byId('presentationSlideCount').disabled = active;
      if (active && [15, 30].includes(slideCount)) byId('presentationSlideCount').value = String(slideCount);
    }
    byId('presentationExport').textContent = active ? `발표자료 작성 중 ${percent}%` : status.status === 'failed' ? '발표자료 다시 작성' : '발표자료 작성';
  }

  async function pollPresentation(id) {
    clearTimeout(presentationTimer);
    try {
      const status = await request(`/api/v2/report/presentations/${encodeURIComponent(id)}`);
      renderPresentation(status);
      if (status.status === 'completed') { location.assign(status.download_url); return; }
      if (status.status === 'failed') return;
      presentationTimer = setTimeout(() => pollPresentation(id), 1400);
    } catch (error) { renderPresentation({ status: 'failed', error_message: error.message }); }
  }

  async function exportPresentation() {
    const slideCount = Number(byId('presentationSlideCount')?.value || 15);
    byId('presentationExport').disabled = true;
    renderPresentation({ status: 'queued', progress: 0, slide_count: slideCount, stage: '발표자료 준비', message: `${slideCount}페이지 샘플 기반 발표자료 작업을 등록하는 중입니다.` });
    try {
      const response = await request('/api/v2/report/presentations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slide_count: slideCount }) });
      presentationStarted = Date.now();
      pollPresentation(response.id);
    } catch (error) {
      try {
        const latest = await request('/api/v2/report/presentations/latest');
        if (['queued', 'running'].includes(latest.status)) {
          presentationStarted = Date.now();
          pollPresentation(latest.id);
          return;
        }
      } catch (_) { /* no active presentation */ }
      renderPresentation({ status: 'failed', error_message: error.message });
    }
  }

  async function refreshPresentationLatest() {
    try {
      const latest = await request('/api/v2/report/presentations/latest');
      renderPresentation(latest);
      if (['queued', 'running'].includes(latest.status)) {
        presentationStarted = Date.now();
        pollPresentation(latest.id);
      }
    } catch (error) { console.error(error); }
  }

  function bind() {
    byId('authRetry').onclick = () => window.KODAME_MODULE_FAILED ? location.reload() : initializeAuth();
    byId('authSignOut').onclick = async () => {
      try { await request('/api/v2/auth/logout', {method:'POST'}); location.reload(); }
      catch (_) { setAuthView('unassigned', '로그아웃 요청을 완료하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.'); }
    };
    byId('codeBtn').addEventListener('click', authenticate);
    ['codeInput', 'authPassword'].forEach((id) => byId(id).addEventListener('keydown', (event) => { if (event.key === 'Enter') authenticate(); }));
    byId('authSwitch').addEventListener('click', () => setAuthMode(authMode === 'login' ? 'register' : 'login'));
    byId('logout').addEventListener('click', async (event) => { event.stopPropagation(); try { await fetch('/api/v2/auth/logout', { method: 'POST' }); } finally { location.reload(); } });
    byId('compactLogout')?.addEventListener('click', () => byId('logout').click());

    byId('daonFold').addEventListener('click', () => {
      byId('fixList').classList.toggle('expanded');
      if (typeof window.syncTodoFold === 'function') {
        window.syncTodoFold(byId('fixList').children.length);
      }
    });

    byId('dashIndToggle')?.addEventListener('click', () => {
      dashboardIndicatorsExpanded = !dashboardIndicatorsExpanded;
      renderDashboardIndicatorList(intake.pdm?.performance_indicators || []);
    });

    foundationUpload.bind();
    byId('uploadBtn').addEventListener('click', (event) => { event.stopPropagation(); if (foundationUpload.canUpload()) byId('bulkFileInput').click(); });
    byId('bulkFileInput').addEventListener('change', () => uploadFiles(byId('bulkFileInput').files));
    ['dropzone', 'spDrop'].forEach((id) => {
      const zone = byId(id);
      zone.addEventListener('click', (event) => { event.stopPropagation(); if (foundationUpload.canUpload()) byId('bulkFileInput').click(); });
      ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add('drag'); }));
      ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove('drag'); }));
      zone.addEventListener('drop', (event) => uploadFiles(event.dataTransfer.files));
    });
    document.addEventListener('click', (event) => { if (event.target.closest('[data-live-upload]')) { event.stopPropagation(); if (foundationUpload.canUpload()) byId('bulkFileInput').click(); } }, true);
    document.addEventListener('click', async event => {
      const scopeButton = event.target.closest('[data-evaluation-scope]');
      if (scopeButton) {
        const job = intake.jobs.find(doc => doc.id === scopeButton.dataset.scopeDocument);
        if (!job || scopeButton.disabled) return;
        const excluded = scopeButton.dataset.evaluationScope === 'exclude';
        const reason = await confirmDocumentAction(excluded ? '평가 대상에서 제외' : '평가 대상에 포함', excluded ? '원본은 보관하며 평가 분석에서 제외합니다. 기존 평가가 있으면 다시 검토해야 합니다.' : '이 문서를 평가 자료에 포함하고 필요한 문서 분석을 다시 진행합니다.', excluded ? '사용자 검토에 따라 평가 대상에서 제외' : '사용자 검토에 따라 평가 자료로 활용');
        if (!reason?.trim()) return;
        scopeButton.disabled = true;
        try {
          await request(`/api/v2/intake/jobs/${encodeURIComponent(job.id)}/evaluation-scope`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({excluded,reason:reason.trim(),expected_updated_at:job.updated_at})});
          notify(excluded ? '원본을 보관하고 평가 대상에서 제외했습니다.' : '평가 대상에 포함하고 분석을 접수했습니다.');
          await refreshIntake();
        } catch (error) { notify(error.message); scopeButton.disabled = false; }
        return;
      }
      const modeButton = event.target.closest('[data-intake-mode]');
      if (modeButton) {
        const job = intake.jobs.find(doc=>doc.id===modeButton.dataset.modeDocument);
        if (!job || modeButton.disabled) return;
        if (job.status==='completed' && !await confirmDocumentAction('문서 분석 다시 실행', '원본은 보관하며 이 문서의 기존 자동 매칭을 초기화하고 선택한 방식으로 다시 분석합니다.')) return;
        modeButton.disabled=true;
        try {
          await request(`/api/v2/intake/jobs/${encodeURIComponent(job.id)}/mode`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:modeButton.dataset.intakeMode,expected_updated_at:job.updated_at})});
          notify('선택한 방식으로 처리하도록 접수했습니다.'); await refreshIntake();
        } catch(error) { notify(error.message); modeButton.disabled=false; }
        return;
      }
      if (event.target.closest('[data-retry-upload]')) uploadFiles(uploadFailures.map(item => item.file));
      const button = event.target.closest('[data-retry-document]');
      if (!button || button.disabled) return;
      button.disabled = true;
      try {
        await request(`/api/v2/intake/jobs/${encodeURIComponent(button.dataset.retryDocument)}/retry`, { method: 'POST' });
        notify('문서를 다시 분석하도록 접수했습니다.');
        await refreshIntake();
      } catch (error) { notify(error.message); button.disabled = false; }
    });
    document.addEventListener('click', (event) => {
      const opener = event.target.closest('[data-risk-open]');
      if (opener) {
        event.preventDefault();
        openRiskDetail(opener.dataset.riskOpen, opener);
        return;
      }
      if (event.target.closest('[data-risk-close]')) closeRiskDetail();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !byId('riskDetailModal')?.hidden) closeRiskDetail();
    });

    document.querySelectorAll('.fchipb').forEach((button) => button.addEventListener('click', () => {
      document.querySelectorAll('.fchipb').forEach((item) => item.classList.remove('on'));
      button.classList.add('on');
      fileFilter = button.dataset.f;
      fileShowAll = false;
      renderFiles();
    }));
    byId('fileSearch').addEventListener('input', (event) => { fileQuery = event.target.value.trim().toLowerCase(); fileShowAll = false; renderFiles(); });
    byId('fileMore').addEventListener('click', () => { fileShowAll = !fileShowAll; renderFiles(); });
    byId('runBtn').addEventListener('click', startEvaluation);
    byId('runBtn2').addEventListener('click', startEvaluation);
    byId('indRefresh').addEventListener('click', () => performanceReview.open());
    byId('seclist').addEventListener('click', (event) => {
      const item = event.target.closest('[data-id]');
      if (item) loadReportSection(item.dataset.id, true).catch((error) => { byId('reportState').textContent = error.message; });
    });
    byId('aiGen').addEventListener('click', generateSection);
    byId('reportGenerationHistorySummary').addEventListener('click', (event) => {
      if (byId('reportGenerationHistory').dataset.active === 'true') event.preventDefault();
    });
    byId('aiPrompt').addEventListener('input', (event) => { if (activeReportPart) reportInstructions.set(activeReportPart, event.target.value); });
    byId('reportAiTemplates').addEventListener('click', (event) => {
      const button = event.target.closest('[data-instruction]');
      if (!button || byId('aiPrompt').disabled) return;
      byId('aiPrompt').value = button.dataset.instruction;
      reportInstructions.set(activeReportPart, button.dataset.instruction);
      byId('aiPrompt').focus();
    });
    byId('aiCheckStatus').addEventListener('click', async () => {
      if (!activeReportPart) return;
      const button = byId('aiCheckStatus');
      button.disabled = true;
      try { await refreshReportLifecycle(true); await loadReportSection(activeReportPart, false); }
      catch (error) { byId('reportAiStatus').textContent = `상태를 확인하지 못했습니다. ${error.message}`; }
      finally { button.disabled = false; }
    });
    byId('repGenAll').addEventListener('click', generateAllReport);
    byId('rhwpPreview').addEventListener('click', previewRhwp);
    byId('hwpxExport').addEventListener('click', exportHwpx);
    byId('presentationExport').addEventListener('click', exportPresentation);
    byId('reportSubmissionDownload').addEventListener('click', async () => {
      const button=byId('reportSubmissionDownload'), status=byId('reportSubmissionStatus');
      const kind=byId('reportSubmissionKind').value, path=`/api/v2/report/submissions/${encodeURIComponent(kind)}`;
      button.disabled=true; status.textContent='저장된 평가·보고서로 파일을 구성하고 있습니다.';
      try {
        const response=await fetch(path,{headers:serviceScope.headers(path)});
        if (!response.ok) {
          const error=await response.json().catch(()=>({}));
          serviceScope.check(path,response,error);
          throw new Error(error.detail||'별도 제출 파일을 만들지 못했습니다.');
        }
        const blob=await response.blob(); serviceScope.check(path,response,null);
        const disposition=response.headers.get('Content-Disposition')||'';
        const name=decodeURIComponent(disposition.split("filename*=UTF-8''")[1]||`submission.${kind.split('-').pop()}`);
        const url=URL.createObjectURL(blob), link=document.createElement('a');
        link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        status.textContent='다운로드 완료 · 제출 전 확인 필요 항목을 검토해 주세요.';
      } catch(error) {status.textContent=error.message;}
      finally {button.disabled=false;}
    });
    byId('adminRefresh')?.addEventListener('click', refreshAdmin);
    byId('adminCreateProject')?.addEventListener('click', openProjectCreator);
    byId('adminCreateAccount')?.addEventListener('click', () => serviceAdmin.openAccountForm());
    byId('adminProjectSearch')?.addEventListener('input', renderAdminProjects);
    byId('adminUserSearch')?.addEventListener('input', renderAdminRows);
    byId('adminUserProject')?.addEventListener('change', renderAdminRows);
    byId('adminProjectList')?.addEventListener('click', event => {
      const remove = event.target.closest('[data-delete-project]');
      if (remove) serviceAdmin.deleteProject(remove.dataset.deleteProject);
      const ai = event.target.closest('[data-project-ai]');
      if (ai) projectAI.open(adminProjects.find(project => project.id === ai.dataset.projectAi));
      const issue = event.target.closest('[data-issue-project]');
      if (issue) serviceAdmin.openAccountForm(null, issue.dataset.issueProject);
      const users = event.target.closest('[data-project-users]');
      if (users) { byId('adminUserProject').value = users.dataset.projectUsers; renderAdminRows(); location.hash = '#/admin/users'; }
    });
    byId('projectLanguageChecks')?.addEventListener('change', syncDefaultLocaleOptions);
    byId('projectCreateForm')?.addEventListener('submit', submitProjectCreate);
    byId('adminAccountRows')?.addEventListener('click', (event) => {
      const row = event.target.closest('[data-admin-account]');
      if (!row) return;
      selectedAdminAccountId = row.dataset.adminAccount;
      renderAdminRows();
      renderAdminDetail(adminAccounts.find((account) => account.id === selectedAdminAccountId));
    });
    byId('adminDetail')?.addEventListener('click', (event) => {
      if (event.target.closest('#adminSaveMenus')) saveAdminMenus();
      const button = event.target.closest('[data-account-action]');
      if (button) serviceAdmin.act(button.dataset.accountAction);
    });
    byId('projList')?.addEventListener('click', async (event) => {
      const button = event.target.closest('[data-select-project]');
      if (!button || button.disabled) return;
      if (reportSections.some((section) => reportFlow.hasDraft(section.part_id)) && !window.confirm('저장하지 않은 보고서 편집 내용이 있습니다. 저장하지 않고 프로젝트를 전환할까요?')) return;
      byId('projList').querySelectorAll('button').forEach((item) => { item.disabled = true; });
      try {
        await request(`/api/v2/account/projects/${encodeURIComponent(button.dataset.selectProject)}/select`, { method: 'PUT', timeoutMs: 15000 });
        allowProjectReload = true;
        location.hash = '#/dashboard';
        location.reload(); // Clear all in-memory report, evidence, evaluation and translation state.
      } catch (error) {
        if (!error.status || error.status >= 500) {
          // An uncertain selection response must never leave old project data
          // displayed against a possibly changed session scope.
          allowProjectReload = true;
          location.reload();
        } else { notify(error.message); await refreshProjectChoices(); }
      }
    });
    window.addEventListener('hashchange', () => {
      if (location.hash.startsWith('#/admin')) refreshAdmin();
      if (location.hash === '#/eval/report') {
        refreshReportLifecycle(true);
        pollGeneration(); // A run may have started elsewhere since the last terminal response.
        if (activeReportPart) loadReportSection(activeReportPart, false).catch(error => { byId('reportState').textContent = error.message; });
      } else sectionPreview.clear();
    });
    byId('optcards').addEventListener('click', (event) => {
      const option = event.target.closest('.opt');
      if (!option) return;
      byId('optcards').querySelectorAll('.opt').forEach((item) => item.classList.toggle('sel', item === option));
      if (option.dataset.action === 'generate') generateAllReport();
      if (option.dataset.action === 'preview') previewRhwp();
    });
  }

  function renderReportOptions() {
    byId('optcards').innerHTML = '<div class="opt sel" data-action="continue"><div class="ot">이어서 작성</div><div class="od">저장된 27개 섹션을 불러와 이어서 편집</div></div><div class="opt" data-action="generate"><div class="ot">새로 작성</div><div class="od">현재 사업 자료로 전체 섹션을 AI 재생성</div></div><div class="opt" data-action="preview"><div class="ot">최근 HWPX 미리보기</div><div class="od">완료된 파일을 rhwp에서 바로 확인</div></div>';
  }

  function startData() {
    if (started) return;
    started = true;
    renderReportOptions();
    const reportTasks = window.hasMenuPermission?.('evaluation_report')
      ? [refreshReportSections(), pollGeneration(), refreshPresentationLatest()]
      : [];
    Promise.all([
      refreshDashboard(), refreshIntake(), refreshEvaluation(), refreshEvaluationStatus(), pdmRefresh.sync(),
      refreshProjectOverview(), ...reportTasks
    ]);
    setInterval(refreshIntake, 3500);
    setInterval(refreshEvaluationStatus, 3500);
    setInterval(() => pdmRefresh.sync(), 3500);
    async function refreshReportTray() {
      if (!window.hasMenuPermission?.('evaluation_report')) return;
      try {
        const snapshot = await request('/api/v2/report/job-tray');
        snapshot.items.forEach(({key,...job}) => window.ServiceJobTray?.update(key,job));
      } catch (_) { /* retain known work while the connection recovers */ }
    }
    refreshReportTray();
    setInterval(refreshReportTray, 5000);
    setInterval(refreshDashboard, 12000);
    setInterval(() => {
      if (!document.hidden && location.hash === '#/eval/report') refreshReportLifecycle();
    }, 12000);
    setInterval(() => request('/api/v2/auth/me').catch(() => {}), 15000);
  }

  detachDemoHandlers();
  renderDashboard({ is_empty: true, project: {} });
  bind();
  window.KODAME_LIVE_READY = true;
  byId('authSwitch').hidden = true;
  setAuthMode('login');
  if (!window.KODAME_MODULE_FAILED) initializeAuth();
})();
