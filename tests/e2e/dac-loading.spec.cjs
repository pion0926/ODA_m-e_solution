const { test, expect } = require('@playwright/test');

const session = {
  account: { id: 'synthetic-account', is_admin: false, menu_permissions: {} },
  has_project: true,
  project: { id: 'synthetic-project', name: '합성 평가 프로젝트', role: 'owner' },
};
const evaluation = {
  status: 'completed', run_id: 'synthetic-completed-run',
  overall: { score: 12.5, koica_grade: 'D', government_grade: '부분성공' },
  criteria: ['relevance', 'coherence', 'effectiveness', 'efficiency', 'sustainability'].map((id, index) => ({
    id, name: ['적절성', '일관성', '효과성', '효율성', '지속가능성'][index],
    score: 2.5, scored: true, summary: '합성 증빙을 검토해 저장한 판단입니다.', question_assessments: [],
  })),
};

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

async function mockProject(page, loadEvaluation, state = {}) {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    // All service responses are synthetic; no live API or provider is reachable.
    if (url.origin !== 'http://127.0.0.1:8317') return route.abort();
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (url.pathname === '/api/v2/auth/me') return route.fulfill({ json: session });
    if (url.pathname === '/api/v2/dashboard') return route.fulfill({ json: { is_empty: false, project: session.project, steps: [] } });
    if (url.pathname === '/api/v2/evaluations') return loadEvaluation(route);
    if (url.pathname === '/api/v2/evaluations/status') return route.fulfill({ json: {
      active: Boolean(state.active), status: state.active ? 'running' : 'completed', can_start: true,
      run_id: state.active ? 'synthetic-new-run' : evaluation.run_id,
      document_count: 1, completed_document_count: 1, completed_criteria: 5, total_criteria: 5,
      completed_at: state.active ? null : '2026-01-02T00:00:00Z',
    } });
    if (url.pathname === '/api/v2/project/i18n/views') return route.fulfill({ json: { locale: 'ko', views: {} } });
    return route.fulfill({ status: 503, json: { detail: '합성 테스트에서 사용하지 않는 API' } });
  });
}

async function expectNeutralScores(page) {
  await expect(page.locator('#v-eval-board h1')).toBeVisible();
  const values = page.locator('#dacScoreSummary .sv');
  await expect(values).toHaveText(['—', '—', '—', '—']);
  await expect(page.locator('#scorechips2')).toBeEmpty();
  await expect(page.locator('#v-eval-board')).not.toContainText('17.5');
  await expect(page.locator('#v-eval-board')).not.toContainText('새 자료 2건');
}

test('reload keeps DAC scores neutral while evaluation hydration is delayed', async ({ page }) => {
  let pending = deferred();
  await mockProject(page, async route => {
    await pending.promise;
    return route.fulfill({ json: evaluation });
  });
  await page.goto('/#/eval/board');
  for (let load = 0; load < 2; load += 1) {
    if (load) {
      pending = deferred();
      await page.reload();
    }
    await expectNeutralScores(page);
    // Status can arrive first without falsely showing "평가 전" or sample scores.
    await expect(page.locator('#pendAnalyze')).toContainText('최근 완료');
    await expect(page.locator('#dacEvaluationState')).toContainText('평가 결과 불러오는 중');
    await expect(page.locator('#dacScoreSummary')).toHaveAttribute('aria-busy', 'true');
    pending.resolve();
    await expect(page.locator('#dacScoreSummary .sv')).toHaveText(['12.5/20', 'D', '부분성공', '—']);
    await expect(page.locator('#dacScoreSummary')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('#scorechips2 .sc')).toHaveText(Array(5).fill('2.5/4'));
  }
});

test('failed initial hydration shows a load error with no invented result', async ({ page }) => {
  await mockProject(page, route => route.fulfill({ status: 503, json: { detail: '평가 조회 연결 오류' } }));
  await page.goto('/#/eval/board');
  await expectNeutralScores(page);
  await expect(page.locator('#dacEvaluationState')).toContainText('평가 결과 조회 실패');
  await expect(page.locator('#dacEvaluationState')).toContainText('새로고침');
  await expect(page.locator('#dacScoreSummary')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#dacScoreSummary')).not.toContainText('평가 전');
  await expect(page.locator('#dacScoreSummary')).not.toContainText('판정보류');
});

test('failed refresh preserves the last saved score and criterion findings', async ({ page }) => {
  const state = { active: true };
  let requests = 0;
  await mockProject(page, route => {
    requests += 1;
    return requests === 1 ? route.fulfill({ json: evaluation })
      : route.fulfill({ status: 503, json: { detail: '평가 갱신 연결 오류' } });
  }, state);
  await page.goto('/#/eval/board');
  await expect(page.locator('#dacScoreSummary .sv').first()).toHaveText('12.5/20');
  await expect(page.locator('#pendAnalyze')).toContainText('분석 중');
  state.active = false; // The real status poll triggers the normal result refresh.
  await expect(page.locator('#dacEvaluationState')).toContainText('평가 결과 갱신 실패');
  await expect(page.locator('#dacEvaluationState')).toContainText('마지막으로 확인한 결과');
  await expect(page.locator('#dacScoreSummary .sv')).toHaveText(['12.5/20', 'D', '부분성공', '—']);
  await page.locator('#scorechips2 button').first().click();
  await expect(page.locator('#critSections .csec')).toHaveCount(5);
  await expect(page.locator('#critSections .csec').first()).toContainText('합성 증빙을 검토해 저장한 판단');
  await expect(page.locator('#dacResultState')).toContainText('평가 결과 갱신 실패');
});
