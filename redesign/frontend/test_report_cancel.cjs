const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('assets/app-controller.js', 'utf8');
const code = source.slice(source.indexOf('  function renderGeneration('), source.indexOf('  async function generateAllReport('));
const elements = new Map();
function element() { return {dataset:{},style:{},parentElement:{},addEventListener(type,fn){this[type]=fn;},after(node){elements.set(node.id,node);}}; }
const calls=[];
const env = { document:{createElement:element}, byId(id){ if(id==='reportCancel')return elements.get(id); if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  reportSections:[],activeReportPart:null,renderSectionAssistant(){},refreshReportSections:async()=>{},
  latestGenerationStatus:{id:'run',status:'running',completed_sections:13},generationTimer:null,generationPollRevision:0,
  window:{ServiceJobTray:{update(_key,value){env.tray=value;}}},
  clearTimeout(){},setTimeout(_fn,ms){env.delay=ms;return 1;},notify(){},
  request:async (url,options)=>{calls.push([url,options]); return {id:'run',status:'running',completed_sections:13,cancel_requested:true};}
};
vm.createContext(env);vm.runInContext(code,env);
(async()=>{
  env.renderGeneration(env.latestGenerationStatus);
  const button=elements.get('reportCancel');assert.equal(button.hidden,false);assert.equal(button.disabled,false);
  await button.click();assert.equal(calls[0][0],'/api/v2/report/generation/run/cancel');assert.equal(calls[0][1].method,'POST');
  assert.equal(button.disabled,true);assert.match(button.textContent,/중단 요청됨/);
  env.renderGeneration({status:'cancelled',completed_sections:13});assert.equal(button.hidden,true);assert.equal(env.tray.cancelled,true);
  assert.match(elements.get('reportGenerationStage').textContent,/중단/);
  env.request=async()=>{throw new Error('offline');};await env.pollGeneration();assert.equal(env.delay,5000);
  console.log('PASS cancel click, pending state, terminal state and polling reconnect');
})().catch(e=>{console.error(e);process.exitCode=1;});
