(function (root) {
  'use strict';
  const dollars = value => value == null ? '확인 불가' : '$' + Number(value).toLocaleString('en-US', {maximumFractionDigits: 4});
  function create({request, escapeHtml: esc, refresh, notify}) {
    function card(project) {
      return `<div class="project-ai-summary"><span>프로젝트 AI</span><code>${esc(project.llm_model || '미배정')}</code><button class="btn sm" data-project-ai="${esc(project.id)}">AI 모델 배정 · 가격 비교</button></div>`;
    }
    async function open(project) {
      if (!project) return;
      document.getElementById('projectAIDialog')?.remove();
      const dialog = document.createElement('dialog');
      dialog.id = 'projectAIDialog'; dialog.className = 'project-ai-dialog';
      dialog.setAttribute('aria-labelledby', 'projectAITitle');
      dialog.innerHTML = `<header><div><h2 id="projectAITitle">프로젝트 AI 모델 배정</h2><p>${esc(project.name)}</p></div><button class="btn" data-ai-close aria-label="AI 모델 배정 닫기">닫기</button></header>
        <p class="project-ai-notice">문서 분석 · PDM · DAC 평가 · AI 섹션 생성/수정 · 보고서 및 발표자료 생성에 공통 적용됩니다. HWPX 고정 양식은 변경하지 않습니다.</p>
        <p>현재 배정: <strong>${esc(project.llm_model || '미배정')}</strong></p>
        <div class="project-ai-toolbar"><div class="project-ai-filters" role="group" aria-label="공급사 필터"><button class="btn sm" data-provider="">전체</button><button class="btn sm" data-provider="Google">Gemini</button><button class="btn sm" data-provider="OpenAI">GPT</button><button class="btn sm" data-provider="Anthropic">Claude</button></div><button class="btn sm" data-ai-refresh>가격·제공 상태 새로고침</button></div>
        <p data-ai-date></p><div class="project-ai-table-wrap"><table class="project-ai-table"><thead><tr><th>선택 · 모델</th><th>입력 / 100만 토큰</th><th>출력 / 100만 토큰</th><th>예시 비용</th></tr></thead><tbody data-ai-models><tr><td colspan="4">모델과 가격을 확인하는 중…</td></tr></tbody></table></div>
        <div class="project-ai-estimate"><label>예시 입력 토큰 <input type="number" min="0" max="10000000" value="10000" data-ai-input></label><label>예시 출력 토큰 <input type="number" min="0" max="1000000" value="2000" data-ai-output></label><span>한 번의 요청 예시 · 보고서 전체 견적 아님</span></div>
        <p data-ai-billing></p><p data-ai-sources></p>
        <footer><div><p>변경 후 시작하는 작업부터 적용합니다. 진행 중인 작업과 기존 결과는 그대로 유지됩니다. 새 모델로 분석·보고서를 다시 만들려면 재평가·재생성을 실행하세요.</p><p data-ai-state role="status" aria-live="polite"></p></div><button class="btn primary" data-ai-save disabled>프로젝트에 모델 배정</button></footer>`;
      document.body.appendChild(dialog);
      let catalog = null, selected = project.llm_model, provider = '', saving = false, loading = false;
      const q = selector => dialog.querySelector(selector);
      const state = message => { q('[data-ai-state]').textContent = message; };
      function render() {
        if (!catalog) return;
        const input = Math.max(0, Math.min(10000000, Number(q('[data-ai-input]').value) || 0));
        const output = Math.max(0, Math.min(1000000, Number(q('[data-ai-output]').value) || 0));
        q('[data-ai-models]').innerHTML = catalog.models.filter(m => !provider || m.provider === provider).map(m => {
          const unavailable = !catalog.can_assign || !m.available;
          const override = (m.pricing_overrides || []).filter(p => input >= Number(p.min_prompt_tokens)).sort((a,b) => b.min_prompt_tokens-a.min_prompt_tokens)[0];
          const inRate = override ? Number(override.prompt)*1e6 : m.input, outRate = override ? Number(override.completion)*1e6 : m.output;
          const estimate = inRate == null || outRate == null ? null : (input*inRate+output*outRate)/1e6;
          return `<tr class="${selected === m.id ? 'selected' : ''}"><td><label><input type="radio" name="projectAIModel" value="${esc(m.id)}" ${selected === m.id ? 'checked' : ''} ${unavailable || saving ? 'disabled' : ''}><span><b>${esc(m.name)}</b><small>${esc(m.description)}${unavailable ? ' · 제공 상태 미확인/미제공' : ''}</small><code>${esc(m.id)}</code></span></label></td><td>${dollars(m.input)}</td><td>${dollars(m.output)}</td><td>${dollars(estimate)}${override ? '<small>긴 문맥 단가 적용</small>' : ''}</td></tr>`;
        }).join('');
        q('[data-ai-save]').disabled = saving || loading || !catalog.can_assign || selected === project.llm_model || !catalog.models.some(m => m.id === selected && m.available);
        dialog.querySelectorAll('[data-provider]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.provider === provider)));
      }
      async function load(force) {
        if (loading || saving) return;
        loading = true; q('[data-ai-refresh]').disabled = true; q('[data-ai-save]').disabled = true;
        state('가격과 제공 상태를 확인하고 있습니다.');
        try {
          catalog = await request('/api/v2/admin/ai-models' + (force ? '?refresh=true' : ''), {timeoutMs:15000});
          if (!dialog.isConnected) return;
          q('[data-ai-date]').textContent = `가격 확인: ${new Date(catalog.checked_at).toLocaleString('ko-KR')} · USD · ${catalog.price_status === 'live' ? 'API 목록 확인됨' : '최근 조회 실패 — 이전 참고 가격, 새 배정 불가'}`;
          q('[data-ai-billing]').textContent = catalog.billing_note;
          q('[data-ai-sources]').innerHTML = `<a href="${esc(catalog.source)}" target="_blank" rel="noopener">실제 연결 단가: OpenRouter</a> · 공급사 공식 가격: ` + Object.entries(catalog.official_sources).map(([name,url]) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(name)}</a>`).join(' · ');
          state(catalog.can_assign ? '모델을 선택하면 배정 버튼이 활성화됩니다.' : '제공 상태 확인 후 다시 배정해 주세요. 기존 배정은 변경하지 않았습니다.');
        } catch (error) { state(error.message); }
        finally { loading = false; if(dialog.isConnected) { q('[data-ai-refresh]').disabled = false; render(); } }
      }
      dialog.addEventListener('click', event => {
        if (event.target.closest('[data-ai-close]') && !saving) dialog.close();
        const filter = event.target.closest('[data-provider]');
        if (filter && !saving) { provider = filter.dataset.provider; render(); }
        if (event.target.closest('[data-ai-refresh]')) load(true);
      });
      dialog.addEventListener('change', event => {
        if (event.target.name === 'projectAIModel') { selected = event.target.value; render(); }
      });
      dialog.querySelectorAll('[data-ai-input],[data-ai-output]').forEach(input => input.addEventListener('input', render));
      q('[data-ai-save]').onclick = async () => {
        if (saving || loading || q('[data-ai-save]').disabled) return;
        saving = true; render(); state('프로젝트 설정을 저장하는 중…');
        try {
          const saved = await request(`/api/v2/admin/projects/${encodeURIComponent(project.id)}/ai-model`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({llm_model:selected, expected_revision:project.ai_revision}), timeoutMs:15000});
          Object.assign(project, saved); await refresh(); dialog.close(); notify(saved.message);
        } catch (error) {
          state(error.status === 409 ? '다른 관리자가 변경했습니다. 창을 닫고 프로젝트 목록을 새로고침한 뒤 다시 선택하세요.' : error.message);
        } finally { saving = false; if(dialog.isConnected) render(); }
      };
      dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
      dialog.addEventListener('close', () => dialog.remove(), {once:true});
      dialog.showModal(); await load(false);
    }
    return {card, open};
  }
  root.ProjectAIUI = {create};
})(window);
