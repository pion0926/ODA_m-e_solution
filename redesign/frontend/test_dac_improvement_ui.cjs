const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window:{}}; vm.createContext(context);
vm.runInContext(fs.readFileSync('assets/dac-scoring-ui.js','utf8'),context);
const esc = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const render = item => context.window.DacScoringUI.renderImprovements(item,esc);
assert.equal(render({}), '');
const html = render({name:'<script>분야</script>',improvement_guidance:{is_stale:true, notice:'재평가 필요',items:[
  {kind:'evidence',title:'<img src=x onerror=alert(1)>',reason:'미확인',action:'연결',required_evidence:'원자료',question:'지속가능한가?'}]}});
assert(!html.includes('<script>')); assert(!html.includes('<img'));
assert(html.includes('이전 평가 기준')); assert(html.includes('증빙 보완 1건'));
assert(html.includes('href="#/evidence"')); assert(html.includes('href="#/eval/board"'));
assert(!html.includes('open>'));
assert(render({name:'효율성',improvement_guidance:{items:[]}}).includes('후속 측정'));
console.log('PASS improvement disclosure, stale guidance, escaping and workflow links');
