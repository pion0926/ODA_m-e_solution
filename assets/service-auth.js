/* Resolve the server session before exposing either the app or login form. */
(function(root) {
  'use strict';
  function create({request, ready, state}) {
    let pending = null;
    function start() {
      if (pending) return pending;
      state('checking');
      pending = (async () => {
        let session;
        try {
          session = await request('/api/v2/auth/me', {timeoutMs:15000});
        } catch (error) {
          if (error.status === 401) state('login');
          else state('error', '서버에 접속 상태를 확인하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.');
          return;
        }
        if (!session?.account?.id) {
          state('error', '접속 확인 응답을 읽지 못했습니다. 다시 시도해 주세요.');
          return;
        }
        if (!session.has_project && !session.account.is_admin) {
          state('unassigned', '로그인되어 있지만 배정된 프로젝트가 없습니다. 관리자에게 프로젝트 배정을 요청해 주세요.');
          return;
        }
        try { await ready(session); }
        catch (_) { state('error', '로그인은 확인됐지만 화면을 열지 못했습니다. 다시 시도해 주세요.'); }
      })().finally(() => { pending = null; });
      return pending;
    }
    return {start};
  }
  root.ServiceAuth = {create};
  if (typeof module !== 'undefined') module.exports = {create};
})(typeof window === 'undefined' ? globalThis : window);
