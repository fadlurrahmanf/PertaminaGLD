// Actual UI and browser downloads; synthetic device and native Windows platform.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {launch,eventually,delay}=require('../wireless-dual-mode/browser-client.cjs');
const here=__dirname,ready=JSON.parse(fs.readFileSync(path.join(here,'e2e/ready.json'),'utf8'));
assert.equal(ready.mode,'pc-simulation');assert.equal(ready.device_validation,false);
assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(ready.origin)&&![5173,5174].includes(ready.http_port));
const output=path.join(here,'browser-output'),downloads=path.join(output,'downloads');fs.mkdirSync(downloads,{recursive:true});
let browser,token;
const evidence={simulation:true,hardware:false,sessions:[],screenshots:[],downloads:[]};
async function request(route,payload){const result=await fetch(ready.origin+route,{method:payload===undefined?'GET':'POST',
 headers:{'Content-Type':'application/json',...(token?{'X-GLD-Bridge-Token':token}:{})},...(payload===undefined?{}:{body:JSON.stringify(payload)})});
 const value=await result.json();if(!result.ok)throw Error(route+': '+value.error);return value;}
const state=()=>request('/api/dataset-workflow/state');
const sim=(action,payload={})=>request('/sim/'+action,payload);
async function waitState(check,description){let result;await eventually(async()=>{result=await state();return check(result);},description,45);return result;}
async function button(id){await eventually(()=>browser.evaluate(`!document.getElementById(${JSON.stringify(id)}).disabled`),id+' enabled',45);await browser.click('#'+id);}
async function notice(){await eventually(()=>browser.evaluate("document.getElementById('appModal').getAttribute('aria-hidden')==='false'&&document.getElementById('appModalTitle').textContent==='CSV terverifikasi'"),'verified CSV popup');return browser.evaluate("document.getElementById('appModalMessage').textContent");}
async function capture(key,anchor,selectors=[]){
 await browser.evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(anchor)});window.scrollTo(0,Math.max(0,n.getBoundingClientRect().top+window.scrollY-95));return true})()`);
 await delay(100);
 const boxes=await browser.evaluate(`(${JSON.stringify(selectors)}).map((selector,i)=>{const n=document.querySelector(selector),r=n.getBoundingClientRect();return {n:i+1,selector,x:r.x,y:r.y,w:r.width,h:r.height};})`);
 const size=await browser.evaluate('({width:innerWidth,height:innerHeight})');
 await browser.screenshot(path.join(output,key+'.png'));
 evidence.screenshots.push({key,path:path.join(output,key+'.png'),...size,boxes});
}
async function setup(mode,prediction=false){
 await button('wfScan');await waitState(s=>s.devices.length===1,'scan lists one GLD');
 await browser.fill('#wfDevice','1002');await waitState(s=>s.selected_device_id==='1002','selected GLD1002');
 await browser.fill('#wfPassword',ready.password);await button('wfConnect');await waitState(s=>s.connected&&s.ready,'authenticated ready');
 await button('wfChooseFile');await waitState(s=>Boolean(s.csv_path),'selected CSV target');
 await browser.fill('#wfMode',mode);await waitState(s=>s.mode===mode,'selected mode');
 if(prediction){await button('wfPrediction');await waitState(s=>s.fields.prediction===true,'prediction checkbox');}
 await browser.fill('#wfLabel','pc_browser_'+mode);await waitState(s=>s.label==='pc_browser_'+mode,'label');
 await eventually(()=>browser.evaluate("!document.getElementById('wfLock').disabled"),'all seven steps valid');
}
async function lock(){await button('wfLock');await waitState(s=>s.locked,'settings locked');assert(await browser.evaluate("[...document.querySelectorAll('[data-wf-step]')].every(n=>n.dataset.ready==='true')"));}
async function start(){await sim('manual');await button('wfStart');return waitState(s=>s.state==='recording','recording');}
async function stop(){await button('wfStop');const s=await waitState(s=>s.verification?.verified&&!s.cleanup_pending,'Stop file verification');await notice();return s;}
async function dismiss(){await button('appModalOkBtn');}
async function download(s){const data=await request('/api/dataset-workflow/export',{}),name=path.basename(data.filename),target=path.join(downloads,name);
 const previous=fs.existsSync(target)?fs.statSync(target).mtimeMs:0;await button('wfExport');
 await eventually(()=>{try{return fs.statSync(target).mtimeMs>previous&&fs.readFileSync(target,'utf8')===data.csv;}catch{return false;}},'actual browser CSV download');
 const text=fs.readFileSync(target,'utf8');
 assert.equal(text,data.csv);assert.equal(text,fs.readFileSync(s.csv_path,'utf8').replace(/\r\n/g,'\n'));
 const preserved=path.join(downloads,`${evidence.downloads.length+1}-`+name);fs.copyFileSync(target,preserved);
 evidence.downloads.push({filename:name,path:preserved,source_csv:s.csv_path,count:s.count,sha256:require('crypto').createHash('sha256').update(text).digest('hex')});
}
async function reset(){await button('wfReset');await waitState(s=>!s.locked&&!s.csv_path&&!s.selected_device_id,'wizard reset');}
async function traceProof(){return browser.evaluate(`(()=>{const c=document.getElementById('wfChart');return {legend:document.getElementById('wfLegend').children.length,width:c.width,height:c.height,strokes:Object.keys(globalThis.__workflowStrokes||{}).length,rows:document.querySelectorAll('#wfRows tr').length}})()`);}

(async()=>{
 const health=await request('/api/health');assert(health.simulation);token=health.csrfToken;
 const initial=await state();assert(!initial.connected&&!initial.cleanup_pending&&!initial.locked,'fixture must be fresh/reset');
 browser=await launch(output);await browser.call('Page.enable');await browser.call('Runtime.enable');
 await browser.call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
 await browser.call('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{const p=CanvasRenderingContext2D.prototype,o=p.stroke;p.stroke=function(...args){if(this.canvas.id==='wfChart'&&this.lineWidth===1.5)(globalThis.__workflowStrokes||={})[this.strokeStyle]=true;return o.apply(this,args);};})();`});
 await browser.call('Page.navigate',{url:ready.app_url});
 await eventually(()=>browser.evaluate("!!document.getElementById('wfMessage')?.textContent"),'wizard initialized');
 await browser.click('[data-tab="dataset"]');await eventually(()=>browser.evaluate("document.querySelector('[data-tab=dataset]').classList.contains('active')"),'Dataset active');
 assert(await browser.evaluate("document.querySelector('#dataset #wirelessDataset')===null&&document.querySelector('#expert #wirelessDataset')!==null"),'legacy cards moved from Dataset to Expert');
 await capture('01-wizard-empty','#datasetWorkflow',['#wfScan','#wfDevice']);
 await setup('direct',true);
 await capture('02-device-connected','[data-wf-step="scan"]',['#wfDevice','#wfConnection','#wfChooseFile']);
 await capture('03-options-ready','[data-wf-step="fields"]',['#wfPrediction','#wfMode','#wfLabel','#wfLock']);
 await lock();await capture('04-locked','[data-wf-step="fields"]',['#wfLock','#wfStart','#wfPause','#wfStop']);
 const first=await start();await sim('acquire',{count:12});await waitState(s=>s.count===12,'12 direct samples');
 await eventually(()=>browser.evaluate("document.getElementById('wfCount').textContent.includes('12 sampel')"),'SSE count12');
 await capture('05-recording','#wfControls',['#wfPause','#wfStop','#wfCount','#wfChart']);
 let proof=await traceProof();assert.equal(proof.legend,8);assert(proof.strokes>=8&&proof.width>0&&proof.height>0);evidence.chart=proof;
 await button('wfPause');let paused=await waitState(s=>s.state==='paused','confirmed pause');const frozenBytes=fs.readFileSync(paused.csv_path,'utf8');
 await sim('acquire',{count:8});assert.equal((await state()).count,12);assert.equal(fs.readFileSync(paused.csv_path,'utf8'),frozenBytes);
 await capture('06-paused','#wfControls',['#wfPause','#wfStop','#wfReset']);
 assert(await browser.evaluate("document.getElementById('wfPause').textContent==='Resume'&&document.getElementById('wfStart').disabled"));
 await button('wfPause');await waitState(s=>s.state==='recording','resumed acquisition');await sim('acquire',{count:8});await waitState(s=>s.count===20,'resumed samples');
 let final=await stop();assert.equal(final.count,20);await capture('07-stop-verified','#appModal',['#appModalTitle','#appModalMessage','#appModalOkBtn']);await dismiss();await download(final);
 await capture('08-continue-ready','#wfControls',['#wfStart','#wfVerification','#wfReset']);
 const continued=await start();assert.notEqual(continued.session_id,first.session_id);assert.equal(continued.csv_path,first.csv_path);
 await sim('acquire',{count:8});await waitState(s=>s.count===28,'same CSV continued');final=await stop();await dismiss();assert.equal(final.count,28);await download(final);
 evidence.sessions.push({scenario:'direct pause/resume/Stop/Continue',first_sid:first.session_id,next_sid:continued.session_id,path:final.csv_path,count:final.count});await reset();

 await setup('direct');await lock();await start();await sim('acquire',{count:8});await waitState(s=>s.count===8,'direct loss prefix');await sim('drop');
 const cut=await waitState(s=>s.cleanup_pending,'direct private cleanup');const cutBytes=fs.readFileSync(cut.csv_path,'utf8');
 await capture('09-direct-link-lost','#wfControls',['#wfState','#wfCount','#wfMessage']);
 await sim('gap',{count:20});await sim('resume');final=await waitState(s=>!s.cleanup_pending&&s.verification?.verified,'direct cleanup complete');
 assert.equal(final.count,8);assert.equal(final.complete,false);assert.equal(fs.readFileSync(final.csv_path,'utf8'),cutBytes);await download(final);
 evidence.sessions.push({scenario:'direct cutoff/private cleanup',path:final.csv_path,count:final.count,complete:final.complete});await reset();

 await setup('replay',true);await lock();const replay=await start();await sim('acquire',{count:8});await waitState(s=>s.count===8,'replay prefix');await sim('drop');
 await waitState(s=>s.state==='recovering','replay recovery');await capture('10-replay-link-lost','#wfControls',['#wfState','#wfMessage']);
 await sim('gap',{count:40});await sim('resume');await waitState(s=>s.count>=48&&s.state==='recording','replay caught up');final=await stop();await dismiss();
 assert.equal(final.csv_path,replay.csv_path);assert.equal(final.gap_count,0);assert.equal(final.duplicate_count,0);await capture('11-replay-complete','#wfControls',['#wfVerification','#wfCount','#wfChart']);await download(final);
 evidence.sessions.push({scenario:'automatic recovery same CSV',path:final.csv_path,count:final.count,replayed_count:final.replayed_count});
 await reset();evidence.fixture=await request('/sim/state');evidence.ok=true;
 fs.writeFileSync(path.join(output,'browser-evidence.json'),JSON.stringify(evidence,null,2));
 console.log(JSON.stringify({ok:true,simulation:true,sessions:evidence.sessions,downloads:evidence.downloads.length,screenshots:evidence.screenshots.length}));
})().catch(async error=>{fs.writeFileSync(path.join(output,'failure.txt'),error.stack);if(browser){try{await browser.screenshot(path.join(output,'failure.png'));console.error(await browser.evaluate("({state:document.getElementById('wfState')?.textContent,message:document.getElementById('wfMessage')?.textContent})"));}catch{}}console.error(error.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
