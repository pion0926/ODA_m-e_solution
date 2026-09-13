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
          await refresh();
          if (account) { dialog.close(); notify('비밀번호를 변경하고 기존 세션을 종료했습니다.'); }
          else {
            dialog.innerHTML = `<h2 id="serviceAccountTitle">계정 발급 완료</h2><p>프로젝트: <b>${esc(saved.project.name)}</b></p><p>아이디: <b id="issuedUsername">${esc(saved.username)}</b></p><p>초기 비밀번호: <code id="issuedPassword" style="user-select:all;overflow-wrap:anywhere">${esc(saved.initial_password)}</code></p><p>이 화면을 닫으면 비밀번호를 다시 조회할 수 없습니다. 이 계정으로 로그인하면 연결된 프로젝트의 빈 화면에서 시작합니다.</p><button class="btn primary" type="button" id="issuedAccountDone">확인 · 사용자 관리로 이동</button>`;
            dialog.querySelector('#issuedAccountDone').onclick = () => { dialog.close(); location.hash = '#/admin/users'; };
          }
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
      let completed = 0;
      try {
        if (action === 'status') await request(`/api/v2/admin/accounts/${encodeURIComponent(account.id)}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_active: !account.is_active }), timeoutMs: 15000 });
        for (const item of changes) {
          await request(`/api/v2/admin/projects/${encodeURIComponent(item.id)}/members/${encodeURIComponent(account.id)}`, { method: item.add ? 'PUT' : 'DELETE', timeoutMs: 15000 });
          completed++;
        }
        await refresh();
        notify(action === 'status' ? '계정 상태를 변경했습니다.' : '프로젝트 배정을 저장했습니다.');
      } catch (error) {
        await refresh();
        const current = document.getElementById('adminServiceState');
        if (current) current.textContent = `${completed ? `${completed}건 적용 후 ` : ''}요청을 완료하지 못했습니다. 현재 목록을 확인해 주세요. ${error.message}`;
      } finally { busy = false; }
    }
    return { detail, openAccountForm, act };
  }
  root.ServiceAdminUI = { create };
})(window);
