// Read-only diagnostics from the same rHWP renderer used by the preview.
// No saved report or browser document is modified by this inspector.
const pending = new Map();
let sequence = 0;
window.addEventListener('message', event => {
  if (event.source !== window || event.origin !== location.origin) return;
  const message = event.data;
  if (message?.type !== 'rhwp-response' || !pending.has(message.id)) return;
  const item = pending.get(message.id);
  pending.delete(message.id);
  clearTimeout(item.timer);
  message.error ? item.reject(new Error(message.error)) : item.resolve(message.result);
});
function request(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = `report-qa-${++sequence}`;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} 응답 시간 초과`)); }, 30000);
    pending.set(id, {resolve, reject, timer});
    window.postMessage({type: 'rhwp-request', id, method, params}, location.origin);
  });
}
const button = document.createElement('button');
button.textContent = '조판 검사';
button.title = '현재 rHWP 페이지의 텍스트·쪽수를 읽기 전용으로 검사';
button.id = 'report-qa-inspect';
document.getElementById('icon-toolbar')?.append(button);
const panel = document.createElement('dialog');
panel.id = 'report-qa-panel';
panel.style.cssText = 'width:min(1000px,90vw);max-height:80vh;overflow:auto;padding:24px;border:1px solid #999';
const close = document.createElement('button');
close.textContent = '검사 닫기';
close.addEventListener('click', () => panel.close());
const progress = document.createElement('p');
const output = document.createElement('pre');
let snapshot = null;
const apply = document.createElement('button');
apply.textContent = '검증된 쪽수로 새 파일 생성';
apply.disabled = true;
const resultLink = document.createElement('a');
resultLink.textContent = '';
resultLink.target = '_blank';
resultLink.rel = 'noopener';
output.id = 'report-qa-result';
output.style.cssText = 'white-space:pre-wrap;font:13px/1.6 sans-serif';
panel.append(close, apply, resultLink, progress, output);
document.body.append(panel);
button.addEventListener('click', async () => {
  button.disabled = true;
  panel.showModal();
  output.textContent = '';
  apply.disabled = true;
  snapshot = null;
  try {
    const total = await request('pageCount');
    if (!Number.isInteger(total) || total < 1 || total > 200) throw new Error('페이지 수 확인 필요');
    const pages = [];
    for (let page = 0; page < total; page++) {
      progress.textContent = `rHWP 실제 조판 검사 ${page+1}/${total}쪽 — 원본 파일은 수정하지 않습니다.`;
      const raw = await request('getPageSvg', {page});
      const svg = typeof raw === 'string' ? raw : raw?.svg;
      if (!svg) throw new Error(`${page+1}쪽 SVG가 비었습니다.`);
      const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
      const nodes = [...doc.querySelectorAll('text')];
      const lines = [];
      let previousY = null;
      for (const node of nodes) {
        const y = node.getAttribute('y');
        if (y !== previousY || !lines.length) lines.push('');
        lines[lines.length-1] += node.textContent;
        previousY = y;
      }
      pages.push({page_number: page+1, text: lines.join('\n')});
    }
    const source = new URL(new URLSearchParams(location.search).get('url') || '', location.origin);
    const exportMatch = source.pathname.match(/^\/api\/v2\/report\/exports\/([0-9a-f-]{36})\/download$/);
    snapshot = {renderer:'rhwp',page_count:total,page_texts:pages};
    if (source.origin === location.origin && exportMatch) {
      const response = await fetch(source, {credentials:'same-origin'});
      if (!response.ok) throw new Error('검사 원본 파일 읽기 실패');
      const digest = await crypto.subtle.digest('SHA-256', await response.arrayBuffer());
      snapshot.source_sha256 = [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
      snapshot.source_export_id = exportMatch[1];
      apply.disabled = false;
    }
    output.textContent = JSON.stringify(snapshot, null, 2);
    progress.textContent = `rHWP ${total}쪽 텍스트 수집 완료. 쪽수 대조용이며 시각적 잘림은 화면에서 별도 확인해야 합니다.`;
  } catch (error) { progress.textContent = `검사 실패: ${error.message}`; }
  finally { button.disabled = false; }
});
apply.addEventListener('click', async () => {
  if (!snapshot?.source_export_id) return;
  apply.disabled = true;
  try {
    const response = await fetch(`/api/v2/report/exports/${snapshot.source_export_id}/verify-rhwp-toc`, {
      method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify(snapshot),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '쪽수 반영 실패');
    resultLink.href = `/assets/rhwp/?url=${encodeURIComponent(result.download_url)}&filename=${encodeURIComponent(result.file_name)}`;
    resultLink.textContent = ' 보정본 미리보기 열기';
    progress.textContent = '원본을 보존하고 실제 rHWP 쪽수를 적용한 새 파일을 생성했습니다. 보정본 화면도 확인해 주세요.';
  } catch (error) { progress.textContent = error.message; apply.disabled = false; }
});
