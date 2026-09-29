// Execute real Expert/Simple Hub functions with inert UI/network stubs.
// No serial, device upload, service restart or hardware access.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '../../..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const manifest = {
  environment: 'gld_model_3', firmwareVersion: '0.8.38',
  source: { gitCommit: '69a493c32d2500134a21e029820cd4addea1794a' },
  schemaVersion: 2, packageType: 'pertamina-gld-prebuilt-firmware',
  deviceId: 'ANY', chip: 'esp32s3', flashFiles: [{ path: 'firmware.bin' }]
};
function element() {
  return { value:'', checked:false, disabled:false, hidden:false, textContent:'',
    dataset:{}, listeners:{}, classList:{toggle(){},add(){},remove(){}},
    setAttribute(){}, focus(){this.focused=true;}, replaceChildren(){},
    addEventListener(event, fn){this.listeners[event]=fn;} };
}
async function expert() {
  const nodes = new Proxy({}, {get(obj,key){return obj[key] ||= element();}});
  nodes.firmwareUploadPort.value='COM999';
  nodes.firmwareUploadEnv.value='gld';
  nodes.firmwareUploadModel.value='model_3';
  const posts=[];
  const urls=[];
  let disconnects=0;
  const context=vm.createContext({
    console, Map, Option:class{}, state:{activeSlot:1,bridgeAvailable:true}, $:id=>nodes[id],
    elements:{portSelect:element()}, appendLog(){},switchTab(){},showBanner(){},
    getField:()=> '1001', requireUnlock:async()=>true, updateSelectedPortDetail(){},
    disconnectSerial:async()=>{disconnects++;}, connectSerial:async()=>{},
    restoreGldConfigAfterReset:async()=>({status:'ok'}),
    bridgeFetch:async(url,options)=>{
      urls.push(url);
      if(options){posts.push(JSON.parse(options.body));return {nvsReset:true};}
      return {manifest,packageFiles:{'firmware.bin':'BASE64'}};
    }
  });
  vm.runInContext(read('apps/gld-operator/js/firmware.js')
    .replace(/^import .*\r?\n/gm,'').replace(/\bexport /g,''),context);
  assert.equal(context.requiresGld1DowngradeReset(manifest),true);
  for(const invalid of [
    {...manifest,firmwareVersion:'0.8.34'},
    {...manifest,environment:'gld_model_2'},
    {...manifest,environment:'gld_v3'},
    {...manifest,source:{gitCommit:'a'.repeat(40)}}
  ]) assert.equal(context.requiresGld1DowngradeReset(invalid),false);
  await context.loadBuiltinPackage('gld');
  assert.equal(urls.at(-1),'/api/firmware/package?env=gld_model_3');
  assert.equal(context.state.manifest.environment,'gld_model_3');
  assert.equal(nodes.firmwareResetNvs.checked,false);
  assert.equal(nodes.firmwareUploadConfirmBtn.disabled,true);
  await context.performFirmwareUpload();
  assert.equal(posts.length,0);
  assert.equal(disconnects,0);
  nodes.firmwareResetNvs.checked=true;
  context.updateFirmwareResetGuard();
  await context.performFirmwareUpload();
  assert.equal(posts[0].env,'gld_model_3');
  assert.equal(posts[0].resetNvs,true);
  assert.equal(posts[0].resetNvsConfirmation,'RESET NVS');
  assert.match(nodes.firmwareUploadStatus.textContent,/nulling 8\/8/);
  assert.match(read('apps/gld-operator/index.html'),/value="model_3">Model 3 — Board 3/);
  console.log('PASS Model 3 Expert: exact package routing, guard scope, explicit consent and upload payload');
}
async function simple() {
  let dialog;
  const context=vm.createContext({
    devices:{gld:{label:'GLD1'}}, Option:class{},
    overview:{firmwarePackageOptions:{gld:{
      models:[{value:'model_3',label:'Model 3 - Board 3',environment:'gld_model_3'}],
      environments:{model_3:'gld_model_3'},
      packages:{gld_model_3:{available:true,firmwareVersion:'0.8.38',requiresNvsResetBeforeBoot:true}}
    }}},
    document:{body:{append(){}},createElement(){
      const nodes={};
      dialog={querySelector(id){return nodes[id] ||= element();},
        close(){this.closed=true;}, remove(){}, showModal(){},
        set innerHTML(html){this.html=html;}};
      return dialog;
    }}
  });
  const source=read('apps/operator-hub/public/js/hub.js');
  const start=source.indexOf('function requestFirmwareUploadOptions(');
  assert.notEqual(start,-1);
  vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),context);
  const resultPromise=context.requestFirmwareUploadOptions({device:'gld',port:'COM999',initialFirmware:false});
  const model=dialog.querySelector('#firmwareUploadModel');
  model.value='model_3';
  model.listeners.change();
  assert.equal(dialog.querySelector('#firmwareUploadResetWarning').hidden,false);
  const accept=dialog.querySelector('#firmwareUploadAccept');
  accept.onclick({preventDefault(){}});
  assert.equal(dialog.closed,undefined);
  assert.equal(dialog.querySelector('#firmwareUploadReset').focused,true);
  dialog.querySelector('#firmwareUploadReset').checked=true;
  accept.onclick({preventDefault(){}});
  const result=await resultPromise;
  assert.equal(result.model,'model_3');
  assert.equal(result.resetNvs,true);
  assert.equal(result.resetNvsConfirmation,'RESET NVS');
  console.log('PASS Model 3 Simple Hub: exact model selection, explicit reset consent and confirmation payload');
}
(async()=>{await expert();await simple();})().catch(err=>{console.error(err);process.exitCode=1;});
