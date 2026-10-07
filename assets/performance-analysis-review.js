(function(root) {
  'use strict';
  const states = {awaiting_review:'업로드 화면에서 처리 방식 선택 필요',queued:'분석 대기',processing:'기본 분석 중',retry:'재시도 중',waiting_llm:'AI 연결 대기',failed:'분석 실패',cancelled:'사용자 중지',completed:'준비 완료'};
  function create({request, start, refreshIntake, notify, escapeHtml:esc}) {
    let dialog=null, plan=null, busy=false, timer=null, loading=null, draft=new Map(), search='';
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
      $('[data-review-summary]').textContent=`PDM: ${plan.source_file_name || '미등록'} · 신규 분석 ${pairs}개 조합 · 대상 지표 ${mapped}개 · 연결 변경 ${(plan.mapping_changed_indicator_ids||[]).length}개 지표 · 유효한 기존 분석 유지`;
      $('[data-review-status]').textContent=plan.message;
      $('[data-review-pending]').innerHTML=plan.documents.filter(doc=>doc.status!=='completed').map(doc=>
        `<div class="performance-document"><b>${esc(doc.file_name)}</b><small>${esc(states[doc.status]||doc.status)} · ${Number(doc.progress)||0}%</small>${['failed','waiting_llm','cancelled'].includes(doc.status)?`<button type="button" class="btn sm" data-review-retry="${esc(doc.id)}" ${busy?'disabled':''}>분석 재시도</button><small class="performance-error">${esc(doc.error_message||'기본 분석 완료가 필요합니다.')}</small>`:''}</div>`).join('');
      $('[data-review-rows]').innerHTML=plan.indicators.map(item=>`<tr data-review-indicator="${esc(item.id)}">
        <td><span class="tag n">${esc(item.tier_name)}</span><p><b>${esc(item.text)}</b></p><small>검증수단: ${esc(item.mov)}</small><p>기존 분석 연결 ${(item.retained_document_ids||[]).length}건 유지${(item.deferred_document_ids||[]).length?` · 이전 ${(item.deferred_document_ids||[]).length}건 목적 재검토 대기`:''}</p></td>
        <td>${[...selected(item)].map(id=>{const doc=docs.get(id);return doc ? `<div class="performance-document"><a href="/api/v2/intake/jobs/${encodeURIComponent(id)}/download" target="_blank" rel="noopener">${esc(doc.file_name)}</a>
          <small>${esc(item.mapping_details?.[id]?.proves || '사용자가 추가한 문서 · 분석 시 근거 확인')}</small><small>${esc(item.mapping_details?.[id]?.limitations || '')}</small><button type="button" class="btn sm" data-review-remove="${esc(id)}" aria-label="${esc(doc.file_name)} 매핑 해제" ${busy?'disabled':''}>해제</button>
          ${['failed','waiting_llm','cancelled'].includes(doc.status)?`<button type="button" class="btn sm" data-review-retry="${esc(id)}" ${busy?'disabled':''}>분석 재시도</button><small class="performance-error">${esc(doc.error_message||'기본 분석 완료가 필요합니다.')}</small>`:''}</div>`:'';}).join('') || '<span class="performance-missing">신규 분석 대상 없음 · 기존 결과 유지</span>'}</td>
        <td><select aria-label="${esc(item.text)} 기존 문서 선택" ${busy?'disabled':''}>${options(item)}</select>
          <div class="performance-row-actions"><button type="button" class="btn sm" data-review-add ${busy?'disabled':''}>매핑 추가</button><button type="button" class="btn sm" data-review-upload ${busy?'disabled':''}>새 문서 업로드</button></div></td>
      </tr>`).join('') || '<tr><td colspan="3">등록된 PDM 지표가 없습니다. <a href="#/evidence" data-review-close>사업 기준 문서 등록으로 이동</a></td></tr>';
      $('[data-review-run]').disabled=busy||!plan.ready||(pairs===0&&!(plan.mapping_changed_indicator_ids||[]).length);
      $('[data-review-reload]').disabled=busy;
      $('[data-review-close]').disabled=busy;
    }
    async function load() {
      if (loading) return loading;
      loading=(async()=>{
        try {
          const next=await request('/api/v2/pdm/analysis-plan',{timeoutMs:15000});
          if (!dialog?.open) return;
          const sourceChanged=plan&&plan.source_document_id!==next.source_document_id;
          if (sourceChanged) { draft.clear(); error('PDM 기준 문서가 변경되어 매핑을 새로 불러왔습니다. 지표와 문서를 다시 확인해 주세요.'); }
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
      const review={revision:plan.revision,mappings:Object.fromEntries(plan.indicators.map(item=>[item.id,[...selected(item)]]))};
      try {
        const job=await start(review);
        if(job){dialog.close();await refreshIntake();}
        else {error('분석 접수를 완료하지 못했습니다. 최신 자료와 매핑을 확인하고 다시 실행해 주세요.');await load();}
      } finally {busy=false;render();}
    }
    async function open() {
      if(dialog?.open){dialog.focus();return;}
      draft=new Map();plan=null;search='';busy=false;
      if(!dialog){
        dialog=document.createElement('dialog');dialog.className='performance-review-dialog';dialog.id='performanceReviewDialog';
        dialog.setAttribute('aria-labelledby','performanceReviewTitle');
        dialog.innerHTML=`<header class="performance-review-header"><div><h2 id="performanceReviewTitle">성과지표 분석 준비</h2><p>분석 범위와 지표별 문서 매핑을 확인해 주세요.</p></div><button type="button" class="btn" data-review-close aria-label="분석 준비 닫기">닫기</button></header>
          <div class="performance-review-body"><section class="performance-overview"><h3>신규 문서·신규 매핑만 분석합니다</h3><ol><li>검증을 마친 문서–지표 조합은 재사용합니다. 집계 범위 등 검토 규칙이 바뀐 조합만 다시 확인합니다.</li><li>새 조합의 원문과 이전 평가 정보를 함께 비교합니다. 연결이 해제된 실적 근거는 결과에서 제외하고 목표 정의의 근거는 별도로 보존합니다.</li><li>같은 대상·집계 범위·단위에서 최신 실적, 같은 기준일이면 높은 수치로 갱신합니다. 개별 행사는 완료 사실과 식별 근거를 검증해 중복을 제외합니다. 누적 실적과 개별 행사 또는 범위가 다른 값은 무조건 합산하지 않습니다.</li></ol><p>이 화면을 여는 것만으로 성과 분석은 실행되지 않습니다. 매핑 변경은 아래 <b>분석 실행</b>을 누를 때 저장됩니다.</p></section>
          <p data-review-summary></p><div class="performance-review-tools"><label>기존 문서 검색 <input type="search" data-review-search placeholder="추가할 문서명 검색"></label><button type="button" class="btn" data-review-reload>자료 상태 새로고침</button></div>
          <div class="performance-review-table"><table><thead><tr><th>성과지표 · 목표 · 검증수단</th><th>신규 분석할 문서</th><th>자료 추가</th></tr></thead><tbody data-review-rows></tbody></table></div>
          <p data-review-status role="status"></p><div data-review-pending></div><p data-review-message role="status" class="performance-review-message"></p></div>
          <footer class="performance-review-footer"><span>새 문서는 기본 분석·매칭 완료 후 사용할 수 있습니다.</span><button type="button" class="btn primary" data-review-run disabled>분석 실행</button></footer>
          <input hidden type="file" multiple data-review-file accept=".pdf,.hwp,.hwpx,.docx,.xlsx,.pptx,.csv,.txt,.md,.zip">`;
        document.body.appendChild(dialog);
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
  root.PerformanceAnalysisReview={create};
})(window);
