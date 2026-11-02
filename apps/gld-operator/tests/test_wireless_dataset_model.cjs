// Host-only UI session/history contract; never opens a browser, COM or device.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const code = fs.readFileSync(path.join(__dirname, '../js/wireless-dataset-model.js'), 'utf8');
  const { applyWirelessEvent, mergeWirelessSnapshot, validWirelessSample, WIRELESS_SENSOR_NAMES, WIRELESS_HISTORY_LIMIT } =
    await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const sample = (seq, session = 'session-a') => ({
    session_id: session, seq, timestamp_ms: seq * 500,
    sensor_voltage: Array.from({ length: 8 }, (_, i) => i / 10), feature_order: WIRELESS_SENSOR_NAMES,
  });
  let view = { session_id: 'session-a', history: [], count: 0 };
  view = applyWirelessEvent(view, { type: 'sample', sample: sample(0), count: 1 });
  assert.equal(view.history.length, 1, 'first seq=0 must reach chart history');
  assert.equal(view.history[0].sensor_voltage.length, 8);
  assert.equal(view.count, 1);
  view = applyWirelessEvent(view, { type: 'sample', sample: sample(0), count: 1 });
  assert.equal(view.history.length, 1, 'duplicate SSE must not duplicate chart points');
  view = applyWirelessEvent(view, { type: 'sample', sample: sample(1, 'old-session'), count: 99 });
  assert.equal(view.count, 1, 'old sessions cannot change the current count');
  assert(!validWirelessSample({ ...sample(1), sensor_voltage: [1] }, 'session-a'));
  assert(!validWirelessSample({ ...sample(1), sensor_voltage: Array(8).fill(NaN) }, 'session-a'));
  assert(!validWirelessSample({ ...sample(1), feature_order: [...WIRELESS_SENSOR_NAMES].reverse() }, 'session-a'));
  view = mergeWirelessSnapshot(view, { session_id: 'session-a', history: [sample(2), sample(1), sample(0)] });
  assert.deepEqual(view.history.map((r) => r.seq), [0, 1, 2], 'reload snapshot repairs missed SSE events');
  view = applyWirelessEvent(view, { type: 'state', session_id: 'session-b', state: 'starting', count: 0 });
  assert.equal(view.history.length, 0, 'new sessions reset chart independently');
  view = mergeWirelessSnapshot(view, { session_id: 'session-b', history: Array.from({ length: WIRELESS_HISTORY_LIMIT + 3 }, (_, i) => sample(i, 'session-b')) });
  assert.equal(view.history.length, WIRELESS_HISTORY_LIMIT, 'UI retention is bounded');
  assert.equal(view.history[0].seq, 3);
  const legacyDataset = fs.readFileSync(path.join(__dirname, '../js/dataset.js'), 'utf8');
  assert(legacyDataset.includes('publishDatasetCommand'));
  assert(!code.includes('state.history'), 'wireless model must not mutate the COM chart state');
  console.log('PASS: wireless UI session/history, eight channels, duplicate/stale/malformed records, snapshot recovery and bounded retention');
})().catch((error) => { console.error(error); process.exitCode = 1; });
