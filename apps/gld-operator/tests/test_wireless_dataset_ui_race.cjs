// Exercise real UI async code with a DOM stub; no network, COM or browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

(async () => {
  const dir = path.join(__dirname, '../js');
  const modelCode = fs.readFileSync(path.join(dir, 'wireless-dataset-model.js'), 'utf8');
  const model = await import(`data:text/javascript;base64,${Buffer.from(modelCode).toString('base64')}`);
  const elements = new Map();
  const element = () => ({ value: '', dataset: {}, style: {}, children: [], clientWidth: 0, clientHeight: 0,
    replaceChildren() { this.children = []; }, append(...children) { this.children.push(...children); }, addEventListener() {} });
  let resolveOldState;
  const oldRequest = new Promise((resolve) => { resolveOldState = resolve; });
  const ctx = {
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); }, createElement: element },
    legacyState: Object.freeze({ bridgeAvailable: true }), CHART_COLORS: Array(8).fill('#aaa'),
    bridgeFetch: async (route) => route.endsWith('/state') ? oldRequest : { session_id: 'new', state: 'recording', count: 0, history: [] },
    ...model,
  };
  vm.createContext(ctx);
  const source = fs.readFileSync(path.join(dir, 'wireless-dataset.js'), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replace(/^export /gm, '');
  vm.runInContext(source + '\nglobalThis.control = { sync, action, get: () => snapshot };', ctx);
  const sync = ctx.control.sync();
  await ctx.control.action('start', { label: 'test', interval_ms: 500 });
  assert.equal(ctx.control.get().session_id, 'new');
  resolveOldState({ session_id: 'old', state: 'complete', history: [] });
  await sync;
  assert.equal(ctx.control.get().session_id, 'new', 'late pre-Start snapshot must never roll the UI back to old session');
  ctx.bridgeFetch = async () => { throw Error('temporary network transition'); };
  await ctx.control.sync();
  assert.match(elements.get('wirelessMessage').textContent, /Status wireless belum tersedia/);
  ctx.bridgeFetch = async () => ({ session_id: 'new', state: 'disconnected', complete: true, filename: 'real.csv', count: 29, history: [] });
  await ctx.control.sync();
  assert.doesNotMatch(elements.get('wirelessMessage').textContent, /Status wireless belum tersedia/);
  assert.match(elements.get('wirelessState').textContent, /sesi lengkap/);
  ctx.bridgeFetch = async (route) => {
    if (!route.endsWith('/state')) throw Error('Start rejected by device');
    return { session_id: 'new', state: 'disconnected', complete: true, filename: 'real.csv', count: 29, history: [] };
  };
  await ctx.control.action('start');
  assert.equal(elements.get('wirelessMessage').textContent, 'Start rejected by device', 'successful status recovery must preserve action errors');
  console.log('PASS: delayed /state cannot overwrite the new Start session; legacy state stays read-only');
  console.log('PASS: transient status error clears after recovery; completion is visible and action errors remain');
})().catch((error) => { console.error(error); process.exitCode = 1; });
