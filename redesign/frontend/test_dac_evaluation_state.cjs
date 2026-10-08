const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

const context = {window: {}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('assets/dac-scoring-ui.js', 'utf8'), context);
const ui = context.window.DacScoringUI;
const previous = Object.freeze({status: 'completed', run_id: 'old', overall: {score: 8.8}, criteria: []});
const active = Object.freeze({active: true, status: 'running', run_id: 'new', total_questions: 11,
  completed_questions: 0, current_stage: 'evidence', lifecycle: {evaluation_stale: true}});
const steps = Object.freeze([{name: '자료수집', percent: 100},
  Object.freeze({name: '기준별 판단', percent: 100, hint: '평가기준 5/5개 분석 완료'}),
  {name: '자료 분류', percent: 100}, {name: '제출 전 검토', percent: 0}]);

test('active run shows its own question progress and labels preserved scores as previous', () => {
  const state = ui.evaluationState(previous, active);
  assert.equal(state.title, '이전 완료 평가 · 새 평가 진행 중');
  assert.equal(state.historical, true);
  assert.match(state.detail, /질문 검증 0\/11개/);
  const current = ui.evaluationSteps(steps, previous, active)[1];
  assert.equal(current.percent, 0);
  assert.equal(current.active, true);
  assert.doesNotMatch(current.hint, /5\/5/);
  assert.equal(steps[1].percent, 100);
  assert.equal(previous.overall.score, 8.8);
});

test('question checkpoints advance current progress without premature completion while saving', () => {
  assert.match(ui.evaluationState(previous, {...active, completed_questions: 4}).detail, /4\/11개/);
  const saving = ui.evaluationSteps(steps, previous, {...active, completed_questions: 11, current_stage: 'saving'})[1];
  assert.equal(saving.percent, 99);
  assert.equal(saving.active, true);
  assert.match(saving.hint, /결과 저장/);
});

test('first evaluation and lifecycle-only loading state never call old results current', () => {
  assert.equal(ui.evaluationState({status: 'not_run'}, active).title, '첫 평가 진행 중');
  const state = ui.evaluationState({...previous, lifecycle: {evaluation_active: true}});
  assert.equal(state.historical, true);
  assert.match(state.progress, /진행률 확인 중/);
});

test('completed status cannot label delayed previous result as new', () => {
  const status = {active: false, status: 'completed', run_id: 'new', lifecycle: {evaluation_stale: false}};
  assert.equal(ui.evaluationState(previous, status).title, '새 평가 완료 · 결과 불러오는 중');
  assert.equal(ui.evaluationState({...previous, run_id: 'new'}, status).title, '');
  assert.equal(ui.evaluationState({...previous, run_id: 'new'}, status).historical, false);
});

test('stale and stopped evaluations preserve old results with explicit labels', () => {
  assert.match(ui.evaluationState({...previous, is_stale: true}).title, /최신 자료 재평가 필요/);
  for (const status of ['failed', 'cancelled']) {
    const state = ui.evaluationState(previous, {active: false, status, run_id: 'new'});
    assert.equal(state.title, '이전 완료 평가 · 새 평가 미완료');
    assert.match(state.detail, /완료된 질문은 보존/);
  }
});

test('actual controller rendering replaces stale 5/5 step while retaining score and detail nodes', () => {
  const source = fs.readFileSync('assets/app-controller.js', 'utf8');
  const nodes = new Map();
  const byId = id => {
    if (!nodes.has(id)) nodes.set(id, {hidden: false, textContent: '', innerHTML: ''});
    return nodes.get(id);
  };
  const labels = [{}, {}, {}];
  const harness = {window: context.window, byId, latestEvaluationData: previous,
    evaluationLoaded: true, evaluationLoadError: '',
    latestEvaluationStatus: active, latestWorkflowSteps: [],
    document: {querySelectorAll: () => labels},
    esc: value => String(value ?? '').replaceAll('<', '&lt;'), tr: (_, fallback) => fallback};
  vm.createContext(harness);
  vm.runInContext(source.slice(source.indexOf('  function renderWorkflowSteps('),
    source.indexOf('  async function refreshDashboard(')), harness);
  vm.runInContext(source.slice(source.indexOf('  function syncEvaluationState('),
    source.indexOf('  function dacQuestionEvidence(')), harness);
  byId('critSections').innerHTML = 'preserved evidence';
  byId('scorechips2').innerHTML = '8.8/20';
  harness.renderWorkflowSteps(steps);
  harness.syncEvaluationState();
  assert.match(byId('stepline').innerHTML, /새 평가 진행 중/);
  assert.match(byId('stepline').innerHTML, /질문 검증 0\/11개/);
  assert.doesNotMatch(byId('stepline').innerHTML, /5\/5/);
  assert.match(labels[0].textContent, /^이전 완료 평가/);
  assert.equal(byId('dacEvaluationState').hidden, false);
  assert.equal(byId('dacResultState').hidden, false);
  assert.equal(byId('critSections').innerHTML, 'preserved evidence');
  assert.equal(byId('scorechips2').innerHTML, '8.8/20');
  // A later dashboard render must not restore the historical completion count.
  harness.renderWorkflowSteps(steps);
  assert.doesNotMatch(byId('stepline').innerHTML, /5\/5/);
  harness.latestEvaluationStatus = {active: false, status: 'completed', run_id: 'new', lifecycle: {evaluation_stale: false}};
  harness.latestEvaluationData = {...previous, run_id: 'new'};
  harness.syncEvaluationState();
  assert.equal(byId('dacEvaluationState').hidden, true);
  assert.equal(labels[0].textContent, '종합점수');
});
