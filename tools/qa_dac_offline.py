"""Local-only audit and rendering. Never invokes an LLM or writes the database."""
import hashlib
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.evaluation_runner import _load_documents
from kodame_intake.dac_replay import fingerprint
from kodame_intake.parsers import parse_document
from kodame_intake.openrouter import redact_for_external_analysis
from kodame_intake.dac_rules import score_question
from kodame_intake.dac_assessor import template
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA

out=Path('/review'); out.mkdir(exist_ok=True)
root=Path('/workspace')
pool.open()
with tenant_context('05460961-f12e-4fe7-ba6f-3e36e27bd23d'):
    docs=_load_documents()
    inventory=[]
    for doc in docs:
        path=Path(doc['stored_path'])
        actual_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_hash==doc['sha256']
        text,method=parse_document(path,doc['extension'],full_text=True)
        assert text.strip()
        inventory.append({'id':doc['id'],'name':doc['name'],'sha256':actual_hash,
            'fulltext_chars':len(text),'method':method,'period':doc['period'],
            'summary_assigned_criteria':doc['assigned_criteria'],
            'all_criteria_review':doc['review_all'],
            'has_source_markers':bool(re.search(r'\[(PDF 페이지|문단|시트:)',text))})
    digest=fingerprint(docs,'offline-audit')
    assert digest==fingerprint(docs,'offline-audit')
    assert digest!=fingerprint(docs[:-1],'offline-audit')
    changed=[dict(d) for d in docs];changed[-1]['sha256']='content-replaced'
    assert digest!=fingerprint(changed,'offline-audit')
    result={'document_count':len(docs),'fulltext_chars':sum(d['fulltext_chars'] for d in inventory),
        'file_hashes_verified':True,'fulltext_extraction_complete':True,'new_or_changed_document_invalidates':True,
        'external_llm_calls':0,'database_writes':0,'documents':inventory}
    (out/'local-data-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='documents'},ensure_ascii=False),flush=True)

# Render a deliberately synthetic held assessment, not an actual user01 result.
q=template(EVALUATION_CRITERIA['relevance'])['question_assessments'][0]
for check in q['indicators']:
    check['finding']='현재 자료에서 해당 지표를 직접 입증할 수 없어 필요한 증빙과 평가시점을 추가로 확인해야 합니다.'
for key in ('four_point_gate','specific_cap','red_flag'):
    q[key]['finding']='판정에 필요한 직접 증빙을 확보하지 못하여 현재는 확인을 보류합니다.'
trace=score_question(q['question_id'],q,{})
question={'score':None,'scoring_trace':trace,'evidence_quotes':[]}
html=(root/'frontend/index.html').read_text(encoding='utf-8')
styles='\n'.join(re.findall(r'<style[^>]*>(.*?)</style>',html,re.S))
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    page=browser.new_page()
    for width in (390,1280):
        page.set_viewport_size({'width':width,'height':1000})
        page.set_content('<meta charset="utf-8"><style>'+styles+'</style><main style="max-width:1000px;margin:16px auto;padding:12px;background:white"><h2>DAC 근거와 점수 계산</h2><div id="view"></div></main>')
        page.add_script_tag(path=str(root/'assets/dac-scoring-ui.js'))
        page.evaluate('''q=>{const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));document.querySelector('#view').innerHTML=DacScoringUI.render(q,esc)}''',question)
        assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth')
        assert '점수 판정 보류' in page.locator('#view').inner_text()
        page.screenshot(path=str(out/f'trace-{width}.png'),full_page=True)
    browser.close()
print('OFFLINE_UI_PASS',flush=True)
