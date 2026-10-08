const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/app-controller.js', 'utf8');
const code = source.slice(source.indexOf('  function renderGeneration('), source.indexOf('  async function generateAllReport('));
const navigation = source.slice(source.indexOf("    window.addEventListener('hashchange'"), source.indexOf("    byId('optcards').addEventListener"));
const nodes = new Map();
function element() {
  return {dataset:{},style:{},parentElement:{},innerHTML:'',classList:{add(){},remove(){},toggle(){}},
    addEventListener(type,handler){this[type]=handler;}, after(node){nodes.set(node.id,node);}, querySelector(){return null;}};
}
function byId(id) { if (!nodes.has(id)) nodes.set(id,element()); return nodes.get(id); }
const history = {id:'old',status:'completed',completed_sections:27,total_sections:27};
const requests = [];
const env = {document:{createElement:element,getElementById:byId}, byId,
  window:{addEventListener(type,handler){env.listeners[type]=handler;}},listeners:{},
  reportSections:Array.from({length:27},(_,i)=>({part_id:`s${i}`,content:'Prior saved draft',status:'draft'})),
  latestGenerationStatus:history,activeReportPart:'s1',generationTimer:null,generationPollRevision:0,
  renderSectionAssistant(){},clearTimeout(){},setTimeout(){return 1;},notify(){},
  refreshReportSections:async()=>env.renderGeneration(env.latestGenerationStatus),
  request:async(url)=>{requests.push(url);return env.serverStatus;},serverStatus:history,
  location:{hash:'#/eval/report'},refreshAdmin(){},refreshReportLifecycle(){},
  loadReportSection:async()=>{env.renderGeneration(env.latestGenerationStatus);},sectionPreview:{clear(){}}
};
vm.createContext(env);
vm.runInContext(fs.readFileSync('assets/service-job-tray.js','utf8'),env);
vm.runInContext(code + navigation,env);

(async()=>{
  await env.pollGeneration(); // The app initially observes a completed previous run.
  env.window.ServiceJobTray.update('report',{name:'보고서 전체 작성',active:true,completed:18,total:27,detail:'new run 18/27'});
  const live = byId('trayJobs').innerHTML;
  env.renderGeneration(history); // Section/detail refresh re-renders cached history.
  assert.equal(byId('trayJobs').innerHTML,live,'cached completed history must not replace the current active tray job');
  assert.match(live,/진행 중/);
  assert.match(live,/new run 18\/27/);

  env.serverStatus = {id:'new',status:'running',completed_sections:19,total_sections:27};
  env.listeners.hashchange(); // Entering the report page requests current generation state.
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.at(-1),'/api/v2/report/generation/latest');
  assert.equal(env.latestGenerationStatus.id,'new');
  assert.match(byId('trayJobs').innerHTML,/진행 중/);
  assert.match(byId('trayJobs').innerHTML,/19\/27개 섹션/);
  assert.match(byId('repStat').textContent,/이번 생성 19\/27/);
  assert.equal(byId('repGenAll').disabled,true,'the current active run must disable duplicate submission');

  let finishOldRead;
  env.request=()=>new Promise(resolve=>{finishOldRead=resolve;});
  const oldRead=env.pollGeneration();
  env.request=async()=>({...env.serverStatus,completed_sections:20});
  await env.pollGeneration();
  finishOldRead(history);
  await oldRead;
  assert.equal(env.latestGenerationStatus.id,'new');
  assert.match(byId('trayJobs').innerHTML,/20\/27개 섹션/,'a superseded generation read must not publish stale completion');

  env.request=async()=>({id:'new',status:'completed',completed_sections:27,total_sections:27});
  await env.pollGeneration();
  assert.match(byId('trayJobs').innerHTML,/>완료</);
  assert.match(byId('trayJobs').innerHTML,/27\/27개 섹션/);
  assert.equal(byId('repGenAll').disabled,false);
  console.log('PASS cached history cannot overwrite live report progress; navigation refresh, superseded read and final completion');
})().catch(error=>{console.error(error);process.exitCode=1;});
