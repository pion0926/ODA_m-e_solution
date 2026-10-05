// Full saved reports need a reader, not the editor and its persisted settings.
if (window.kodameReadOnlyReport) {
  await import('./report-reader.js');
} else {
  const module = document.querySelector('script[data-studio-module]')?.dataset.studioModule;
  if (!module?.startsWith('/assets/rhwp/assets/')) throw Error('Missing pinned Studio module');
  await import(module);
}
