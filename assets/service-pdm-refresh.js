(function(root) {
  'use strict';
  function create({request, update, button, refreshViews, notify}) {
    let polling = null, lastSaved = null, lastJob = null;
    function render(job) {
      lastJob = job;
      button(Boolean(job.active));
      if (job.status === 'not_run') return;
      const detail = job.active ? '증빙·실적·리스크를 분석 중입니다. 새로고침해도 서버 작업은 계속됩니다.'
        : job.error_message || job.result?.message || 'PDM 상태 확인 완료';
      update({name:'성과지표 분석', active:job.active, failed:job.status === 'failed',
        warning:job.status === 'partial', detail});
    }
    async function apply(job) {
      render(job);
      if (!['completed','partial'].includes(job.status) || lastSaved === job.id) return;
      try {
        await refreshViews(job);
        lastSaved = job.id;
      } catch (_) {
        // This is a display error, not a failed mutation. Retain the server receipt
        // and retry view synchronization on the next poll without another POST.
        update({name:'성과지표 분석',active:false,failed:false,warning:true,
          detail:(job.result?.message || 'PDM 저장 완료') + ' · 화면 조회 지연, 자동 재확인 중'});
      }
    }
    async function sync() {
      if (polling) return polling;
      polling = (async () => {
        try { const job=await request('/api/v2/pdm/refresh/status',{timeoutMs:15000}); await apply(job); return job; }
        catch (_) {
          if (lastJob?.active) update({name:'성과지표 분석',active:true,warning:true,
            detail:'서버 상태 조회가 지연되고 있습니다. 작업 실패로 확정하지 않고 자동 재확인합니다.'});
          return null;
        }
      })();
      try { return await polling; } finally { polling=null; }
    }
    async function start(review) {
      button(true);
      const previousId=lastJob?.id;
      try {
        const job=await request('/api/v2/pdm/refresh',{method:'POST',timeoutMs:15000,
          ...(review ? {headers:{'Content-Type':'application/json'},body:JSON.stringify(review)} : {})});
        await apply(job);
        notify('성과 분석을 접수했습니다. AI 작업에서 진행 상태를 확인할 수 있습니다.');
        return job;
      } catch (error) {
        const job=await sync();
        if (job?.active || (job?.id !== previousId && ['completed','partial'].includes(job?.status))) {
          notify('서버에서 PDM 작업 상태를 확인했습니다.');
          return job;
        } else {
          button(false);
          notify(error.status ? error.message : '접수 응답을 확인하지 못했습니다. AI 작업 상태를 확인한 뒤 다시 시도해 주세요. 중복 실행은 서버에서 방지합니다.');
          return null;
        }
      }
    }
    return {start,sync};
  }
  root.ServicePdmRefresh={create};
  if (typeof module !== 'undefined') module.exports={create};
})(typeof window === 'undefined' ? globalThis : window);
