const assert=require('node:assert/strict');
const {create}=require('../../assets/service-pdm-refresh.js');
(async()=>{
  const saved={id:'job1',status:'completed',active:false,result:{message:'저장 완료'}};
  const updates=[],calls=[];let views=0,fail=true;
  const client=create({request:async(p)=>{calls.push(p);return saved;},update:j=>updates.push(j),button:()=>{},notify:()=>{},
    refreshViews:async()=>{views++;if(fail)throw Error('display failed');}});
  await client.sync();
  assert.equal(updates.at(-1).failed,false);assert.match(updates.at(-1).detail,/저장 완료.*조회 지연/);
  fail=false;await client.sync();await client.sync();assert.equal(views,2);
  assert(calls.every(p=>p.endsWith('/status')));
  const queued={id:'job2',status:'running',active:true};let posts=0;
  const recovered=[];
  const lost=create({request:async(p)=>{if(!p.endsWith('/status')){posts++;throw Error('lost response');}return queued;},
    update:j=>recovered.push(j),button:()=>{},notify:()=>{},refreshViews:async()=>{}});
  await lost.start();assert.equal(posts,1);assert.equal(recovered.at(-1).active,true);
  const partial=[];
  const c=create({request:async()=>({...saved,status:'partial'}),update:j=>partial.push(j),button:()=>{},notify:()=>{},refreshViews:async()=>{}});
  await c.sync();assert.equal(partial[0].warning,true);assert.equal(partial[0].failed,false);
  console.log('PASS PDM saved/view-failure recovery, receipt reload, lost POST response, partial status');
})().catch(e=>{console.error(e);process.exit(1);});
