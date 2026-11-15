const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../js/chart.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '').replace(/^export /gm, '');
const ctx = { state: {}, elements: {}, CHART_COLORS: [], SENSOR_NAMES: [], $() {} };
vm.createContext(ctx);
vm.runInContext(source + '\nglobalThis.display = runningDisplayHistory;', ctx);
const points = [
  { ts: 1000, sensorVoltage: [0, 2], featureOrder: [] },
  { ts: 1500, sensorVoltage: [1, 4], featureOrder: [] },
];
const original = JSON.stringify(points);
const display = ctx.display(points, 1750);
assert.equal(display.length, 2);
assert.equal(display[1].ts, 1250);
assert.equal(display[1].sensorVoltage[0], 0.5);
assert.equal(display[1].sensorVoltage[1], 3);
assert.equal(JSON.stringify(points), original, 'raw history is unchanged');
assert.equal(ctx.display(points, 1400).length, 0);
assert.equal(ctx.display(points, 2500).at(-1).ts, 1500);
const gap = [points[0], { ...points[1], ts: 3000 }];
assert.equal(ctx.display(gap, 2500).length, 1, 'do not interpolate a long gap');
ctx.state = { history: gap, polling: false, hiddenSensorChartChannels: new Set() };
ctx.elements = { sensorChart: {}, rangeSelect: {}, legend: {} };
ctx.$ = () => null;
vm.runInContext('drawOneChart = (...args) => { globalThis.rendered = args[5]; }; drawRunningChart();', ctx);
assert.equal(ctx.rendered.gaps.length, 1);
assert.equal(ctx.rendered.gaps[0].start, 1000);
assert.equal(ctx.rendered.gaps[0].end, 3000);
assert.equal(ctx.rendered.history[1].breakBefore, true);
assert.equal(gap[1].breakBefore, undefined, 'gap marker must not alter stored data');
console.log('Running display interpolation: PASS');
