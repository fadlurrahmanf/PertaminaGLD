const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const here=__dirname;
(async()=>{let b;const result={hardware_actions:false};try{
 const origin='http://127.0.0.1:5174';const health=await (await fetch(origin+'/api/health')).json();assert(health.features.datasetWorkflow);const headers={'X-GLD-Bridge-Token':health.csrfToken};
 const current=await (await fetch(origin+'/api/dataset-workflow/state',{headers})).json();assert(!current.connected&&!current.count&&!current.csv_path&&!current.cleanup_pending);result.idle=true;
 for(const m of [1,2,3]){
  const r=JSON.parse(fs.readFileSync(path.join(here,`model${m}-build-receipt.json`)));const p=await (await fetch(origin+`/api/firmware/package?env=gld_model_${m}_dataset_workflow_wifi`,{headers})).json();assert.equal(p.manifest.flashFiles.find(f=>f.path==='firmware.bin').sha256,r.firmwareSha256);
 }
 result.three_live_packages_match_builds=true;const hub=await fetch('http://127.0.0.1:5173/');assert.equal(hub.status,200);result.hub_http=200;
 b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-proxy-server','--disable-gpu']});const p=await b.newPage({viewport:{width:1600,height:1100}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(origin,{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.querySelector('#wfState')?.textContent==='Belum terhubung');await p.locator('[data-tab=dataset]').click();
 result.ui=await p.evaluate(()=>({steps:document.querySelectorAll('[data-wf-step]').length,all_grey:[...document.querySelectorAll('[data-wf-step]')].every(n=>n.dataset.ready==='false'),readings:document.querySelector('#wfReadings').children.length,primary:document.querySelector('#wfPrimaryLabel').textContent,controls_hidden:document.querySelector('#wfControls').hidden,lock_disabled:document.querySelector('#wfLock').disabled,legacy_expert:!!document.querySelector('#expert #wirelessDataset'),password_field:!!document.querySelector('#wfPassword')}));
 assert.equal(result.ui.steps,5);assert(result.ui.all_grey&&result.ui.controls_hidden&&result.ui.lock_disabled&&result.ui.legacy_expert&&!result.ui.password_field);assert.equal(result.ui.readings,8);assert.equal(result.ui.primary,'Start');assert.equal(errors.length,0);
 await p.screenshot({path:path.join(here,'final-stock-workspace.png'),fullPage:true});result.js_errors=errors;result.ok=true;
}finally{if(b)await b.close();fs.writeFileSync(path.join(here,'final-stock-smoke.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));}})().catch(e=>{console.error(e.message);process.exitCode=1});
