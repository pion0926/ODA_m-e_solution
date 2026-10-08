const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { window: {} }; vm.createContext(context);
vm.runInContext(fs.readFileSync('assets/dac-scoring-ui.js', 'utf8'), context);
const esc = text => String(text ?? '').replaceAll('<','&lt;').replaceAll('>','&gt;');
const render = question => context.window.DacScoringUI.render(question, esc);
assert(render({score:3, levels:{1:'하위',3:'상위'}}).includes('재평가 후'));
const html = render({score:3,scoring_trace:{selected_score:3,status:'provisional',selected_level_reason:'<script>reason</script>',next_level_gap:'다음 등급 근거',levels:{3:'3점 요건'},checks:[{criterion:'수요 검토',status:'unverified',finding:'확인 필요'}]}});
assert(html.includes('미확인 항목 포함'));
assert(html.includes('상위 점수를 부여하지 않은 이유'));
assert(html.includes('&lt;script&gt;'));
assert(!html.includes('<script>'));
assert(!fs.readFileSync('assets/app-controller.js','utf8').includes('판단 근거 원문 보기'));
const held = render({score:null,scoring_trace:{rubric_digest:'digest',selected_score:null,status:'needs_evidence',
  checks:[],applied_rules:[],coverage:0,confidence:0,merit_index:null},
  evidence_quotes:[{file_name:'<script>bad</script>',quote:'<img src=x>',finding:'원문 위치 검증됨',locator:{section:'PDF 페이지 2'}}]});
assert(held.includes('점수 판정 보류'));
const partialEvidence = render({score:2,scoring_trace:{rubric_digest:'new',selected_score:2,
  status:'proposed',evidence_status:'needs_evidence',coverage:0.4,confidence:58,merit_index:50,checks:[]}});
assert(partialEvidence.includes('2점 산정 근거'));
assert(partialEvidence.includes('증빙 보완 필요'));
assert(partialEvidence.includes('증거 신뢰도 58%'));
assert(!partialEvidence.includes('보류'));
assert(!held.includes('0점 산정'));
assert(held.includes('&lt;img src=x&gt;'));
assert(!held.includes('<script>bad'));
const measurement = render({scoring_trace:{rubric_digest:'digest',checks:[{state:'unverified',
  applied_rules:['근거 부족으로 확인 보류'],measurements:[{metric:'<교육>',target:6,actual:29,unit:'건',period:'2026',
  population:'교과목',ratio:null,comparable:false,due:false}]}]},evidence_quotes:[]});
assert(measurement.includes('목표 6건 / 실적 29건'));
assert(measurement.includes('정의·기간·대상 비교 보류'));
assert(measurement.includes('&lt;교육&gt;'));
const rejected = render({scoring_trace:{rubric_digest:'digest',checks:[{state:'unverified',
  measurements:[{metric:'교육',target:6,actual:999,unit:'건',period:'2026',population:'교과목',
    ratio:null,comparable:true,due:true,validation_error:'원문에서 <999>를 확인할 수 없습니다.'}]}]}});
assert(rejected.includes('원문 확인 전 제안값'));
assert(rejected.includes('점수 반영 제외'));
assert(rejected.includes('&lt;999&gt;'));
assert(!rejected.includes('목표시점 미도래'));
const contextual = render({scoring_trace:{rubric_digest:'new',assessment_basis:'provisional_document_review',
  timing:{scored_count:2,unverified_count:1,not_due_count:2},checks:[{state:'not_due',merit:null}]}});
assert(contextual.includes('현재 자료 기준 잠정 진단'));
assert(contextual.includes('목표시점 미도래 · 평가 제외'));
assert(contextual.includes('자료 미확인 1개'));
assert(contextual.includes('목표시점 미도래 2개'));
console.log('PASS DAC trace rendering, legacy honesty, escaping, no raw quote control');
