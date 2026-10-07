(function(root) {
  'use strict';
  const states = {awaiting_review:'업로드 화면에서 처리 방식 선택 필요',queued:'분석 대기',processing:'기본 분석 중',retry:'재시도 중',waiting_llm:'AI 연결 대기',failed:'분석 실패',cancelled:'사용자 중지',completed:'준비 완료'};
  function create({request, start, refreshIntake, notify, escapeHtml:esc}) {
    let dialog=null, plan=null, busy=false, timer=null, loading=null, draft=new Map(), search='', fullQuestions=new Set();
    const $ = selector => dialog.querySelector(selector);
    const selected = item => draft.get(item.id) || new Set(item.document_ids);
    const error = message => { $('[data-review-message]').textContent=message; };
    function options(item) {
      const ids=selected(item);
      return '<option value="">신규 매핑할 문서 선택</option>' + plan.documents.filter(doc=>doc.status==='completed'&&!ids.has(doc.id)&&!(item.analyzed_document_ids||[]).includes(doc.id)&&doc.file_name.toLowerCase().includes(search.toLowerCase()))
        .map(doc=>`<option value="${esc(doc.id)}">${esc(doc.file_name)}</option>`).join('');
    }
    function render() {
      if (!dialog?.open || !plan) return;
      const docs=new Map(plan.documents.map(doc=>[doc.id,doc]));
      const mapped=plan.indicators.filter(item=>selected(item).size).length;
      const pairs=plan.indicators.reduce((n,item)=>n+selected(item).size,0);
      $('[data-review-summary]').textContent=`DAC 질문 ${plan.indicators.length}개 · 검토 문서 연결 ${pairs}개 · 문서가 연결된 질문 ${mapped}개`; 
      $('[data-review-status]').textContent=plan.message+' 입력이 같은 질문의 검증 결과는 재사용하며, 자료·모델·평가기준·평가시점이 달라진 질문은 다시 평가합니다.';
      $('[data-review-pending]').innerHTML=plan.documents.filter(doc=>doc.status!=='completed').map(doc=>
        `<div class="performance-document"><b>${esc(doc.file_name)}</b><small>${esc(states[doc.status]||doc.status)} · ${Number(doc.progress)||0}%</small>${['failed','waiting_llm','cancelled'].includes(doc.status)?`<button type="button" class="btn sm" data-review-retry="${esc(doc.id)}" ${busy?'disabled':''}>분석 재시도</button><small class="performance-error">${esc(doc.error_message||'기본 분석 완료가 필요합니다.')}</small>`:''}</div>`).join('');
      $('[data-review-rows]').innerHTML=plan.indicators.map(item=>`<tr data-review-indicator="${esc(item.id)}">
        <td><span class="tag n">${esc(item.tier_name)}</span><p><b>${esc(item.text)}</b></p><small>검증수단: ${esc(item.mov)}</small><p><label><input type="checkbox" data-review-full ${fullQuestions.has(item.id)?'checked':''} ${busy?'disabled':''}> 이 질문의 선택 문서 전체 본문 검토</label></p></td>
        <td>${[...selected(item)].map(id=>{const doc=docs.get(id);return doc ? `<div class="performance-document"><a href="/api/v2/intake/jobs/${encodeURIComponent(id)}/download" target="_blank" rel="noopener">${esc(doc.file_name)}</a>
          <small>${esc(doc.summary||'요약 없음')}</small><small>검토 목적: ${esc(item.scopes?.[id]?.reason||'추가 매핑')}</small><small>미검토 범위 ${(item.scopes?.[id]?.unreviewed_ranges||[]).reduce((n,r)=>n+r[1]-r[0],0).toLocaleString()}자 / 원문 ${(item.scopes?.[id]?.source_characters||0).toLocaleString()}자 · 근거 부족·상충 시 자동 확대 검토</small><small>${esc(item.scopes?.[id]?.limitation||'')}</small><details><summary>${fullQuestions.has(item.id)?'전체 본문 검토 예정 · 추천 구간 보기':'선별한 원문 구간 보기'}</summary>${(item.scopes?.[id]?.previews||[]).map(p=>`<p><b>추출본문 ${p.start+1}–${p.end}자</b><br>${esc(p.excerpt)}…</p>`).join('')||'기본 분석 완료 후 구간을 확인할 수 있습니다.'}</details><button type="button" class="btn sm" data-review-remove="${esc(id)}" aria-label="${esc(doc.file_name)} 매핑 해제" ${busy?'disabled':''}>해제</button>
          ${['failed','waiting_llm','cancelled'].includes(doc.status)?`<button type="button" class="btn sm" data-review-retry="${esc(id)}" ${busy?'disabled':''}>분석 재시도</button><small class="performance-error">${esc(doc.error_message||'기본 분석 완료가 필요합니다.')}</small>`:''}</div>`:'';}).join('') || '<span class="performance-missing">연결 문서 없음 · 근거 부족으로 판정이 보류될 수 있습니다.</span>'}</td>
        <td><select aria-label="${esc(item.text)} 기존 문서 선택" ${busy?'disabled':''}>${options(item)}</select>
          <div class="performance-row-actions"><button type="button" class="btn sm" data-review-add ${busy?'disabled':''}>매핑 추가</button><button type="button" class="btn sm" data-review-upload ${busy?'disabled':''}>새 문서 업로드</button></div></td>
      </tr>`).join('') || '<tr><td colspan="3">등록된 PDM 지표가 없습니다. <a href="#/evidence" data-review-close>사업 기준 문서 등록으로 이동</a></td></tr>';
      $('[data-review-run]').disabled=busy||!plan.ready||pairs===0;
      $('[data-review-reload]').disabled=busy;
      $('[data-review-close]').disabled=busy;
    }
    async function load() {
      if (loading) return loading;
      loading=(async()=>{
        try {
          const next=await request('/api/v2/evaluations/analysis-plan',{timeoutMs:15000});
          if (!dialog?.open) return;
          const sourceChanged=plan&&plan.source_document_id!==next.source_document_id;
          if (sourceChanged) { draft.clear(); error('PDM 기준 문서가 변경되어 매핑을 새로 불러왔습니다. 지표와 문서를 다시 확인해 주세요.'); }
          if (!plan) fullQuestions=new Set(next.indicators.filter(item=>item.full_review).map(item=>item.id));
          plan=next;
          const available=new Set(plan.documents.map(doc=>doc.id));
          for (const [key,ids] of draft) draft.set(key,new Set([...ids].filter(id=>available.has(id)&&!(plan.indicators.find(i=>i.id===key)?.analyzed_document_ids||[]).includes(id))));
          render();
        } catch(e) { if(dialog?.open){error(e.message);$('[data-review-run]').disabled=true;} }
      })();
      try { await loading; } finally { loading=null; }
    }
    function edit(row, operation) {
      const item=plan.indicators.find(item=>item.id===row.dataset.reviewIndicator);
      if(!item)return;
      const ids=new Set(selected(item));operation(ids);draft.set(item.id,ids);render();
    }
    async function upload(input) {
      const files=Array.from(input.files||[]), indicator=input.dataset.indicator;
      if(!files.length||busy)return;
      busy=true;render();
      let failed=[];
      try {
        const item=plan.indicators.find(item=>item.id===indicator);
        const ids=new Set(selected(item));draft.set(indicator,ids);
        for(let index=0;index<files.length;index++) {
          const file=files[index];error(`새 문서 접수 ${index+1}/${files.length} · ${file.name}`);
          const form=new FormData();form.append('files',file,file.name);
          try {
            const result=await request('/api/v2/intake/uploads',{method:'POST',body:form});
            for(const doc of result.accepted||[])ids.add(doc.id);
            for(const rejected of result.rejected||[])failed.push(`${rejected.file_name}: ${rejected.error}`);
          } catch(e) { failed.push(`${file.name}: ${e.message}`); if([401,403].includes(e.status)||e.code==='workspace_changed')break; }
        }
        error(failed.length?failed.join('\n'):'문서를 접수했습니다. 기본 분석·매칭이 완료되면 선택한 지표에 연결한 상태로 분석을 실행할 수 있습니다.');
      } finally {input.value='';busy=false;await load();await refreshIntake();}
    }
    async function run() {
      if(busy||!plan?.ready)return;
      busy=true;render();error('확인한 문서 매핑으로 분석을 접수하고 있습니다.');
      const review={revision:plan.revision,full_questions:[...fullQuestions],mappings:Object.fromEntries(plan.indicators.map(item=>[item.id,[...selected(item)]]))};
      try {
        const job=await start(review);
        if(job){dialog.close();await refreshIntake();}
        else {error('분석 접수를 완료하지 못했습니다. 최신 자료와 매핑을 확인하고 다시 실행해 주세요.');await load();}
      } finally {busy=false;render();}
    }
    async function open() {
      if(dialog?.open){dialog.focus();return;}
      draft=new Map();plan=null;search='';fullQuestions=new Set();busy=false;
      if(!dialog){
        dialog=document.createElement('dialog');dialog.className='performance-review-dialog';dialog.id='dacReviewDialog';
        dialog.setAttribute('aria-labelledby','dacReviewTitle');
        dialog.innerHTML=`<header class="performance-review-header"><div><h2 id="dacReviewTitle">DAC 평가 준비</h2><p>질문별 검토 목적·문서·원문 구간을 확인해 주세요.</p></div><button type="button" class="btn" data-review-close aria-label="분석 준비 닫기">닫기</button></header>
          <div class="performance-review-body"><section class="performance-overview"><h3>저장된 요약·정보·DAC 매핑으로 검토 계획을 준비합니다</h3><ol><li>업로드 때의 매핑과 요약을 참고하여 질문별 검토 문서와 원문 구간을 제안합니다. 추가 AI 평가 없이 준비하는 계획입니다.</li><li>선별 구간과 주변 맥락에서 실제 근거를 검증합니다. 요약만으로 점수를 매기지 않습니다. 누락이 우려되면 문서를 추가하거나 전체 본문 검토를 선택하세요.</li><li>사업계획서·PDM은 계획 대조에, 책·교재는 산출물 내용 확인에 사용합니다. 제작·배포·효과는 별도 근거가 필요합니다.</li><li>확정한 범위의 긍정·반대 근거를 함께 평가합니다. 기존 점수보다 낮아지거나 판정이 보류될 수 있습니다.</li></ol><p>화면을 여는 것만으로 평가가 실행되지 않습니다. 아래 <b>평가 실행</b>을 누르면 현재 계획을 저장하고 평가합니다.</p></section>
          <p data-review-summary></p><div class="performance-review-tools"><label>기존 문서 검색 <input type="search" data-review-search placeholder="추가할 문서명 검색"></label><button type="button" class="btn" data-review-reload>자료 상태 새로고침</button></div>
          <div class="performance-review-table"><table><thead><tr><th>DAC 질문 · 검토할 내용</th><th>검토할 문서 · 원문 범위</th><th>자료 추가</th></tr></thead><tbody data-review-rows></tbody></table></div>
          <p data-review-status role="status"></p><div data-review-pending></div><p data-review-message role="status" class="performance-review-message"></p></div>
          <footer class="performance-review-footer"><span>새 문서는 기본 분석·매칭 완료 후 사용할 수 있습니다.</span><button type="button" class="btn primary" data-review-run disabled>평가 실행</button></footer>
          <input hidden type="file" multiple data-review-file accept=".pdf,.hwp,.hwpx,.docx,.xlsx,.pptx,.csv,.txt,.md,.zip">`;
        document.body.appendChild(dialog);
        dialog.addEventListener('change',event=>{if(event.target.matches('[data-review-full]')){const id=event.target.closest('[data-review-indicator]').dataset.reviewIndicator;if(event.target.checked)fullQuestions.add(id);else fullQuestions.delete(id);render();}});
        dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
        dialog.addEventListener('close',()=>{clearInterval(timer);timer=null;});
        dialog.addEventListener('click',async event=>{
          if(event.target.closest('[data-review-close]')){if(!busy)dialog.close();return;}
          if(event.target.closest('[data-review-run]'))return run();
          if(event.target.closest('[data-review-reload]')){if(!busy)await load();return;}
          if(busy)return;
          const retry=event.target.closest('[data-review-retry]');
          if(retry){busy=true;render();try{await request(`/api/v2/intake/jobs/${encodeURIComponent(retry.dataset.reviewRetry)}/retry`,{method:'POST'});}catch(e){error(e.message);}finally{busy=false;await load();}return;}
          const row=event.target.closest('[data-review-indicator]');if(!row)return;
          const remove=event.target.closest('[data-review-remove]');
          if(remove)return edit(row,ids=>ids.delete(remove.dataset.reviewRemove));
          if(event.target.closest('[data-review-add]')){const id=row.querySelector('select').value;if(id)edit(row,ids=>ids.add(id));return;}
          if(event.target.closest('[data-review-upload]')){const input=$('[data-review-file]');input.dataset.indicator=row.dataset.reviewIndicator;input.click();return;}
        });
        $('[data-review-file]').addEventListener('change',event=>upload(event.target));
        $('[data-review-search]').addEventListener('input',event=>{search=event.target.value;for(const row of dialog.querySelectorAll('[data-review-indicator]'))row.querySelector('select').innerHTML=options(plan.indicators.find(item=>item.id===row.dataset.reviewIndicator));});
      }
      $('[data-review-search]').value='';$('[data-review-rows]').innerHTML='';$('[data-review-summary]').textContent='';$('[data-review-status]').textContent='분석 개요를 불러오는 중입니다.';$('[data-review-run]').disabled=true;error('');dialog.showModal();
      await load();
      timer=setInterval(()=>{if(!busy&&plan?.pending_count&&!['SELECT','INPUT'].includes(document.activeElement?.tagName))load();},3500);
    }
    return {open};
  }
  root.DacAnalysisReview={create};
})(window);
