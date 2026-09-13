/* Offline state/performance regression; never calls an API or an LLM. */
const assert = require('node:assert/strict');
const { performance } = require('node:perf_hooks');
const { createFlow } = require('../../assets/report-section-flow.js');
let now = 0;
const flow = createFlow(() => now);
flow.select('a');
const oldRead = flow.beginRead('a');
flow.select('b');
assert.equal(flow.isCurrent('a', oldRead), false, 'late section A response must not overwrite B');
const read1 = flow.beginRead('b');
const read2 = flow.beginRead('b');
assert.equal(flow.isCurrent('b', read1), false, 'older polling response must be ignored');
assert.equal(flow.isCurrent('b', read2), true);
flow.edit('b', 'local draft');
assert.equal(flow.content('b', 'server old'), 'local draft', 'polling must preserve unsaved edits');
assert.equal(flow.begin('b'), true);
assert.equal(flow.isCurrent('b', read2), false, 'pre-submit GET must not overwrite accepted operation');
assert.equal(flow.begin('b'), false, 'double click must be rejected synchronously');
flow.observe({ part_id: 'b', status: 'draft' });
assert.equal(flow.busy('b'), true, 'pre-acceptance GET cannot clear submit lock');
now = 125;
flow.accepted('b');
assert.equal(flow.begin('b'), false, 'accepted operation must stay locked');
flow.observe({ part_id: 'b', status: 'generating' });
now = 9125;
flow.observe({ part_id: 'b', status: 'draft', content: 'generated' });
assert.equal(flow.busy('b'), false);
assert.equal(flow.content('b', 'generated'), 'generated');
assert.equal(flow.state('b').acceptedMs, 125);
assert.equal(flow.state('b').elapsedMs, 9125);
flow.edit('b', 'must survive');
flow.begin('b');
flow.accepted('b');
flow.observe({ part_id: 'b', status: 'failed', error_message: 'provider unavailable' });
assert.equal(flow.content('b', 'server'), 'must survive', 'failed generation must preserve draft');
flow.begin('b');
flow.rejected('b', 'timeout', true);
assert.equal(flow.begin('b'), false, 'unknown acceptance must not trigger blind duplicate retry');
flow.observe({ part_id: 'b', status: 'generating' });
assert.equal(flow.busy('b'), true);
flow.observe({ part_id: 'b', status: 'draft' });
flow.edit('b', 'saved');
flow.edit('b', 'newer typing');
flow.saved('b', 'saved');
assert.equal(flow.content('b', ''), 'newer typing', 'save response must not erase later typing');
flow.saved('b', 'newer typing');
assert.equal(flow.hasDraft('b'), false);
const timings = [];
for (let repeat = 0; repeat < 50; repeat++) {
  const sample = createFlow();
  const start = performance.now();
  for (let i = 0; i < 10000; i++) {
    const id = `section-${i % 27}`;
    sample.select(id);
    const token = sample.beginRead(id);
    sample.isCurrent(id, token);
    sample.observe({ part_id: id, status: 'draft' });
    sample.edit(id, '검증용 본문 '.repeat(100));
    sample.content(id, '');
    sample.saved(id, '검증용 본문 '.repeat(100));
  }
  timings.push(performance.now() - start);
}
timings.sort((a, b) => a - b);
const p95 = timings[Math.floor(timings.length * .95)];
assert.ok(p95 < 500, `10,000 state transitions p95 must remain <500ms; actual ${p95.toFixed(2)}`);
console.log(JSON.stringify({ status: 'PASS', scenarios: 12, cyclesPerSample: 10000, samples: 50,
  stateCycleMedianMs: timings[25], stateCycleP95Ms: p95, scope: 'local state machine; excludes network, DOM and LLM latency' }, null, 2));
