const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');const ready=JSON.parse(fs.readFileSync(path.join(root,'e2e/ready.json'),'utf8'));
const results={fixture:true,hardware:false,stateMutation:false,cases:[],errors:[]};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--no-proxy-server','--disable-gpu']});
 try{
  for(const width of [1600,1024,736,320])for(const theme of ['light','dark']){
   const context=await browser.newContext({viewport:{width,height:1000},colorScheme:theme});const page=await context.newPage();
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(theme=>localStorage.setItem('gldOperatorWeb.theme',theme),theme);
   await page.goto(ready.app_url,{waitUntil:'domcontentloaded',timeout:30000});
   await page.waitForFunction(()=>document.getElementById('wfMessage')?.textContent,{timeout:30000});
   await page.locator('[data-tab="dataset"]').click();
   await page.waitForFunction(()=>document.getElementById('dataset').classList.contains('active'));
   await page.waitForTimeout(200);
   const details=await page.evaluate(()=>{
    const viewport=innerWidth,workflow=document.getElementById('datasetWorkflow'),table=workflow.querySelector('.wireless-table-wrap');
    const box=n=>{const r=n.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
    const offenders=[...workflow.querySelectorAll('*')].filter(n=>{if(!n.getClientRects().length||table.contains(n)||n.closest('svg'))return false;const r=n.getBoundingClientRect();return r.right>viewport+1||r.left< -1;}).map(n=>({tag:n.tagName,id:n.id,class:n.className,box:box(n)}));
    const controls=['wfScan','wfDevice','wfConnect','wfDisconnect','wfChooseFile','wfPrediction','wfGain','wfSensorStatus','wfTiming','wfModeDirect','wfModeReplay','wfLabel','wfLock','wfReset','wfExport'].map(id=>{const n=document.getElementById(id);return{id,box:box(n),visible:!!n.getClientRects().length,disabled:n.disabled};});
    return{viewport,documentWidth:document.documentElement.scrollWidth,theme:document.documentElement.dataset.theme,state:document.getElementById('wfState').textContent,workflow:box(workflow),table:{...box(table),clientWidth:table.clientWidth,scrollWidth:table.scrollWidth},controls,offenders,steps:workflow.querySelectorAll('[data-wf-step]').length,readings:document.getElementById('wfReadings').children.length};
   });
   const name=`workspace-${width}-${theme}.png`;await page.screenshot({path:path.join(__dirname,name),fullPage:true});
   results.cases.push({width,theme,...details,screenshot:name,errors});await context.close();
  }
 }finally{await browser.close();}
 results.pass=results.cases.length===8&&results.cases.every(r=>r.documentWidth<=r.viewport+1&&r.offenders.length===0&&r.errors.length===0&&r.steps===5&&r.readings===8&&r.controls.every(c=>c.visible&&c.box.width>0&&c.box.height>0));
 fs.writeFileSync(path.join(__dirname,'report.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify({pass:results.pass,cases:results.cases.map(r=>({width:r.width,theme:r.theme,documentWidth:r.documentWidth,offenders:r.offenders.length,errors:r.errors.length,tableOwnScroll:r.table.scrollWidth>r.table.clientWidth}))}));
 if(!results.pass)process.exitCode=1;
})().catch(e=>{results.errors.push(e.stack);fs.writeFileSync(path.join(__dirname,'report.json'),JSON.stringify(results,null,2));console.error(e);process.exitCode=1;});
