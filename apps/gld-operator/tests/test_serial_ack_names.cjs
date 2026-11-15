const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../js/serial-protocol.js'),'utf8');
function get(name){const i=src.indexOf(`function ${name}(`);return src.slice(i,src.indexOf('\n}',i)+2)}
const ctx=vm.createContext({});vm.runInContext(get('serialCommandName')+'\n'+get('expectedResponses'),ctx);
assert.deepEqual(Array.from(ctx.expectedResponses('SET_SENSOR_POWER_JSON {}')),['ack:SET_SENSOR_POWER']);
assert.deepEqual(Array.from(ctx.expectedResponses('GET_TELEMETRY')),['telemetry']);
assert.deepEqual(Array.from(ctx.expectedResponses('RUN_CURRENT_STATE_CHECK')),['current-state-done']);
console.log('PASS JSON serial commands match firmware ACK names');
