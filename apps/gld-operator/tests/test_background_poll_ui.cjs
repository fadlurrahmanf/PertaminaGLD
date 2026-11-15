const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../js/serial-protocol.js'),'utf8');
function get(name){const start=source.indexOf(`function ${name}(`);assert(start>=0);return source.slice(start,source.indexOf('\n}',start)+2)}
let statusResolve, calls=[], timers=0; const logs=[];
const ctx=vm.createContext({state:{connected:true,mock:false,bridgeAvailable:true,activeSlot:2,polling:false,mode:'inference'},
  newBackgroundPollOwner:()=> 'owner-session-123456', backgroundPollSession:null, pollingGeneration:0,
  pollIntervalMs:()=>500,setPollButtonLabel(){},saveUiSession(){},telemetryPollCommand:()=> 'GET_TELEMETRY',
  appendLog:s=>logs.push(s),showBanner(){},setInterval(){timers++;return 1},clearInterval(){},
  bridgeFetch:(url,opts)=>{calls.push([url,opts?.body && JSON.parse(opts.body),opts?.keepalive]);
    if(url.includes('/status'))return new Promise(resolve=>statusResolve=resolve);
    return Promise.resolve({ok:true});}});
vm.runInContext(get('togglePolling')+'\n'+get('stopPolling'),ctx);
(async()=>{
  ctx.togglePolling();assert.equal(ctx.state.polling,true);assert.equal(timers,0);assert.match(calls[0][0],/slot=2/);
  const stopping=ctx.stopPolling();assert.equal(ctx.state.polling,false);await stopping;
  assert.match(calls[1][0],/\/stop$/);assert.equal(calls[1][1].slot,2);assert.equal(calls[1][2],true);
  statusResolve({connected:true,telemetryStream:'stream-1'});await Promise.resolve();await Promise.resolve();
  assert.match(calls[2][0],/\/start$/);assert.equal(calls[2][1].stream,'stream-1');assert.equal(calls[2][1].slot,2);
  assert.deepEqual(logs,[]);
  const buttons=[{textContent:''}];ctx.document={querySelectorAll:()=>buttons};
  ctx.state.polling=true;ctx.backgroundPollSession={slot:2,owner:'owner-session-123456'};
  ctx.bridgeFetch=async()=>{throw new Error('unresolved')};
  assert.equal(await ctx.stopPolling(),false);assert.equal(ctx.state.polling,true);
  assert.equal(ctx.backgroundPollSession.slot,2);assert.match(buttons[0].textContent,/belum pasti/);
  console.log('PASS delayed start, connection identity and uncertain stop ownership');
})().catch(e=>{console.error(e);process.exitCode=1});
