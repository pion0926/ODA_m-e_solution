/* Bind each page to the account/project that supplied its data. */
(function (root) {
  'use strict';
  function create(onBlocked) {
    let identity = null;
    let blocked = null;
    const isAuth = path => path.split('?')[0].startsWith('/api/v2/auth/');
    const error = () => Object.assign(new Error(blocked.message), { status: blocked.status, code: blocked.code });
    function block(message, status, code) {
      if (!blocked) { blocked = { message, status, code }; onBlocked(blocked); }
      throw error();
    }
    return {
      bind(data) { identity = { account: data.account.id, project: data.project?.id || '' }; blocked = null; },
      headers(path, values) {
        if (blocked) throw error();
        const headers = new Headers(values || {});
        if (identity && !isAuth(path)) {
          headers.set('X-ODAME-Account', identity.account);
          headers.set('X-ODAME-Project', identity.project);
        }
        return headers;
      },
      check(path, response, body) {
        if (!identity) return;
        if (blocked) throw error(); // Discard responses already in flight when scope changed.
        if (response.status === 401) block('로그인이 만료되었거나 계정 이용이 중지되었습니다. 다시 로그인해 주세요.', 401, 'session_expired');
        if (body?.code === 'workspace_changed') block(body.detail, 409, body.code);
        if (path === '/api/v2/auth/me' && response.ok &&
            (body.account?.id !== identity.account || (body.project?.id || '') !== identity.project)) {
          block('다른 탭에서 계정·프로젝트가 변경되었거나 프로젝트 배정이 바뀌었습니다. 현재 화면의 요청을 중지했습니다.', 409, 'workspace_changed');
        }
      }
    };
  }
  root.ServiceScope = { create };
})(window);
