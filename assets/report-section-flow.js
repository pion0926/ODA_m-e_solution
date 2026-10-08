/* State boundaries for section editing. No document text is persisted outside this page. */
(function (root) {
  'use strict';
  function generationBlock({ allowed = true, loading = false, batchActive = false, status = '', lifecycle = null } = {}) {
    if (!allowed) return { reason: '관리자가 설정한 보고서 접근 권한을 확인해 주세요.' };
    if (loading) return { reason: '선택 섹션을 불러오고 있습니다. 잠시 기다려 주세요.' };
    if (batchActive) return { reason: '전체 보고서 작성이 진행 중입니다. 완료 후 섹션별 수정 요청을 보낼 수 있습니다.' };
    if (status === 'submitting') return { reason: '현재 본문과 요청을 서버에 전송하고 있습니다. 중복 요청은 보내지 않습니다.' };
    if (status === 'generating') return { reason: '현재 섹션을 AI가 작성하고 있습니다. 완료 시 한글 미리보기가 갱신됩니다.' };
    if (status === 'uncertain') return { reason: '접수 여부를 확인하지 못했습니다. 중복 생성을 방지하기 위해 먼저 진행 상태를 다시 확인해 주세요.' };
    if (lifecycle?.can_generate_report === false || ['empty_project', 'processing_documents', 'evaluation_required', 'evaluation_active'].includes(lifecycle?.phase)) {
      const action = lifecycle.phase === 'evaluation_required' ? { href: '#/eval/board', label: 'DAC 재평가로 이동' }
        : ['empty_project', 'processing_documents', 'documents_need_attention'].includes(lifecycle.phase) ? { href: '#/evidence', label: '자료 처리 상태 확인' } : null;
      return { reason: lifecycle.message || '자료·평가 처리가 완료된 뒤 수정할 수 있습니다.', action };
    }
    return null;
  }
  function createFlow(clock = () => performance.now()) {
    const records = new Map();
    const drafts = new Map();
    const reads = new Map();
    let active = null;
    function record(id) {
      if (!records.has(id)) records.set(id, { status: 'empty', startedAt: null });
      return records.get(id);
    }
    return {
      select(id) { active = id; },
      beginRead(id) { const token = (reads.get(id) || 0) + 1; reads.set(id, token); return token; },
      isCurrent(id, token) { return active === id && reads.get(id) === token; },
      state(id) { return { ...record(id) }; },
      busy(id) { return ['submitting', 'generating', 'uncertain'].includes(record(id).status); },
      begin(id) {
        if (this.busy(id)) return false;
        reads.set(id, (reads.get(id) || 0) + 1);
        Object.assign(record(id), { status: 'submitting', startedAt: clock(), acceptedMs: null, elapsedMs: null, error: '' });
        return true;
      },
      accepted(id) {
        const value = record(id);
        value.status = 'generating';
        value.acceptedMs = clock() - value.startedAt;
      },
      rejected(id, error, uncertain = false) {
        Object.assign(record(id), { status: uncertain ? 'uncertain' : 'failed', error: String(error || '') });
      },
      observe(section) {
        const value = record(section.part_id);
        // A GET that started before a POST was accepted is not proof that the POST finished.
        if (value.status === 'submitting') return;
        if (value.startedAt !== null && value.status === 'generating' && section.status !== 'generating') {
          value.elapsedMs = clock() - value.startedAt;
          if (section.status !== 'failed') drafts.delete(section.part_id);
        }
        Object.assign(value, { status: section.status, error: section.error_message || '' });
      },
      edit(id, content) { if (id) drafts.set(id, content); },
      hasDraft(id) { return drafts.has(id); },
      discard(id) { drafts.delete(id); },
      content(id, saved) { return drafts.has(id) ? drafts.get(id) : (saved || ''); },
      saved(id, submitted) { if (drafts.get(id) === submitted) drafts.delete(id); },
      diagnostics() {
        return [...records].map(([partId, value]) => ({ partId, status: value.status,
          acceptedMs: value.acceptedMs ?? null, elapsedMs: value.elapsedMs ?? null }));
      }
    };
  }
  root.ReportSectionFlow = { createFlow, generationBlock };
  if (typeof module !== 'undefined' && module.exports) module.exports = { createFlow, generationBlock };
})(typeof window !== 'undefined' ? window : globalThis);
