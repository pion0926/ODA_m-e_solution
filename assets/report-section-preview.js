/* Selected-section proof controller: transient HWPX, latest-input-wins, no autosave. */
(function (root) {
  'use strict';
  function createRevisionGate() {
    let version = 0, current = null;
    return {
      update(partId, content) {
        if (current?.partId === partId && current?.content === content) return null;
        current = { partId, content, version: ++version };
        return { ...current };
      },
      current() { return current && { ...current }; },
      accepts(item) { return Boolean(current && item && current.version === item.version); },
      invalidate() { current = null; version++; }
    };
  }

  function create({ request }) {
    const byId = id => document.getElementById(id);
    const gate = createRevisionGate();
    const frame = byId('reportSectionFrame');
    const status = byId('reportPreviewStatus');
    const pending = new Map();
    let sequence = 0, timer, running = null, loadedVersion = null;
    const origin = location.origin;
    function rpc(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = `section-proof-${++sequence}`;
        const timeout = setTimeout(() => { pending.delete(id); reject(new Error('rHWP 응답이 지연되었습니다. 다시 미리보기를 눌러 주세요.')); }, 45000);
        pending.set(id, { resolve, reject, timeout });
        frame.contentWindow.postMessage({ type: 'rhwp-request', id, method, params }, origin);
      });
    }
    window.addEventListener('message', event => {
      if (event.origin !== origin || event.source !== frame.contentWindow) return;
      if (event.data?.type === 'section-preview-zoom-state') {
        if (/^\d{1,3}%$/.test(event.data.zoom)) byId('reportPreviewZoom').textContent = event.data.zoom;
        return;
      }
      if (event.data?.type !== 'rhwp-response') return;
      const item = pending.get(event.data.id);
      if (!item) return;
      clearTimeout(item.timeout); pending.delete(event.data.id);
      event.data.error ? item.reject(new Error(event.data.error)) : item.resolve(event.data.result);
    });
    let frameReady;
    function initFrame() {
      frameReady = new Promise(resolve => frame.addEventListener('load', resolve, { once: true }));
      frame.src = '/assets/rhwp/?sectionPreview=1';
    }
    async function waitForFrame() {
      let timeout;
      try {
        await Promise.race([frameReady, new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new Error('rHWP 화면을 불러오지 못했습니다. 미리보기 새로고침을 눌러 주세요.')), 45000);
        })]);
      } finally { clearTimeout(timeout); }
    }
    initFrame();
    function stale(message) {
      status.dataset.state = 'pending';
      frame.style.visibility = 'hidden';
      byId('reportPreviewEmpty').hidden = false;
      byId('reportPreviewEmpty').textContent = message;
      status.textContent = message;
      byId('reportPreviewPages').textContent = '';
      byId('reportPreviewZoom').textContent = '—';
    }
    function cancel() {
      if (!running) return;
      running.abort(); running = null;
      for (const item of pending.values()) { clearTimeout(item.timeout); item.reject(new Error('미리보기 요청 변경')); }
      pending.clear();
      // A previous renderer load must not overwrite a newer selection.
      initFrame();
    }
    async function render() {
      clearTimeout(timer);
      cancel();
      const item = gate.current();
      if (!item || loadedVersion === item.version) return;
      if (!String(item.content || '').trim()) {
        stale('아직 작성된 내용이 없습니다. AI 섹션 생성 후 미리보기를 확인하세요.');
        status.dataset.state = 'empty';
        return;
      }
      const attempt = new AbortController();
      running = attempt;
      const deadline = setTimeout(() => attempt.abort(), 90000);
      byId('reportPreviewRefresh').disabled = false;
      byId('reportPreviewRefresh').textContent = '다시 불러오기';
      stale('선택 섹션을 한글 양식으로 조판 중…');
      const started = performance.now();
      try {
        const result = await request(`/api/v2/report/sections/${encodeURIComponent(item.partId)}/preview`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: item.content }), signal: attempt.signal
        });
        if ((!gate.accepts(item) || attempt.signal.aborted) || result.part_id !== item.partId) return;
        await waitForFrame();
        await rpc('ready');
        if ((!gate.accepts(item) || attempt.signal.aborted)) return;
        const bytes = Uint8Array.from(atob(result.hwpx_base64), value => value.charCodeAt(0));
        const focused = document.activeElement;
        const caret = focused?.tagName === 'TEXTAREA' ? [focused.selectionStart, focused.selectionEnd] : null;
        const loaded = await rpc('loadFile', { data: Array.from(bytes), fileName: result.file_name, skipUnsavedGuard: true });
        // rHWP focuses its own input on document load. Keep users typing in
        // the source/AI panel; rendering must not steal their caret or scroll.
        if (caret && document.activeElement === frame && focused.isConnected) {
          focused.focus({ preventScroll: true });
          focused.setSelectionRange(...caret);
        }
        if ((!gate.accepts(item) || attempt.signal.aborted)) return;
        frame.contentWindow.postMessage({ type: 'section-preview-fit' }, origin);
        loadedVersion = item.version;
        frame.style.visibility = 'visible';
        byId('reportPreviewEmpty').hidden = true;
        byId('reportPreviewPages').textContent = `${loaded.pageCount}쪽 · 섹션 미리보기`;
        byId('reportPreviewNote').textContent = result.note;
        status.textContent = `저장된 섹션 반영 완료 · ${((performance.now() - started) / 1000).toFixed(1)}초`;
        status.dataset.state = 'ready';
      } catch (error) {
        if (gate.accepts(item) && running === attempt) {
          stale(`미리보기를 만들지 못했습니다. 편집 내용은 유지됩니다. ${error.message}`);
          status.dataset.state = 'failed';
        }
      } finally {
        clearTimeout(deadline);
        if (running === attempt) { running = null; byId('reportPreviewRefresh').textContent = '새로고침'; }
      }
    }
    byId('reportPreviewRefresh').addEventListener('click', () => {
      if (status.dataset.state === 'failed') initFrame();
      loadedVersion = null; render();
    });
    byId('reportPreviewExpand').addEventListener('click', () => {
      const expanded = byId('reportWorkbench').classList.toggle('preview-expanded');
      byId('reportPreviewExpand').textContent = expanded ? 'AI 수정 요청 같이 보기' : '미리보기 크게';
      byId('reportPreviewExpand').setAttribute('aria-expanded', String(expanded));
      frame.contentWindow.postMessage({ type: 'section-preview-fit' }, origin);
    });
    for (const [id, action] of Object.entries({ reportZoomIn: 'in', reportZoomOut: 'out', reportZoomActual: '100', reportZoomFit: 'fit' })) {
      byId(id).addEventListener('click', () => {
        frame.contentWindow.postMessage({ type: 'section-preview-zoom', action }, origin);
      });
    }
    // Resize the renderer itself, not a CSS-scaled bitmap. Refit after the
    // pane's actual width changes (window size, TOC collapse, expanded proof).
    let lastWidth = 0, fitFrame;
    new ResizeObserver(entries => {
      const width = Math.round(entries[0].contentRect.width);
      if (!width || width === lastWidth) return;
      lastWidth = width;
      cancelAnimationFrame(fitFrame);
      fitFrame = requestAnimationFrame(() => frame.contentWindow.postMessage({ type: 'section-preview-fit' }, origin));
    }).observe(frame);
    return {
      select(partId, content, title) {
        byId('reportPreviewTitle').textContent = title || '선택 섹션 한글 미리보기';
        if (!gate.update(partId, content)) return;
        cancel();
        stale('선택 섹션의 미리보기 갱신 대기…');
        clearTimeout(timer); timer = setTimeout(render, 700);
      },
      clear() { gate.invalidate(); cancel(); clearTimeout(timer); stale('섹션을 선택하세요.'); },
      fit() { frame.contentWindow.postMessage({ type: 'section-preview-fit' }, origin); },
      refresh() { loadedVersion = null; return render(); }
    };
  }
  root.ReportSectionPreview = { create, createRevisionGate };
  if (typeof module !== 'undefined' && module.exports) module.exports = { createRevisionGate };
})(typeof window !== 'undefined' ? window : globalThis);
