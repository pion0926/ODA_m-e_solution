const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const nodes = new Map(), handlers = {};
function node() { return {value:'', innerHTML:'', textContent:'', disabled:false, addEventListener(){}}; }
const dialog = {...node(), open:false, setAttribute(){}, querySelector(selector) {
  if (!nodes.has(selector)) nodes.set(selector,node());
  return nodes.get(selector);
}, addEventListener(type, handler) { handlers[type]=handler; },
showModal(){this.open=true;}, close(){this.open=false;handlers.close?.();}};
const env = {window:{}, document:{body:{appendChild(){}},createElement:()=>dialog},setInterval:()=>1,clearInterval(){}};
vm.createContext(env);
vm.runInContext(fs.readFileSync('assets/performance-analysis-review.js','utf8'),env);
const plan = {ready:true, revision:'r', source_file_name:'pdm', source_document_id:'pdm', message:'ready', pending_count:0,
  documents:['old','retained','new'].map(id=>({id,file_name:id+'.pdf',status:'completed'})),
  indicators:[{id:'i',text:'양성 인원',mov:'명단',tier_name:'산출물',document_ids:[],
    retained_document_ids:['retained'],analyzed_document_ids:['old','retained'],restorable_document_ids:['old']}],
  mapping_changed_indicator_ids:[]};
let submitted;
const client = env.window.PerformanceAnalysisReview.create({request:async()=>structuredClone(plan),
  start:async review=>{submitted=review;return{id:'run'};},refreshIntake:async()=>{},notify(){},escapeHtml:String});

(async()=>{
  await client.open();
  assert.match(dialog.innerHTML, /분석·연결 복원할 문서/);
  const rows = nodes.get('[data-review-rows]');
  assert.match(rows.innerHTML, /option value="old"[^>]*>old\.pdf · 기존 분석 재사용하여 연결 복원/);
  assert.doesNotMatch(rows.innerHTML, /option value="retained"/);
  assert.match(rows.innerHTML, /option value="new"/);
  const row={dataset:{reviewIndicator:'i'},querySelector:()=>({value:'old'})};
  await handlers.click({target:{closest:selector=>selector==='[data-review-indicator]'?row:selector==='[data-review-add]'?{}:null}});
  assert.match(nodes.get('[data-review-summary]').textContent,/신규 분석 0개 조합 · 기존 분석 재사용·연결 복원 1개 조합/);
  assert.equal(nodes.get('[data-review-run]').disabled,false);
  // Refreshing the review must not discard the user's deliberate restoration.
  await handlers.click({target:{closest:selector=>selector==='[data-review-reload]'?{}:null}});
  assert.match(rows.innerHTML,/사용자가 연결 복원 · 기존 유효 측정값 재사용/);
  await handlers.click({target:{closest:selector=>selector==='[data-review-run]'?{}:null}});
  assert.deepEqual(JSON.parse(JSON.stringify(submitted)),{revision:'r',mappings:{i:['old']}});
  assert.equal(dialog.open,false);
  console.log('PASS manual mapping restoration display, retained-pair exclusion, draft refresh and submission');
})().catch(error=>{console.error(error);process.exitCode=1;});
