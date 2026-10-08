// K-ODAME compatibility methods retained from the previous bundled viewer.
// This source is inserted before installEmbedRuntime by build_rhwp.py.
window.addEventListener('message', async (event: MessageEvent) => {
  const message = event.data;
  const methods = ['searchAllText', 'replaceAll', 'replaceText', 'insertText', 'getFieldList', 'setFieldValueByName', 'setFieldValue', 'scrollToPage'];
  if (event.origin !== location.origin || event.source !== window.parent || message?.type !== 'rhwp-request' || !methods.includes(message.method)) return;
  event.stopImmediatePropagation();
  const params = message.params ?? {};
  const response: Record<string, unknown> = { type: 'rhwp-response', id: message.id };
  try {
    await initPromise;
    let result: unknown;
    const mutation = !['searchAllText', 'getFieldList', 'scrollToPage'].includes(message.method);
    if (mutation && new URLSearchParams(location.search).get('sectionPreview') === '1') throw new Error('Section preview is read-only');
    switch (message.method) {
      case 'searchAllText': result = wasm.searchAllText(params.query ?? params.text ?? '', !!params.caseSensitive, !!params.includeCells); break;
      case 'replaceAll': result = wasm.replaceAll(params.query ?? '', params.newText ?? params.value ?? '', !!params.caseSensitive); break;
      case 'replaceText': result = wasm.replaceText(params.sec ?? params.sectionIndex ?? 0, params.para ?? params.paragraphIndex ?? 0, params.charOffset ?? 0, params.length ?? 0, params.newText ?? params.text ?? ''); break;
      case 'insertText': result = wasm.insertText(params.sec ?? params.sectionIndex ?? 0, params.para ?? params.paragraphIndex ?? 0, params.charOffset ?? 0, params.text ?? ''); break;
      case 'getFieldList': result = wasm.getFieldList(); break;
      case 'setFieldValueByName': result = wasm.setFieldValueByName(params.name ?? '', params.value ?? ''); break;
      case 'setFieldValue': result = wasm.setFieldValue(params.fieldId ?? 0, params.value ?? ''); break;
      case 'scrollToPage': {
        const container = document.getElementById('scroll-container');
        const content = document.getElementById('scroll-content');
        const total = Math.max(1, wasm.pageCount);
        container?.scrollTo({ top: Math.max(0, Math.min(total - 1, Number(params.pageIndex) || 0)) * (content?.scrollHeight ?? 0) / total });
        result = !!container; break;
      }
    }
    if (mutation) {
      canvasView?.loadDocument();
      documentState.markDirty('kodame-api-' + message.method);
      eventBus.emit('document-changed', 'kodame-api-' + message.method);
    }
    response.result = result;
  } catch (error) { response.error = error instanceof Error ? error.message : String(error); }
  (event.source as WindowProxy).postMessage(response, event.origin);
}, true);
