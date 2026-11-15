// Isolated browser/bridge integration. Uses a fake serial device and a fresh
// temporary Chrome profile; does not connect to a physical board or live hub.
const {spawn}=require('node:child_process');const fs=require('node:fs');const os=require('node:os');
const path=require('node:path');const assert=require('node:assert/strict');
const py=process.env.GLD_TEST_PYTHON || 'D:/Github/PertaminaGLD/apps/gld-operator/python-embed/python.exe';
const chrome=process.env.GLD_TEST_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const fixture=path.join(__dirname,'browser_poll_fixture.py');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'gld-browser-poll-'));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
function line(child){return new Promise((resolve,reject)=>{let text='';const t=setTimeout(()=>reject(Error('fixture startup timeout')),15000);
 child.stdout.on('data',buf=>{text+=buf;const m=/^(\d+)\s*$/m.exec(text);if(m){clearTimeout(t);resolve(Number(m[1]));}});
 child.once('exit',code=>{clearTimeout(t);reject(Error('fixture exited '+code))});});}
class CDP{constructor(ws){this.ws=ws;this.id=0;this.waiters=new Map();ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&this.waiters.has(m.id)){const p=this.waiters.get(m.id);this.waiters.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}})}
 send(method,params={}){const id=++this.id;return new Promise((resolve,reject)=>{this.waiters.set(id,{resolve,reject});this.ws.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(this.waiters.delete(id))reject(Error(method+' timeout'))},10000)})}}
async function evaluate(cdp,expression){for(let attempt=0;attempt<40;attempt++){try{const r=await cdp.send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}catch(e){if(!/execution context/i.test(e.message)||attempt===39)throw e;await wait(100)}}}
(async()=>{let server,browser,socket,cdp;try{
 server=spawn(py,[fixture],{windowsHide:true,stdio:['ignore','pipe','pipe']});const port=await line(server);
 browser=spawn(chrome,['--headless=new','--disable-gpu','--disable-background-networking','--disable-component-update','--disable-extensions','--disable-sync','--no-proxy-server','--no-first-run','--no-default-browser-check',`--user-data-dir=${profile}`,'--remote-debugging-port=0',`http://127.0.0.1:${port}/`],{windowsHide:true,stdio:'ignore'});
 let debugPort;for(let i=0;i<150;i++){try{debugPort=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);break}catch{await wait(100)}}
 if(!debugPort)throw Error('Chrome debug startup timeout');
 let target;for(let i=0;i<100;i++){const items=await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();target=items.find(x=>x.type==='page'&&x.url.includes(`:${port}/`));if(target)break;await wait(100)}
 if(!target)throw Error('test page not found');socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});cdp=new CDP(socket);
 await cdp.send('Runtime.enable');
 let ready=false;for(let i=0;i<100;i++){ready=await evaluate(cdp,"(async()=>{try{let {state}=await import('/js/state.js');return !!state.bridgeAvailable && !!state.eventSource}catch{return false}})()");if(ready)break;await wait(100)}
 if(!ready)throw Error('bridge UI did not initialize');
 await evaluate(cdp,"(async()=>{let {state}=await import('/js/state.js'); state.connected=true;state.bridgeAvailable=true;state.mode='inference';state.info={deviceId:'1001',capabilities:{lightweightTelemetry:'GET_TELEMETRY'}};let p=await import('/js/serial-protocol.js');if(!state.polling)p.togglePolling();})()");
 let before;for(let i=0;i<80;i++){before=await evaluate(cdp,"(async()=>{let {state}=await import('/js/state.js');return {count:state.history.length,polling:state.polling}})()");if(before.count>=2)break;await wait(100)}
 assert(before.count>=2 && before.polling,'initial polling must produce samples');
 const w=await cdp.send('Browser.getWindowForTarget');const minimizedAt=Date.now();await cdp.send('Browser.setWindowBounds',{windowId:w.windowId,bounds:{windowState:'minimized'}});await wait(250);
 const visibility=await evaluate(cdp,'document.visibilityState');
 if(visibility!=='hidden')throw Error('headless Chrome did not report hidden after minimize; cannot claim minimize validation');
 await wait(2500);const restoredAt=Date.now();await cdp.send('Browser.setWindowBounds',{windowId:w.windowId,bounds:{windowState:'normal'}});await wait(1800);
 const after=await evaluate(cdp,"(async()=>{let {state}=await import('/js/state.js');return {count:state.history.length,polling:state.polling,times:state.history.map(x=>x.ts)}})()");
 assert(after.polling,'polling remains enabled');assert(after.count>=before.count+3,`history did not continue: ${before.count} -> ${after.count}`);
 assert(after.times.every((t,i,a)=>i===0||t>=a[i-1]),'history remains chronological');
 assert(after.times.filter(t=>t>=minimizedAt&&t<=restoredAt).length>=3,'must collect samples during the actual minimized interval');
 const frozenAt=Date.now();await cdp.send('Browser.setWindowBounds',{windowId:w.windowId,bounds:{windowState:'minimized'}});await wait(200);
 await cdp.send('Page.setWebLifecycleState',{state:'frozen'});await wait(2500);
 const thawedAt=Date.now();await cdp.send('Page.setWebLifecycleState',{state:'active'});
 await cdp.send('Browser.setWindowBounds',{windowId:w.windowId,bounds:{windowState:'normal'}});await wait(1800);
 const thawed=await evaluate(cdp,"(async()=>{let {state}=await import('/js/state.js');return {count:state.history.length,times:state.history.map(x=>x.ts)}})()");
 assert(thawed.times.filter(t=>t>=frozenAt&&t<=thawedAt).length>=3,'must recover samples collected while page execution is frozen');
 assert(thawed.times.every((t,i,a)=>i===0||t>=a[i-1]),'recovered history remains chronological');
 await evaluate(cdp,"(async()=>{let p=await import('/js/serial-protocol.js');await p.stopPolling()})()");
 const stopped=await evaluate(cdp,"(async()=>{let b=await import('/js/bridge-client.js');return (await b.bridgeFetch('/api/serial/telemetry-replay?slot=1&after=0')).sequence})()");
 await wait(800);
 const stillStopped=await evaluate(cdp,"(async()=>{let b=await import('/js/bridge-client.js');return (await b.bridgeFetch('/api/serial/telemetry-replay?slot=1&after=0')).sequence})()");
 assert.equal(stillStopped,stopped,'Stop Poll must stop bridge acquisition');
 await evaluate(cdp,"(async()=>{let p=await import('/js/serial-protocol.js');p.togglePolling()})()");await wait(700);
 const health=await (await fetch(`http://127.0.0.1:${port}/api/health`)).json();
 await cdp.send('Page.navigate',{url:'about:blank'});await wait(1200);
 const replayUrl=`http://127.0.0.1:${port}/api/serial/telemetry-replay?slot=1&after=0`;
 const auth={headers:{'X-GLD-Bridge-Token':health.csrfToken}};
 const afterClose=(await (await fetch(replayUrl,auth)).json()).sequence;await wait(800);
 const afterIdle=(await (await fetch(replayUrl,auth)).json()).sequence;
 assert.equal(afterIdle,afterClose,'leaving page must release its background poll');
 console.log(`PASS isolated Chrome minimized and frozen polling: ${before.count} -> ${after.count} -> ${thawed.count} samples; history ordered`);
 }finally{if(cdp)try{await Promise.race([cdp.send('Browser.close'),wait(500)])}catch{};if(socket)socket.close();if(browser)browser.kill();if(server)server.kill();await wait(500);
  const base=path.resolve(os.tmpdir())+path.sep;const full=path.resolve(profile);if(full.startsWith(base)&&path.basename(full).startsWith('gld-browser-poll-')){try{fs.rmSync(full,{recursive:true,force:true})}catch{}}}
})().catch(e=>{console.error(e.stack||e);process.exitCode=1});
