const test = require('node:test');
const assert = require('node:assert/strict');
const {create} = require('../../assets/service-auth.js');
const user = {account:{id:'a'},has_project:true,project:{id:'p'}};

test('pending session hides login, deduplicates checks and restores the app',async()=>{
  let resolve, calls=0, opened=null; const states=[];
  const auth=create({request:(path,options)=>{calls++;assert.equal(path,'/api/v2/auth/me');assert.equal(options.timeoutMs,15000);return new Promise(r=>resolve=r);},
    ready:session=>{opened=session;},state:s=>states.push(s)});
  const pending=auth.start(); assert.equal(auth.start(),pending);
  assert.deepEqual(states,['checking']);assert.equal(calls,1);assert.equal(opened,null);
  resolve(user);await pending;assert.equal(opened,user);assert.deepEqual(states,['checking']);
});

test('only an unauthenticated server response opens login',async()=>{
  for(const status of [401,403,500,502,undefined]){
    const states=[];
    await create({request:async()=>{throw Object.assign(new Error('failure'),{status});},
      ready:()=>assert.fail('must not expose app'),state:s=>states.push(s)}).start();
    assert.deepEqual(states,['checking',status===401?'login':'error']);
  }
});

test('network failure can be retried without credentials',async()=>{
  let calls=0,opened=0; const states=[];
  const auth=create({request:async()=>{if(!calls++)throw new Error('offline');return user;},
    ready:()=>opened++,state:s=>states.push(s)});
  await auth.start();await auth.start();
  assert.deepEqual(states,['checking','error','checking']);assert.equal(opened,1);
});

test('missing project and malformed sessions do not pretend the user is logged out',async()=>{
  for(const [session,expected] of [[null,'error'],[{},'error'],[{account:{id:'a'},has_project:false},'unassigned']]){
    const states=[];
    await create({request:async()=>session,ready:()=>assert.fail('must not expose app'),state:s=>states.push(s)}).start();
    assert.equal(states.at(-1),expected);
  }
});

test('administrator without a project enters normally and rendering failures offer retry',async()=>{
  let opened=0;const states=[];
  await create({request:async()=>({account:{id:'admin',is_admin:true},has_project:false}),ready:()=>opened++,state:s=>states.push(s)}).start();
  assert.equal(opened,1);assert.deepEqual(states,['checking']);
  await create({request:async()=>user,ready:()=>{throw new Error('render failure');},state:s=>states.push(s)}).start();
  assert.equal(states.at(-1),'error');assert.ok(!states.includes('login'));
});
