'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];

/* ============ 아이콘 ============ */
const IC={
 dash:'<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
 lib:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
 pdm:'<path d="M12 3v4M12 11v4M12 19v2M6 7h12M6 15h12"/><circle cx="12" cy="9" r="2"/><circle cx="12" cy="17" r="2"/><circle cx="12" cy="3" r="1.5"/>',
 slots:'<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><path d="m14.5 17 2 2 4-4.5"/>',
 ovv:'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5Z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
 ind:'<path d="M3 20h18"/><path d="M6 16v-5M11 16V8M16 16v-3M21 16V5"/>',
 gap:'<path d="M12 8v5M12 16.5v.5"/><path d="M10.3 3.8 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0Z"/>',
 board:'<circle cx="12" cy="12" r="9"/><path d="M12 12 12 6M12 12l4.2 2.5"/>',
 results:'<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4-4"/><path d="M8.5 11h5M11 8.5v5"/>',
 report:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/><path d="M9 14.5 11 16.5 15 12"/>',
 lock:'<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>'};
const svg=(n,s)=>`<svg width="${s||16}" height="${s||16}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${IC[n]}</svg>`;

/* ============ i18n (사업 제공 언어: 프로젝트 설정) ============ */
let LANG='ko';
let PROJ_LANGS=['ko'];
let PROJECT_TRANSLATIONS={};
let PROJECT_LANGUAGE_META={ko:{name:'한국어',native_name:'한국어'}};
const LANG_NAMES={ko:'한국어',en:'English',vi:'Tiếng Việt',ru:'Русский',uz:'O‘zbekcha'};
const LX={ko:0,en:1,vi:2};
const I18N={
 logout:['권한 변경','Switch role','Đổi vai trò'],tray:['AI 작업','AI jobs','Tác vụ AI'],upload:['증빙 업로드','Upload evidence','Tải minh chứng'],
 'd-fix':['성과 리스크 예측 및 개선권고','Performance risk & recommendations','Rủi ro và khuyến nghị'],
 'd-fix-s':['PDM · DAC 두 관점을 종합해 현재 처리할 우선순위로 정렬합니다','Combined PDM · DAC view, sorted by what to do first','Tổng hợp hai góc nhìn PDM · DAC theo thứ tự nên xử lý'],
 'd-ind':['핵심 성과지표 달성 현황','Key indicator status','Tiến độ chỉ số chính'],
 'd-dac':['종료평가 준비도','Evaluation readiness','Mức sẵn sàng đánh giá'],
 'd-assign':['AI 자동 배정','AI automatic assignment','AI tự động phân bổ'],
 'd-assign-s':['AI가 문서를 PDM·DAC 슬롯에 자동으로 배정합니다.','AI automatically assigns documents to PDM and DAC slots.','AI tự động phân bổ tài liệu vào ô PDM và DAC.'],
 'more-ind':['성과지표 모니터링 ›','Indicators ›','Giám sát chỉ số ›'],'more-dac':['DAC 평가진단 ›','DAC assessment ›','Chẩn đoán DAC ›'],
 't-ev':['자료 업로드','Evidence upload','Tải minh chứng'],
 's-ev':['문서의 역할과 사실을 정리하고 PDM · DAC · 보고서에 연결합니다.','Identify the document’s role and facts, then link it to PDM, DAC and report sections.','Xác định vai trò và dữ kiện của tài liệu, rồi liên kết với PDM, DAC và các phần báo cáo.'],
 't-evpdm':['PDM 증빙','PDM evidence','Minh chứng PDM'],
 's-evpdm':['검증수단 기준으로 파일 등록 여부를 확인하는 화면입니다 · 미확보 항목이 항상 위에 표시됩니다.','Check every means of verification for registered files · missing first.','Kiểm tra hồ sơ theo phương tiện xác minh · thiếu xếp trước.'],
 't-evdac':['DAC 증빙','DAC evidence','Minh chứng DAC'],
 's-evdac':['적절성 · 일관성 등 5대 평가기준별 증빙 확보 현황입니다 · 미확보는 분석 감점 요인과 직접 연결됩니다.','Coverage by the 5 DAC criteria · gaps map to scoring penalties.','Hiện trạng theo 5 tiêu chí DAC · thiếu hồ sơ dẫn đến trừ điểm.'],
 't-projov':['사업 개요','Project overview','Tổng quan dự án'],
 's-projov':['사업 일반 정보와 PDM 전체를 한눈에 · 이 논리구조가 성과지표와 평가 판단의 기준이 됩니다.','Project basics and the full PDM at a glance.','Thông tin dự án và toàn bộ PDM trong một màn hình.'],
 't-ind':['성과지표 모니터링','Indicator monitoring','Giám sát chỉ số'],
 's-ind':['성과지표 분석에서 분석 개요와 지표별 문서 매핑을 확인·보완한 뒤 분석 실행을 누르면 목표·실적·달성도와 리스크를 분석합니다.','When indicators are refreshed, AI analyzes targets, actuals, achievement, and evidence to generate detailed risks and recommendations.','Khi cập nhật chỉ số, AI phân tích mục tiêu, thực hiện, mức đạt và minh chứng để tạo rủi ro và khuyến nghị chi tiết.'],
 't-evcov':['증빙 충족도','Evidence coverage','Mức đáp ứng minh chứng'],
 's-evcov':['PDM 검증수단과 DAC 평가기준의 증빙 확보 수준을 함께 확인하고 보완 우선순위를 판단합니다.','Review PDM and DAC evidence coverage together.','Theo dõi mức đáp ứng minh chứng PDM và DAC.'],
 't-gaps':['성과 리스크 예측 및 개선권고','Performance risk & recommendations','Rủi ro và khuyến nghị'],
 's-gaps':['AI가 목표·실적·달성도·산출근거를 종합해 위험, 원인, 전망, 개선권고, 추가 필요 근거를 구체적으로 제시합니다.','AI combines targets, actuals, achievement, and evidence to provide concrete risks, causes, outlooks, recommendations, and evidence needs.','AI tổng hợp mục tiêu, thực hiện, mức đạt và minh chứng để nêu cụ thể rủi ro, nguyên nhân, triển vọng, khuyến nghị và nhu cầu minh chứng.'],
 't-evalov':['종료평가 준비도','Evaluation readiness','Mức sẵn sàng đánh giá'],
 's-evalov':['평가보고서 양식에 기반한 이번 평가의 목적 · 기준 · 일정 안내입니다.','Purpose, criteria and schedule per the report template.','Mục đích, tiêu chí và lịch trình theo mẫu báo cáo.'],
 't-board':['DAC 평가진단','DAC assessment','Chẩn đoán DAC'],
 's-board':['DAC 근거 분석·평가 버튼을 누르면 문서 원문 근거를 분석하고 평가점수를 산정합니다. 성과지표 분석은 별도로 실행합니다.','Summary scores and per-criterion status · re-evaluate to refresh.','Tóm tắt điểm và hiện trạng theo tiêu chí · chạy đánh giá lại để cập nhật.'],
 't-results':['분석 결과','Analysis results','Kết quả phân tích'],
 's-results':['기준별 세부 평가질문의 점수(1~4점)와 판단 근거, 참고 문서입니다 · 근거 칩을 누르면 원본이 열립니다.','Question-level scores (1~4), judgments and references.','Điểm từng câu hỏi (1~4), căn cứ và tài liệu tham chiếu.'],
 'dz-big':['파일을 끌어다 놓거나 클릭해서 업로드합니다','Drop files here, or click to browse','Kéo thả tệp vào đây hoặc bấm để chọn']};
function applyLang(){
 document.documentElement.lang=LANG;
 window.KODAME_LOCALE=LANG;
 $$('[data-i]').forEach(el=>{const d=I18N[el.dataset.i];const fallback=d?.[LX[LANG]]||d?.[0]||el.textContent;el.textContent=projectText(`ui.${el.dataset.i}`,fallback);});
 window.refreshLiveLocalizedLabels?.();
 renderNav();renderCrumb();renderLangSw();
}
function projectText(key,fallback){return PROJECT_TRANSLATIONS?.[LANG]?.[key]||fallback||key;}
window.configureProjectLanguages=function(data){
 PROJ_LANGS=(data?.supported_locales||['ko']).filter(Boolean);
 PROJECT_TRANSLATIONS=data?.translations||PROJECT_TRANSLATIONS||{};
 PROJECT_LANGUAGE_META=data?.languages||PROJECT_LANGUAGE_META;
 const preferred=data?.preferred_locale||data?.default_locale||PROJ_LANGS[0]||'ko';
 LANG=PROJ_LANGS.includes(preferred)?preferred:(PROJ_LANGS[0]||'ko');
 const summary=$('#projectLanguageSummary');
 if(summary)summary.innerHTML=PROJ_LANGS.map(l=>`<span>${(PROJECT_LANGUAGE_META[l]?.native_name)||LANG_NAMES[l]||l.toUpperCase()}</span>`).join('');
 applyLang();
};
function renderLangSw(){
 $('#langSw').innerHTML=`<select aria-label="화면 언어">${PROJ_LANGS.map(l=>`<option value="${l}" ${LANG===l?'selected':''}>${(PROJECT_LANGUAGE_META[l]?.native_name)||LANG_NAMES[l]||l.toUpperCase()}</option>`).join('')}</select>`;
}

/* ============ 내비게이션 · 라우터 ============ */
const NAV=[
 {g:null,items:[{r:'#/dashboard',ko:'대시보드',en:'Dashboard',vi:'Bảng điều khiển',ic:'dash'}]},
 {g:['증빙자료','Evidence','Minh chứng'],gk:'group.evidence',items:[
  {r:'#/evidence',ko:'자료 업로드',en:'Evidence upload',vi:'Tải minh chứng',ic:'lib',badge:1},
  {r:'#/evidence/pdm',ko:'PDM 증빙',en:'PDM evidence',vi:'Minh chứng PDM',ic:'pdm'},
  {r:'#/evidence/dac',ko:'DAC 증빙',en:'DAC evidence',vi:'Minh chứng DAC',ic:'slots'},
  {r:'#/evidence/coverage',ko:'증빙 충족도',en:'Evidence coverage',vi:'Mức đáp ứng',ic:'results'}]},
 {g:['성과 관리','Performance','Quản lý kết quả'],gk:'group.performance',items:[
  {r:'#/project/overview',ko:'사업 개요',en:'Overview',vi:'Tổng quan',ic:'ovv'},
  {r:'#/project/indicators',ko:'성과지표 모니터링',en:'Indicators',vi:'Chỉ số',ic:'ind'},
  {r:'#/project/gaps',ko:'성과 리스크 예측 및 개선권고',en:'Risk & recommendations',vi:'Rủi ro & khuyến nghị',ic:'gap'}]},
 {g:['종료평가','Evaluation','Đánh giá'],gk:'group.evaluation',items:[
  {r:'#/eval/overview',ko:'종료평가 준비도',en:'Readiness',vi:'Mức sẵn sàng',ic:'ovv'},
  {r:'#/eval/board',ko:'DAC 평가진단',en:'DAC assessment',vi:'Chẩn đoán DAC',ic:'board'},
  {r:'#/eval/results',ko:'분석 결과',en:'Analysis',vi:'Kết quả',ic:'results'},
  {r:'#/eval/report',ko:'보고서 자동작성',en:'Auto report',vi:'Tạo báo cáo',ic:'report'}]},
 {g:['관리자','Admin','Quản trị'],gk:'group.admin',adminOnly:true,items:[
  {r:'#/admin/projects',ko:'프로젝트 관리',en:'Projects',vi:'Dự án',ic:'board'},
  {r:'#/admin/users',ko:'사용자 및 권한 관리',en:'Users & access',vi:'Tài khoản',ic:'board'}]}];
const ROUTES={
 '#/dashboard':{v:'v-dashboard',c:[['대시보드','Dashboard','Bảng điều khiển']]},
 '#/evidence':{v:'v-ev-manage',c:[['증빙자료','Evidence','Minh chứng'],['자료 업로드','Upload','Tải lên']]},
 '#/evidence/pdm':{v:'v-ev-pdm',c:[['증빙자료','Evidence','Minh chứng'],['PDM 증빙','PDM evidence','Minh chứng PDM']]},
 '#/evidence/dac':{v:'v-ev-dac',c:[['증빙자료','Evidence','Minh chứng'],['DAC 증빙','DAC evidence','Minh chứng DAC']]},
 '#/evidence/coverage':{v:'v-ev-coverage',c:[['증빙자료','Evidence','Minh chứng'],['증빙 충족도','Coverage','Mức đáp ứng']]},
 '#/project/overview':{v:'v-proj-overview',c:[['성과 관리','Performance','Quản lý kết quả'],['사업 개요','Overview','Tổng quan']]},
 '#/project/indicators':{v:'v-proj-indicators',c:[['성과 관리','Performance','Quản lý kết quả'],['성과지표 모니터링','Indicators','Chỉ số']]},
 '#/project/gaps':{v:'v-proj-gaps',c:[['성과 관리','Performance','Quản lý kết quả'],['성과 리스크 예측 및 개선권고','Risk & recommendations','Rủi ro & khuyến nghị']]},
 '#/eval/overview':{v:'v-eval-overview',c:[['종료평가','Evaluation','Đánh giá'],['종료평가 준비도','Readiness','Mức sẵn sàng']]},
 '#/eval/board':{v:'v-eval-board',c:[['종료평가','Evaluation','Đánh giá'],['DAC 평가진단','DAC assessment','Chẩn đoán DAC']]},
 '#/eval/results':{v:'v-eval-results',c:[['종료평가','Evaluation','Đánh giá'],['분석 결과','Analysis','Kết quả']]},
 '#/eval/report':{v:'v-eval-report',c:[['종료평가','Evaluation','Đánh giá'],['보고서 자동작성','Auto report','Tạo báo cáo']],report:1,menu:'evaluation_report'},
 '#/admin':{v:'v-admin',c:[['관리자','Admin','Quản trị'],['계정 및 권한 관리','Accounts & access','Tài khoản']],admin:1}};
Object.assign(ROUTES,{
 '#/admin/projects':{v:'v-admin',c:[['관리자','Admin','Quản trị'],['프로젝트 관리','Projects','Dự án']],admin:1},
 '#/admin/users':{v:'v-admin',c:[['관리자','Admin','Quản trị'],['사용자 및 권한 관리','Users & access','Tài khoản']],admin:1},
 '#/dashboard':{...ROUTES['#/dashboard'],menu:'dashboard'}, '#/evidence':{...ROUTES['#/evidence'],menu:'evidence_upload'},
 '#/evidence/pdm':{...ROUTES['#/evidence/pdm'],menu:'evidence_pdm'}, '#/evidence/dac':{...ROUTES['#/evidence/dac'],menu:'evidence_dac'},
 '#/evidence/coverage':{...ROUTES['#/evidence/coverage'],menu:'evidence_coverage'}, '#/project/overview':{...ROUTES['#/project/overview'],menu:'project_overview'},
 '#/project/indicators':{...ROUTES['#/project/indicators'],menu:'project_indicators'}, '#/project/gaps':{...ROUTES['#/project/gaps'],menu:'project_gaps'},
 '#/eval/overview':{...ROUTES['#/eval/overview'],menu:'evaluation_overview'}, '#/eval/board':{...ROUTES['#/eval/board'],menu:'evaluation_board'},
 '#/eval/results':{...ROUTES['#/eval/results'],menu:'evaluation_results'}
});
let CURRENT_ROLE='발주처';
const isAdmin=()=>CURRENT_ROLE==='발주처';
function hasMenuPermission(menuKey){
 return !window.KODAME_IS_ADMIN&&window.KODAME_MENU_PERMISSIONS?.[menuKey]!==false;
}
let CUR='#/dashboard', FORCE=false, PREV_HASH='#/dashboard';
function go(h){
 if(!ROUTES[h])h='#/dashboard';
 try{location.hash=h;}catch(e){}
 if(location.hash!==h){FORCE=true;CUR=h;route();}
}
function renderNav(){
 const k=LX[LANG];
 $('#gnbNav').innerHTML=NAV.filter(gr=>window.KODAME_IS_ADMIN?gr.adminOnly:!gr.adminOnly).map(gr=>{
  const items=gr.items.filter(it=>ROUTES[it.r]?.admin||hasMenuPermission(ROUTES[it.r]?.menu)).map(it=>{
   const active=CUR===it.r;
   const pendingCount=Number.isInteger(window.LIVE_PENDING_COUNT)?window.LIVE_PENDING_COUNT:ASSIGN.length;
   const badge=it.badge&&pendingCount>0?`<span class="nb num">${pendingCount}</span>`:'';
   const menuKey=ROUTES[it.r]?.admin?'admin':ROUTES[it.r]?.menu;
   const label=ROUTES[it.r]?.admin?(it[LANG]||it.ko):projectText(`menu.${menuKey}`,it[LANG]||it.ko);
   return `<button class="nitem ${active?'active':''}" data-r="${it.r}">${svg(it.ic)}<span class="lb">${label}</span>${badge}</button>`;}).join('');
  return gr.g?`<div class="ngroup"><div class="nglabel"><span>${projectText(gr.gk,gr.g[k]||gr.g[0])}</span></div><div class="nsub">${items}</div></div>`
             :`<div class="ngroup">${items}</div>`;}).join('');
}
function renderCrumb(){
 const r=ROUTES[CUR]||ROUTES['#/dashboard'];const k=LX[LANG];
 const groupKey=CUR.startsWith('#/evidence')?'group.evidence':CUR.startsWith('#/project')?'group.performance':CUR.startsWith('#/eval')?'group.evaluation':CUR==='#/admin'?'group.admin':null;
 const menuKey=CUR==='#/admin'?'admin':r.menu;
 $('#crumb').innerHTML=r.c.map((c,i)=>{const key=i===r.c.length-1?`menu.${menuKey}`:groupKey;const value=projectText(key,c[k]||c[0]);return i===r.c.length-1?`<b>${value}</b>`:`<span>${value}</span><span class="sep">›</span>`;}).join('');
}
function firstAllowedRoute(){
 if(window.KODAME_IS_ADMIN)return '#/admin/projects';
 return Object.entries(ROUTES).find(([hash,r])=>hash!=='#/admin'&&r.menu&&hasMenuPermission(r.menu))?.[0]||'#/dashboard';
}
function route(){
 let h=FORCE?CUR:(location.hash||'#/dashboard');
 if(window.KODAME_IS_ADMIN&&(!h.startsWith('#/admin/')||h==='#/admin')){go('#/admin/projects');return;}
 if(!ROUTES[h]){go('#/dashboard');return;}
 CUR=h;
 const r=ROUTES[h];
 if(r.admin&&!window.KODAME_IS_ADMIN){toast('관리자 계정만 접근할 수 있습니다');go('#/dashboard');return;}
 if(r.menu&&!hasMenuPermission(r.menu)){
  const fallback=firstAllowedRoute();
  if(h!==fallback){toast('관리자페이지에서 허용되지 않은 메뉴입니다');go(fallback);return;}
 }
 document.body.classList.toggle('report-mode',!!r.report);
 document.body.classList.toggle('admin-mode',!!window.KODAME_IS_ADMIN);
 if(r.admin){const users=h==='#/admin/users';$('#adminPageTitle').textContent=users?'사용자 및 권한 관리':'프로젝트 관리';$$('[data-admin-panel]').forEach(panel=>{panel.hidden=panel.dataset.adminPanel!==(users?'users':'projects');});}
 $$('.view').forEach(v=>v.classList.toggle('active',v.id===r.v));
 renderNav();renderCrumb();
 window.scrollTo({top:0});
 PREV_HASH=h;
}
window.addEventListener('hashchange',()=>{FORCE=false;route();});
document.addEventListener('click',e=>{
 const n=e.target.closest('.nitem');
 if(n){go(n.dataset.r);return;}
 const g=e.target.closest('[data-go]');
 if(g){go(g.dataset.go);return;}
});

/* ============ 데이터 ============ */
const CRIT=[{nm:'적절성',en:'Relevance',desc:'사업 목적·설계가 수원국 수요와 정책에 부합하는가',score:4},
 {nm:'일관성',en:'Coherence',desc:'한국·국제 전략 및 타 사업과 정합적으로 추진되는가',score:3.5},
 {nm:'효과성',en:'Effectiveness',desc:'산출물·성과지표가 목표 대비 달성되었는가',score:3},
 {nm:'효율성',en:'Efficiency',desc:'투입이 산출·성과로 경제적으로 전환되었는가',score:3.5},
 {nm:'지속가능성',en:'Sustainability',desc:'사업 편익이 종료 후에도 지속될 여건인가',score:3.5}];
const SLOTS=[
 {nm:'적절성',items:[{t:'예비/기획조사 결과보고서 (Baseline)',file:'무구지역_사전조사_결과보고서.pdf'},{t:'수혜자·이해관계자 수요조사서',file:'수혜자_수요조사_결과.pdf'},{t:'사업개요서 / 사업요청서 (PCP)',file:'라이프케어_PCP.pdf'},{t:'협력국 국가개발전략·부문 정책',file:'베트남_국가보건전략.pdf'},{t:'우선순위·정책 부합성 증빙',file:null}]},
 {nm:'일관성',items:[{t:'공여기관 협력전략 (CPS)',file:'KOICA_베트남_CPS.pdf'},{t:'국제개발목표(SDGs) 연계 근거',file:null},{t:'유사·중복 사업 검토 자료',file:null},{t:'현지 정부·타 공여기관 협업 문서',file:'MOU_뚜옌꽝성보건국.pdf'}]},
 {nm:'효과성',items:[{t:'사업설계매트릭스 (PDM)',file:'라이프케어_PDM.hwp',pdm:1},{t:'성과지표 실적자료',file:'성과지표_실적_2027.xlsx',pdm:1},{t:'기준선(Baseline) 조사자료',file:'기준선조사_결과.pdf',pdm:1},{t:'종료선(Endline) 조사자료',file:null,pdm:1},{t:'소외계층 포용·형평성 자료',file:null}]},
 {nm:'효율성',items:[{t:'예산 집행 내역',file:'예산집행_내역서.xlsx',pdm:1},{t:'사업 일정·공정 자료',file:'사업공정표.xlsx'},{t:'조달 내역·계약 문서',file:null,pdm:1},{t:'투입 대비 산출 분석',file:null}]},
 {nm:'지속가능성',items:[{t:'운영·유지관리 계획',file:'운영유지관리_계획서.hwp'},{t:'현지 인력 교육·인수인계 자료',file:'현지인력_교육이수명단.xlsx',pdm:1},{t:'재정 자립·예산 확보 근거',file:null},{t:'제도화·거버넌스 자료',file:'사업운영위원회_회의록.pdf'}]}];
const PDMSLOTS=[
 {nm:'영향',items:[{t:'성(省) 보건통계 연보',file:null}]},
 {nm:'성과',items:[{t:'기준선 조사자료',file:'기준선조사_결과.pdf'},{t:'종료선 조사자료',file:null},{t:'보건소 등록 기록',file:null}]},
 {nm:'산출물',items:[{t:'보건소 실적 보고',file:'성과지표_실적_2027.xlsx'},{t:'교육 이수 명단·평가지',file:'현지인력_교육이수명단.xlsx'},{t:'장비 인수인계서',file:null}]},
 {nm:'활동',items:[{t:'조달·설치 확인서',file:null},{t:'교육 운영 보고',file:null},{t:'훈련 결과 보고',file:null}]},
 {nm:'투입',items:[{t:'예산 집행 내역',file:'예산집행_내역서.xlsx'}]}];
const slotFilled=a=>a.reduce((x,s)=>x+s.items.filter(i=>i.file).length,0);
const slotTotal=a=>a.reduce((x,s)=>x+s.items.length,0);
const extOf=n=>{const e=(n.split('.').pop()||'').toUpperCase();return e.length>5?'FILE':e;};
const extCls=n=>{const e=extOf(n);return e.startsWith('HWP')?'hwp':e.startsWith('XLS')?'xls':e.startsWith('DOC')?'doc':'pdf';};
const PDM_OF={'기준선조사_결과.pdf':'성과 · 기준선 조사자료','성과지표_실적_2027.xlsx':'산출물 · 보건소 실적 보고','현지인력_교육이수명단.xlsx':'산출물 · 교육 이수 명단·평가지','예산집행_내역서.xlsx':'투입 · 예산 집행 내역'};
const FILES=[];
// Real file inventory is populated exclusively by the authenticated live layer.
const ASSIGN=[
 {fn:'종료선조사_중간집계.xlsx',meta:'XLSX · 310KB · 조사자료',to:'효과성 · 종료선(Endline) 조사자료',also:'성과 · 종료선 조사자료',conf:91,ai:1},
 {fn:'형평성_분석_소수민족.pdf',meta:'PDF · 1.4MB · 분석자료',to:'효과성 · 소외계층 포용·형평성 자료',conf:87,ai:1},
 {fn:'유사사업_검토메모.docx',meta:'DOCX · 95KB · 검토메모',to:'일관성 · 유사·중복 사업 검토 자료',conf:74,ai:1},
 {fn:'현지_인터뷰_녹취록.docx',meta:'DOCX · 1.2MB · 음성 전사 · AI 제안 불가',ai:0},
 {fn:'워크숍_결과보고.pdf',meta:'PDF · 860KB · 행사 결과 · 기준 판단 모호',ai:0}];
const INDS=[
 {tier:'impact',tn:'영향',name:'NCD 조기사망률 감소',base:'·',target:'미설정',act:'·',rate:null,st:'unset',mov:'성(省) 보건통계 연보',ev:null,basis:'PDM 개정 필요 · 목표치·측정연도 미정'},
 {tier:'outcome',tn:'성과',name:'고혈압·당뇨 등록관리율',base:'25%',target:'40%',act:'33%',rate:53,st:'under',mov:'기준선·종료선 조사',ev:'기준선조사_결과.pdf',basis:'기준선 25% → 실적 33% (증가분 8%p / 목표 15%p)'},
 {tier:'outcome',tn:'성과',name:'응급이송 평균 소요시간 단축',base:'·',target:'-30%',act:'-22%',rate:73,st:'watch',mov:'이송기록 분석',ev:null,basis:'3·4분기 이송기록 미집계 · 보완 시 재산정'},
 {tier:'output',tn:'산출물',name:'선별검사 수검자 (연간)',base:'0',target:'12,000명',act:'13,400명',rate:112,st:'ok',mov:'보건소 실적 보고',ev:'성과지표_실적_2027.xlsx',basis:'실적 13,400 ÷ 목표 12,000'},
 {tier:'output',tn:'산출물',name:'보건인력·CHW 교육 이수',base:'0',target:'300명 · 수료 90%',act:'312명 · 92%',rate:104,st:'ok',mov:'교육 이수 명단·평가지',ev:'현지인력_교육이수명단.xlsx',basis:'이수 312 ÷ 목표 300'},
 {tier:'output',tn:'산출물',name:'응급장비 보급 보건시설',base:'0',target:'26개소',act:'26개소',rate:100,st:'ok',mov:'장비 인수인계서',ev:null,basis:'실적 26 ÷ 목표 26 · 인수인계서 증빙 필요'},
 {tier:'activity',tn:'활동',name:'교육과정 운영 회차',base:'·',target:'미설정',act:'·',rate:null,st:'unset',mov:'교육 운영 보고',ev:null,basis:'운영 지표 미정의 · 실적 미집계'},
 {tier:'input',tn:'투입',name:'예산 집행률',base:'·',target:'100%',act:'96.8%',rate:97,st:'ok',mov:'예산 집행 내역',ev:'예산집행_내역서.xlsx',basis:'집행 8.9M ÷ 예산 9.2M불'}];
const IST={ok:['g','달성'],watch:['w','주의'],under:['b','미달'],unset:['n','미설정']};
const NARR=[
 {tier:'impact',tn:'영향',sum:'뚜옌꽝성 산악·소수민족 지역 주민의 건강수준 향상',inds:[0]},
 {tier:'outcome',tn:'성과',sum:'NCD 예방관리·응급대응 서비스의 접근성·질 향상',inds:[1,2]},
 {tier:'output',tn:'산출물',sum:'1. 보건소 NCD 선별검사 체계 구축',inds:[3]},
 {tier:'output',tn:'산출물',sum:'2. 보건인력·마을보건원(CHW) 역량강화',inds:[4]},
 {tier:'output',tn:'산출물',sum:'3. 응급대응 체계 구축',inds:[5]},
 {tier:'activity',tn:'활동',sum:'교육과정 개발·운영 및 이송체계 정비',inds:[6]},
 {tier:'input',tn:'투입',sum:'사업비 920만불 · 전문가 파견 · 현지 사무소 운영',inds:[7]}];
const GAPS=[
 {tier:'outcome',tn:'성과',name:'고혈압·당뇨 등록관리율',goal:'목표 40% (기준선 25%)',act:'실적 33% · 달성도 53%',rate:53,st:'under',
  why:'산악지역 접근성 제약으로 하반기 등록 캠페인이 지연됐고, 종료선 조사가 완료되지 않아 최신 실적이 반영되지 않았습니다.',
  fix:'① 종료선(Endline) 조사 결과 등록 → 실적 재산정 ② 보건소 등록기록 3·4분기분 보완',
  slot:'#/evidence/pdm',slotName:'성과 · 종료선 조사자료',due:'D-14 · 수행자'},
 {tier:'outcome',tn:'성과',name:'응급이송 평균 소요시간 단축',goal:'목표 -30%',act:'실적 -22% · 달성도 73%',rate:73,st:'watch',
  why:'우기 도로 사정으로 산간 3개 코뮌의 개선 폭이 낮습니다. 3·4분기 이송기록이 아직 미집계 상태입니다.',
  fix:'이송기록 3·4분기 데이터 보완 후 재산정 · 모의훈련 결과 반영',
  slot:null,due:'D-21 · 수행자'},
 {tier:'impact',tn:'영향',name:'NCD 조기사망률 감소',goal:'목표치 미설정',act:'실적 집계 불가',rate:null,st:'unset',
  why:'영향(Impact) 계층 지표의 목표치와 측정 시점이 PDM에 정의되지 않았습니다.',
  fix:'① PDM 개정: 목표치·측정연도 설정 ② 성(省) 보건통계 연보 확보·연결',
  slot:'#/evidence/pdm',slotName:'영향 · 성(省) 보건통계 연보',due:'D-7 · 발주처·수행자 협의'},
 {tier:'activity',tn:'활동',name:'교육과정 운영 회차',goal:'지표 미설정',act:'실적 미집계',rate:null,st:'unset',
  why:'활동 계층의 운영 관리 지표가 정의되지 않아 실적이 집계되지 않습니다.',
  fix:'PDM 보완: 운영 회차·이수율 지표 추가',
  slot:null,due:'D-30 · 수행자'}];
const CRITQA=[
 {nm:'적절성',desc:'사업 목적·설계가 수원국 수요와 정책에 부합하는가',qa:[
  {q:'사업이 이해관계자의 주요 정책·수요·우선순위를 반영하여 설계되었는가?',s:4,a:'사전조사·수요조사에서 수혜자 요구가 구체적으로 확인되고 PCP 설계에 반영됨.'},
  {q:'협력국 국가개발전략 및 부문 정책과 정합성이 있는가?',s:4,a:'베트남 국가보건전략의 NCD 예방 목표와 사업 목표가 직접 연계됨.'},
  {q:'내·외부 상황변화에 맞춰 설계가 적절히 관리·유지되었는가?',s:4,a:'연차 계획 조정 이력과 위험관리 문서에서 적기 대응이 확인됨.'}]},
 {nm:'일관성',desc:'한국·국제 전략 및 타 사업과 정합적으로 추진되는가',qa:[
  {q:'공여기관(KOICA) 협력전략과 부합하는가?',s:4,a:'KOICA 베트남 CPS 보건 중점분야와 일치함.'},
  {q:'국제개발목표(SDGs) 및 국제 규범과 연계되는가?',s:3,a:'SDG3 연계는 서술되어 있으나 지표 수준의 연계 근거 문서가 미확보됨.',lost:'SDGs 연계 근거 문서 미확보 · 보완 시 4점 가능'},
  {q:'유사·중복 사업과의 조정 및 협업이 이루어졌는가?',s:3,a:'현지 MOU는 확인되나 유사사업 검토 자료가 없어 중복성 판단이 제한적.',lost:'유사·중복 사업 검토 자료 미확보'}]},
 {nm:'효과성',desc:'산출물·성과지표가 목표 대비 달성되었는가',qa:[
  {q:'직접적·일차적 산출물(output)을 계획대로 달성하였는가?',s:4,a:'PDM 대비 보건소 기자재·교육 산출물 달성이 실적자료로 확인됨.'},
  {q:'중장기 성과(outcome)를 달성했거나 달성할 것으로 예상되는가?',s:3,a:'기준선 대비 개선 추세는 확인되나 종료선 자료가 없어 판단이 제한적.',lost:'종료선(Endline) 조사자료 미등록 · 감점 요인'},
  {q:'소외계층을 포용하여 형평성 있게 성과를 달성하였는가?',s:2,a:'산악·소수민족 대상 활동은 있으나 분리 통계·포용성 증빙이 부족함.',lost:'소외계층 분리 통계·형평성 자료 미확보'}]},
 {nm:'효율성',desc:'투입이 산출·성과로 경제적으로 전환되었는가',qa:[
  {q:'사업이 경제적·시의적절한 방식으로 추진되었는가?',s:4,a:'예산 집행률과 일정 준수율이 계획 범위 내에서 관리됨.'},
  {q:'투입(예산·인력) 대비 산출이 적정한가?',s:3,a:'집행 내역은 확인되나 투입 대비 산출 분석 자료가 없어 정량 판단 제한.',lost:'투입 대비 산출 분석 미확보'},
  {q:'조달·계약이 투명하고 효율적으로 수행되었는가?',s:3,a:'공정표 상 지연은 없으나 조달 내역·계약 문서가 미확보됨.',lost:'조달 내역·계약 문서 미확보'}]},
 {nm:'지속가능성',desc:'사업 편익이 종료 후에도 지속될 여건인가',qa:[
  {q:'운영·유지관리 체계와 계획이 마련되어 있는가?',s:4,a:'운영유지관리 계획서와 운영위원회 회의록으로 체계가 확인됨.'},
  {q:'현지 인력 역량이양·인수인계가 이루어졌는가?',s:4,a:'현지인력 교육 이수 명단으로 역량이양이 확인됨.'},
  {q:'재정적 자립·예산 확보 방안이 구체적인가?',s:3,a:'지방정부 예산 편성 의지는 확인되나 확보 근거 문서가 없음.',lost:'재정 자립·예산 확보 근거 미확보'}]}];
const PDM=[
 {tier:'impact',tn:'영향 (Impact)',rows:[
  {sum:'뚜옌꽝성 산악·소수민족 지역 주민의 건강수준 향상',ind:'NCD(비감염성질환) 조기사망률 감소',mov:'성(省) 보건통계 연보',asm:'국가 보건정책 기조 유지',st:'w',stt:'목표치 미설정',ev:[{n:'성(省) 보건통계 연보',ok:false}]}]},
 {tier:'outcome',tn:'성과 (Outcome)',rows:[
  {sum:'NCD 예방관리 및 응급대응 서비스의 접근성·질 향상',ind:'고혈압·당뇨 등록관리율 25% → 40%<br>응급이송 평균 소요시간 30% 단축',mov:'기준선·종료선 조사<br>보건소 등록 기록',asm:'보건인력 이직률 안정적 유지',st:'g',stt:'설계 완료',ev:[{n:'기준선조사_결과.pdf',ok:true},{n:'종료선 조사자료',ok:false}]}]},
 {tier:'output',tn:'산출물 (Output)',rows:[
  {sum:'1. 보건소 NCD 선별검사 체계 구축',ind:'선별검사 수검자 연 12,000명',mov:'보건소 실적 보고',asm:'기자재 통관·설치 지연 없음',st:'g',stt:'설계 완료',ev:[{n:'성과지표_실적_2027.xlsx',ok:true}]},
  {sum:'2. 보건인력·마을보건원(CHW) 역량강화',ind:'교육 이수 300명 · 수료율 90%',mov:'교육 이수 명단·평가지',asm:'교육 대상자 참여 지속',st:'g',stt:'설계 완료',ev:[{n:'현지인력_교육이수명단.xlsx',ok:true}]},
  {sum:'3. 응급대응 체계 구축',ind:'응급장비 보급 보건시설 26개소',mov:'장비 인수인계서',asm:'지방정부 운영인력 배치',st:'g',stt:'설계 완료',ev:[{n:'장비 인수인계서',ok:false}]}]},
 {tier:'activity',tn:'활동 (Activity)',rows:[
  {sum:'1-1. 선별검사 장비·기자재 지원 및 공통 기록양식 도입',ind:'·',mov:'조달·설치 확인서',asm:'현지 조달 일정 준수',st:'g',stt:'설계 완료',ev:[{n:'조달·설치 확인서',ok:false}]},
  {sum:'2-1. NCD 관리·응급처치 교육과정 개발·운영',ind:'·',mov:'교육 운영 보고',asm:'·',st:'w',stt:'지표 미설정',ev:[]},
  {sum:'3-1. 구급장비 보급 및 이송체계 정비·모의훈련',ind:'·',mov:'훈련 결과 보고',asm:'·',st:'w',stt:'지표 미설정',ev:[]}]},
 {tier:'input',tn:'투입 (Input)',rows:[
  {sum:'사업비 920만불 · 전문가 파견 · 현지 사무소 운영',ind:'·',mov:'예산 집행 내역',asm:'환율·물가 급변 없음',st:'g',stt:'설계 완료',ev:[{n:'예산집행_내역서.xlsx',ok:true}]}]}];
const SECS=[['표지','done'],['목차','done'],['평가보고서 공지','done'],['평가등급 결과표','done'],['Ⅰ. 평가결과 요약 · 국문 요약','draft'],['Ⅱ. 대상사업 개요 · 추진배경','draft'],['사업개요','draft'],['사업설계매트릭스(PDM)','rev'],['Ⅲ. 평가 목적과 범위','draft'],['평가매트릭스','rev'],['평가방법','draft'],['평가의 한계','draft'],['평가팀 구성·시행체계','done'],['Ⅳ. 성과 달성도','rev'],['적절성 평가결과','draft'],['일관성 평가결과','draft'],['효과성 평가결과','rev'],['효율성 평가결과','draft'],['지속가능성 평가결과','draft'],['범분야 이슈','draft'],['그 외 평가기준','draft'],['Ⅴ. 결론','draft'],['작동요인','draft'],['비작동요인','draft'],['변화이론 분석','rev'],['환류과제·제언','draft'],['부록 · 증빙 목록','draft']];
const FORMS=[
 ['HWPX','종료평가 결과보고서 양식','1,227 KB','evaluation-report-hwpx'],
 ['HWP','종료평가 결과보고서 양식','1,412 KB','evaluation-report-hwp'],
 ['PDF','사용자 매뉴얼 · 2026.09.20','최신','user-manual'],
 ['PDF','KOICA 평가 길라잡이 v2.2','1.3 MB','evaluation-guide-v22'],
 ['XLSX','종료평가 등급 결과표 · v2.2','28 KB','evaluation-grade-xlsx'],
 ['HWP','종료평가 등급 결과표 · 한글','83 KB','evaluation-grade-hwp'],
 ['XLSM','평가 환류과제 이행방안 원본','20 KB','evaluation-feedback-xlsm'],
 ['PPTX','분야별 평가 교훈 리포트 양식','95 KB','evaluation-lessons-pptx'],
 ['HWP','현지 평가 컨설턴트 개인정보 동의서','17 KB','consultant-consent-hwp'],
 ['HWP','평가업무수행 길라잡이 FAQ','97 KB','evaluation-faq-hwp']
];
const EVTL=[
 {n:'착수 · 평가계획 확정',m:'2026-06 · 평가매트릭스 합의',st:'done'},
 {n:'자료수집 · 증빙 확보',m:'2026-07~08 · 진행 중',st:'cur'},
 {n:'기준별 분석 · 판단',m:'2026-09 · AI 분석 + 전문가 검토',st:''},
 {n:'보고서 작성 · 검토',m:'2026-10 · 27개 섹션',st:''},
 {n:'심의 · 제출',m:'2026-11 · 발주처 최종 승인',st:''}];
const PROJECTS=[];
const STEPS=[
 {n:'1. 자료수집',st:'run',chip:'진행 중',d:()=>`필수 증빙 ${slotFilled(SLOTS)+slotFilled(PDMSLOTS)}/${slotTotal(SLOTS)+slotTotal(PDMSLOTS)}건 확보 · 미확보 ${slotTotal(SLOTS)+slotTotal(PDMSLOTS)-slotFilled(SLOTS)-slotFilled(PDMSLOTS)}건`,cur:1},
 {n:'2. 기준별 판단',st:'stop',chip:'지연',d:()=>`감점 요인 ${CRITQA.reduce((a,c)=>a+c.qa.filter(q=>q.lost).length,0)}건 처리 후 재평가 필요`},
 {n:'3. 자료 자동 배정',st:'done',chip:'완료',d:()=>`PDM·DAC 슬롯 자동 배정을 완료했습니다`},
 {n:'4. 제출 전 검토',st:'wait',chip:'대기',d:()=>'점수 산정 이유와 본문 판단 근거 최종 대조'}];
let analysisPending=2, analyzed=true;

/* ============ 공용 ============ */
let toastTimer=null;
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('on');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('on'),2600);}
function openLayer(id){$('#'+id).classList.add('on');const ov=$('#'+id+'Ov');if(ov)ov.classList.add('on');}
function closeLayer(id){$('#'+id).classList.remove('on');const ov=$('#'+id+'Ov');if(ov)ov.classList.remove('on');}
document.addEventListener('click',e=>{
 const x=e.target.closest('[data-close]');if(x){closeLayer(x.dataset.close);return;}
 if(e.target.classList&&e.target.classList.contains('modal-ov'))e.target.classList.remove('on');
 if(e.target.id==='spanelOv')closeLayer('spanel');
 if(e.target.id==='drawerOv')closeLayer('drawer');
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){['viewerOv','formsModal'].forEach(m=>$('#'+m).classList.remove('on'));closeLayer('spanel');closeLayer('drawer');}});

/* ============ 파일 뷰어 (전역) ============ */
function openViewer(name){
 const f=FILES.find(x=>x.n===name)||{n:name,dac:null,pdm:null,size:'·',date:'·'};
 const slots=[f.dac?`<span class="tag i" style="font-size:9.5px;padding:1px 6px">DAC</span> ${f.dac}`:null,f.pdm?`<span class="tag g" style="font-size:9.5px;padding:1px 6px">PDM</span> ${f.pdm}`:null].filter(Boolean).join('<br>');
 $('#vwMeta').innerHTML=`<div class="k">파일명</div><div style="font-weight:700">${f.n}</div>
  <div class="k">형식 · 크기</div><div class="num">${extOf(f.n)} · ${f.size}</div>
  <div class="k">업로드</div><div class="num">${f.date}</div>
  <div class="k">연결 슬롯</div><div>${slots||'<span style="color:var(--bad-t);font-weight:700">미배정</span>'}</div>`;
 $('#vwHead').textContent='1. '+f.n.replace(/\.[^.]+$/,'');
 $('#vwSlot').textContent=(f.dac||f.pdm)?'연결 슬롯으로 이동':'배정하러 가기';
 $('#vwSlot').dataset.go=f.dac?'#/evidence/dac':(f.pdm?'#/evidence/pdm':'#/evidence');
 openLayer('viewerOv');
}
$('#vwSlot').addEventListener('click',()=>closeLayer('viewerOv'));
document.addEventListener('click',e=>{const v=e.target.closest('[data-viewfile]');if(v)openViewer(v.dataset.viewfile);});

/* ============ 렌더러 · 대시보드 ============ */
function drawRadar(id,max){
 const el=document.getElementById(id);if(!el)return;
 const cx=200,cy=155,R=106,N=CRIT.length;max=max||4;
 const ang=i=>(-90+i*360/N)*Math.PI/180;const pt=(i,r)=>[cx+r*Math.cos(ang(i)),cy+r*Math.sin(ang(i))];
 const poly=r=>CRIT.map((_,i)=>pt(i,r).join(',')).join(' ');let s='';
 for(let g=1;g<=4;g++)s+=`<polygon points="${poly(R*g/4)}" fill="none" stroke="#E4EAF1" stroke-width="1"/>`;
 for(let i=0;i<N;i++){const[x,y]=pt(i,R);s+=`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#E4EAF1"/>`;}
 s+=`<polygon points="${CRIT.map((c,i)=>pt(i,R*c.score/max).join(',')).join(' ')}" fill="rgba(79,179,232,.18)" stroke="#4FB3E8" stroke-width="2" stroke-linejoin="round"/>`;
 CRIT.forEach((c,i)=>{const[x,y]=pt(i,R*c.score/max);s+=`<circle cx="${x}" cy="${y}" r="3" fill="#2E9FD4"/>`;});
 CRIT.forEach((c,i)=>{const[lx,ly]=pt(i,R+21);const a=Math.abs(lx-cx)<6?'middle':(lx<cx?'end':'start');s+=`<text x="${lx}" y="${ly+4}" font-size="11.5" font-weight="600" fill="#63788C" text-anchor="${a}">${c.nm} <tspan font-weight="800" fill="#1173A8">${c.score}</tspan></text>`;});
 el.innerHTML=s;
}
function achievePct(){
 const dac=Math.round(slotFilled(SLOTS)/slotTotal(SLOTS)*100);
 const pdm=Math.round(slotFilled(PDMSLOTS)/slotTotal(PDMSLOTS)*100);
 const ok=INDS.filter(x=>x.st==='ok').length;
 const ind=Math.round(ok/INDS.length*100);
 return {dac,pdm,ind,total:Math.round((dac+pdm+ind)/3)};
}
function renderRing(){
 const p=achievePct();
 $('#achievePct').textContent=p.total+'%';
 $('#achieveBar').style.width=p.total+'%';
 const missing=slotTotal(SLOTS)+slotTotal(PDMSLOTS)-slotFilled(SLOTS)-slotFilled(PDMSLOTS);
 $('#daonSub').textContent=`제출까지 D-45 · 증빙 ${missing}건과 미달 지표 2건이 남았습니다 · PDM·DAC를 종합한 우선순위입니다`;
}
const fixDone={};
function renderFix(){
 const items=[];
 items.push({key:'endline',sev:'긴급',sc:'b',vt:'DAC',vc:'i',t:'종료선(Endline) 조사자료 등록',d:'효과성 Q2 감점 요인 · 등록관리율 실적 재산정의 필수 증빙이에요',go:'#/evidence/dac'});
 items.push({key:'reg',sev:'보완',sc:'w',vt:'PDM',vc:'g',t:'등록관리율 미달 원인 확인 (33% / 목표 40%)',d:'성과 리스크 예측 및 개선권고에서 조치 내용을 확인하세요',go:'#/project/gaps'});
 items.push({key:'ncd',sev:'보완',sc:'w',vt:'PDM',vc:'g',t:'NCD 조기사망률 목표치 설정 (PDM 개정)',d:'영향 계층 지표의 목표치·측정연도가 비어 있습니다',go:'#/project/gaps'});
 items.push({key:'sdg',sev:'안내',sc:'i',vt:'DAC',vc:'n',t:'SDGs 연계 근거 문서 확인',d:'일관성 기준 · 보완 시 4점 가능',go:'#/evidence/dac'});
 $('#fixList').innerHTML=items.map(x=>`<div class="ti ${fixDone[x.key]?'done':''}" data-k="${x.key}"><span class="cb">${fixDone[x.key]?'✓':''}</span><span class="tt">${x.t}<span class="td">${x.d}</span></span><span class="tag ${x.vc}" style="font-size:10px">${x.vt}</span><span class="tag ${x.sc}">${x.sev}</span><span class="go2" data-go="${x.go}">이동 ›</span></div>`).join('');
 const left=items.filter(x=>!fixDone[x.key]).length;
 $('#fixFoot').textContent=left?`오늘 남은 할 일 ${left}건 · 완료 항목을 확인합니다`:'오늘 할 일을 모두 완료했습니다. 다온이 재평가를 준비합니다 ✦';
 $('#daonHello').innerHTML=`오늘 해야 할 일을 <em>다온</em>이 알려드려요!`;
 syncTodoFold(items.length);
}
function syncTodoFold(total){
 const list=$('#fixList'),fold=$('#daonFold'),hasMore=Number(total)>5;
 if(!hasMore)list.classList.remove('expanded');
 fold.hidden=!hasMore;
 fold.textContent=list.classList.contains('expanded')?'접기 ▴':'펼치기 ▾';
}
$('#fixList').addEventListener('click',e=>{
 if(e.target.closest('[data-go]'))return;
 const ti=e.target.closest('.ti');if(!ti)return;
 fixDone[ti.dataset.k]=!fixDone[ti.dataset.k];renderFix();});
$('#daonFold').addEventListener('click',()=>{
 $('#fixList').classList.toggle('expanded');
 syncTodoFold($('#fixList').children.length);});
function renderDashMini(){
 const order={under:0,watch:1,unset:2,ok:3};
 const rows=[...INDS].sort((a,b)=>order[a.st]-order[b.st]).slice(0,5);
 $('#dashInd').innerHTML=rows.map(x=>{const[c,l]=IST[x.st];
  const bar=x.rate===null?`<span style="flex:1;max-width:110px"></span>`:`<div class="pbar" style="max-width:110px"><i class="${c==='g'?'g':c==='w'?'w':c==='b'?'r':''}" style="width:${Math.min(x.rate,100)}%"></i></div><span class="mv num">${x.rate}%</span>`;
  return `<div class="minirow" data-go="${x.st==='ok'?'#/project/indicators':'#/project/gaps'}" style="cursor:pointer"><span class="tier ${x.tier}" style="font-size:9.5px;padding:2px 7px">${x.tn}</span><span class="mn">${x.name}</span>${bar}<span class="tag ${c}">${l}</span></div>`;}).join('');
 const okN=INDS.filter(x=>x.st==='ok').length,underN=INDS.filter(x=>x.st==='under'||x.st==='watch').length,unsetN=INDS.filter(x=>x.st==='unset').length;
 $('#pdmBig').innerHTML=`${okN}<small>/${INDS.length}</small>`;
 $('#pdmKl').textContent=`지표 달성 · 미달·주의 ${underN} · 목표 미설정 ${unsetN}`;
 $('#dacReady').innerHTML=`
  <div class="minirow" data-go="#/evidence/dac" style="cursor:pointer"><span class="mn">DAC 증빙 확보</span><span class="mv num">${slotFilled(SLOTS)}/${slotTotal(SLOTS)}</span></div>
  <div class="minirow" data-go="#/eval/board" style="cursor:pointer"><span class="mn">재평가 대기</span><span class="mv num" style="color:${analysisPending?'var(--warn-t)':'var(--good-t)'}">${analysisPending}건</span></div>
  <div class="minirow" data-go="#/eval/board" style="cursor:pointer"><span class="mn">진행 단계</span><span class="mv num">2<small style="color:var(--muted);font-weight:600">/4</small></span><span class="tag w">자료수집</span></div>
  <div class="minirow" data-go="#/eval/results" style="cursor:pointer"><span class="mn">감점 요인</span><span class="mv num" style="color:var(--warn-t)">${CRITQA.reduce((a,c)=>a+c.qa.filter(q=>q.lost).length,0)}건</span></div>`;
}
/* ============ 증빙자료 관리 ============ */
function renderStats(){
 const df=slotFilled(SLOTS),dt=slotTotal(SLOTS),pf=slotFilled(PDMSLOTS),pt=slotTotal(PDMSLOTS);
 $('#statPdm').innerHTML=`${pf}<span>/${pt}</span>`;$('#statPdmBar').style.width=Math.round(pf/pt*100)+'%';
 $('#statDac').innerHTML=`${df}<span>/${dt}</span>`;$('#statDacBar').style.width=Math.round(df/dt*100)+'%';
 $('#statFiles').textContent=FILES.length;
 $('#cntAll').textContent=FILES.length+'건';
 $('#boardEv').innerHTML=`${df}<small>/${dt}</small>`;
 $('#pdmEvCnt').textContent=`${pf}/${pt}`;
 $('#coveragePdmValue').innerHTML=`${pf}<span>/${pt}</span>`;
 $('#coveragePdmBar').style.width=Math.round(pf/pt*100)+'%';
 $('#coverageDacValue').innerHTML=`${df}<span>/${dt}</span>`;
 $('#coverageDacBar').style.width=Math.round(df/dt*100)+'%';
 $('#coverageDocumentValue').textContent=FILES.length;
 $('#coverageGapList').innerHTML=`<div class="minirow" data-go="#/evidence/pdm"><span class="tag g">PDM</span><span class="mn">검증수단 미확보 항목</span><span class="mv num">${pt-pf}건</span><span class="go2">확인 ›</span></div><div class="minirow" data-go="#/evidence/dac"><span class="tag i">DAC</span><span class="mn">평가기준 증빙 미확보 항목</span><span class="mv num">${dt-df}건</span><span class="go2">확인 ›</span></div>`;
}
let fileFilter='all', fileQuery='', fileShowAll=false;
const FILE_LIMIT=8;
function renderFiles(){
 const list=FILES.filter(f=>fileFilter==='all'||(fileFilter==='linked'?(f.dac||f.pdm):!(f.dac||f.pdm)))
  .filter(f=>!fileQuery||f.n.toLowerCase().includes(fileQuery));
 const shown=fileShowAll?list:list.slice(0,FILE_LIMIT);
 $('#fileRows').innerHTML=shown.length?shown.map(f=>{
  const slots=[f.dac?`<div style="display:flex;align-items:center;gap:6px;margin:1px 0"><span class="tag i" style="font-size:9px;padding:1px 6px">DAC</span><span style="font-weight:600;color:var(--ink-2)">${f.dac}</span></div>`:'',
   f.pdm?`<div style="display:flex;align-items:center;gap:6px;margin:1px 0"><span class="tag g" style="font-size:9px;padding:1px 6px">PDM</span><span style="font-weight:600;color:var(--ink-2)">${f.pdm}</span></div>`:''].join('');
  return `<tr data-viewfile="${f.n}" style="cursor:pointer"><td><span style="display:flex;align-items:center;gap:9px;font-weight:600;min-width:0"><span class="ext ${extCls(f.n)}">${extOf(f.n)}</span><span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${f.n}</span></span></td><td>${slots||'<span class="tag b">미배정</span>'}</td><td class="meta2 num">${f.size}</td><td class="meta2 num">${f.date}</td></tr>`;}).join('')
  :`<tr><td colspan="4"><div class="empty" style="border:none">조건에 맞는 문서가 없습니다. 다른 필터나 키워드로 검색합니다.</div></td></tr>`;
 const more=$('#fileMore');
 if(list.length>FILE_LIMIT){more.style.display='block';more.textContent=fileShowAll?'접기 ▴':`전체 ${list.length}건 모두 보기 ▾`;}
 else more.style.display='none';
}
$$('.fchipb').forEach(b=>b.addEventListener('click',()=>{$$('.fchipb').forEach(x=>x.classList.remove('on'));b.classList.add('on');fileFilter=b.dataset.f;fileShowAll=false;renderFiles();}));
$('#fileSearch').addEventListener('input',e=>{fileQuery=e.target.value.trim().toLowerCase();fileShowAll=false;renderFiles();});
$('#fileMore').addEventListener('click',()=>{fileShowAll=!fileShowAll;renderFiles();});
function emptySlotOptions(){
 const o1=[],o2=[];
 SLOTS.forEach(s=>s.items.forEach(it=>{if(!it.file)o1.push(`${s.nm} · ${it.t}`);}));
 PDMSLOTS.forEach(s=>s.items.forEach(it=>{if(!it.file)o2.push(`${s.nm} · ${it.t}`);}));
 return `<optgroup label="DAC 평가기준">${o1.map(o=>`<option>${o}</option>`).join('')}</optgroup><optgroup label="PDM 검증수단">${o2.map(o=>`<option>${o}</option>`).join('')}</optgroup>`;
}
function slotView(path){
 const nm=path.split(' · ')[0];
 return SLOTS.some(s=>s.nm===nm)?'#/evidence/dac':'#/evidence/pdm';
}
function renderAssign(){
 $('#assignCount').textContent=`미처리 ${ASSIGN.length}건`;
 const sp=$('#spPend');if(sp)sp.textContent=ASSIGN.length+'건';
 $('#assignList').innerHTML=ASSIGN.length?ASSIGN.map((s,i)=>{
  if(s.ai)return `<div class="arow"><div class="fn"><span data-viewfile="${s.fn}" style="cursor:pointer">${s.fn}</span><small>${s.meta}</small></div><span class="arw">→</span><span class="to" data-go="${slotView(s.to)}" title="해당 슬롯 화면으로 이동">${s.to}${s.also?' <b style="color:var(--good-t)">＋PDM</b>':''}</span><div class="confcol"><span class="conf num">AI 신뢰도 ${s.conf}%</span>${s.conf<80?`<span class="tag w" style="font-size:10px">직접 확인 권장</span>`:`<span class="tag g" style="font-size:10px">자동 제안</span>`}</div><div class="acts2"><button class="btn sm primary" data-ok="${i}">승인</button></div></div>`;
  return `<div class="arow manual"><div class="fn"><span data-viewfile="${s.fn}" style="cursor:pointer">${s.fn}</span><small>${s.meta}</small></div><span class="arw">→</span><select data-sel="${i}"><option value="">배정할 슬롯 선택…</option>${emptySlotOptions()}</select><div class="confcol"><span class="tag n" style="font-size:10px">AI 제안 불가</span></div><div class="acts2"><button class="btn sm primary" data-assign="${i}">배정</button></div></div>`;
 }).join('')
 :`<div class="empty"><b>배정할 문서가 없습니다.</b><br>새 증빙을 올리면 다온이 PDM · DAC 슬롯에 자동으로 배정합니다.</div>`;
 renderNav();
}
function fillSlot(path,fn){
 const[nm,...rest]=path.split(' · ');const t=rest.join(' · ');
 const arr=SLOTS.some(s=>s.nm===nm)?SLOTS:PDMSLOTS;
 const sec=arr.find(s=>s.nm===nm);if(!sec)return false;
 const it=sec.items.find(x=>x.t===t&&!x.file);if(!it)return false;
 it.file=fn;
 const f=FILES.find(x=>x.n===fn);
 if(f){if(arr===SLOTS)f.dac=path;else f.pdm=path;}
 return true;
}
function refreshAll(){
 renderStats();renderRing();renderFix();renderDashMini();renderFiles();renderAssign();renderSlots();renderSteps();updateAnalyze();
}
$('#assignList').addEventListener('click',e=>{
 if(e.target.closest('[data-viewfile]')||e.target.closest('[data-go]'))return;
 const ok=e.target.closest('[data-ok]');
 if(ok){const s=ASSIGN[+ok.dataset.ok];
  fillSlot(s.to,s.fn);if(s.also)fillSlot(s.also,s.fn);
  ASSIGN.splice(+ok.dataset.ok,1);analysisPending++;refreshAll();
  toast(s.also?`승인 완료 · DAC·PDM 두 슬롯에 중복 배정했습니다`:`승인 완료 · ${s.to}에 연결했습니다`);return;}
 const as=e.target.closest('[data-assign]');
 if(as){const i=+as.dataset.assign;const sel=$(`select[data-sel="${i}"]`);
  if(!sel.value){toast('배정할 슬롯을 먼저 선택해 주세요');sel.focus();return;}
  const s=ASSIGN[i];fillSlot(sel.value,s.fn);ASSIGN.splice(i,1);analysisPending++;refreshAll();
  toast(`배정 완료 · ${sel.value}`);}
});
/* KPI 카드 헬퍼 */
const statCard=(label,value,sub,cls,go)=>`<div class="stat${go?' link':''}"${go?` data-go="${go}"`:''}><div class="sl">${label}</div><div class="sv num ${cls||''}">${value}</div><div class="ss">${sub||''}</div></div>`;
/* 슬롯 현황 (PDM · DAC 두 화면 · 2열 카드 그리드) */
function slotSectionsHTML(data,admin){
 return data.map((s,i)=>{
  const have=s.items.filter(x=>x.file).length,need=s.items.length;
  const pct=need?Math.round(have/need*100):0;const cl=pct>=90?'g':pct>=50?'':'r';
  const sorted=s.items.map((it,oi)=>({it,oi})).sort((a,b)=>((a.it.file?1:0)-(b.it.file?1:0)));
  return `<div class="slotsec"><div class="slotsec-h"><div class="nm">${s.nm}</div><div class="cov"><div class="cvtxt"><span>확보 ${have}/${need}</span><span class="cv num">${pct}%</span></div><div class="pbar" style="margin-top:5px"><i class="${cl}" style="width:${pct}%"></i></div></div>${need-have?`<span class="tag b" style="flex:0 0 auto">미확보 ${need-have}</span>`:'<span class="tag g" style="flex:0 0 auto">완료</span>'}</div><div class="slotbody">${admin?`<button class="addslot" data-sec="${i}">＋ 슬롯 추가</button>`:''}${sorted.map(({it,oi})=>`<div class="slotrow ${it.file?'':'missrow'}"><span class="ck ${it.file?'on':'off'}">${it.file?'✓':'·'}</span><span class="sn">${it.t}${it.pdm?'<span class="pdmtag">PDM 공유</span>':''}</span>${it.file?`<span class="filechip" data-viewfile="${it.file}"><span class="t">${it.file}</span></span>`:`<span class="miss">미확보</span><button class="up" data-openup="1">업로드</button>`}${admin?`<button class="del" data-sec="${i}" data-item="${oi}" title="슬롯 삭제">×</button>`:''}</div>`).join('')}</div></div>`;}).join('');
}
function renderSlots(){
 const pf=slotFilled(PDMSLOTS),pt=slotTotal(PDMSLOTS),df=slotFilled(SLOTS),dt=slotTotal(SLOTS);
 $('#covPdm').innerHTML=
  statCard('검증수단 확보',`${pf}<span>/${pt}</span>`,`전체 대비 ${Math.round(pf/pt*100)}%`)
  +statCard('미확보',`${pt-pf}`,'지표 실적 인정 불가 상태','bad')
  +statCard('완전 충족 계층',`${PDMSLOTS.filter(s=>s.items.every(x=>x.file)).length}<span>/${PDMSLOTS.length}</span>`,'투입 · 활동 · 산출물 · 성과 · 영향');
 $('#covPdmNote').innerHTML=`검증수단 증빙은 <b data-go="#/project/indicators">성과지표 모니터링</b>의 실적 인정 근거입니다`;
 $('#covDac').innerHTML=
  statCard('필수 슬롯 확보',`${df}<span>/${dt}</span>`,`전체 대비 ${Math.round(df/dt*100)}%`)
  +statCard('미확보',`${dt-df}`,'분석 감점 요인과 직결','bad')
  +statCard('완전 충족 기준',`${SLOTS.filter(s=>s.items.every(x=>x.file)).length}<span>/${SLOTS.length}</span>`,'5대 평가기준 중');
 $('#covDacNote').innerHTML=`미확보 슬롯은 <b data-go="#/eval/results">분석 결과</b>의 감점 요인과 직접 연결됩니다`;
 $('#adminNote').textContent=isAdmin()?'발주처 권한 · 슬롯 추가·삭제 가능':'';
 $('#slotSecPdm').innerHTML=slotSectionsHTML(PDMSLOTS,false);
 $('#slotSecDac').innerHTML=slotSectionsHTML(SLOTS,isAdmin());
}
['slotSecPdm','slotSecDac'].forEach(id=>{
 $('#'+id).addEventListener('click',e=>{
  if(e.target.closest('[data-viewfile]'))return;
  if(e.target.closest('[data-openup]')){openLayer('spanel');return;}
  const del=e.target.closest('.del');
  if(del){SLOTS[+del.dataset.sec].items.splice(+del.dataset.item,1);refreshAll();return;}
  const add=e.target.closest('.addslot');
  if(add){const nm=prompt('추가할 자료 슬롯 이름을 입력하세요');if(nm&&nm.trim())SLOTS[+add.dataset.sec].items.unshift({t:nm.trim(),file:null});refreshAll();return;}});
});
/* ============ 프로젝트 현황 ============ */
function renderPdm(){
 $('#pdmBody').innerHTML=PDM.map(t=>{
  const[ko,en]=t.tn.replace(')','').split(' (');
  return t.rows.map((r,i)=>`<tr class="${i===0?'tier-first':''}">${i===0?`<td rowspan="${t.rows.length}" class="tiercell"><span class="tiername">${ko}</span><span class="tieren">${en}</span></td>`:''}<td class="sum">${r.sum}</td><td class="ind num">${r.ind}</td><td class="mov">${r.mov}</td><td class="asm">${r.asm}</td></tr>`).join('');}).join('');
}
function renderNarr(){
 const ok=INDS.filter(x=>x.st==='ok').length,watch=INDS.filter(x=>x.st==='watch').length,under=INDS.filter(x=>x.st==='under').length,unset=INDS.filter(x=>x.st==='unset').length;
 $('#indSummary').innerHTML=
  statCard('전체 지표 (OVI)',`${INDS.length}`,'PDM 객관적 검증지표')
  +statCard('달성',`${ok}`,'목표 100% 이상','good')
  +statCard('주의',`${watch}`,'달성도 70~99%','warn')
  +statCard('미달',`${under}`,'달성도 70% 미만','bad','#/project/gaps')
  +statCard('목표 미설정',`${unset}`,'PDM 보완 필요','mut','#/project/gaps');
 $('#indSummaryNote').innerHTML=`미달 · 미설정 상세는 <b data-go="#/project/gaps">성과 리스크 예측 및 개선권고</b>에서 확인하세요`;
 const TIER_EN={impact:'Impact',outcome:'Outcome',output:'Output',activity:'Activity',input:'Input'};
 $('#narrList').innerHTML=`<div class="panel" style="padding:0;overflow:hidden"><div style="overflow-x:auto"><table class="pdmtbl">
  <thead><tr><th style="width:80px">계층</th><th style="min-width:180px">요약 (Narrative Summary)</th><th style="min-width:170px">지표 (OVI)</th><th style="width:130px">기준선 → 목표</th><th style="min-width:160px">실적 · 달성도</th><th style="width:72px">상태</th><th style="min-width:190px">산출근거 · 증빙</th></tr></thead><tbody>`
  +NARR.map(n=>{
  const inds=n.inds.map(i=>INDS[i]);
  return inds.map((x,i)=>{const[c,l]=IST[x.st];
   const ph=v=>!v||v==='·'||v==='-';
   const bar=x.rate===null?`<span class="meta2" style="font-size:11px">집계 불가</span>`:`<div class="ibar"><div class="pbar"><i class="${c==='g'?'g':c==='w'?'w':c==='b'?'r':''}" style="width:${Math.min(x.rate,100)}%"></i></div><span class="pv num">${x.rate}%</span></div>`;
   const goal=x.target==='미설정'?`<span class="tag n">목표 미설정</span>`:`${ph(x.base)?'':x.base+' → '}<b style="font-weight:700;color:var(--ink)">${x.target}</b>`;
   const act=ph(x.act)?'실적 미집계':'실적 '+x.act;
   const lead=i===0?`<td rowspan="${inds.length}" class="tiercell"><span class="tiername">${n.tn}</span><span class="tieren">${TIER_EN[n.tier]}</span></td><td rowspan="${inds.length}" class="sum">${n.sum}</td>`:'';
   return `<tr class="${i===0?'tier-first':''}">${lead}<td><div style="font-weight:600">${x.name}</div><div class="isub num" style="color:var(--muted);font-size:10.5px;margin-top:2px">${act}</div></td><td class="meta2 num">${goal}</td><td>${bar}</td><td><span class="tag ${c}">${l}</span></td><td><div style="color:var(--muted);font-size:11px;font-weight:500">${x.basis}</div><div style="margin-top:5px">${x.ev?`<span class="filechip" data-viewfile="${x.ev}"><span class="t">${x.ev}</span></span>`:`<span class="meta2" style="font-size:10.5px">${x.mov} · <b style="color:var(--bad-t)">증빙 미확보</b></span>`}</div></td></tr>`;}).join('');}).join('')
  +`</tbody></table></div></div>`;
}
function renderGaps(){
 $('#gapCount').textContent=`미달 · 미설정 ${GAPS.length}건`;
 $('#gapList').innerHTML=GAPS.map(g=>{const[c,l]=IST[g.st];
  return `<div class="gapcard">
   <div class="gh"><span class="tier ${g.tier}" style="font-size:10px;padding:3px 8px">${g.tn}</span><span class="ttl">${g.name}</span>${g.rate!==null?`<div class="ibar" style="max-width:180px"><div class="pbar"><i class="${g.st==='under'?'r':'w'}" style="width:${g.rate}%"></i></div><span class="pv num">${g.rate}%</span></div>`:''}<span class="tag ${c}">${l}</span></div>
   <div class="gb">
    <div class="gcell"><div class="gl goal">목표 · 실적</div><div class="gv num"><b>${g.goal}</b><br>${g.act}</div></div>
    <div class="gcell"><div class="gl why">원인</div><div class="gv">${g.why}</div></div>
    <div class="gcell" style="grid-column:1/-1"><div class="gl fix">필요 조치</div><div class="gv">${g.fix}</div></div>
   </div>
   <div class="gfoot"><span class="num">${g.due}</span>${g.slot?`<button class="btn sm" data-go="${g.slot}" style="margin-left:auto">관련 증빙 채우러 가기 ›</button>`:''}</div>
  </div>`;}).join('');
}
/* ============ 종료평가 ============ */
function renderCritDefs(){
 $('#critDefs').innerHTML=CRIT.map(c=>`<div class="cdef"><div class="cn">${c.nm} <span class="ce">${c.en}</span></div><div class="cd">${c.desc}</div></div>`).join('');
 $('#evalTimeline').innerHTML=EVTL.map(t=>`<div class="evt ${t.st}"><span class="ed"></span><div><div class="en">${t.n}</div><div class="em2 num">${t.m}</div></div></div>`).join('');
}
function renderChips(){
 $('#scorechips2').innerHTML=CRIT.map(c=>{const col=c.score<3?'var(--warn-t)':'var(--ink)';
  return `<button class="schip" data-go="#/eval/results"><div class="nm">${c.nm}</div><div class="sc num" style="color:${col}">${c.score}<small>/4</small></div></button>`;}).join('');
}
const STICON={done:'✓',run:'●',stop:'!',wait:'○'};
function renderSteps(){
 $('#stepline').innerHTML=STEPS.map(s=>`<div class="stepitem ${s.cur?'cur':''}"><span class="si ${s.st}">${STICON[s.st]}</span><div style="flex:1;min-width:0"><div class="sn2">${s.n}</div><div class="sd2 num">${s.d()}</div></div><span class="st2 ${s.st}">${s.chip}</span></div>`).join('');
}
function qTag(s){return s>=4?['g','충족']:s>=3?['g','양호']:s>=2?['w','보완']:['b','미흡'];}
function renderCrit(){
 $('#critSections').innerHTML=CRITQA.map(c=>{
  const avg=c.qa.reduce((a,q)=>a+q.s,0)/c.qa.length;const score=Math.round(avg*2)/2;
  const ev=((SLOTS.find(s=>s.nm===c.nm)||{items:[]}).items).filter(x=>x.file);
  const[bc,bt]=score<3?['w','보완 필요']:['g','양호'];
  const body=c.qa.map((q,qi)=>{const[tc,tt]=qTag(q.s);
   return `<div class="qrow"><span class="qno">Q${qi+1}</span><div class="qbody"><div class="qq">${q.q}</div><div class="qa"><b>AI 판단</b> · ${q.a}</div>${q.lost?`<div class="qlost ${q.s<=1?'b':'w'}">▼ 감점 요인 · ${q.lost}</div>`:''}</div><div class="qmeta"><span class="qscore num">${q.s}<small> /4</small></span><span class="tag ${tc}">${tt}</span></div></div>`;}).join('');
  const foot=`<div class="csec-foot"><span>분석 근거 ${ev.length}건</span>${ev.slice(0,3).map(x=>`<span class="filechip" data-viewfile="${x.file}"><span class="t">${x.file}</span></span>`).join('')}${ev.length>3?`<span class="filechip"><span class="t">＋${ev.length-3}건</span></span>`:''}</div>`;
  const pct=Math.round(score/4*100);
  return `<div class="csec"><div class="csec-h"><div class="nm">${c.nm}</div><div class="hbar"><div class="pbar"><i class="${bc==='w'?'w':'g'}" style="width:${pct}%"></i></div></div><span class="tag ${bc}">${bt}</span><span class="scr num">${score.toFixed(1)}<small> /4</small></span></div><div class="csec-b">${body}${foot}</div></div>`;}).join('');
}
function updateAnalyze(){
 const txt=analysisPending>0?`새 자료 ${analysisPending}건 분석 대기`:'모든 증빙 반영됨 · 최신 분석 상태';
 $('#pendAnalyze').textContent=txt;$('#stPend').textContent=txt;
 $('#pendAnalyze').classList.toggle('ok',analysisPending===0);
}
/* ============ 보고서 ============ */
const stN={done:'확정',draft:'초안',rev:'검토'};
let activeSec=4;
function renderSecs(){
 $('#seclist').innerHTML=SECS.map((s,i)=>`<div class="it ${i===activeSec?'active':''}" data-si="${i}"><span class="no num">${i+1}</span><span>${s[0]}</span><span class="st ${s[1]}">${stN[s[1]]}</span></div>`).join('');
 const cnt={done:0,draft:0,rev:0};SECS.forEach(s=>cnt[s[1]]++);
 $('#repStat').textContent=`${SECS.length}개 섹션 · 확정 ${cnt.done} · 검토 ${cnt.rev} · 초안 ${cnt.draft} · 자동 저장됨`;
}
$('#seclist').addEventListener('click',e=>{const it=e.target.closest('.it');if(!it)return;activeSec=+it.dataset.si;renderSecs();$('#reportPreviewTitle').textContent=SECS[activeSec][0];});
const OPTS=[['이어서 작성','저장본(섹션 1~27)을 불러와 이어서 편집',1],['새로 작성','섹션 전체를 AI로 다시 생성',0],['원본 양식 열기','저장본 초기화 후 원본 HWPX 양식 열기',0]];
$('#optcards').innerHTML=OPTS.map((o,i)=>`<div class="opt ${o[2]?'sel':''}"><div class="ot">${o[0]}</div><div class="od">${o[1]}</div></div>`).join('');
$('#optcards').addEventListener('click',e=>{const o=e.target.closest('.opt');if(!o)return;$$('#optcards .opt').forEach(x=>x.classList.remove('sel'));o.classList.add('sel');});
$('#repExit').addEventListener('click',()=>go('#/eval/board'));
const demoRepSave=$('#repSave');if(demoRepSave)demoRepSave.addEventListener('click',()=>toast('완성된 보고서를 한글(HWP) 파일로 저장했습니다 (데모)'));
/* 서식 모달 */
function renderForms(q){
 const list=FORMS.filter(f=>!q||f[1].toLowerCase().includes(q)||f[0].toLowerCase().includes(q));
 $('#formsList').innerHTML=list.length?list.map(f=>`<div class="form-row"><span class="ext">${f[0]}</span><span class="fn2">${f[1]}</span><span class="fs num">${f[2]}</span><a class="dl" href="/api/v2/samples/templates/${encodeURIComponent(f[3])}/download" download>다운로드</a></div>`).join('')
  :'<div class="empty">검색 결과가 없습니다.</div>';
}
function openForms(){openLayer('formsModal');renderForms('');$('#formsSearch').value='';setTimeout(()=>$('#formsSearch').focus(),60);}
$('#formsOpen').addEventListener('click',openForms);
const fo2=$('#formsOpen2');if(fo2)fo2.addEventListener('click',openForms);
$('#formsSearch').addEventListener('input',e=>renderForms(e.target.value.trim().toLowerCase()));
$('#formsList').addEventListener('click',e=>{if(e.target.closest('.dl'))toast('샘플서식 다운로드를 시작했습니다.');});

/* ============ AI 작업 트레이 ============ */
const JOBS=[];
function renderTray(){
 if(window.ServiceJobTray){window.ServiceJobTray.render();return;}
 $('#trayLive').classList.toggle('on',JOBS.some(j=>j.p<100));
 $('#trayJobs').innerHTML=JOBS.length?[...JOBS].reverse().map(j=>`<div class="job"><div class="jt"><span>${j.name}</span><span class="jst ${j.p>=100?'done':''}">${j.p>=100?'완료':j.step}</span></div><div class="jbar"><i style="width:${j.p}%"></i></div><div class="jd">${j.desc}</div></div>`).join('')
  :'<div class="tray-empty">진행 중인 AI 작업이 없습니다.<br>재평가·보고서 생성·지표 갱신을 실행하면 여기서 진행률을 확인할 수 있습니다.</div>';
}
function addJob(name,desc,steps,onDone){
 // Never simulate successful AI work if the live script failed to initialize.
 toast('서비스 연결을 확인해 주세요. 실제 AI 작업은 서버 접수 후 표시됩니다.');
}
$('#trayBtn').addEventListener('click',()=>{$('#tray').classList.toggle('on');renderTray();});
function runAnalysis(){
 if(JOBS.some(j=>j.name==='DAC 재평가'&&j.p<100)){toast('이미 재평가가 진행 중이에요');openLayer('tray');return;}
 addJob('DAC 재평가',`증빙 ${slotFilled(SLOTS)}건 · 5대 기준`,['증빙 자료 읽는 중…','기준별 매핑 중…','점수 산출 중…','판단 근거 생성 중…'],()=>{
  analysisPending=0;refreshAll();renderCrit();
  toast('✓ 재평가 완료 · 새 증빙이 반영되었습니다');
 });
}
$('#runBtn').addEventListener('click',runAnalysis);
$('#runBtn2').addEventListener('click',runAnalysis);
$('#indRefresh').addEventListener('click',()=>{
 addJob('지표 실적 갱신','검증수단 증빙 대조 · 달성도 재산정',['실적자료 읽는 중…','달성도 재산정…'],()=>{
  $('#updTime').textContent='업데이트 2026-08-19 (방금)';
  toast('✓ 지표 실적을 갱신했습니다 · 새 증빙 기준으로 재산정됐습니다');
 });
});
$('#aiGen').addEventListener('click',()=>{
 const p=$('#aiPrompt').value.trim();
 addJob('보고서 섹션 생성',`${SECS[activeSec][0]}${p?' · 지시 반영':''}`,['참고문서 수집…','초안 작성 중…','판단 근거 대조…'],()=>{
  if(SECS[activeSec][1]!=='done')SECS[activeSec][1]='draft';
  renderSecs();toast(`✓ '${SECS[activeSec][0]}' 초안이 생성되었습니다 (데모)`);
 });
});
$('#repGenAll').addEventListener('click',()=>{
 addJob('보고서 전체 작성',`27개 섹션 · 전체 문서 분석`,['전체 증빙·PDM 분석…','섹션별 초안 작성…','근거 대조·정리…','목차·표지 구성…'],()=>{
  SECS.forEach(s=>{if(s[1]!=='done')s[1]='draft';});
  renderSecs();toast('✓ 보고서 전체 초안이 완성되었습니다 · 섹션별로 검토합니다');
 });
});

/* ============ 업로드 · 드롭존 ============ */
document.addEventListener('click',e=>{if(e.target.closest('#uploadBtn'))openLayer('spanel');});
function fakeUpload(names){
 toast('업로드 서비스 연결을 확인해 주세요. 서버에 접수되지 않은 파일은 등록된 것으로 표시하지 않습니다.');
}
function wireDrop(el){
 if(!el)return;
 el.addEventListener('click',e=>{if(el.id==='dropzone'&&e.target.closest('.flow'))return;
  if(el.id==='dropzone')openLayer('spanel');
  fakeUpload(['새_증빙자료_'+(FILES.length+1)+'.pdf']);});
 ['dragover','dragenter'].forEach(ev=>el.addEventListener(ev,e=>{e.preventDefault();el.classList.add('drag');}));
 ['dragleave','dragend'].forEach(ev=>el.addEventListener(ev,()=>el.classList.remove('drag')));
 el.addEventListener('drop',e=>{e.preventDefault();el.classList.remove('drag');
  const names=[...((e.dataTransfer&&e.dataTransfer.files)||[])].map(f=>f.name);
  openLayer('spanel');fakeUpload(names.length?names:['새_증빙자료.pdf']);});
}
wireDrop($('#dropzone'));wireDrop($('#spDrop'));

/* ============ 사업정보 퀵드로어 ============ */
$('#projChip').addEventListener('click',()=>{openLayer('drawer');});
$('#projList').innerHTML='<div class="empty">로그인 후 배정된 프로젝트를 불러옵니다.</div>';
$('#langSw').addEventListener('change',async e=>{const select=e.target.closest('select');if(!select)return;
 const previous=LANG;const next=select.value;select.disabled=true;
 try{
  const bundle=await window.prepareLocalizedProjectViews(next);
  await window.KODAME_REQUEST('/api/v2/project/i18n/locale',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({locale:next})});
  LANG=next;applyLang();await window.applyLocalizedProjectViews(bundle);
 }catch(_){LANG=previous;applyLang();toast('대시보드와 사업개요 전체 번역을 완료하지 못해 이전 언어를 유지합니다.');}
 finally{renderLangSw();}
});

/* ============ 역할 · 부팅 ============ */
function applyRole(role){
 CURRENT_ROLE=role;
 $('#roleName').textContent=role;$('#roleAv').textContent=role[0];
 const hint=$('#reportRoleHint');
 const reportAllowed=hasMenuPermission('evaluation_report');
 hint.style.display=reportAllowed?'block':'none';
 hint.textContent='관리자페이지 권한 · 평가보고서를 열람·작성·생성할 수 있습니다.';
 $('#aiGen').disabled=!reportAllowed;
 renderNav();
}
$$('.rolecard').forEach(b=>b.addEventListener('click',()=>{
 applyRole(b.dataset.role);
 $('#gate').style.display='none';$('#app').style.display='grid';
 go(ROUTES[location.hash]?location.hash:'#/dashboard');
 route();
}));
$('#logout').addEventListener('click',()=>{
 document.body.classList.remove('report-mode');
 $('#app').style.display='none';$('#gate').style.display='flex';});

/* Initial service shell: no example-project, score, file or report content. */
$('#trayAv').src=document.querySelector('.daonbox .av').src;
renderCritDefs();renderTray();renderLangSw();renderCrumb();
function reportModuleUnavailable(){
 window.KODAME_MODULE_FAILED=true;
 const message='화면을 불러오지 못했습니다. 새로고침해 주세요. 문제가 계속되면 관리자에게 문의해 주세요.';
 $('#authForm').hidden=true;$('#authStatus').hidden=false;
 $('#authStatusMessage').textContent=message;$('#authRetry').hidden=false;$('#authRetry').onclick=()=>location.reload();
 $('#gate').style.display='flex';$('#app').style.display='none';
}
