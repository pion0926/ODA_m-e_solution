/* Exercise production UI functions without a browser, real writes or LLM calls. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { createFlow, generationBlock } = require('../../assets/report-section-flow.js');
const live = fs.readFileSync('assets/app-controller.js', 'utf8');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const renderer = live.slice(live.indexOf('  function renderSectionAssistant(section) {'), live.indexOf('  async function loadReportSection('));
const submitter = live.slice(live.indexOf('  async function generateSection() {'), live.indexOf('  function renderGeneration(status) {'));
function fixture() {
  const nodes = new Map();
  const byId = id => {
    if (!nodes.has(id)) nodes.set(id, { value: '', disabled: false, hidden: false, dataset: {}, textContent: '', title: '' });
    return nodes.get(id);
  };
  const section = { part_id: 'criteria-relevance', section_number: 15, title: '적절성', content: '저장된 현재 본문', status: 'draft' };
  const flow = createFlow();
  flow.select(section.part_id); flow.observe(section);
  const calls = [];
  const ctx = {
    window: { ReportSectionFlow: { generationBlock }, hasMenuPermission: () => true },
    reportFlow: flow, reportInstructions: new Map(), reportSections: [section],
    activeReportPart: section.part_id, sectionLoadPending: null, reportBatchSubmitting: false,
    latestGenerationStatus: null, reportLifecycle: { phase: 'current', can_generate_report: true },
    byId, performance, refreshReportLifecycle: async () => {},
    request: async (path, options) => { calls.push({path, ...options}); return { status: 'generating' }; },
    loadReportSection: async partId => { assert.equal(partId, section.part_id); flow.observe({ ...section, status: 'draft' }); }
  };
  vm.createContext(ctx); vm.runInContext(renderer + submitter, ctx);
  return { ctx, section, calls, byId };
}
async function main() {
  for (const phase of ['empty_project', 'processing_documents', 'evaluation_required', 'evaluation_active', 'report_generating']) {
    const f = fixture();
    f.ctx.reportLifecycle = { phase, can_generate_report: false, message: `차단 이유: ${phase}` };
    f.ctx.renderSectionAssistant(f.section);
    assert.equal(f.byId('aiGen').disabled, true);
    assert.ok(f.byId('reportAiStatus').textContent.includes(`차단 이유: ${phase}`), 'disabled button must explain the actual reason');
    assert.equal(f.byId('reportAiNextStep').hidden, !['empty_project', 'processing_documents', 'evaluation_required'].includes(phase));
    await f.ctx.generateSection(); assert.equal(f.calls.length, 0, 'blocked state must not send a POST');
  }
  const ready = fixture();
  ready.ctx.renderSectionAssistant(ready.section);
  assert.equal(ready.byId('aiGen').disabled, false, 'a saved draft is editable after evaluation');
  ready.byId('aiPrompt').value = '사실과 수치를 유지하고 중복 문장을 정리';
  await Promise.all([ready.ctx.generateSection(), ready.ctx.generateSection()]);
  assert.equal(ready.calls.length, 1, 'double click must submit only once');
  assert.equal(ready.calls[0].path, '/api/v2/report/sections/criteria-relevance/generate');
  assert.deepEqual(JSON.parse(ready.calls[0].body), { instruction: ready.byId('aiPrompt').value, current_content: ready.section.content });
  assert.equal(ready.ctx.reportInstructions.get(ready.section.part_id), ready.byId('aiPrompt').value);
  const staleAtSubmit = fixture();
  staleAtSubmit.ctx.refreshReportLifecycle = async () => { staleAtSubmit.ctx.reportLifecycle = { phase: 'evaluation_required', can_generate_report: false, message: '새 자료 재평가 필요' }; };
  await staleAtSubmit.ctx.generateSection();
  assert.equal(staleAtSubmit.calls.length, 0, 'fresh lifecycle check must catch uploads made since page load');
  assert.ok(staleAtSubmit.byId('reportAiStatus').textContent.includes('새 자료 재평가 필요'));
  const uncertain = fixture();
  uncertain.ctx.request = async () => { throw new Error('timeout'); };
  await uncertain.ctx.generateSection();
  assert.equal(uncertain.ctx.reportFlow.state(uncertain.section.part_id).status, 'uncertain');
  assert.equal(uncertain.byId('aiGen').disabled, true);
  assert.equal(uncertain.byId('aiCheckStatus').hidden, false);
  for (const id of ['reportEditor', 'saveReportSection', 'resetReportSection', 'reportMeta']) {
    assert.ok(!html.includes(`id="${id}"`));
    assert.ok(!live.includes(`byId('${id}')`), 'removed editor must have no DOM dependency');
  }
  assert.ok(!html.includes('id="reportNavToggle"'));
  assert.ok(!html.includes('aria-label="보고서 섹션 목차" hidden'));
  assert.ok(live.includes("['generating', 'failed', 'empty'].includes(state)"), 'ordinary draft must not have a list badge');
  assert.ok(!submitter.includes("method: 'PUT'"), 'AI-only request must not save a hidden manual editor');
  console.log('PASS: AI-only UI, 5 lifecycle gates + explanations, submit, double click, fresh-input guard, timeout/retry, no manual editor or normal draft badge');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
