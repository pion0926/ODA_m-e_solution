(function(root){
  'use strict';
  function create({request, escapeHtml:esc, notify}) {
    const lines=(items,empty='등록된 항목 없음')=>items?.length?`<ul>${items.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:`<p>${empty}</p>`;
    function claimReview(payload){
      const names=new Map((payload.inputs.documents||[]).map(d=>[d.id,d.original_name]));
      return payload.sections.map(s=>{
        const audit=s.generation_metadata?.claim_audit||{};
        const claims=(audit.claims||[]).map(c=>`${({supported:'근거 확인',conflicting:'상충 근거 있음',deferred:'판정 보류'})[c.verdict]||'확인 필요'} · ${c.claim}`);
        return `<details><summary>${esc(s.title||s.part_id)} · AI 검토 ${s.quality_score==null?'미평가':`${Math.round(s.quality_score)}점`}</summary><h4>검토 주장</h4>${lines(claims,'자동 주장 검토 기록이 없어 직접 확인해야 합니다.')}<h4>확인할 사항</h4>${lines([...(audit.issues||[]),...(s.generation_metadata?.evidence_gaps||[])])}<h4>연결 원문</h4>${lines((s.source_document_ids||[]).map(id=>names.get(id)||'등록 문서'))}</details>`;
      }).join('');
    }
    const openDialog=(title,body)=>{
      const el=document.createElement('dialog');el.className='performance-review-dialog';
      el.innerHTML=`<header class="performance-review-header"><h2>${esc(title)}</h2><button class="btn" data-close-review>닫기</button></header><div class="performance-review-body">${body}</div>`;
      el.querySelector('[data-close-review]').onclick=()=>el.close();el.onclose=()=>el.remove();document.body.append(el);el.showModal();return el;
    };
    async function source(id,start=0,end=null,existing=null){
      try{
        const data=await request(`/api/v2/intake/jobs/${encodeURIComponent(id)}/source?start=${start}${end==null?'':`&end=${end}`}`);
        const loc=data.location||{};
        const body=`<p>${esc(data.file_name)} · ${loc.page?`${loc.page}쪽 · `:''}추출 원문 ${data.start+1}–${data.end}자 / ${data.total_chars}자</p><p><a href="/api/v2/intake/jobs/${encodeURIComponent(id)}/download?inline=true${loc.page?`#page=${loc.page}`:''}" target="_blank" rel="noopener">원본 위치 열기</a></p><pre class="source-excerpt">${esc(data.text)}</pre><p><button class="btn" data-source-next>다음 구간</button></p><h3>등록 사실의 원문 위치</h3>${data.facts.filter(f=>f.source_location).map(f=>`<button class="btn source-fact" data-source-start="${f.source_location.start}" data-source-end="${f.source_location.end}">${esc(f.value||f.fact||f.finding||f.evidence_quote||f.quote)} · ${f.source_location.page?`${f.source_location.page}쪽 · `:''}${f.source_location.line_start}행</button>`).join('')||'<p>위치가 확인된 등록 사실이 없습니다.</p>'}`;
        const dialog=existing||openDialog('원문 근거 확인','');dialog.querySelector('.performance-review-body').innerHTML=body;
        dialog.querySelector('[data-source-next]').onclick=()=>source(id,data.end,null,dialog);
        dialog.querySelector('[data-source-next]').disabled=data.end>=data.total_chars;
        dialog.querySelectorAll('[data-source-start]').forEach(b=>b.onclick=()=>source(id,Number(b.dataset.sourceStart),Number(b.dataset.sourceEnd),dialog));
      }catch(e){notify(e.message);}
    }
    async function review(){
      try {
        const data=await request('/api/v2/report/review');
        const dialog=openDialog('제출 전 검토 · 승인 버전',`<p>${data.submission_status==='approved'?'현재 버전 제출 승인 완료':'생성된 보고서는 검토 대기 상태입니다.'}</p><p>원문 출처와 결론의 타당성을 확인한 뒤 승인합니다. 자료·매핑·본문 변경 시 다시 검토해야 합니다.</p><details><summary>질문·주장별 검토 기록</summary>${claimReview(data.payload)}</details><p><label><input type="checkbox" data-fidelity> 원문과 수치·출처의 일치를 확인했습니다.</label></p><p><label><input type="checkbox" data-validity> 결론·상충 근거·판정보류의 타당성을 확인했습니다.</label></p><label>검토 의견<textarea data-review-note rows="3" maxlength="4000" style="width:100%"></textarea></label><button class="btn primary" data-approve>현재 결과 승인 · 버전 고정</button><p data-review-result role="status"></p><h3>승인 이력 · 현재와 비교</h3>${data.versions.map(v=>`<p><button class="btn" data-version="${esc(v.id)}">${esc(v.created_at)} · ${esc(v.reviewer_name)}</button></p>`).join('')||'<p>승인 이력 없음</p>'}<pre class="source-excerpt" data-version-diff hidden></pre>`);
        dialog.querySelector('[data-approve]').onclick=async e=>{
          e.target.disabled=true;
          try{await request('/api/v2/report/review/approve',{method:'POST',body:JSON.stringify({revision:data.revision,source_fidelity:dialog.querySelector('[data-fidelity]').checked,conclusion_validity:dialog.querySelector('[data-validity]').checked,note:dialog.querySelector('[data-review-note]').value})});dialog.close();notify('검토자와 승인 버전을 고정해 저장했습니다.');}
          catch(err){dialog.querySelector('[data-review-result]').textContent=err.message;e.target.disabled=false;}
        };
        dialog.querySelectorAll('[data-version]').forEach(b=>b.onclick=async()=>{try{const v=await request(`/api/v2/report/review/versions/${encodeURIComponent(b.dataset.version)}`);const out=dialog.querySelector('[data-version-diff]');out.hidden=false;out.textContent=JSON.stringify(v.changes_to_current,null,2);}catch(e){notify(e.message);}});
      }catch(e){notify(e.message);}
    }
    document.getElementById('reportReviewApproval')?.addEventListener('click',review);
    document.addEventListener('click',e=>{const b=e.target.closest('[data-document-source]');if(b)source(b.dataset.documentSource);});
    return {source,review};
  }
  root.ServiceReview={create};
})(window);
