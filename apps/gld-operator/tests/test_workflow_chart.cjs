// Exercise the actual shared renderer with inert canvas/DOM objects. No browser,
// network, device, or legacy telemetry state is modified by this test.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const NOW = 1_800_000_000_000;
const COLORS = ['#ffa400', '#4fd8e0', '#ff8a3d', '#8fd6ff', '#bc9cff', '#ffd166', '#77d28a', '#ff6b6b'];
const NAMES = ['MQ8', 'MQ135', 'MQ3', 'MQ5', 'MQ4', 'MQ7', 'MQ6', 'MQ2'];
// Captured from the pre-extension Running renderer with the fixture below.
// A workflow source must not alter default Running grid, typography, axes,
// line paths, labels, colors, sizing, or the selected range.
const EXPECTED_RUNNING_DRAW_SHA = '1fa2444e79decbdc5d20b6863b673784ab098777bea12e6793460e1e34497cac';

function element() {
  return { children: [], style: {}, _html: '',
    set innerHTML(value) { this._html = value; this.children = []; },
    get innerHTML() { return this._html; },
    append(...values) { this.children.push(...values); },
    appendChild(value) { this.children.push(value); },
  };
}

function canvas() {
  const commands = [];
  let current = [], dash = [];
  const ctx = { fillStyle: '', strokeStyle: '', lineWidth: 1, font: '', textAlign: 'start', textBaseline: 'alphabetic',
    setTransform(...args) { commands.push(['setTransform', ...args]); },
    clearRect(...args) { commands.push(['clearRect', ...args]); },
    fillRect(...args) { commands.push(['fillRect', this.fillStyle, ...args]); },
    strokeRect(...args) { commands.push(['strokeRect', this.strokeStyle, this.lineWidth, ...args]); },
    beginPath() { current = []; },
    moveTo(...args) { current.push(['moveTo', ...args]); },
    lineTo(...args) { current.push(['lineTo', ...args]); },
    setLineDash(values) { dash = [...values]; },
    stroke() { commands.push(['stroke', this.strokeStyle, this.lineWidth, [...dash], current.map(p => [...p])]); },
    fillText(...args) { commands.push(['fillText', this.fillStyle, this.font, this.textAlign, this.textBaseline, ...args]); },
  };
  const value = { parentElement: { clientWidth: 1000 }, width: 0, height: 0, style: {}, getContext(type) { assert.equal(type, '2d'); return ctx; } };
  return { value, commands };
}

function point(ts, delta = 0, extra = {}) {
  return { ts, sensorVoltage: NAMES.map((_, i) => (i + 1) / 10 + delta), featureOrder: [...NAMES], ...extra };
}
const fixture = [point(NOW - 1000), point(NOW - 500, 0.01), point(NOW, 0.02)];

function harness(history, sourceOverride = null) {
  const fields = new Map([
    ['chartYAxisFixed', { checked: false }], ['chartYAxisMin', { value: '0' }], ['chartYAxisMax', { value: '2.5' }],
  ]);
  const state = { history, hiddenSensorChartChannels: new Set([2]), dataset: {} };
  // This clock exists solely inside the VM; global Date and all product state
  // outside this module remain untouched.
  class FixtureDate extends Date { static now() { return NOW; } }
  const context = { state, CHART_COLORS: COLORS, SENSOR_NAMES: NAMES, elements: {},
    $: id => fields.get(id), Date: FixtureDate,
    document: { createElement: element, createTextNode: text => ({ textContent: text }) },
    window: { devicePixelRatio: 1, innerHeight: 900 },
  };
  vm.createContext(context);
  const source = (sourceOverride ?? fs.readFileSync(path.join(__dirname, '../js/chart.js'), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '').replace(/^export /gm, '');
  vm.runInContext(source + '\nglobalThis.renderer={drawOneChart};', context);
  const draw = (dataSource, channels = null) => {
    const chart = canvas(), legend = element();
    context.renderer.drawOneChart(chart.value, { value: '60' }, legend, [], channels, dataSource);
    return { commands: chart.commands, width: chart.value.width, height: chart.value.height,
      style: chart.value.style, legend: legend.children.map(item => ({
        label: item.children[1].textContent, color: item.children[0].style.background,
      })) };
  };
  return { state, context, source, draw };
}
const digest = result => crypto.createHash('sha256').update(JSON.stringify(result)).digest('hex');
const series = result => result.commands.filter(c => c[0] === 'stroke' && c[2] === 1.8);

const globalClock = Date.now;
const old = harness(structuredClone(fixture));
const originalState = JSON.stringify(old.state.history), originalHidden = [...old.state.hiddenSensorChartChannels];
const running = old.draw();

if (process.argv.includes('--capture-baseline')) {
  const originalSource = require('node:child_process').execFileSync('git', ['show', 'HEAD:apps/gld-operator/js/chart.js'], {
    cwd: path.join(__dirname, '../../..'), encoding: 'utf8', windowsHide: true,
  });
  const baseline = harness(structuredClone(fixture), originalSource);
  assert(!/function drawOneChart\([^\n]*dataSource/.test(baseline.source), 'Capture only the original five-argument renderer');
  console.log(digest(baseline.draw()));
  process.exit(0);
}

assert.equal(digest(running), EXPECTED_RUNNING_DRAW_SHA, 'default Running rendering must preserve the pre-extension baseline');
const explicit = old.draw({ history: structuredClone(fixture), now: NOW });
assert.deepEqual(explicit, running, 'identical feed/time must draw Running and workflow pixel commands identically');
assert.equal(explicit.width, 1000); assert.equal(explicit.height, 735);
assert(explicit.commands.some(c => c[0] === 'fillRect' && c[1] === '#14110d'), 'same Running chart background');
assert(explicit.commands.some(c => c[0] === 'strokeRect' && c[1] === '#35301f'), 'same enclosing grid');
assert(explicit.commands.some(c => c[0] === 'stroke' && c[1] === '#f3c969' && c[3].join(',') === '7,5'), 'same zero-voltage axis');
assert.deepEqual(series(explicit).map(c => c[1]), COLORS, 'all eight sensor traces use Running colors');
assert.equal(explicit.legend.length, 8);
const compact = old.draw({ history: structuredClone(fixture), now: NOW, height: 340 });
assert.equal(compact.height,340,'workflow may request a compact chart');assert.equal(series(compact).length,8);
assert.equal(old.draw().height,735,'compact workflow chart must not change default Running height');
assert.equal(old.draw({history:fixture,now:NOW,height:1}).height,240,'explicit height has a readable floor');
assert.equal(old.draw({history:fixture,now:NOW,height:NaN}).height,735,'invalid size retains Running default');
for (const name of NAMES) assert(explicit.commands.some(c => c[0] === 'fillText' && c[5] === name), `right-edge label ${name}`);

const otherFeed = [point(NOW - 1000, 30), point(NOW - 500, 35), point(NOW, 40)];
const isolated = old.draw({ history: otherFeed, now: NOW });
assert.notDeepEqual(series(isolated), series(running), 'workflow must draw its own feed rather than the global Running history');
const isolatedHarness = harness([point(NOW, -200)]);
assert.deepEqual(isolatedHarness.draw({ history: otherFeed, now: NOW }), isolated, 'unrelated Running telemetry must not affect workflow scaling/path');

const gapFeed = structuredClone(fixture); gapFeed[1].breakBefore = true;
const broken = old.draw({ history: gapFeed, now: NOW });
for (const stroke of series(broken)) {
  assert.deepEqual(stroke[4].map(p => p[0]), ['moveTo', 'moveTo', 'lineTo'], 'Pause/session boundary starts a separate path, without a synthetic connecting line');
}
const stale = old.draw({ history: [point(NOW - 61_000)], now: NOW });
assert.equal(series(stale).length, 0, 'own-feed range must use the supplied clock');
assert(stale.commands.some(c => c[0] === 'fillText' && c[5] === 'Waiting for telemetry'));
const shiftedNow = NOW + 120_000;
const shifted = old.draw({ history: [point(shiftedNow)], now: shiftedNow });
assert.equal(series(shifted)[0][4][0][1], 942, 'own clock anchors the latest sample to the right plot edge, without changing global Date');
assert.equal(JSON.stringify(old.state.history), originalState, 'workflow must not replace, prune, or append global Running telemetry');
assert.deepEqual([...old.state.hiddenSensorChartChannels], originalHidden, 'workflow must not mutate Running visibility settings');
assert.equal(Date.now, globalClock, 'shared renderer must not replace the global clock');
console.log('PASS shared chart preserves Running baseline; workflow isolates feed/time, eight traces and Pause/session gaps');
