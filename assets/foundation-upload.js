(function (root) {
  'use strict';
  const labels = { project_plan: '사업계획서', pdm: 'PDM' };
  const stages = { queued: '분석 대기', retry: '분석 재시도 중', processing: '분석 중', waiting_llm: 'AI 연결 대기', failed: '분석 실패', cancelled: '사용자 중지', completed: '분석 완료' };
  function create({ request, escapeHtml: esc, refresh, notify }) {
    let state = { ready: false, documents: {} }, busy = false;
    const byId = id => document.getElementById(id);
    function render(value) {
      state = value || { ready: false, documents: {} };
      const panel = byId('foundationDocuments');
      panel.innerHTML = Object.entries(labels).map(([role, label]) => {
        const doc = state.documents[role];
        const pending = doc && ['queued', 'retry', 'processing', 'waiting_llm'].includes(doc.status);
        return `<article class="foundation-card"><h3>${label}</h3><p>${doc ? esc(doc.original_name) : '등록된 문서가 없습니다.'}</p>
          <p role="status">${doc ? esc(stages[doc.status] || doc.status) + (pending ? ` · ${Number(doc.progress) || 0}%` : '') : '업로드 필요'}</p>
          ${doc?.error_message ? `<p class="foundation-error">${esc(doc.error_message)}</p>` : ''}
          <button type="button" class="btn" data-foundation-role="${role}" ${busy || pending ? 'disabled' : ''}>${doc ? '문서 교체' : label + ' 업로드'}</button>
          ${doc && ['failed', 'waiting_llm', 'cancelled'].includes(doc.status) ? `<button type="button" class="btn" data-foundation-retry="${esc(doc.id)}" ${busy ? 'disabled' : ''}>분석 재시도</button>` : ''}
        </article>`;
      }).join('');
      byId('foundationGate').textContent = state.ready ? '기준 문서 분석이 완료되었습니다. 일반 자료를 업로드할 수 있습니다.' : '사업계획서와 PDM을 각각 등록하고 두 문서의 분석이 완료되면 일반 자료를 업로드할 수 있습니다.';
      ['uploadBtn', 'bulkFileInput'].forEach(id => { if (byId(id)) byId(id).disabled = !state.ready || busy; });
      ['dropzone', 'spDrop'].forEach(id => {
        byId(id)?.setAttribute('aria-disabled', String(!state.ready || busy));
      });
    }
    function canUpload() {
      if (state.ready && !busy) return true;
      notify('사업계획서와 PDM의 분석 완료 후 일반 자료를 업로드해 주세요.');
      return false;
    }
    async function upload(role, file) {
      if (!file || busy) return;
      busy = true;
      try {
        const current = await request('/api/v2/intake/foundation');
        const previous = current.documents[role];
        let impact=null, reason='';
        if (previous) {
          impact=await request(`/api/v2/intake/foundation/${role}/impact`);
          reason=root.prompt(`교체 영향: 지표 ${impact.indicators.length}개 · 문서 매핑 ${impact.mappings.length}개 · 작성 섹션 ${impact.report_sections.length}개\n${impact.policy}\n\n교체 사유를 기록해 주세요.`, '')?.trim();
          if (!reason) return;
        }
        if (previous && !root.confirm(`${labels[role]}를 교체하면 전체 사업 구성이 새 문서를 기준으로 변경됩니다. 사업 개요·PDM·성과지표가 갱신되며, 기존 DAC 평가와 보고서는 재평가·재생성이 필요합니다.\n\n현재: ${previous.original_name}\n교체: ${file.name}\n\n교체하시겠습니까?`)) return;
        render(current);
        const form = new FormData(); form.append('files', file, file.name);
        const query = new URLSearchParams({ role });
        if (previous) query.set('replaces', previous.id);
        if (impact) {query.set('impact_revision',impact.revision);query.set('change_reason',reason);}
        const result = await request(`/api/v2/intake/uploads?${query}`, { method: 'POST', body: form });
        if (result.rejected?.length) throw new Error(result.rejected[0].error);
        notify(result.accepted?.[0]?.deduplicated ? '이미 등록된 동일 파일입니다.' : `${labels[role]} 접수 완료. 분석 성공 후 사업 기준에 반영됩니다.`);
      } catch (error) { notify(error.message); }
      finally { busy = false; byId('foundationFileInput').value = ''; await refresh(); }
    }
    function bind() {
      byId('foundationDocuments').addEventListener('click', async event => {
        const button = event.target.closest('[data-foundation-role]');
        if (button && !busy) {
          const input = byId('foundationFileInput'); input.dataset.role = button.dataset.foundationRole; input.click();
        }
        const retry = event.target.closest('[data-foundation-retry]');
        if (retry && !busy) {
          busy = true; render(state);
          try { await request(`/api/v2/intake/jobs/${encodeURIComponent(retry.dataset.foundationRetry)}/retry`, { method: 'POST' }); }
          catch (error) { notify(error.message); }
          finally { busy = false; await refresh(); }
        }
      });
      byId('foundationFileInput').addEventListener('change', event => upload(event.target.dataset.role, event.target.files[0]));
      render(state);
    }
    return { render, bind, canUpload };
  }
  root.FoundationUpload = { create };
})(window);
