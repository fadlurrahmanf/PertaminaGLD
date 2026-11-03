// Execute Expert's real upload action; all UI, timers and device I/O are inert.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '../../..');
const source = fs.readFileSync(path.join(root, 'apps/gld-operator/js/firmware.js'), 'utf8')
  .replace(/^import .*\r?\n/gm, '').replace(/\bexport /g, '');

function element() {
  return { value:'', checked:false, disabled:false, hidden:false, textContent:'',
    dataset:{}, classList:{toggle(){},add(){},remove(){}}, setAttribute(){}, focus(){},
    replaceChildren(){}, addEventListener(){} };
}

async function upload(environment, capabilities, {reset=false, info, connected=true, delayInfo=false}={}) {
  const nodes = new Proxy({}, {get(obj,key){return obj[key] ||= element();}});
  nodes.firmwareUploadPort.value='COM999';
  nodes.firmwareUploadModel.value=environment.replace(/^gld_/, '');
  nodes.firmwareUploadEnv.value=environment;
  nodes.firmwareResetNvs.checked=reset;
  const manifest = {environment, capabilities, firmwareVersion:'1.2.3', schemaVersion:2,
    packageType:'pertamina-gld-prebuilt-firmware', deviceId:'ANY', chip:'esp32s3',
    flashFiles:[{path:'firmware.bin'}]};
  const state = {bridgeAvailable:true, activeSlot:1, manifest,
    manifestPackageFiles:new Map([['firmware.bin','BASE64']])};
  const posts=[], errors=[];
  let connects=0, disconnects=0, clock=0;
  const readback = info === undefined ? {deviceId:'1001',firmwareVersion:'1.2.3'} : info;
  const context=vm.createContext({
    console, Map, Option:class{}, state, $:id=>nodes[id], elements:{portSelect:element()},
    Date:{now:()=>clock}, setTimeout(fn,ms){clock+=ms;if(delayInfo && clock>=200) state.info=readback;fn();},
    appendLog(){}, switchTab(){}, showBanner(message, kind){if(kind==='error') errors.push(message);},
    getField:()=> '1001', requireUnlock:async()=>true, updateSelectedPortDetail(){},
    disconnectSerial:async()=>{disconnects++;state.connected=false;state.info=null;},
    connectSerial:async()=>{connects++;state.connected=connected;state.info=delayInfo?null:readback;},
    restoreGldConfigAfterReset:async()=>{throw new Error('NVS restore must not run');},
    bridgeFetch:async(url,options)=>{assert.equal(url,'/api/firmware/upload');posts.push(JSON.parse(options.body));return {nvsReset:false};}
  });
  vm.runInContext(source,context);
  await context.performFirmwareUpload();
  return {nodes,state,posts,errors,connects,disconnects,clock};
}

(async()=>{
  for(const model of [1,2,3]) {
    const env=`gld_model_${model}_dataset_workflow_wifi`;
    const result=await upload(env,{nativeSerial:true,datasetWifi:true},{delayInfo:true});
    assert.equal(result.connects,1);
    assert.equal(result.disconnects,1);
    assert.equal(result.errors.length,0);
    assert.match(result.nodes.firmwareUploadStatus.textContent,/Connected to COM999/);
    assert.equal(result.posts[0].resetNvs,false);
    assert.equal(result.posts[0].env,env);
    assert(result.clock>=200,'waits for fresh GET_INFO');
    for(const caps of [undefined,{nativeSerial:false},{nativeSerial:'true'}]) {
      const legacy=await upload(env,caps);
      assert.equal(legacy.connects,0);
      assert.match(legacy.nodes.firmwareUploadStatus.textContent,/belum diverifikasi/);
    }
    for(const suffix of ['dataset_wifi','dataset_replay_wifi']) {
      assert.equal((await upload(`gld_model_${model}_${suffix}`,{nativeSerial:true})).connects,0);
    }
    const reset=await upload(env,{nativeSerial:true},{reset:true});
    assert.equal(reset.posts.length,0);
    assert.equal(reset.disconnects,0);
  }
  for(const options of [
    {info:{deviceId:'1002',firmwareVersion:'1.2.3'}},
    {info:{deviceId:'1001',firmwareVersion:'0.0.0'}},
    {info:null}, {connected:false}
  ]) {
    const failed=await upload('gld_model_1_dataset_workflow_wifi',{nativeSerial:true},options);
    assert.equal(failed.connects,1);
    assert.equal(failed.errors.length,1);
    assert.match(failed.nodes.firmwareUploadStatus.textContent,/Upload gagal: Flash selesai/);
  }
  const normal=await upload('gld_model_1',undefined);
  assert.equal(normal.connects,1);
  assert.equal(normal.errors.length,0);
  console.log('PASS Expert native workflow upload: three models, COM readback, identity/version failures, bounded timeout, legacy paths and NVS protection');
})().catch(error=>{console.error(error);process.exitCode=1;});
