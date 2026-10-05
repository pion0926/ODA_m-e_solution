import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { parse, validateHwpx, hwpxToProfile, openHwpxDocument, renderHwpxToSvg } from 'kordoc';

test('report template supports every API used by the validation service', async () => {
  const bytes = await fs.readFile(new URL('../../samples/5-1. 종료평가 결과보고서 placeholder.hwpx', import.meta.url));
  const validation = await validateHwpx(bytes);
  assert.ok(validation);
  const parsed = await parse(bytes);
  assert.equal(parsed.success, true);
  assert.ok(parsed.markdown.length > 100);
  const profile = await hwpxToProfile(bytes);
  assert.ok(profile.tables.length > 0);
  const session = await openHwpxDocument(bytes);
  assert.ok(session.blocks.length > 0);
  assert.ok(Array.isArray(session.capabilities()));
  const rendered = await renderHwpxToSvg(bytes, { reflow: true, reflowMode: 'keep' });
  assert.ok(rendered.pageCount > 1);
  assert.match(rendered.svg, /<g\s+data-page="\d+"/);
  assert.match(rendered.svg, /<text\b/);
});
