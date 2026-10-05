/* Operator-only account issuance and membership controls. API remains authoritative. */
(function (root) {
  'use strict';
  function create({ request, escapeHtml: esc, refresh, accounts, projects, selected, notify }) {
    let busy = false;
    const assigned = (account) => account.projects || (account.project ? [account.project] : []);
    function confirmAction(message) {
      if (document.getElementById('serviceConfirmDialog')) return Promise.resolve(false);
      return new Promise(resolve => {
        const dialog = document.createElement('dialog');
        dialog.id = 'serviceConfirmDialog'; dialog.className = 'service-account-dialog';
        dialog.setAttribute('aria-labelledby', 'serviceConfirmTitle');
        dialog.innerHTML = `<h2 id="serviceConfirmTitle">계정 설정 변경 확인</h2><p style="margin:14px 0">${esc(message)}</p><div class="report-ai-actions"><button class="btn" data-confirm-cancel>취소</button><button class="btn primary" data-confirm-ok>확인</button></div>`;
        let accepted = false;
        dialog.querySelector('[data-confirm-cancel]').onclick = () => dialog.close();
        dialog.querySelector('[data-confirm-ok]').onclick = () => { accepted = true; dialog.close(); };
        dialog.addEventListener('close', () => { dialog.remove(); resolve(accepted); }, {once:true});
        document.body.appendChild(dialog); dialog.showModal();
      });
    }
    function detail(account) {
      if (account.is_admin) return '';
      const ids = new Set(assigned(account).map((project) => project.id));
      return `<section class="admin-service-controls"><h3>서비스 계정 관리</h3><p>상태: <b>${account.is_active ? '활성' : '중지'}</b> · 비밀번호 변경 또는 계정 중지 시 기존 세션을 종료합니다.</p><div class="report-ai-actions"><button class="btn sm" data-account-action="password">비밀번호 재설정</button><button class="btn sm" data-account-action="status">${account.is_active ? '계정 이용 중지' : '계정 활성화'}</button></div><h3 style="margin-top:16px">참여 프로젝트</h3><div class="project-account-grid">${projects().map((project) => `<label><input type="checkbox" data-member-project="${esc(project.id)}" ${ids.has(project.id) ? 'checked' : ''}><span>${esc(project.name)}</span></label>`).join('') || '프로젝트를 먼저 만들어 주세요.'}</div><p>계정의 문서·평가·보고서는 선택한 프로젝트 안에서 분리됩니다. 배정 해제는 계정 접근만 차단하며 사업 자료를 삭제하지 않습니다.</p><button class="btn sm" data-account-action="members">프로젝트 배정 저장</button><div role="status" class="project-form-state" id="adminServiceState"></div></section>`;
    }
    function openAccountForm(account = null, projectId = '') {
      if (busy) return;
      const available = projects().filter(project => project.status !== 'archived');
      if (!account && !available.length) { notify('프로젝트를 먼저 생성해 주세요.'); return; }
      document.getElementById('serviceAccountDialog')?.remove();
      const dialog = document.createElement('dialog');
      dialog.id = 'serviceAccountDialog';
      dialog.className = 'service-account-dialog';
      dialog.setAttribute('aria-labelledby', 'serviceAccountTitle');
      const fields = account
        ? '<label><span>새 비밀번호 · 10자 이상</span><input name="password" type="password" minlength="10" maxlength="256" autocomplete="new-password" required></label><label><span>비밀번호 확인</span><input name="confirm_password" type="password" minlength="10" maxlength="256" autocomplete="new-password" required></label>'
        : `<label><span>연결할 프로젝트</span><select name="project_id" required><option value="">프로젝트 선택</option>${available.map(project => `<option value="${esc(project.id)}" ${project.id === projectId ? 'selected' : ''}>${esc(project.name)}</option>`).join('')}</select></label><label><span>로그인 아이디</span><input name="username" type="text" minlength="3" maxlength="64" autocomplete="off" required></label><label><span>사용자·기관명</span><input name="display_name" type="text" minlength="2" maxlength="80" required></label><p>초기 비밀번호는 안전한 난수로 자동 발급됩니다. 자료 등록·PDM·DAC 평가·보고서 생성 권한을 기본 허용하며, 발급 후 사용자 관리에서 개별 조정할 수 있습니다.</p>`;
      dialog.innerHTML = `<form class="project-form" id="serviceAccountForm"><h2 id="serviceAccountTitle">${account ? `${esc(account.username)} 비밀번호 재설정` : '프로젝트 연결 계정 발급'}</h2><p>${account ? '새 비밀번호를 발급하고 기존 로그인 세션을 종료합니다.' : '선택한 프로젝트와 계정을 동시에 연결합니다. 다른 프로젝트의 자료는 복사하지 않습니다.'}</p>${fields}<p>${account ? '변경한 비밀번호는 다시 표시하지 않습니다.' : '발급된 비밀번호는 완료 화면에서 한 번만 표시됩니다. 닫기 전에 안전한 경로로 사용자에게 전달해 주세요.'}</p><div role="status" class="project-form-state" id="serviceAccountState"></div><div class="report-ai-actions"><button class="btn" type="button" data-account-cancel>취소</button><button class="btn primary" type="submit">${account ? '비밀번호 변경' : '계정 발급 및 연결'}</button></div></form>`;
      document.body.appendChild(dialog);
      dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
      dialog.querySelector('[data-account-cancel]').onclick = () => { if (!busy) dialog.close(); };
      dialog.addEventListener('close', () => dialog.remove());
      dialog.querySelector('form').addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy) return;
        const form = event.target;
        const data = new FormData(form);
        const state = dialog.querySelector('#serviceAccountState');
        if (account && data.get('password') !== data.get('confirm_password')) { state.textContent = '비밀번호 확인이 일치하지 않습니다.'; return; }
        if (!account && !/^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$/.test(String(data.get('username') || '').trim())) {
          state.textContent = '아이디는 영문·숫자로 시작하는 3~64자로 입력해 주세요. 영문, 숫자, 점(.), 밑줄(_), 하이픈(-)만 사용할 수 있습니다.';
          return;
        }
        if (!account && String(data.get('display_name') || '').trim().length < 2) {
          state.textContent = '사용자·기관명을 2자 이상 입력해 주세요.';
          return;
        }
        busy = true;
        form.querySelectorAll('button').forEach((button) => { button.disabled = true; });
        state.textContent = '처리 중…';
        try {
          const payload = account ? { password: data.get('password') } : { username: String(data.get('username')).trim(), display_name: String(data.get('display_name')).trim(), project_id: data.get('project_id') };
          const saved = await request(account ? `/api/v2/admin/accounts/${encodeURIComponent(account.id)}/password` : '/api/v2/admin/accounts', { method: account ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), timeoutMs: 15000 });
          form.reset();
          if (!account) selected(saved.id);
          if (account) { dialog.close(); notify('비밀번호를 변경하고 기존 세션을 종료했습니다.'); }
          else {
            dialog.innerHTML = `<h2 id="serviceAccountTitle">계정 발급 완료</h2><p>프로젝트: <b>${esc(saved.project.name)}</b></p><p>아이디: <b id="issuedUsername">${esc(saved.username)}</b></p><p>초기 비밀번호: <code id="issuedPassword" style="user-select:all;overflow-wrap:anywhere">${esc(saved.initial_password)}</code></p><p>이 화면을 닫으면 비밀번호를 다시 조회할 수 없습니다. 이 계정으로 로그인하면 연결된 프로젝트의 빈 화면에서 시작합니다.</p><button class="btn primary" type="button" id="issuedAccountDone">확인 · 사용자 관리로 이동</button>`;
            dialog.querySelector('#issuedAccountDone').onclick = () => { dialog.close(); location.hash = '#/admin/users'; };
          }
          // Show one-time credentials before any fallible list refresh.
          try { await refresh(); } catch (_) { notify('계정 처리는 완료됐습니다. 목록은 새로고침해 주세요.'); }
        } catch (error) { state.textContent = error.status ? error.message : `접수 여부를 확인하지 못했습니다. 창을 닫고 계정 목록을 새로고침하여 결과를 확인한 뒤 다시 시도하세요. ${error.message}`; }
        finally { busy = false; form.querySelectorAll('button').forEach((button) => { button.disabled = false; }); }
      });
      dialog.showModal();
    }
    async function act(action) {
      const account = accounts().find((item) => item.id === selected());
      if (!account || account.is_admin || busy) return;
      if (action === 'password') { openAccountForm(account); return; }
      if (action === 'status' && !await confirmAction(`${account.username} 계정을 ${account.is_active ? '중지하고 로그인 세션을 종료' : '다시 활성화'}할까요? 사업 자료는 삭제하지 않습니다.`)) return;
      const target = document.getElementById('adminServiceState');
      const changes = [];
      if (action === 'members') {
        const oldIds = new Set(assigned(account).map((project) => project.id));
        document.querySelectorAll('[data-member-project]').forEach((input) => {
          if (oldIds.has(input.dataset.memberProject) !== input.checked) changes.push({ id: input.dataset.memberProject, add: input.checked });
        });
        if (!changes.length) { target.textContent = '변경된 배정이 없습니다.'; return; }
        if (changes.some((item) => !item.add) && !await confirmAction('해제할 프로젝트의 계정 접근을 차단합니다. 해당 사업 자료는 보존됩니다. 배정을 변경할까요?')) return;
      }
      busy = true;
      target.textContent = '저장 중…';
      try {
        if (action === 'status') await request(`/api/v2/admin/accounts/${encodeURIComponent(account.id)}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_active: !account.is_active }), timeoutMs: 15000 });
        if (action === 'members') {
          const projectIds = new Set(assigned(account).map(project => project.id));
          changes.forEach(item => item.add ? projectIds.add(item.id) : projectIds.delete(item.id));
          await request(`/api/v2/admin/accounts/${encodeURIComponent(account.id)}/projects`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, timeoutMs: 15000,
            body: JSON.stringify({ project_ids: [...projectIds], expected_project_ids: assigned(account).map(project => project.id) })
          });
        }
        await refresh();
        notify(action === 'status' ? '계정 상태를 변경했습니다.' : '프로젝트 배정을 저장했습니다.');
      } catch (error) {
        await refresh();
        const current = document.getElementById('adminServiceState');
        if (current) current.textContent = `${error.status && error.status < 500 ? '변경은 적용되지 않았습니다.' : '접수 여부를 확인하지 못했습니다. 현재 목록을 확인해 주세요.'} ${error.message}`;
      } finally { busy = false; }
    }
    async function deleteProject(projectId) {
      if (busy || document.getElementById('projectDeleteDialog')) return;
      busy = true;
      try {
        const preview = await request(`/api/v2/admin/projects/${encodeURIComponent(projectId)}/deletion-preview`);
        const dialog = document.createElement('dialog');
        dialog.id = 'projectDeleteDialog'; dialog.className = 'service-account-dialog';
        dialog.setAttribute('aria-labelledby', 'projectDeleteTitle');
        dialog.innerHTML = `<form><h2 id="projectDeleteTitle">프로젝트 및 관련 계정 삭제</h2><p><b>${esc(preview.name)}</b>의 원본·추출 파일, 분석·평가 데이터, 보고서·발표자료와 연결된 계정을 영구 삭제합니다. 복구할 수 없습니다.</p><p>문서 ${preview.counts.intake_documents}개 · 평가 ${preview.counts.evaluation_runs}건 · 보고서 섹션 ${preview.counts.report_sections}개 · 내보내기 ${preview.counts.report_exports + preview.counts.presentation_exports}건</p><h3>함께 삭제할 계정 (${preview.accounts.length}개)</h3><ul style="max-height:200px;overflow:auto">${preview.accounts.map(a => `<li><b>${esc(a.username)}</b> · ${esc(a.display_name)}${a.other_projects.length ? `<br><strong style="color:var(--bad-t)">다른 프로젝트 접근도 삭제: ${a.other_projects.map(esc).join(', ')}</strong>` : ''}</li>`).join('') || '<li>연결 계정 없음</li>'}</ul><p>시스템 관리자 계정은 보존됩니다. 다른 프로젝트의 자료는 보존되며 필요한 경우 관리 소유권이 현재 관리자에게 이전됩니다.</p><label>확인을 위해 프로젝트명을 정확히 입력하세요.<input name="projectName" autocomplete="off" required style="width:100%;margin:8px 0"></label><div role="status" data-delete-state></div><div class="report-ai-actions"><button type="button" class="btn" data-delete-cancel>취소</button><button type="submit" class="btn" style="color:var(--bad-t)" data-delete-submit disabled>삭제 대상 확인</button></div></form>`;
        let executing = false, reviewed = false;
        const input = dialog.querySelector('input');
        const submit = dialog.querySelector('[data-delete-submit]');
        const status = dialog.querySelector('[data-delete-state]');
        input.oninput = () => { reviewed = false; submit.textContent = '삭제 대상 확인'; submit.disabled = input.value !== preview.name; status.textContent = ''; };
        dialog.querySelector('[data-delete-cancel]').onclick = () => { if (!executing) dialog.close(); };
        dialog.addEventListener('cancel', event => { if (executing) event.preventDefault(); });
        dialog.addEventListener('close', () => { dialog.remove(); busy = false; }, {once:true});
        dialog.querySelector('form').onsubmit = async event => {
          event.preventDefault();
          if (executing || input.value !== preview.name) return;
          if (!reviewed) {
            reviewed = true;
            status.textContent = `정말 삭제하시겠습니까? ${preview.name}의 모든 자료와 계정 ${preview.accounts.length}개가 영구 삭제됩니다. 아래 최종 삭제 버튼을 눌러야 실행됩니다.`;
            submit.textContent = '최종 확인 · 영구 삭제';
            return;
          }
          executing = true; submit.disabled = true; input.disabled = true;
          dialog.querySelector('[data-delete-cancel]').disabled = true;
          status.textContent = '프로젝트 데이터와 파일을 삭제하고 있습니다…';
          try {
            const result = await request(`/api/v2/admin/projects/${encodeURIComponent(projectId)}`, {method:'DELETE', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:input.value, revision:preview.revision, confirmed:true})});
            dialog.close(); await refresh();
            notify(result.cleanup_pending ? '프로젝트와 계정을 삭제했습니다. 남은 파일은 백그라운드에서 삭제 재시도 중입니다.' : '프로젝트, 관련 계정 및 파일을 모두 삭제했습니다.');
          } catch (error) {
            status.textContent = `${error.message} 목록을 새로 확인한 뒤 다시 시도해 주세요.`;
            reviewed = false; submit.textContent = '삭제 대상 확인'; submit.disabled = false; input.disabled = false;
            dialog.querySelector('[data-delete-cancel]').disabled = false;
          } finally { executing = false; }
        };
        document.body.appendChild(dialog); dialog.showModal(); input.focus();
      } catch (error) { busy = false; notify(error.message); }
    }
    return { detail, openAccountForm, act, deleteProject };
  }
  root.ServiceAdminUI = { create };
})(window);
