// Render the pinned rHWP SVG in a worker. Text remains native/selectable;
// no editor/caret/shape mutation code is loaded into a saved report preview.
const root = document.getElementById('studio-root');
root.replaceChildren();
document.getElementById('report-qa-panel')?.remove();
const css = document.createElement('link'); css.rel='stylesheet'; css.href='/assets/rhwp/report-reader.css'; document.head.append(css);
root.innerHTML = `<div id="reader-toolbar" aria-label="미리보기 도구"><label>쪽 <input id="reader-page" type="number" min="1" value="1" aria-label="이동할 쪽"></label><span id="reader-total"></span><button id="reader-go">이동</button><button id="reader-fit">쪽 맞춤</button><button id="reader-width">폭 맞춤</button><button id="reader-out" aria-label="축소">−</button><output id="reader-zoom"></output><button id="reader-in" aria-label="확대">+</button><span id="reader-status" role="status">원본 파일을 불러오는 중…</span><button id="reader-retry" hidden>다시 시도</button></div><main id="reader-pages" aria-label="보고서 페이지"></main>`;
const byId = id => document.getElementById(id);
const pages = byId('reader-pages'), status = byId('reader-status');
let worker, counter=0, pending=new Map(), holders=[], observer, busy=false, wanted=new Set(), scale=1, mode='page', generation=0;
let pageWidth=794, pageHeight=1123, rendered=new Set();
function fail(message) {status.textContent=message;byId('reader-retry').hidden=false;}
function rpc(type, fields={}, transfer=[]) {
  return new Promise((resolve,reject)=>{
    const id=++counter;
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('미리보기 응답이 지연되었습니다. 다시 시도해 주세요.'));},90000);
    pending.set(id,{resolve,reject,timer}); worker.postMessage({id,type,...fields},transfer);
  });
}
function safeSvg(raw, page) {
  const doc = new DOMParser().parseFromString(raw,'image/svg+xml');
  if(doc.querySelector('parsererror') || doc.documentElement.localName!=='svg') throw Error('페이지 표시 데이터를 읽지 못했습니다.');
  for(const node of doc.querySelectorAll('script,foreignObject,iframe,object,embed,style')) node.remove();
  for(const node of doc.querySelectorAll('a')) node.replaceWith(...node.childNodes);
  for(const node of doc.querySelectorAll('*')) for(const attr of [...node.attributes]) {
    const name=attr.localName.toLowerCase(), value=attr.value.trim();
    if(name.startsWith('on') || (name==='href' && !value.startsWith('#') && !/^data:image\/(png|jpeg|webp|gif);base64,/i.test(value)) || (name==='style' && /url\s*\(|expression\s*\(|@import/i.test(value))) node.removeAttributeNode(attr);
  }
  // Each rHWP page reuses clip-path IDs. Inline pages share one DOM, so every
  // definition/reference must be scoped or earlier pages clip later-page text.
  const ids=new Map();
  for(const node of doc.querySelectorAll('[id]')){const id=node.id;ids.set(id,`reader-${page}-${id}`);node.id=ids.get(id);}
  for(const node of doc.querySelectorAll('*'))for(const attr of [...node.attributes]){
    let value=attr.value.replace(/url\(#([^)]*)\)/g,(match,id)=>ids.has(id)?`url(#${ids.get(id)})`:match);
    if(attr.localName==='href'&&value.startsWith('#')&&ids.has(value.slice(1)))value='#'+ids.get(value.slice(1));
    attr.value=value;
  }
  return document.importNode(doc.documentElement,true);
}
function fit() {
  if(mode==='page') scale=Math.min(1,(pages.clientWidth-32)/pageWidth,(pages.clientHeight-32)/pageHeight);
  if(mode==='width') scale=Math.min(2,(pages.clientWidth-32)/pageWidth);
  scale=Math.max(.15,Math.min(3,scale));
  pages.style.setProperty('--page-width',`${pageWidth*scale}px`);
  pages.style.setProperty('--page-height',`${pageHeight*scale}px`);
  byId('reader-zoom').textContent=`${Math.round(scale*100)}%`;
}
async function showPage(index, epoch=generation) {
  const raw=await rpc('page',{page:index});
  if(epoch!==generation)return;
  const svg=safeSvg(raw,index);
  if(index===0){
    const box=svg.getAttribute('viewBox')?.split(/[ ,]+/).map(Number);
    const width=box?.[2] || parseFloat(svg.getAttribute('width'));
    const height=box?.[3] || parseFloat(svg.getAttribute('height'));
    if(width>0 && height>0){pageWidth=width;pageHeight=height;fit();}
  }
  holders[index].replaceChildren(svg); rendered.add(index);
  holders[index].setAttribute('aria-busy','false');
}
async function drain() {
  if(busy)return;
  busy=true; const epoch=generation;
  try {
    while(wanted.size && epoch===generation){
      const index=wanted.values().next().value;wanted.delete(index);
      if(!rendered.has(index))await showPage(index,epoch);
    }
  } catch(error){if(epoch===generation)fail(error.message);}
  finally{if(epoch===generation)busy=false;}
}
async function start() {
  const epoch=++generation;
  observer?.disconnect();worker?.terminate();
  for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error('미리보기 다시 시작'));}pending.clear();
  busy=false;wanted.clear();rendered.clear();holders=[];pages.replaceChildren();
  byId('reader-retry').hidden=true;status.textContent='원본 파일을 불러오는 중…';
  try {
    worker=new Worker(new URL('./report-reader-worker.js',import.meta.url),{type:'module'});
    worker.onmessage=({data})=>{const p=pending.get(data.id);if(!p)return;clearTimeout(p.timer);pending.delete(data.id);data.error?p.reject(Error(data.error)):p.resolve(data.result);};
    worker.onerror=()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error('문서 렌더러를 실행하지 못했습니다.'));}pending.clear();fail('문서 렌더러를 실행하지 못했습니다. 다시 시도해 주세요.');};
    const url=new URLSearchParams(location.search).get('url');
    if(!/^\/api\/v2\/report\/exports\/[a-f0-9-]+\/download$/.test(url || ''))throw Error('유효하지 않은 보고서 주소');
    const response=await fetch(url,{credentials:'same-origin',signal:AbortSignal.timeout(60000)});
    if(!response.ok)throw Error(response.status===401?'로그인을 확인한 뒤 다시 시도해 주세요.':`파일 읽기 실패 (${response.status})`);
    const bytes=await response.arrayBuffer();
    if(epoch!==generation)return;
    status.textContent='문서 쪽을 구성하는 중…';
    const total=await rpc('open',{bytes},[bytes]);
    if(epoch!==generation)return;
    if(!Number.isInteger(total)||total<1)throw Error('표시할 페이지가 없습니다.');
    byId('reader-total').textContent=`/ ${total}`;byId('reader-page').max=String(total);
    for(let index=0;index<total;index++){
      const holder=document.createElement('section');holder.className='reader-page';holder.dataset.page=String(index);
      holder.setAttribute('aria-label',`${index+1}쪽`);holder.setAttribute('aria-busy','true');holder.textContent=`${index+1}쪽`;
      holders.push(holder);pages.append(holder);
    }
    mode='page';fit();await showPage(0,epoch);
    if(epoch!==generation)return;
    status.textContent='글자를 드래그하여 선택·복사할 수 있습니다.';
    observer=new IntersectionObserver(entries=>{
      for(const entry of entries){const index=Number(entry.target.dataset.page);if(entry.isIntersecting)wanted.add(index);else wanted.delete(index);}
      void drain();
    },{root:pages,rootMargin:'200px'});
    holders.forEach(holder=>observer.observe(holder));
  }catch(error){if(epoch===generation)fail(error.message);}
}
byId('reader-go').onclick=()=>{const index=Number(byId('reader-page').value)-1;if(Number.isInteger(index)&&holders[index])holders[index].scrollIntoView({block:'start'});};
byId('reader-page').onkeydown=event=>{if(event.key==='Enter')byId('reader-go').click();};
byId('reader-fit').onclick=()=>{mode='page';fit();};byId('reader-width').onclick=()=>{mode='width';fit();};
byId('reader-in').onclick=()=>{mode='manual';scale+=.1;fit();};byId('reader-out').onclick=()=>{mode='manual';scale-=.1;fit();};
byId('reader-retry').onclick=start;
new ResizeObserver(fit).observe(pages);
window.addEventListener('pagehide',()=>worker?.terminate(),{once:true});
await start();
