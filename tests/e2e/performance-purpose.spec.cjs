const {test,expect}=require('@playwright/test');

test('performance review explains evidence purpose and preserves explicit additions',async({page})=>{
  await page.route('**/api/**',r=>r.fulfill({status:401,body:'{}'}));
  await page.goto('/');
  await page.addScriptTag({url:'/assets/performance-analysis-review.js'});
  await page.evaluate(()=>{
    const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
    window.submitted=null;
    window.purposeReview=PerformanceAnalysisReview.create({escapeHtml:esc,refreshIntake:async()=>{},notify:()=>{},
      request:async()=>({ready:true,revision:'r',source_document_id:'p',source_file_name:'합성 PDM',message:'직접 증빙 확인',
        documents:[{id:'a',file_name:'개별 훈련 결과',status:'completed'},{id:'b',file_name:'인터뷰 기록',status:'completed'}],
        indicators:[{id:'i',text:'합동훈련 횟수',mov:'실시 기록',tier_name:'산출물',document_ids:['a'],retained_document_ids:[],analyzed_document_ids:[],
          mapping_details:{a:{proves:'해당 기관 합동훈련의 실제 실시',limitations:'동일 행사 문서는 중복 집계 제외 <img src=x>'}}}]}),
      start:async review=>{window.submitted=review;return {id:'job'};}});
    return window.purposeReview.open();
  });
  await expect(page.getByText('해당 기관 합동훈련의 실제 실시',{exact:true})).toBeVisible();
  await expect(page.locator('#performanceReviewDialog img')).toHaveCount(0);
  await page.locator('#performanceReviewDialog select').selectOption('b');
  await page.getByRole('button',{name:'매핑 추가',exact:true}).click();
  await page.getByRole('button',{name:'분석 실행',exact:true}).click();
  expect(await page.evaluate(()=>window.submitted.mappings.i)).toEqual(['a','b']);
});
