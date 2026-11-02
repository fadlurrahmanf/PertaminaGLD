// Execute real selection/upload UI functions with inert DOM/network stubs.
// No COM, upload process, service restart, or device action.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '../../..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const expertSource = read('apps/gld-operator/js/firmware.js').replace(/^import .*\r?\n/gm, '').replace(/\bexport /g, '');
const hubSource = read('apps/operator-hub/public/js/hub.js');
function element() {
  return {value:'',checked:false,disabled:false,hidden:false,textContent:'',dataset:{},listeners:{},
    classList:{toggle(){},add(){},remove(){}},setAttribute(){},focus(){},replaceChildren(){},
    addEventListener(name,callback){this.listeners[name]=callback;},append(value){this.appended=value;}};
}
function functionSource(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1);
  return source.slice(source.slice(0, start).endsWith('async ') ? start - 6 : start,
    source.indexOf('\n}', start) + 2);
}
function manifestFor(environment) {
  return {environment, firmwareVersion:'0.8.39', source:{gitCommit:'a'.repeat(40)}, schemaVersion:2,
    packageType:'pertamina-gld-prebuilt-firmware', deviceId:'ANY', chip:'esp32s3', flashFiles:[{path:'firmware.bin'}]};
}
function receiptFor(environment) {
  return {selectedEnvironment:environment,flashToolCompleted:true,deviceVerified:false,
    verificationPending:'hotspot',nextStep:'Sambungkan hotspot GLD, lalu Dataset Wireless dan Connect GLD.'};
}
let datasetSuffix = '_dataset_wifi';
async function expert(number, hotspot) {
  const value = `model_${number}${hotspot ? datasetSuffix : ''}`;
  const environment = `gld_${value}`;
  const nodes = new Proxy({}, {get(object,key){return object[key] ||= element();}});
  nodes.firmwareUploadPort.value = 'COM999';
  nodes.firmwareUploadEnv.value = 'gld';
  nodes.firmwareUploadModel.value = value;
  const posts = [], gets = [];
  let connects=0, disconnects=0, restores=0;
  const context = vm.createContext({Map,Option:class{},$:id=>nodes[id],state:{activeSlot:1,bridgeAvailable:true,connected:false},
    elements:{portSelect:element()},appendLog(){},switchTab(){},showBanner(){},getField:()=> '1001',
    requireUnlock:async()=>true,updateSelectedPortDetail(){},
    disconnectSerial:async()=>{disconnects++;},connectSerial:async()=>{connects++;context.state.connected=true;},
    restoreGldConfigAfterReset:async()=>{restores++;},
    bridgeFetch:async(url,options)=>{
      if(options){posts.push(JSON.parse(options.body));return {ok:true,nvsReset:false};}
      gets.push(url);return {manifest:manifestFor(environment),packageFiles:{'firmware.bin':'BASE64'}};
    }});
  vm.runInContext(expertSource, context);
  await context.loadBuiltinPackage('gld');
  assert.equal(gets.at(-1),`/api/firmware/package?env=${environment}`);
  assert.equal(posts.length,0,'selection alone must never upload');
  assert.equal(connects+disconnects,0,'selection alone must never connect COM');
  assert.equal(context.requiresGld1DowngradeReset(context.state.manifest),false);
  if(hotspot){
    nodes.firmwareResetNvs.checked=true;
    await context.performFirmwareUpload();
    assert.equal(posts.length,0,'reset must be refused before an upload');
    assert.equal(disconnects,0,'reset must be refused before any COM disconnect');
    assert.match(nodes.firmwareUploadStatus.textContent,/Matikan Reset NVS/);
    nodes.firmwareResetNvs.checked=false;
  }
  await context.performFirmwareUpload();
  assert.equal(posts.length,1);
  assert.equal(posts[0].env,environment);
  assert.equal(posts[0].resetNvs,false);
  assert.equal(disconnects,1);
  assert.equal(connects,hotspot ? 0 : 1);
  assert.equal(restores,0);
  if(hotspot){
    assert.match(nodes.firmwareUploadStatus.textContent,/perangkat belum diverifikasi/);
    assert.match(nodes.firmwareUploadStatus.textContent,/Dataset Wireless dan Connect GLD/);
    const title = datasetSuffix === '_dataset_replay_wifi' ? 'Hotspot buffer 5 menit (tahap 2)' : 'Hotspot Dataset 500 ms (mode khusus)';
    assert(read('apps/gld-operator/index.html').includes(`value="${value}">GLD1 Model ${number} — ${title}`));
  }
}
async function hubUpload(hotspot) {
  let verified=0;
  const nodes = new Proxy({}, {get(object,key){return object[key] ||= element();}});
  const result = hotspot ? receiptFor(`gld_model_1${datasetSuffix}`) : {selectedEnvironment:'gld_model_1',readback:{info:{}}};
  const context = vm.createContext({$:id=>nodes[id],notice:element(),uploadProgress:0,uploadLines:[],
    active:'gld',lastTestReport:{ok:true},testReportsByDevice:{gld:{ok:true}},overview:{devices:{gld:{connected:true,info:{deviceId:'1001'}}}},
    uploadEventsReady:false,uploadFlashDone:false,uploadReadbackVerified:false,uploadSuccessShown:false,hotspotUploadReceipt:null,
    document:{createElement:()=>element()},window:{setTimeout(callback){callback();}},
    renderUploadProgress(){},setUploadBusy(){},openUploadEvents:async()=>{},closeUploadEvents(){},show(){},
    markReadbackVerified(){verified++;},api:async()=>result});
  for(const name of ['isPendingHotspotUpload','showHotspotUploadNextStep','runFirmwareUpload'])
    vm.runInContext(functionSource(hubSource,name),context);
  const returned = await context.runFirmwareUpload({device:'gld'});
  assert.equal(returned,result);
  assert.equal(verified,hotspot ? 0 : 1);
  if(hotspot){
    assert.equal(context.hotspotUploadReceipt,result);
    assert.equal(context.lastTestReport,null);
    assert.equal(context.testReportsByDevice.gld,null);
    assert.equal(context.overview.devices.gld.connected,false);
    assert.equal(context.overview.devices.gld.info,null);
    assert.equal(context.notice.appended.href,'http://127.0.0.1:5174/');
    assert.equal(context.isPendingHotspotUpload(receiptFor(`gld_model_4${datasetSuffix}`)),false);
  }
}
async function hubFollowup(hotspot, initial) {
  let refreshes=0, deviceTests=0;
  const result = hotspot ? receiptFor(`gld_model_3${datasetSuffix}`) : {readback:{info:{}}};
  const context = vm.createContext({active:'gld',overview:{devices:{gld:{port:'COM999'}}},$:()=>element(),
    initialFirmwareRequired:true,show(){},requestFirmwareUploadOptions:async()=>({model:`model_3${datasetSuffix}`}),
    runFirmwareUpload:async()=>result,refresh:async()=>{refreshes++;},testDevice:async()=>{deviceTests++;}});
  vm.runInContext(functionSource(hubSource,'isPendingHotspotUpload'),context);
  const name = initial ? 'initialFirmwareUpload' : 'manualFirmwareUpload';
  vm.runInContext(functionSource(hubSource,name),context);
  await context[name]();
  assert.equal(refreshes,hotspot ? 0 : 1);
  assert.equal(deviceTests,hotspot ? 0 : 1);
}
async function hotspotSelector(initial) {
  let dialog;
  const environment=`gld_model_1${datasetSuffix}`, value=`model_1${datasetSuffix}`;
  const context=vm.createContext({devices:{gld:{label:'GLD'}},Option:class{},
    overview:{firmwarePackageOptions:{gld:{models:[{value,environment,label:'GLD1 Model 1 Hotspot Dataset 500 ms'}],
      environments:{[value]:environment},packages:{[environment]:{available:true,firmwareVersion:'0.8.39',requiresNvsResetBeforeBoot:false}}}}},
    document:{body:{append(){}},createElement(){
      const nodes={};
      dialog={querySelector(id){return nodes[id] ||= element();},close(){this.closed=true;},remove(){},showModal(){},
        set innerHTML(value){this.html=value;}};
      return dialog;
    }}});
  vm.runInContext(functionSource(hubSource,'requestFirmwareUploadOptions'),context);
  const result=context.requestFirmwareUploadOptions({device:'gld',port:'COM999',initialFirmware:initial});
  const model=dialog.querySelector('#firmwareUploadModel');model.value=value;model.listeners.change();
  const reset=dialog.querySelector('#firmwareUploadReset');reset.checked=true;
  const accept=dialog.querySelector('#firmwareUploadAccept');
  accept.onclick({preventDefault(){}});
  assert.equal(dialog.closed,undefined);
  assert.match(dialog.querySelector('#firmwareUploadError').textContent,/Reset NVS OFF/);
  if(initial){
    assert(dialog.html.includes(`value="${value}" disabled`));
    dialog.oncancel({preventDefault(){}});
    assert.equal(await result,null);
  } else {
    reset.checked=false;accept.onclick({preventDefault(){}});
    const selected=await result;
    assert.equal(selected.model,value);assert.equal(selected.resetNvs,false);
  }
}
(async()=>{
  for (const suffix of ['_dataset_wifi', '_dataset_replay_wifi']) {
  datasetSuffix = suffix;
  for(const number of [1,2,3]) await expert(number,true);
  await expert(2,false);
  for(const hotspot of [true,false]){
    await hubUpload(hotspot);
    await hubFollowup(hotspot,true);
    await hubFollowup(hotspot,false);
  }
  await hotspotSelector(false);await hotspotSelector(true);
  }
  console.log('PASS Stage1 and replay Expert exact model1/2/3 routing, no forced NVS reset or auto COM reconnect');
  console.log('PASS hotspot Simple Hub pending receipt, no verified claim/autorefresh/TestDevice; normal flows retained');
})().catch(error=>{console.error(error);process.exitCode=1;});
