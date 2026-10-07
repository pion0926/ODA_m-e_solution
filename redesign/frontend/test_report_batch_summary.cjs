const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/app-controller.js', 'utf8');
const code = source.slice(source.indexOf('  function renderReportList()'), source.indexOf('  async function refreshReportLifecycle('))
  + source.slice(source.indexOf('  function renderGeneration('), source.indexOf('  async function pollGeneration()'));
const elements = new Map();
const element = () => ({dataset:{},style:{},parentElement:{},addEventListener(){},after(node){elements.set(node.id,node);}});
const sections = () => Array.from({length:27},(_,index)=>({part_id:`s${index}`,section_number:index+1,
  title:`Section ${index+1}`,status:'draft',content:'previously stored body'}));
const env = {document:{createElement:element},byId(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  reportSections:sections(),latestGenerationStatus:null,activeReportPart:null,reportNames:{generating:'생성 중',failed:'실패',empty:'미작성'},
  esc:String,renderSectionAssistant(){},window:{ServiceJobTray:{update(){}}},request(){throw Error('No extra polling allowed');}};
vm.createContext(env);vm.runInContext(code,env);
env.renderReportList();
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 작성 27 · 생성 중 0 · 확인 필요 0');

env.latestGenerationStatus={status:'running',total_sections:27,completed_sections:9};
env.renderGeneration(env.latestGenerationStatus);
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 저장된 본문 27 · 이번 생성 9/27');
env.renderReportList();
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 저장된 본문 27 · 이번 생성 9/27',
  'section-list refresh must not replace batch progress with prior-draft completion');

env.reportSections[9].status='generating';
env.latestGenerationStatus={status:'running',total_sections:27,completed_sections:10,failed_sections:1};
env.renderGeneration(env.latestGenerationStatus);
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 저장된 본문 27 · 이번 생성 10/27 · 이번 실패 1');
env.latestGenerationStatus={status:'queued',total_sections:27,completed_sections:0};
env.renderGeneration(env.latestGenerationStatus);
assert.match(elements.get('repStat').textContent,/저장된 본문 27 · 이번 생성 0\/27 · 대기 중/);

env.reportSections=sections();
env.latestGenerationStatus={status:'completed',total_sections:27,completed_sections:27};
env.renderGeneration(env.latestGenerationStatus);
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 작성 27 · 생성 중 0 · 확인 필요 0');
env.reportSections[0].status='failed';env.reportSections[1].content='';
env.renderReportList();
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 작성 25 · 생성 중 0 · 확인 필요 2');
env.reportSections=sections().map(item=>({...item,content:''}));
env.latestGenerationStatus={status:'running',total_sections:27,completed_sections:0};
env.renderGeneration(env.latestGenerationStatus);
assert.equal(elements.get('repStat').textContent,'27개 섹션 · 저장된 본문 0 · 이번 생성 0/27');
console.log('PASS stored drafts vs current batch, progress-only updates, list refresh, queue, failures and completion');
