// Actual shared evaluator, Running renderer, Expert renderer and Bind handler.
// Inert DOM/serial stubs only; no device, NVS, browser or service operation.
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const root=path.resolve(__dirname,'../../..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const strip=s=>s.replace(/^import .*\r?\n/gm,'').replace(/^export /gm,'');
function node(){return {textContent:'',className:'',dataset:{},children:[],listeners:{},classes:new Set(),
  classList:{toggle(name,on){this.owner.classes[on?'add':'delete'](name);}},
  append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
  addEventListener(event,fn){this.listeners[event]=fn;}};}
const nodes=new Map();
const get=id=>{if(!nodes.has(id)){const n=node();n.classList.owner=n;nodes.set(id,n);}return nodes.get(id);};
const state={};
const context=vm.createContext({console,state,$:get,document:{createElement(){return node();}}});
vm.runInContext(strip(read('apps/gld-operator/js/model-binding.js')),context);
vm.runInContext(strip(read('apps/gld-operator/js/expert.js')),context);
const serial=read('apps/gld-operator/js/serial-protocol.js');
const start=serial.indexOf('export function renderModelBindingStatus(');
vm.runInContext(strip(serial.slice(start,serial.indexOf('\n}',start)+2)),context);
assert(serial.slice(serial.indexOf('function updateStatus('),serial.indexOf('function maybeAppendTelemetry('))
  .includes('renderModelBindingStatus(status);'),'real Running status path calls shared renderer');

function check(status,value,reason){
  const result=context.modelBindingState(status);
  assert.equal(result.value,value);assert.equal(result.reason,reason);
  context.renderModelBindingStatus(status);
  assert.equal(get('modelNullingBindingStatus').dataset.bindingState,value===true?'ready':value===false?'blocked':'unknown');
  assert.equal(get('modelNullingBindingStatus').dataset.bindingReason,reason);
  assert.equal(get('modelNullingBindingStatus').textContent,result.text);
  const row=context.asRows(status).find(r=>r.key==='binding');
  assert.equal(row.value,value);assert.equal(row.detail,result.text);
  context.renderExpertStatus(status);
  const rendered=get('expertStatusRows').children[4];
  if(!rendered){assert.equal(value,null);assert(get('expertStatusSummary').className.includes('is-unknown'));return;}
  assert(rendered.className.includes(value===true?'is-ready':value===false?'is-blocked':'is-unknown'));
  assert.equal(rendered.title,result.text);
  if(value!==true)assert(!rendered.className.includes('is-ready'));
}
for(const model of [1,2,3]){
  const good=()=>({model:{profileId:`model_${model}`,productionApproved:true,bindingValid:true,bindingModelMatches:true,
    boundNullingProfileId:2,activeNullingProfileId:2,profileReady:true,
    readiness:{allSensorsValid:true,sensorsPrimed:true,mlReady:true,nullingProfileApplied:true,dacVerificationReady:true,inferenceValid:true}}});
  check(good(),true,'matched');
  let status=good();status.model.boundNullingProfileId=1;check(status,false,'profile_id_mismatch');
  assert.match(get('modelNullingBindingStatus').textContent,/#1.*#2/);
  status=good();status.model.bindingModelMatches=false;check(status,false,'model_mismatch');
  status=good();status.model.productionApproved=false;check(status,false,'model_not_approved');
  status=good();status.model.profileReady=false;check(status,false,'profile_not_ready');
  status=good();status.model.readiness.profileReady=false;check(status,false,'profile_not_ready');
  status=good();status.model.readiness.bindingValid=false;check(status,false,'binding_invalid');
  status=good();status.model.readiness.bindingModelMatches=false;check(status,false,'model_mismatch');
  status=good();status.model.readiness.productionApproved=false;check(status,false,'model_not_approved');
  for(const bad of [undefined,null,0,-1,1.5,NaN,Infinity,'2',true]){
    for(const key of ['boundNullingProfileId','activeNullingProfileId']){
      status=good();status.model[key]=bad;check(status,null,'profile_id_unknown');
    }
  }
  status=good();delete status.model.productionApproved;check(status,null,'binding_unknown');
}
check({},null,'profile_id_unknown');
check({model:{bindingValid:true,bindingModelMatches:true}},null,'profile_id_unknown');

const main=read('apps/gld-operator/js/main.js');
const handlerStart=main.indexOf('  $("bindModelToNullingProfileBtn")?.addEventListener(');
const handler=main.slice(handlerStart,main.indexOf('\n  $("datasetSettingsBtn")',handlerStart));
const calls=[];
Object.assign(context,{showConfirm:async()=>{calls.push('confirm');return true;},
  showAlert:async(text)=>{calls.push(text);}, withBusy:async(_button,_label,fn)=>fn(),
  applyAndAlert:async()=>{calls.push('bind');},sendCommand:()=>{calls.push('status');}});
vm.runInContext(handler,context);
(async()=>{
  for(const model of [1,2,3]){
    calls.length=0;state.status={model:{profileId:`model_${model}`,productionApproved:false}};
    await get('bindModelToNullingProfileBtn').listeners.click();
    assert.equal(calls.length,1);assert.match(calls[0],/belum disetujui/);
    assert(!calls.includes('confirm'));assert(!calls.includes('bind'));
  }
  calls.length=0;state.status={model:{activeNullingProfileId:2}};
  await get('bindModelToNullingProfileBtn').listeners.click();
  assert.deepEqual(calls,['confirm','bind','status'],'legacy unknown retains explicit confirmation and firmware-authoritative command');
  console.log('PASS Model1/2/3 shared Running/Expert binding status: ID equality, approval, mismatches, readiness, invalid/legacy data and Bind guard');
})().catch(error=>{console.error(error);process.exitCode=1;});
