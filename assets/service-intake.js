(function (root) {
  'use strict';
  async function uploadBatch(request, files, progress = () => {}) {
    const result = { accepted: 0, duplicates: 0, failed: [] };
    const selected = Array.from(files);
    for (let index = 0; index < selected.length; index++) {
      const file = selected[index];
      progress(index + 1, selected.length, file.name);
      const form = new FormData(); form.append('files', file, file.name);
      try {
        const response = await request('/api/v2/intake/uploads', { method: 'POST', body: form });
        for (const item of response.accepted || []) item.deduplicated ? result.duplicates++ : result.accepted++;
        for (const item of response.rejected || []) result.failed.push({ file, error: item.error });
      } catch (error) {
        result.failed.push({ file, error: error.message });
        if (error.status === 401 || error.status === 403 || error.code === 'workspace_changed') {
          for (const remaining of selected.slice(index + 1)) result.failed.push({ file: remaining, error: '작업 공간 또는 권한 확인이 필요하여 접수하지 않았습니다.' });
          break;
        }
      }
    }
    return result;
  }
  async function listAll(request) {
    const items = new Map();
    let before = null;
    const cursors = new Set();
    do {
      const page = await request(`/api/v2/intake/jobs?limit=200${before == null ? '' : `&before=${encodeURIComponent(before)}`}`);
      for (const item of page.items || []) items.set(item.id, item);
      before = page.next_before;
      if (before != null && cursors.has(before)) throw new Error('문서 목록 페이지를 확인하지 못했습니다. 다시 불러와 주세요.');
      cursors.add(before);
    } while (before != null);
    return { items: [...items.values()] };
  }
  root.ServiceIntake = { uploadBatch, listAll };
})(window);
