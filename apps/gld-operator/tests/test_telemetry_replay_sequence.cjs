const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../js/bridge-client.js'),'utf8');
function get(name){const start=source.indexOf(`function ${name}(`);assert(start>=0);const offset=source.slice(0,start).endsWith('async ')?start-6:start;return source.slice(offset,source.indexOf('\n}',start)+2);}
const replayed=[], live=[], logs=[];let replies=[];
const ctx=vm.createContext({telemetryCursors:new Map(),state:{activeSlot:1,mock:false},
  bridgeFetch:async()=>{assert(replies.length);return replies.shift()},
  replayRunningTelemetry:samples=>replayed.push(...samples),handleLine:(line,ts)=>live.push([line,ts]),
  updateFleetFromLine(){},flushDelayedTelemetry(){},stageDelayedTelemetry(){},isRunningTelemetryLine:()=>false,
  appendLog:msg=>logs.push(msg)});
for(const name of ['telemetryCursor','adoptTelemetryStream','recoverTelemetry','queueTelemetryRecovery','queueTelemetryLine'])vm.runInContext(get(name),ctx);
(async()=>{
  replies.push({stream:'s1',sequence:1,samples:[{sequence:1,receivedMs:1000,line:'first'}]});
  ctx.queueTelemetryRecovery(1);
  ctx.queueTelemetryLine(1,{telemetryStream:'s1',telemetrySequence:2,receivedMs:1500,line:'second'});
  await ctx.telemetryCursor(1).chain;
  assert.equal(replayed.length,1);assert.deepEqual(live,[['second',1500]]);
  replies.push({stream:'s1',sequence:4,samples:[{sequence:3,receivedMs:2000,line:'third'},{sequence:4,receivedMs:2500,line:'fourth'}]});
  ctx.queueTelemetryLine(1,{telemetryStream:'s1',telemetrySequence:4,receivedMs:2500,line:'fourth'});
  await ctx.telemetryCursor(1).chain;
  assert.equal(replayed.length,3);assert.equal(live.length,1,'replayed event must not be applied twice');
  assert.equal(ctx.telemetryCursor(1).sequence,4);assert.deepEqual(logs,[]);
  ctx.queueTelemetryLine(1,{telemetryStream:'s2',telemetrySequence:1,receivedMs:3000,line:'new'});
  ctx.queueTelemetryLine(1,{telemetryStream:'s1',telemetrySequence:5,receivedMs:3100,line:'stale'});
  await ctx.telemetryCursor(1).chain;
  assert.deepEqual(live.at(-1),['new',3000]);assert.equal(ctx.telemetryCursor(1).stream,'s2');
  console.log('PASS replay/live sequencing and missing-event recovery');
})().catch(e=>{console.error(e);process.exitCode=1});
