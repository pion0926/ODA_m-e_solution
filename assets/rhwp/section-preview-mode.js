// An embedded section proof must not offer unsynchronised document edits.
// All content edits go through report_sections.content and the same adapters.
if (new URLSearchParams(location.search).get('sectionPreview') === '1') {
  document.documentElement.classList.add('section-proof');
  const style = document.createElement('style');
  style.textContent = '#menu-bar,#icon-toolbar,#style-bar{display:none!important}#studio-root{height:100vh!important}#scroll-container{top:0!important}.ruler{display:none!important}';
  document.head.append(style);
  const block = event => { event.preventDefault(); event.stopImmediatePropagation(); };
  for (const type of ['beforeinput', 'paste', 'cut', 'drop', 'compositionstart']) document.addEventListener(type, block, true);
  document.addEventListener('keydown', event => {
    if (!['PageDown','PageUp','Home','End','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Tab','Escape'].includes(event.key)) block(event);
  }, true);
  // Prevent caret placement, drag handles and table/shape modifications.
  document.addEventListener('pointerdown', event => { if (event.target.closest('#scroll-content,canvas,svg')) block(event); }, true);
  document.addEventListener('mousedown', event => { if (event.target.closest('#scroll-content,canvas,svg')) block(event); }, true);
  const publishZoom = () => {
    const zoom = document.getElementById('sb-zoom-val')?.textContent?.trim();
    if (/^\d{1,3}%$/.test(zoom)) parent.postMessage({ type: 'section-preview-zoom-state', zoom }, location.origin);
  };
  const zoomValue = document.getElementById('sb-zoom-val');
  if (zoomValue) new MutationObserver(publishZoom).observe(zoomValue, { childList: true, characterData: true, subtree: true });
  window.addEventListener('message', event => {
    if (event.source !== parent || event.origin !== location.origin) return;
    if (event.data?.type === 'section-preview-fit') {
      document.getElementById('sb-zoom-fit-width')?.click();
      document.getElementById('scroll-container')?.scrollTo({ top: 0, left: 0 });
    } else if (event.data?.type === 'section-preview-zoom') {
      const controls = { in: '#sb-zoom-in', out: '#sb-zoom-out', '100': '[data-cmd="view:zoom-100"]', fit: '#sb-zoom-fit-width' };
      const selector = controls[event.data.action];
      if (!selector) return;
      document.querySelector(selector)?.click();
    } else return;
    publishZoom();
  });
}
