"""Check saved live results against original indexed text and render actual traces."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from kodame_intake.dac_rules import score_question, mean_score
from kodame_intake.openrouter import redact_for_external_analysis
from kodame_intake.dac_evidence import _quote_matches

root=Path('/workspace')
output=Path('/review')
data_root=Path('/app/data')
first=json.loads((data_root/'qa/dac-20260918/first.json').read_text())
repeat=json.loads((data_root/'qa/dac-20260918/repeat.json').read_text())
assert first['criteria']==repeat['criteria']
assert repeat['reused_from_run_id']==first['run_id']
questions=[q for c in first['criteria'] for q in c['question_assessments']]
assert len(questions)==11
assert sum(len(q['scoring_trace']['checks']) for q in questions)==55
source_texts={}
review=[]
for q in questions:
    registry={e['evidence_id']:e for e in q['evidence_quotes']}
    for source in registry.values():
        did=source['document_id']
        if did not in source_texts:
            matches=list(data_root.rglob(did+'.dac-fulltext.txt'))
            assert len(matches)==1, (did,len(matches))
            source_texts[did]=redact_for_external_analysis(matches[0].read_text())[0]
        assert _quote_matches(source['quote'],source_texts[did]),source['file_name']
        assert source['locator']['text_sha256']
    trace=q['scoring_trace']
    candidates={eid:e for eid,e in registry.items() if e.get('table_row_candidate')}
    rows=q.get('table_row_reviews',[])
    assert {r['evidence_id'] for r in rows}==set(candidates)
    assert len(rows)==len(candidates)
    measurements=[m for c in trace['checks'] for m in c['measurements']]
    for row in rows:
        matches=[m for m in measurements if m.get('table_row_id')==row['evidence_id']]
        assert len(matches)==(1 if row['decision']=='included' else 0)
        for measurement in matches:
            assert all(measurement[k]==candidates[row['evidence_id']][k] for k in ('target','actual'))
    assert q['positive_evidence']==[c['finding'] for c in trace['checks'] if c['valid_evidence'] and c['state'] in {'limited','substantial','verified'}]
    item={'question_id':q['question_id'],
        'indicators':[{'indicator_id':c['id'],'state':c['proposed_state'],
            **{key:c[key] for key in ('finding','evidence_ids','quality','source_families','measurements','negative_fact_quote')}} for c in trace['checks']],
        **{key:trace[key] for key in ('four_point_gate','specific_cap','red_flag')}}
    computed=score_question(q['question_id'],item,registry)
    for field in ('selected_score','merit_index','coverage','confidence','status','checks'):
        assert computed[field]==trace[field],(q['question_id'],field)
    review.append({'question_id':q['question_id'],'score':q['score'],'finding':q['finding'],
        'status':trace['status'],'coverage':trace['coverage'],'confidence':trace['confidence'],
        'citations':len(registry),'pdm_indicators':q['pdm_indicator_ids'],
        'table_row_reviews':rows,
        'checks':[{key:c[key] for key in ('id','criterion','state','finding','quality','measurements','applied_rules')} for c in trace['checks']]})
for criterion in first['criteria']:
    assert mean_score([q['score'] for q in criterion['question_assessments']])==criterion['score']
report={'run_id':first['run_id'],'repeat_run_id':repeat['run_id'],'model':first['model'],
    'scores':{c['name']:c['score'] for c in first['criteria']},'overall':first['overall'],
    'rule_recalculation_pass':True,'quotes_match_original_text':True,'replay_identical':True,
    'cited_document_count':len(source_texts),'question_count':len(questions),
    'citation_count':sum(len(q['evidence_quotes']) for q in questions),'questions':review}
output.mkdir(exist_ok=True)
(output/'live-result-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
html=(root/'frontend/index.html').read_text(encoding='utf-8')
styles='\n'.join(re.findall(r'<style[^>]*>(.*?)</style>',html,re.S))
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    page=browser.new_page()
    for width in (390,1280):
        page.set_viewport_size({'width':width,'height':1000})
        page.set_content('<meta charset="utf-8"><style>'+styles+'</style><main style="max-width:1000px;margin:16px auto;padding:12px;background:white"><h2>user01 DAC 실제 평가</h2><div id="view"></div></main>')
        page.add_script_tag(path=str(root/'assets/dac-scoring-ui.js'))
        page.evaluate('''items=>{const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));document.querySelector('#view').innerHTML=items.map(q=>'<h3>'+esc(q.question)+'</h3>'+DacScoringUI.render(q,esc)).join('')}''',questions)
        assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth')
        assert page.locator('.dac-score-trace').count()==11
        page.screenshot(path=str(output/f'live-trace-{width}.png'),full_page=True)
        page.screenshot(path=str(output/f'live-top-{width}.png'))
        page.locator('.dac-score-trace').nth(6).evaluate("e=>e.scrollIntoView({block:'start'})")
        page.screenshot(path=str(output/f'live-held-{width}.png'))
        # Expand one real citation group and ensure long evidence remains inside the viewport.
        page.locator('.evidence-fold').first.locator('summary').click()
        assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth')
        page.locator('.dac-score-trace').first.screenshot(path=str(output/f'live-detail-{width}.png'))
    browser.close()
print(json.dumps({k:v for k,v in report.items() if k!='questions'},ensure_ascii=False),flush=True)
print('LIVE_RESULT_REVIEW_PASS',flush=True)
