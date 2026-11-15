const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../js/serial-protocol.js'), 'utf8');
function extract(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0);
  return source.slice(start, source.indexOf('\n}', start) + 2);
}
let draws = 0, progress = 0, captures = 0;
const state = {history:[{ts:1500,deviceId:'1001',mode:'inference',sampleMs:500,sensorVoltage:[1],featureOrder:[]},
                         {ts:1600,deviceId:'1001',mode:'dataset',sampleMs:7,sensorVoltage:[9],featureOrder:[]}]};
const ctx = vm.createContext({state, Number, String, Array, formatGas:()=>'', pruneHistory(){},
  updateTelemetryCollectionProgress(){progress++;}, drawChart(){draws++;}, drawQcCharts(){},
  maybeCaptureDatasetTelemetry(){captures++;}});
vm.runInContext(extract('parseJsonAfter') + '\n' + extract('replayRunningTelemetry') + '\n' + extract('maybeAppendTelemetry'), ctx);
const record = (ts,sampleMs,mode='inference') => ({receivedMs:ts, line:'GLD_TELEMETRY_JSON '+JSON.stringify({
  deviceId:'1001',mode,telemetry:{valid:true,sampleMs,sensorVoltage:[sampleMs/1000],featureOrder:[]}})});
ctx.replayRunningTelemetry([record(1000,0),record(1400,500),record(2000,1000),record(2100,11,'dataset')]);
assert.deepEqual(Array.from(state.history, p=>p.ts), [1000,1500,1600,2000]);
assert.equal(state.history[2].mode,'dataset','existing dataset history preserved');
assert.equal(draws,1);assert.equal(progress,1);
state.mode='inference';state.info={deviceId:'1001'};
ctx.maybeAppendTelemetry({deviceId:'1001',mode:'inference',telemetry:{valid:true,sampleMs:750,sensorVoltage:[.75]}},1700);
assert.deepEqual(Array.from(state.history, p=>p.ts), [1000,1500,1600,1700,2000]);
ctx.maybeAppendTelemetry({deviceId:'1001',mode:'inference',telemetry:{valid:true,sampleMs:750,sensorVoltage:[.75]}},1750);
assert.equal(captures,1,'duplicate must not run Dataset capture');
console.log('PASS Running replay merges timestamps, deduplicates and leaves Dataset history untouched');
