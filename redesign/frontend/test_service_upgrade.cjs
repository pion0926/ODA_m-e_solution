const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { window: {}, Headers, FormData };
vm.createContext(context);
for (const file of ['service-scope.js', 'service-intake.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../../assets', file), 'utf8'), context);
async function run() {
  let blocks = 0;
  const scope = context.window.ServiceScope.create(() => blocks++);
  scope.bind({ account: { id: 'a' }, project: { id: 'p1' } });
  assert.equal(scope.headers('/api/v2/report/generate-all').get('X-ODAME-Project'), 'p1');
  assert.equal(scope.headers('/api/v2/auth/me').get('X-ODAME-Project'), null);
  assert.throws(() => scope.check('/api/v2/auth/me', { ok: true }, { account: { id: 'a' }, project: { id: 'p2' } }), /다른 탭/);
  assert.throws(() => scope.headers('/api/v2/report/generate-all'), /다른 탭/);
  assert.throws(() => scope.check('/api/v2/dashboard', { ok: true }, {}), /다른 탭/);
  assert.equal(blocks, 1, 'concurrent requests show one blocking dialog');
  scope.bind({ account: { id: 'a' }, project: { id: 'p1' } });
  assert.throws(() => scope.check('/api/v2/intake/uploads', { status: 401 }, {}), /로그인/);
  scope.bind({ account: { id: 'a' }, project: { id: 'p1' } });
  assert.throws(() => scope.check('/api/v2/admin/accounts', { status: 409 }, { code: 'workspace_changed', detail: 'changed' }), /changed/);
  const files = ['good.txt', 'bad.exe', 'duplicate.txt', 'later.txt'].map(name => new File(['text'], name));
  let calls = 0;
  const outcome = await context.window.ServiceIntake.uploadBatch(async () => {
    calls++;
    if (calls === 2) throw new Error('형식 오류');
    return { accepted: [{ deduplicated: calls === 3 }] };
  }, files);
  assert.equal(calls, 4, 'one failed file does not skip later files');
  assert.equal(outcome.accepted, 2); assert.equal(outcome.duplicates, 1);
  assert.equal(outcome.failed[0].file.name, 'bad.exe');
  calls = 0;
  const halted = await context.window.ServiceIntake.uploadBatch(async () => { calls++; throw Object.assign(new Error('changed'), {code:'workspace_changed'}); }, files);
  assert.equal(calls, 1); assert.equal(halted.failed.length, 4, 'scope change halts all remaining uploads');
  const requests = [];
  const listed = await context.window.ServiceIntake.listAll(async url => {
    requests.push(url);
    return requests.length === 1 ? { items: [{id:'2'},{id:'1'}], next_before: 1 } : { items: [{id:'0'}], next_before: null };
  });
  assert.equal(listed.items.length, 3); assert.ok(requests[1].endsWith('&before=1'));
  console.log('PASS workspace identity, expired session, late response rejection, mixed upload, scope interruption and pagination');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
