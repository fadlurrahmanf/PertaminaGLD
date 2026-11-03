// Actual operator UI + isolated HTTP/SSE/WS fixture. Synthetic sensors only.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {launch,eventually,delay}=require('./browser-client.cjs');
const here=__dirname;
const ready=JSON.parse(fs.readFileSync(path.join(here,'fixture-ready.json'),'utf8'));
if(!ready.simulation || !/^http:\/\/127\.0\.0\.1:\d+$/.test(ready.origin) || [5173,5174].includes(ready.http_port)) throw Error('Refuse non-fixture endpoint');
const output=path.join(here,'browser-output');fs.mkdirSync(output,{recursive:true});
const downloads=path.join(output,'downloads');fs.mkdirSync(downloads,{recursive:true});
let token;
async function request(route,payload) {
  const result=await fetch(ready.origin+route,{method:payload===undefined?'GET':'POST',
    headers:{'Content-Type':'application/json',...(token?{'X-GLD-Bridge-Token':token}:{})},
    ...(payload===undefined?{}:{body:JSON.stringify(payload)})});
  const data=await result.json();if(!result.ok)throw Error(`${route}: ${data.error}`);return data;
}
const state=mode=>request(`/api/${mode==='direct'?'wireless-dataset':'wireless-replay'}/state`);
const sim=(action,payload={})=>request(`/sim/${action}`,payload);
let browser;
const evidence={mode:'PC simulation',device_validation:false,sessions:[],screenshots:[]};
async function button(id) {await eventually(()=>browser.evaluate(`!document.getElementById(${JSON.stringify(id)}).disabled`),`${id} enabled`);await browser.click('#'+id);}
async function waitState(mode,predicate,description){let result;await eventually(async()=>{result=await state(mode);return predicate(result);},description,35);return result;}
async function chartProof(name) {
  await browser.evaluate("document.getElementById('wirelessDataset').scrollIntoView({block:'start'})");
  const proof=await browser.evaluate(`(()=>{const canvas=document.getElementById('wirelessChart');return {legend:[...document.querySelectorAll('#wirelessLegend>*')].map(n=>n.textContent),rows:[...document.querySelectorAll('#wirelessRows tr')].map(n=>n.children.length),width:canvas.width,height:canvas.height,strokes:globalThis.__wirelessStrokes||{},status:document.getElementById('wirelessState').textContent}})()`);
  assert.equal(proof.legend.length,8);assert(proof.rows.length>0&&proof.rows.every(n=>n===10));
  assert(proof.width>0&&proof.height>0);assert(Object.keys(proof.strokes).length>=8,'eight actual colored chart traces');
  await browser.screenshot(path.join(output,name+'.png'));evidence.screenshots.push({file:name+'.png',proof});return proof;
}
async function download(mode,final) {
  const before=new Set(fs.readdirSync(downloads));await button('wirelessExportBtn');
  let filename;await eventually(()=>{filename=fs.readdirSync(downloads).find(n=>!before.has(n)&&n.endsWith('.csv'));return !!filename;},'browser CSV download');
  const csv=fs.readFileSync(path.join(downloads,filename),'utf8');
  const exported=await request(`/api/${mode==='direct'?'wireless-dataset':'wireless-replay'}/export`,{});
  assert.equal(csv,exported.csv,'download exact matches backend CSV');
  assert.equal(csv,fs.readFileSync(final.path,'utf8').replace(/\r\n/g,'\n'),'download matches disk records (Python export normalizes CRLF)');
  return {filename,count:final.count,session_id:final.session_id,complete:final.complete,csv_path:final.path};
}
async function connect(mode,label) {
  await browser.fill('#wirelessMode',mode);
  await browser.fill('#wirelessPassword',ready.password);
  await button('wirelessConnectBtn');await waitState(mode,s=>s.ready&&s.connected,'ready');
  await browser.fill('#wirelessLabel',label);await button('wirelessStartBtn');
  return waitState(mode,s=>s.state==='recording','recording');
}
async function disconnect(mode){if((await state(mode)).connected)await button('wirelessDisconnectBtn');await waitState(mode,s=>!s.connected,'disconnected');}
(async()=>{
  const health=await request('/api/health');assert(health.simulation);token=health.csrfToken;
  for(const mode of ['direct','replay']) {const s=await state(mode);assert(!s.connected&&!s.cleanup_pending&&!s.recovery_active,'fixture must be idle');}
  browser=await launch(output);
  await browser.call('Page.enable');await browser.call('Runtime.enable');
  await browser.call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
  await browser.call('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{const p=CanvasRenderingContext2D.prototype;const original=p.stroke;p.stroke=function(...args){if(this.canvas.id==='wirelessChart'&&this.lineWidth===1.5){(globalThis.__wirelessStrokes||={})[this.strokeStyle]=true;}return original.apply(this,args);};})();`});
  await browser.call('Page.navigate',{url:ready.app_url});
  await eventually(()=>browser.evaluate("!!document.querySelector('[data-tab=dataset]')&&typeof document.getElementById('wirelessConnectBtn').onclick!=='undefined'"),'page');
  await eventually(()=>browser.evaluate("!!document.getElementById('wirelessMessage').textContent&&!document.getElementById('wirelessConnectBtn').disabled"),'wireless initialized');
  await browser.click('[data-tab="dataset"]');
  await eventually(()=>browser.evaluate("document.querySelector('[data-tab=dataset]').classList.contains('active')"),'Dataset tab visible');
  await connect('direct','pc_ui_direct_clean');await sim('acquire',{count:12});
  await waitState('direct',s=>s.count===12,'direct 12 samples');
  await eventually(()=>browser.evaluate("document.querySelector('#wirelessRows tr')?.children.length===10"),'direct visible samples');
  await chartProof('direct-clean');await button('wirelessStopBtn');
  let final=await waitState('direct',s=>s.complete,'direct complete');
  evidence.sessions.push({scenario:'direct clean',...await download('direct',final)});await disconnect('direct');

  await connect('direct','pc_ui_direct_drop');await sim('acquire',{count:8});
  await waitState('direct',s=>s.count===8,'direct cutoff baseline');await sim('drop');
  const frozen=await waitState('direct',s=>s.cleanup_pending,'direct cleanup pending');
  const frozenBytes=fs.readFileSync(frozen.path,'utf8');
  await chartProof('direct-link-lost');
  assert(await browser.evaluate("document.getElementById('wirelessMode').disabled&&document.getElementById('wirelessStartBtn').disabled"));
  await button('wirelessDisconnectBtn');await waitState('direct',s=>s.cleanup_paused,'cleanup manually paused');
  await eventually(()=>browser.evaluate("document.getElementById('wirelessConnectBtn').textContent==='Selesaikan sesi'"),'resume button');
  await sim('gap',{count:20});await sim('resume');
  await browser.fill('#wirelessPassword',ready.password);await button('wirelessConnectBtn');
  final=await waitState('direct',s=>!s.cleanup_pending&&s.cleanup_confirmed,'private cleanup confirmed');
  assert.equal(final.count,frozen.count);assert.equal(fs.readFileSync(final.path,'utf8'),frozenBytes);assert.equal(final.complete,false);
  await chartProof('direct-cleanup-complete');
  evidence.sessions.push({scenario:'direct loss + pause + manual cleanup resume',frozen_count:frozen.count,...await download('direct',final)});

  await connect('direct','pc_ui_direct_next');await sim('acquire',{count:8});
  await waitState('direct',s=>s.count===8,'next direct samples');await button('wirelessStopBtn');
  final=await waitState('direct',s=>s.complete,'next direct complete');
  evidence.sessions.push({scenario:'next direct after cleanup',...await download('direct',final)});await disconnect('direct');

  await connect('replay','pc_ui_replay_drop');await sim('acquire',{count:8});
  const initial=await waitState('replay',s=>s.count===8,'replay baseline');await sim('drop');
  await waitState('replay',s=>s.recovery_active,'replay recovering');await chartProof('replay-link-lost');
  await sim('gap',{count:40});await sim('resume');
  await waitState('replay',s=>s.count>=48&&!s.recovery_active,'replay caught up');await button('wirelessStopBtn');
  final=await waitState('replay',s=>s.complete,'replay complete');
  assert.equal(final.path,initial.path);assert.equal(final.session_id,initial.session_id);
  assert.equal(final.gap_count,0);assert.equal(final.duplicate_count,0);
  await chartProof('replay-complete');
  evidence.sessions.push({scenario:'replay loss and same CSV recovery',replayed_count:final.replayed_count,...await download('replay',final)});await disconnect('replay');
  evidence.fixture=await request('/sim/dual-state');assert.deepEqual(evidence.fixture.errors,[]);
  evidence.ok=true;fs.writeFileSync(path.join(output,'browser-evidence.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify({ok:true,simulation:true,sessions:evidence.sessions.map(({scenario,count,complete})=>({scenario,count,complete})),screenshots:evidence.screenshots.length}));
})().catch(async error=>{fs.writeFileSync(path.join(output,'browser-failure.txt'),error.stack);if(browser){try{await browser.screenshot(path.join(output,'failure.png'));console.error(await browser.evaluate("({status:document.getElementById('wirelessState')?.textContent,message:document.getElementById('wirelessMessage')?.textContent})"));}catch{}}console.error(error.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
