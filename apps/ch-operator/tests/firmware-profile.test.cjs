const fs=require('fs'), vm=require('vm'), assert=require('assert/strict'), path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../js/ch-main.js'),'utf8');
const part=source.slice(source.indexOf('async function loadFirmwareUploadProfile()'),source.indexOf('// ---- Event wiring'));
const nodes=new Proxy({}, {get(o,k){return o[k] ||= {value:'',disabled:false,checked:false,dataset:{},setAttribute(){},replaceChildren(){}}}});
nodes.firmwareUploadPort.value='COM99';
const state={manifest:null,manifestFiles:new Map(),activeSlot:1,connected:false};
const elements={fwTargetId:{value:'0010'},portSelect:{value:'COM99'}};
let posts=[], requests=[], pending, fail=false;
const ctx=vm.createContext({state,elements,manualUploadPackage:null,packageRequest:0,Map,Object,Option:class{},
  $:id=>nodes[id], DEFAULT_CH_ID:'0010', normalizeHexId:x=>x,validateChAddress:()=>({ok:true}),
  switchTab(){},appendLog(){},showBanner(){},setFirmwareUploadDialog(){},
  setFirmwareUploadStatus(s){nodes.firmwareUploadStatus.textContent=s},
  disconnectSerial:async()=>{},connectSerial:async()=>{},
  bridgeFetch:async(url,opts)=>{
    if(opts){posts.push(JSON.parse(opts.body));return {firmwareVersion:'0.8.0'}}
    requests.push(url); let env=new URL('http://localhost'+url).searchParams.get('env');
    if(env==='ch_small' && pending) return await pending;
    if(fail) throw Error('missing');
    return {manifest:{environment:env,firmwareVersion:'0.8.0',boardProfile:env},packageFiles:{'firmware.bin':'data'}};
  }});
vm.runInContext(part,ctx);
(async()=>{
  for(const e of ['ch_small','ch_large','ch','chFieldtest']){
    nodes.firmwareUploadEnv.value=e; await ctx.loadFirmwareUploadProfile();
    assert.equal(state.manifest.environment,e); assert.equal(nodes.firmwareUploadConfirmBtn.disabled,false);
    assert.equal(requests.at(-1).includes('package=current-source-20261116'),e==='ch_small'||e==='ch_large');
    await ctx.uploadFirmware(); assert.equal(posts.at(-1).env,e); assert.equal(posts.at(-1).resetNvs,false);
  }
  let resolve; pending=new Promise(r=>resolve=r);
  nodes.firmwareUploadEnv.value='ch_small'; const old=ctx.loadFirmwareUploadProfile();
  nodes.firmwareUploadEnv.value='ch_large'; await ctx.loadFirmwareUploadProfile();
  resolve({manifest:{environment:'ch_small'},packageFiles:{}}); await old;
  assert.equal(state.manifest.environment,'ch_large','late older request cannot change the selected board');
  fail=true; nodes.firmwareUploadEnv.value='ch_large'; await ctx.loadFirmwareUploadProfile();
  assert.equal(state.manifest,null); assert.equal(nodes.firmwareUploadConfirmBtn.disabled,true);
  assert.match(nodes.firmwareUploadStatus.textContent,/missing/); fail=false;
  nodes.firmwareUploadEnv.value=''; await ctx.loadFirmwareUploadProfile();
  assert.equal(state.manifest,null); assert.equal(nodes.firmwareUploadConfirmBtn.disabled,true);
  console.log('CH Expert board selection and stale request: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
