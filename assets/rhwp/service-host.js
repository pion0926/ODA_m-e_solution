const reportDownload = new URLSearchParams(location.search).get('url') || '';
const isReportProof = /^\/api\/v2\/report\/exports\/[a-f0-9-]+\/download$/.test(reportDownload);
window.kodameReadOnlyReport = isReportProof;
if (isReportProof) {
  document.addEventListener('DOMContentLoaded', () => {
    const nav = document.createElement('nav');
    nav.id = 'report-proof-navigation';
    nav.setAttribute('aria-label', '보고서 미리보기');
    const back = document.createElement('a'); back.href = '/#/eval/report'; back.textContent = '← 보고서 작성으로 돌아가기';
    const label = document.createElement('span'); label.textContent = '생성된 보고서 · 읽기 전용';
    const download = document.createElement('a'); download.href = reportDownload; download.textContent = 'HWPX 내려받기';
    nav.append(back, label, download); document.body.prepend(nav);
    const style = document.createElement('style');
    style.textContent = '#report-proof-navigation{height:48px;box-sizing:border-box;display:flex;align-items:center;gap:24px;padding:0 20px;background:#fff;color:#183b67;font:14px sans-serif;border-bottom:1px solid #ccd5df}#report-proof-navigation a{color:#183b67}#report-proof-navigation span{flex:1}#studio-root{height:calc(100vh - 48px)!important}';
    document.head.append(style);
  });
}
// Service-owned guard, loaded before the generated Studio module runs.
if (isReportProof || new URLSearchParams(location.search).get('sectionPreview') === '1') {
  window.addEventListener('message', event => {
    if (!['rhwp-request', 'rhwp-connect', 'hwpctl-load', 'section-preview-fit', 'section-preview-zoom'].includes(event.data?.type)) return;
    const allowed = event.origin === location.origin && event.source === parent;
    const methodAllowed = event.data.type === 'section-preview-fit' ||
      (event.data.type === 'section-preview-zoom' && ['in', 'out', '100', 'fit'].includes(event.data.action)) ||
      (event.data.type === 'rhwp-request' && ['ready', 'loadFile', 'pageCount', 'getPageSvg'].includes(event.data.method));
    if (!allowed || !methodAllowed) event.stopImmediatePropagation();
  }, true);
}
function requestSafeHwpxSave(event) {
  event.preventDefault();
  event.stopImmediatePropagation();
  if (isReportProof) location.assign(reportDownload);
  else parent.postMessage({ type: 'rhwp-safe-save-request' }, location.origin);
}
window.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 's') requestSafeHwpxSave(event);
}, true);
for (const type of ['pointerdown', 'mousedown', 'click']) {
  document.addEventListener(type, event => {
    if (event.target?.closest?.('[data-cmd="file:save"], [data-cmd="file:save-as"]')) requestSafeHwpxSave(event);
  }, true);
}
