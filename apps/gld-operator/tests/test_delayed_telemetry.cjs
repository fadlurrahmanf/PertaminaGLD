const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../js/bridge-client.js'),'utf8');
function get(name){const start=src.indexOf(`function ${name}(`);assert(start>=0);return src.slice(start,src.indexOf('\n}',start)+2)}
const recovered=[],live=[],timers=[];class FakeDate extends Date{static now(){return 10000}}
const ctx=vm.createContext({telemetryCursors:new Map(),delayedTelemetry:new Map(),state:{activeSlot:1,mock:false},Date:FakeDate,
 window:{setTimeout:f=>timers.push(f)},replayRunningTelemetry:r=>recovered.push(...r),handleLine:(...x)=>live.push(x),
 updateFleetFromLine(){},appendLog(){},bridgeFetch:async()=>{throw Error('unexpected')}});
for(const name of ['telemetryCursor','adoptTelemetryStream','flushDelayedTelemetry','stageDelayedTelemetry','isRunningTelemetryLine','queueTelemetryLine'])vm.runInContext(get(name),ctx);
(async()=>{
 const line='GLD_TELEMETRY_JSON '+JSON.stringify({mode:'inference',telemetry:{valid:true}});
 ctx.queueTelemetryLine(1,{telemetryStream:'s',telemetrySequence:1,receivedMs:1000,line});
 await ctx.telemetryCursor(1).chain;assert.equal(live.length,0);assert.equal(timers.length,1);timers[0]();
 assert.equal(recovered.length,1);assert.equal(recovered[0].receivedMs,1000);
 console.log('PASS delayed Running data goes to batched replay without live side effects');
})().catch(e=>{console.error(e);process.exitCode=1});
