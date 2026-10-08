(function(root) {
  'use strict';
  const jobs = new Map();
  const pending = new Set();
  let performAction = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function render() {
    const target = document.getElementById('trayJobs');
    if (!target) return;
    const active = [...jobs.values()].some(job => job.active);
    document.getElementById('trayLive')?.classList.toggle('on', active);
    if (active) document.getElementById('tray')?.classList.add('on');
    const close = document.getElementById('tray')?.querySelector?.('[data-close="tray"]');
    if (close) close.hidden = active;
    target.innerHTML = jobs.size ? [...jobs.values()].sort((a,b) =>
      (a.priority ?? (a.active ? 1 : 5)) - (b.priority ?? (b.active ? 1 : 5)) || (a.queuePosition || 0) - (b.queuePosition || 0)).map(job => {
      const percent = job.total > 0 ? Math.max(0, Math.min(100, Math.round(job.completed / job.total * 100))) : null;
      const action = job.documentId && job.action ? [job.action, ...(job.offerRetry ? ['retry'] : [])].map(action => `<button class="btn sm" data-intake-action="${action}" data-intake-id="${escape(job.documentId)}" ${pending.has(job.documentId) ? 'disabled' : ''}>${action === 'review' ? '처리 방식 선택' : action === 'cancel' ? '중지' : '재요청'}</button>`).join(' ') : '';
      return `<div class="job"><div class="jt"><span style="overflow-wrap:anywhere">${escape(job.name)}</span><span class="jst ${job.active ? '' : 'done'}">${escape(job.statusLabel || (job.active ? '진행 중' : job.cancelled ? '중단' : job.failed ? '실패' : job.warning ? '확인 필요' : '완료'))}</span></div>${percent === null ? '' : `<div class="jbar"><i style="width:${percent}%"></i></div>`}<div class="jd" style="overflow-wrap:anywhere">${escape(job.detail)}</div>${action}</div>`;
    }).join('') : '<div class="tray-empty">진행 중인 AI 작업이 없습니다.</div>';
  }
  function update(key, job) {
    if (job.active || job.failed || job.cancelled || job.warning || job.restored || jobs.has(key)) jobs.set(key, job);
    render();
  }
  function clear() { jobs.clear(); pending.clear(); document.getElementById('tray')?.classList.remove('on'); render(); }
  function configure(handler) {
    performAction = handler;
    const target = document.getElementById('trayJobs');
    if (target) target.onclick = async event => {
      const button = event.target.closest('[data-intake-action]');
      if (!button || pending.has(button.dataset.intakeId)) return;
      const id = button.dataset.intakeId;
      pending.add(id); render();
      try { await performAction(id, button.dataset.intakeAction); }
      finally { pending.delete(id); render(); }
    };
  }
  function syncIntake(documents) {
    const ids = new Set(documents.map(doc => `intake:${doc.id}`));
    for (const key of jobs.keys()) if (key.startsWith('intake:') && !ids.has(key)) jobs.delete(key);
    const labels = {queued:'분석 대기', processing:'분석 중', retry:'재시도 대기', waiting_llm:'AI 연결 대기', failed:'분석 실패', completed:'분석 완료', cancelled:'중지됨',awaiting_review:'처리 방식 선택 필요'};
    const stages = {queued:'분석 슬롯이 비면 대기 순서에 따라 시작합니다.', parsing:'문서에서 텍스트를 추출하고 있습니다.', stored:'추출한 텍스트를 저장했습니다.', analyzing:'AI 기본 분석을 진행하고 있습니다.', review:'기본 분석과 파일별 매칭을 저장했습니다.'};
    for (const doc of documents) {
      const key = `intake:${doc.id}`;
      if (doc.status === 'completed' && !jobs.has(key)) continue;
      const active = ['queued','processing','retry'].includes(doc.status);
      let detail = stages[doc.stage] || labels[doc.status] || doc.stage || doc.status;
      if (doc.stage==='triaging') detail='일부 본문으로 산출물 등록 또는 일반 자료 분석을 사전 판단하고 있습니다.';
      if (doc.status==='completed' && doc.intake_mode==='artifact') detail='산출물 기본 정보와 일부 본문의 관련 항목을 등록했습니다. 제작·배포·효과는 별도 확인이 필요합니다.';
      if (doc.status==='awaiting_review') detail=doc.triage?.reason || '유형 판단이 불확실합니다. 처리 방식을 선택해 주세요.';
      if (doc.stage === 'analyzing' && Number(doc.progress) >= 68) detail = ['project_plan','pdm'].includes(doc.upload_role) ? '기준 문서의 원문 근거와 사업 구성을 분석하고 있습니다.' : '사업계획서·PDM·DAC 슬롯·보고서 섹션과의 매칭을 분석하고 있습니다.';
      if (['failed','waiting_llm','retry'].includes(doc.status)) detail = doc.error_message || labels[doc.status];
      if (doc.cancel_requested && doc.status === 'processing') detail = '중지 요청을 접수했습니다. 현재 외부 AI 응답이 끝나면 결과를 반영하지 않고 중지합니다.';
      if (doc.status === 'cancelled') detail = '사용자가 중지했습니다. 재요청하면 실행 시점의 최신 연결 모델로 분석합니다.';
      if (['queued','retry'].includes(doc.status)) detail += ' 실행 시 최신 연결 모델을 사용합니다.';
      else if (doc.analysis_model) detail += ` · 모델: ${doc.analysis_model}`;
      jobs.set(key, {name:`문서 분석 · ${doc.file_name}`, active, failed:doc.status==='failed', warning:['waiting_llm','awaiting_review'].includes(doc.status),
        documentId:doc.id, offerRetry:doc.status==='waiting_llm', action:doc.status==='awaiting_review' ? 'review' : doc.cancel_requested && doc.status==='processing' ? null : ['queued','processing','retry','waiting_llm'].includes(doc.status) ? 'cancel' : ['failed','cancelled'].includes(doc.status) ? 'retry' : null,
        priority:({processing:0,awaiting_review:1,queued:2,retry:3,waiting_llm:4,failed:4,completed:5})[doc.status], queuePosition:Number(doc.queue_position)||0,
        statusLabel:doc.cancel_requested && doc.status==='processing' ? '중지 중' : labels[doc.status], completed:Number(doc.progress)||0, total:100, detail});
    }
    render();
  }
  root.ServiceJobTray = {update, render, clear, syncIntake, configure};
})(window);
