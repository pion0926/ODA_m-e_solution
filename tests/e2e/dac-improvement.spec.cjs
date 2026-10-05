const {test, expect} = require('@playwright/test');

test('criterion tips disclose long evidence safely and link back to the workflow', async ({page}) => {
  await page.route('**/api/**',route=>route.fulfill({status:401,body:'{}'}));
  await page.goto('/');
  await page.evaluate(() => {document.body.innerHTML='<main id="tips"></main>';});
  await page.addScriptTag({url:'/assets/dac-scoring-ui.js'});
  await page.evaluate(() => {
    const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
    document.querySelector('#tips').innerHTML = DacScoringUI.renderImprovements({name:'지속가능성',improvement_guidance:{
      is_stale:true,notice:'보완 후 DAC 평가를 직접 실행해야 점수에 반영됩니다.',items:[
        {kind:'evidence',title:'농가 관개용수 공급 지속성',question:'시설 운영과 지역사회의 장기적인 편익이 지속되는가? '.repeat(8),
          reason:'현재 자료에서 유지관리 예산을 확인하지 못했습니다.',
          action:'예산서와 운영실적을 연결하세요.',required_evidence:'장기운영계획'.repeat(180)+'<img src=x onerror=alert(1)>'}]
    }},esc);
  });
  await expect(page.getByRole('heading',{name:'평가점수 개선 팁'})).toBeVisible();
  await expect(page.getByRole('status')).toContainText('이전 평가 기준');
  await expect(page.getByText('예산서와 운영실적을 연결하세요.',{exact:false})).toBeHidden();
  await page.getByText('증빙 보완 1건',{exact:true}).click();
  await expect(page.getByText('예산서와 운영실적을 연결하세요.',{exact:false})).toBeVisible();
  await expect(page.locator('#tips img')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});
  expect(await page.locator('.dac-improvements .meta2').evaluate(el=>getComputedStyle(el).whiteSpace)).toBe('normal');
  expect(await page.locator('#tips').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await expect(page.getByRole('link',{name:'자료 등록·연결 확인'})).toHaveAttribute('href','#/evidence');
  await expect(page.getByRole('link',{name:'DAC 평가 계획 확인'})).toHaveAttribute('href','#/eval/board');
});
