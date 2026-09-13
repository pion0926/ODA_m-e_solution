(function(root) {
  'use strict';
  const jobs = new Map();
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function render() {
    const target = document.getElementById('trayJobs');
    if (!target) return;
    document.getElementById('trayLive')?.classList.toggle('on', [...jobs.values()].some(job => job.active));
    target.innerHTML = jobs.size ? [...jobs.values()].map(job => {
      const percent = job.total > 0 ? Math.max(0, Math.min(100, Math.round(job.completed / job.total * 100))) : null;
      return `<div class="job"><div class="jt"><span>${escape(job.name)}</span><span class="jst ${job.active ? '' : 'done'}">${job.active ? '진행 중' : job.failed ? '실패' : '완료'}</span></div>${percent === null ? '' : `<div class="jbar"><i style="width:${percent}%"></i></div>`}<div class="jd">${escape(job.detail)}</div></div>`;
    }).join('') : '<div class="tray-empty">진행 중인 AI 작업이 없습니다.</div>';
  }
  function update(key, job) {
    if (job.active || job.failed || jobs.has(key)) jobs.set(key, job);
    render();
  }
  function clear() { jobs.clear(); render(); }
  root.ServiceJobTray = {update, render, clear};
})(window);
