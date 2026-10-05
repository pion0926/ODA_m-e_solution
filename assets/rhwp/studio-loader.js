// Full saved reports need a reader, not the editor and its persisted settings.
if (window.kodameReadOnlyReport) {
  await import('./report-reader.js');
} else {
  // Dynamic imports can finish after iframe load. Preserve the parent's initial
  // handshake until the Studio has installed its RPC listener.
  const waiting = new Map();
  function holdReady(event) {
    if (event.origin !== location.origin || event.source !== parent ||
        event.data?.type !== 'rhwp-request' || event.data.method !== 'ready') return;
    event.stopImmediatePropagation();
    if (waiting.size < 32) waiting.set(event.data.id, event);
  }
  window.addEventListener('message', holdReady, true);
  const module = document.querySelector('script[data-studio-module]')?.dataset.studioModule;
  try {
    if (!module?.startsWith('/assets/rhwp/assets/')) throw Error('Missing pinned Studio module');
    await import(module);
    window.removeEventListener('message', holdReady, true);
    for (const event of waiting.values()) {
      window.dispatchEvent(new MessageEvent('message', {
        data: event.data, origin: event.origin, source: event.source,
      }));
    }
  } catch (error) {
    window.removeEventListener('message', holdReady, true);
    for (const event of waiting.values()) event.source.postMessage({
      type: 'rhwp-response', id: event.data.id, error: '한글 편집기를 불러오지 못했습니다. 다시 불러와 주세요.',
    }, event.origin);
    throw error;
  } finally { waiting.clear(); }
}
