// Actual Operator bridge/UI and GLD1002; ONLY CSV chooser is injected in QA host.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {launch,eventually,delay}=require('./browser-client.cjs');
const runName=process.env.GLD_QA_RUN||'real-browser';assert(/^[a-z0-9-]+$/.test(runName));
const here=__dirname,out=path.join(here,runName),downloads=path.join(out,'downloads');
fs.mkdirSync(downloads,{recursive:true});
const origin='http://127.0.0.1:5174';let token='',browser;
const evidence={hardware:true,simulation:false,native_file_dialog:false,csv_chooser:'Unique isolated path supplied by QA wrapper; all radio/data/control/storage/UI real',sessions:[],screenshots:[],downloads:[],errors:[]};
const py=path.resolve('apps/gld-operator/python-embed/python.exe');
const heartbeat=setInterval(()=>{try{execFileSync(py,[path.join(here,'heartbeat.py')],{windowsHide:true,stdio:'ignore'});}catch{}},20000);
async function request(route,data){
 const r=await fetch(origin+route,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-GLD-Bridge-Token':token},...(data===undefined?{}:{body:JSON.stringify(data)}),signal:AbortSignal.timeout(45000)});
 const value=await r.json();if(!r.ok)throw Error(route+': '+value.error);return value;
}
const state=()=>request('/api/dataset-workflow/state');
async function waitState(check,description,seconds=25){let s;await eventually(async()=>{s=await state();return check(s);},description,seconds);return s;}
async function button(id){await eventually(()=>browser.evaluate(`!document.getElementById(${JSON.stringify(id)}).disabled`),id+' enabled',20);await browser.click('#'+id);}
async function capture(key,anchor='#datasetWorkflow',selectors=[]){
 await browser.evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(anchor)}).getBoundingClientRect();scrollTo(0,Math.max(0,r.top+scrollY-105));return true})()`);await delay(120);
 const boxes=await browser.evaluate(`(${JSON.stringify(selectors)}).map((selector,i)=>{const r=document.querySelector(selector).getBoundingClientRect();return {n:i+1,selector,x:r.x,y:r.y,w:r.width,h:r.height}})`);
 const size=await browser.evaluate('({width:innerWidth,height:innerHeight})');
 const file=path.join(out,key+'.png');await browser.screenshot(file);evidence.screenshots.push({key,path:file,...size,boxes});
}
async function setup(mode){
 await button('wfScan');const scanned=await waitState(s=>s.devices.some(d=>d.device_id==='1002'),'real AP scan');
 assert(scanned.devices.every(d=>/^GLD-DATASET-/.test(d.ssid)));
 await browser.fill('#wfDevice','1002');await waitState(s=>s.selected_device_id==='1002','select real GLD1002');
 await button('wfConnect');const connected=await waitState(s=>s.connected&&s.ready,'real authenticated protocol3 connection');
 assert.equal(connected.device_id,'1002');assert.match(connected.model.profile_id,/board-1/);
 if(process.env.GLD_REQUIRE_PREDICTION==='1')assert.equal(connected.prediction_available,true,'Corrected Model1 must report prediction readiness');
 evidence.model=connected.model;evidence.nulling_profile_id=connected.nulling_profile_id;
 await capture('connected-'+mode,'#datasetWorkflow',['#wfConnection','#wfDevice','#wfChooseFile']);
 await button('wfChooseFile');await waitState(s=>!!s.csv_path,'real CSV target');
 if(connected.prediction_available){await button('wfPrediction');await waitState(s=>s.fields.prediction,'prediction selected');}
 await button(mode==='replay'?'wfModeReplay':'wfModeDirect');await waitState(s=>s.mode===mode,'mode selected');
 await browser.fill('#wfLabel','live_'+mode+'_workspace');await waitState(s=>s.label==='live_'+mode+'_workspace','label configured');
 await capture('settings-'+mode,'[data-wf-step="fields"]',['#wfPrediction','#wfMode','#wfLabelStamp','#wfLabel','#wfLock']);
 await button('wfLock');await waitState(s=>s.locked,'locked');
 assert(await browser.evaluate("[...document.querySelectorAll('[data-wf-step]')].every(n=>n.dataset.ready==='true')"));
 await button('wfPrimary');return waitState(s=>s.state==='recording','real acquisition started');
}
async function stop(){
 await button('wfStop');const s=await waitState(s=>s.verification?.verified&&!s.cleanup_pending,'full real CSV verification');
 await eventually(()=>browser.evaluate("document.getElementById('appModal').getAttribute('aria-hidden')==='false'&&document.getElementById('appModalTitle').textContent==='CSV terverifikasi'"),'verified popup');
 await capture('stop-verified-'+evidence.sessions.length,'#appModal',['#appModalTitle','#appModalMessage','#appModalOkBtn']);
 await button('appModalOkBtn');return s;
}
async function download(s){
 const value=await request('/api/dataset-workflow/export',{}),target=path.join(downloads,path.basename(value.filename));
 const before=fs.existsSync(target)?fs.statSync(target).mtimeMs:0;await button('wfExport');
 await eventually(()=>fs.existsSync(target)&&fs.statSync(target).mtimeMs>before,'actual browser download');
 const text=fs.readFileSync(target,'utf8');assert.equal(text,value.csv);assert.equal(text,fs.readFileSync(s.csv_path,'utf8').replace(/\r\n/g,'\n'));
 evidence.downloads.push({path:target,source_csv:s.csv_path,count:s.count,sha256:require('crypto').createHash('sha256').update(text).digest('hex')});
}
async function network(name){
 const r=execFileSync('netsh',['wlan','connect','name='+name,'interface=Wi-Fi'],{windowsHide:true,encoding:'utf8',timeout:10000});
 assert(!/failed|not found|cannot/i.test(r),'network association request rejected');
 await eventually(()=>{
  const value=execFileSync('netsh',['wlan','show','interfaces'],{windowsHide:true,encoding:'utf8',timeout:10000});
  return [...value.matchAll(/^\s*SSID\s*:\s*(.*?)\s*$/gm)].some(m=>m[1]===name);
 },'actual Windows association to '+name,18);
}
async function reset(){await button('wfReset');await waitState(s=>!s.csv_path&&!s.selected_device_id&&!s.connected,'reset finished');}
function timing(history){
 const gaps=history.slice(1).map((r,i)=>r.timestamp_ms-history[i].timestamp_ms).sort((a,b)=>a-b);
 return {count:gaps.length,min_ms:gaps[0],median_ms:gaps[Math.floor(gaps.length/2)],max_ms:gaps.at(-1)};
}
(async()=>{
 const health=await request('/api/health');assert(health.features.datasetWorkflow&&!health.simulation);token=health.csrfToken;
 assert(!(await state()).connected,'fresh isolated actual bridge required');
 browser=await launch(out);await browser.call('Page.enable');await browser.call('Runtime.enable');
 await browser.call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
 await browser.call('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{const p=CanvasRenderingContext2D.prototype,o=p.stroke;p.stroke=function(...a){if(this.canvas.id==='wfChart'&&Math.abs(this.lineWidth-1.8)<.001)(globalThis.__liveStrokes||={})[this.strokeStyle]=true;return o.apply(this,a)}})()`});
 await browser.call('Page.navigate',{url:origin+'/'});await eventually(()=>browser.evaluate("!!document.querySelector('#wfMessage')?.textContent"),'actual UI initialized');
 await browser.click('[data-tab="dataset"]');await capture('workspace-initial','#datasetWorkflow',['#wfScan','#wfDevice','#wfConnect']);
 if(process.env.GLD_NOTICE_ONLY==='1'){
  await setup('replay');let s=await waitState(s=>s.count>=12,'notice prefix');
  await eventually(()=>browser.evaluate("!document.querySelector('#wfPrimary').disabled&&document.querySelector('#wfPrimary').dataset.command==='pause'"),'Start action complete');
  await network('ITB Guest');await waitState(s=>s.state==='recovering','notice actual recovery');await delay(4000);
  assert.equal((await state()).error,'','Expected transport loss should use normal recovery notice');
  await eventually(()=>browser.evaluate("document.querySelector('#wfMessage').dataset.error==='false'"),'recovery hint not false error');
  await capture('replay-disconnected','#datasetWorkflow',['#wfState','#wfMessage','#wfCount']);
  await network('GLD-DATASET-1002');await waitState(s=>s.state==='recording'&&s.replayed_count>0,'notice real recovery',40);
  s=await stop();await download(s);evidence.sessions.push({case:'recovery_notice_real_radio',csv:s.csv_path,count:s.count,replayed:s.replayed_count,verified:s.verification});
  await capture('replay-recovered','#datasetWorkflow',['#wfCount']);await reset();evidence.ok=true;return;
 }
 const first=await setup('direct');let s=await waitState(s=>s.count>=24,'24 actual samples',25);
 assert(s.history.every(r=>r.sensor_voltage.length===8&&r.sensor_voltage.every(Number.isFinite)));
 const chart=await browser.evaluate("({traces:Object.keys(globalThis.__liveStrokes||{}).length,readings:document.querySelector('#wfReadings').children.length,class:document.querySelector('#wfPredictedClass').textContent,confidence:document.querySelector('#wfConfidenceScore').textContent})");
 assert.equal(chart.traces,8);assert.equal(chart.readings,8);evidence.chart=chart;evidence.timing=timing(s.history);
 evidence.prediction={available:s.prediction_available,valid_samples:s.history.filter(r=>r.prediction?.valid).length,warmup_samples:s.history.filter(r=>r.prediction?.status==='warmup').length};
 if(process.env.GLD_REQUIRE_PREDICTION==='1')assert(evidence.prediction.valid_samples>0,'Actual model must emit valid predictions after warmup');
 await capture('recording-real','#datasetWorkflow',['#wfPrimary','#wfStop','#wfCount','#wfChart']);
 await button('wfPrimary');s=await waitState(s=>s.state==='paused','Pause acknowledged');
 const pausedCount=s.count,pausedBytes=fs.readFileSync(s.csv_path);await delay(1600);assert.equal((await state()).count,pausedCount);assert.deepEqual(fs.readFileSync(s.csv_path),pausedBytes);
 await capture('paused-real','#datasetWorkflow',['#wfPrimary','#wfStop','#wfState']);
 await button('wfPrimary');await waitState(s=>s.state==='recording'&&s.count>=pausedCount+6,'Resume actual acquisition');
 s=await stop();await download(s);await capture('continue-real','#datasetWorkflow',['#wfPrimary','#wfStop','#wfVerification']);
 await capture('export-real','.wf-sample-panel',['#wfRows','#wfExport','#wfVerification']);const stoppedCount=s.count;
 await button('wfPrimary');const continued=await waitState(s=>s.state==='recording'&&s.session_id!==first.session_id,'Continue new session');
 assert.equal(continued.csv_path,first.csv_path);await waitState(s=>s.count>=stoppedCount+6,'Continue appends same CSV');s=await stop();await download(s);
 evidence.sessions.push({case:'direct_pause_resume_stop_continue',csv:s.csv_path,count:s.count,verified:s.verification,first_sid:first.session_id,next_sid:continued.session_id});await reset();
 const replay=await setup('replay');s=await waitState(s=>s.count>=12,'replay real prefix');const prefix=s.count;
 await network('ITB Guest');await waitState(s=>s.state==='recovering','actual WiFi loss recovery');await delay(6000);await capture('replay-disconnected','#datasetWorkflow',['#wfState','#wfMessage','#wfCount']);
 await network('GLD-DATASET-1002');s=await waitState(s=>s.state==='recording'&&s.count>prefix+8&&s.replayed_count>0,'actual retained sample replay',35);
 s=await stop();assert.equal(s.csv_path,replay.csv_path);assert.equal(s.gap_count,0);assert.equal(s.duplicate_count,0);await download(s);
 evidence.sessions.push({case:'real_wifi_loss_and_replay_same_csv',csv:s.csv_path,count:s.count,replayed:s.replayed_count,gaps:s.gap_count,duplicates:s.duplicate_count,verified:s.verification});
 await capture('replay-recovered','#datasetWorkflow',['#wfVerification','#wfCount','#wfChart']);await reset();
 await setup('direct');await waitState(s=>s.count>=8,'direct loss prefix');await network('ITB Guest');const cut=await waitState(s=>s.cleanup_pending,'real direct cutoff');const frozen=fs.readFileSync(cut.csv_path);await delay(1800);await network('GLD-DATASET-1002');
 s=await waitState(s=>!s.cleanup_pending&&s.verification?.verified,'direct owned cleanup',35);assert.equal(s.count,cut.count);assert.deepEqual(fs.readFileSync(s.csv_path),frozen);await download(s);
 evidence.sessions.push({case:'real_direct_loss_freezes_csv',csv:s.csv_path,count:s.count,complete:s.complete,verified:s.verification});await reset();evidence.ok=true;
})().catch(async e=>{evidence.ok=false;evidence.errors.push(e.stack);if(browser)try{await browser.screenshot(path.join(out,'failure.png'));}catch{};console.error(e.message);process.exitCode=1;})
.finally(async()=>{
 clearInterval(heartbeat);
 try{let s=await state();if(['recording','paused'].includes(s.state)){await request('/api/dataset-workflow/stop',{});await waitState(s=>s.verification?.verified,'finally close owned session',15);}evidence.final_state=await state();}catch(e){evidence.cleanup_error=e.message;}
 if(browser)await browser.close();fs.writeFileSync(path.join(out,'evidence.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify({ok:evidence.ok,hardware:true,sessions:evidence.sessions,chart:evidence.chart,prediction:evidence.prediction,timing:evidence.timing,downloads:evidence.downloads.length,errors:evidence.errors}));
});
