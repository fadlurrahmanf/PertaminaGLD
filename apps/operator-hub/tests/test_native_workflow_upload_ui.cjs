// Execute Expert's real upload action; UI, timers and all device I/O are inert.
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
const INFO={deviceId:'1001',firmwareVersion:'1.2.3'};
async function upload(environment, capabilities, options={}) {
  const {reset=false, preInfo=INFO, postInfo=INFO, connected=true, delayInfo=false,
    manualId='1003', packageId='ANY', wrongPort=false, apiError=false,
    slotChange=false, staleOnly=false} = options;
  const nodes = new Proxy({}, {get(obj,key){return obj[key] ||= element();}});
  nodes.firmwareUploadPort.value='COM999';
  nodes.firmwareUploadModel.value=environment.replace(/^gld_/, '');
  nodes.firmwareUploadEnv.value=environment;
  nodes.firmwareResetNvs.checked=reset;
  nodes.targetDeviceId.value=manualId;
  const manifest = {environment, capabilities, firmwareVersion:'1.2.3', schemaVersion:2,
    packageType:'pertamina-gld-prebuilt-firmware', deviceId:packageId, chip:'esp32s3',
    flashFiles:[{path:'firmware.bin'}]};
  // A stale previous-device SSE snapshot must never decide expected identity.
  const state = {bridgeAvailable:true, activeSlot:1, manifest, connected:true,
    info:{deviceId:'1003',firmwareVersion:'1.2.3'},
    manifestPackageFiles:new Map([['firmware.bin','BASE64']])};
  const posts=[], errors=[], logs=[], writes=[];
  let connects=0, disconnects=0, clock=0, sequence=17, fresh=null, sentAt=0;
  const context=vm.createContext({
    console, Map, Option:class{}, state, $:id=>nodes[id], elements:{portSelect:element()},
    Date:{now:()=>clock}, setTimeout(fn,ms){clock+=ms;fn();},
    appendLog(message){logs.push(message);}, switchTab(){},
    showBanner(message, kind){if(kind==='error') errors.push(message);},
    getField:id=>nodes[id].value, requireUnlock:async()=>true, updateSelectedPortDetail(){},
    disconnectSerial:async()=>{disconnects++;state.connected=false;state.info=null;},
    connectSerial:async()=>{connects++;state.connected=connected;state.info={deviceId:'1003',firmwareVersion:'1.2.3'};},
    restoreGldConfigAfterReset:async()=>{throw new Error('NVS restore must not run');},
    bridgeFetch:async(url,options)=>{
      if(apiError && url.startsWith('/api/serial/status')) throw new Error('synthetic API error');
      if(url.startsWith('/api/serial/status')) {
        assert.match(url,/slot=1/);
        return {connected,port:wrongPort?'COM888':'COM999'};
      }
      if(url.startsWith('/api/serial/recent')) {
        assert.match(url,/slot=1/);
        if(!url.includes('&after=')) return {sequence,lines:[{sequence,line:'GLD_INFO_JSON '+JSON.stringify({deviceId:'1003',firmwareVersion:'old'})}]};
        const after=Number(new URL('http://localhost'+url).searchParams.get('after'));
        const ready=fresh && (!delayInfo || clock-sentAt>=200);
        return {sequence,lines:ready?[fresh]:[{sequence:after,line:'GLD_INFO_JSON '+JSON.stringify({deviceId:'1003',firmwareVersion:'old'})}]};
      }
      if(url==='/api/serial/write') {
        const payload=JSON.parse(options.body);writes.push(payload);
        assert.equal(payload.slot,1);assert.equal(payload.line,'GET_INFO');
        const info=posts.length?postInfo:preInfo;sentAt=clock;
        fresh=info && !staleOnly?{sequence:++sequence,line:'GLD_INFO_JSON '+JSON.stringify(info)}:null;
        if(slotChange) state.activeSlot=2;
        return {ok:true};
      }
      assert.equal(url,'/api/firmware/upload');
      posts.push(JSON.parse(options.body));
      return {nvsReset:false};
    }
  });
  vm.runInContext(source,context);
  await context.performFirmwareUpload();
  return {nodes,state,posts,errors,logs,writes,connects,disconnects,clock};
}

(async()=>{
  for(const model of [1,2,3]) {
    const env=`gld_model_${model}_dataset_workflow_wifi`;
    const result=await upload(env,{nativeSerial:true,datasetWifi:true},{delayInfo:true});
    assert.equal(result.connects,2,'read fresh identity both before and after flash');
    assert.equal(result.disconnects,1);
    assert.equal(result.errors.length,0);
    assert.match(result.nodes.firmwareUploadStatus.textContent,/Connected to COM999\. GLD 1001/);
    assert.equal(result.posts[0].resetNvs,false);
    assert.equal(result.posts[0].env,env);
    assert.equal(result.posts[0].targetDeviceId,'1001','fresh device ID, not cached1003');
    assert.equal(result.posts[0].slot,1);
    assert.equal(result.nodes.targetDeviceId.value,'1003','manual Inject ID intent unchanged');
    assert.deepEqual(result.writes.map(x=>x.line),['GET_INFO','GET_INFO'],'no SET_DEVICE_ID');
    assert(result.logs.some(x=>/UPLOAD_ID_DETECTED COM999 GLD 1001/.test(x)));
    assert(result.clock>=400,'waits for fresh explicit GET_INFO in both phases');

    // Blank/unresponsive old firmware can still be recovered with an ANY
    // package, but must retain a visible preservation-unverified warning.
    const recovery=await upload(env,{nativeSerial:true},{preInfo:null});
    assert.equal(recovery.posts.length,1);assert.equal(recovery.errors.length,0);
    assert.equal(recovery.nodes.firmwareUploadStatus.dataset.state,'warn');
    assert.match(recovery.nodes.firmwareUploadStatus.textContent,/pelestarian ID belum dapat dibandingkan/);
    assert.equal(recovery.clock,8000,'pre-flash unknown-ID wait is bounded');
    assert.equal(recovery.nodes.targetDeviceId.value,'1003');

    for(const caps of [undefined,{nativeSerial:false},{nativeSerial:'true'}]) {
      const legacy=await upload(env,caps);
      assert.equal(legacy.connects,0);assert.equal(legacy.writes.length,0);
      assert.match(legacy.nodes.firmwareUploadStatus.textContent,/belum diverifikasi/);
    }
    for(const suffix of ['dataset_wifi','dataset_replay_wifi']) {
      assert.equal((await upload(`gld_model_${model}_${suffix}`,{nativeSerial:true})).connects,0);
    }
    const reset=await upload(env,{nativeSerial:true},{reset:true});
    assert.equal(reset.posts.length,0);assert.equal(reset.disconnects,0);assert.equal(reset.connects,0);
    const constrained=await upload(env,{nativeSerial:true},{packageId:'1003'});
    assert.equal(constrained.posts.length,0);assert.match(constrained.errors[0],/manifest deviceId 1003.*target ID 1001/);
    const constrainedUnknown=await upload(env,{nativeSerial:true},{packageId:'1003',preInfo:null});
    assert.equal(constrainedUnknown.posts.length,0);assert.match(constrainedUnknown.errors[0],/ber-ID khusus/);
    const constrainedMatch=await upload(env,{nativeSerial:true},{packageId:'1001'});
    assert.equal(constrainedMatch.posts.length,1);assert.equal(constrainedMatch.errors.length,0);
  }
  for(const options of [
    {postInfo:{deviceId:'1002',firmwareVersion:'1.2.3'}},
    {postInfo:{deviceId:'1001',firmwareVersion:'0.0.0'}},
    {postInfo:{deviceId:'invalid',firmwareVersion:'1.2.3'}},
    {postInfo:null}
  ]) {
    const failed=await upload('gld_model_1_dataset_workflow_wifi',{nativeSerial:true},options);
    assert.equal(failed.posts.length,1);assert.equal(failed.errors.length,1);
    assert.match(failed.nodes.firmwareUploadStatus.textContent,/Flash selesai, verifikasi belum berhasil/);
    assert(failed.clock<=35000,'bounded post-flash readback');
  }
  for(const options of [{connected:false},{wrongPort:true},{apiError:true},{slotChange:true},
    {preInfo:{deviceId:'invalid',firmwareVersion:'old'}}]) {
    const failed=await upload('gld_model_1_dataset_workflow_wifi',{nativeSerial:true},options);
    assert.equal(failed.posts.length,0,'port/slot/API/invalid-identity failures must not flash');
    assert.equal(failed.errors.length,1);
  }
  const stale=await upload('gld_model_1_dataset_workflow_wifi',{nativeSerial:true},{staleOnly:true});
  assert.equal(stale.posts.length,1,'ANY recovery permitted');
  assert.equal(stale.errors.length,1,'retained old log/SSE identity cannot verify recovery');
  assert(stale.clock<=43000);
  const normal=await upload('gld_model_1',undefined);
  assert.equal(normal.connects,1);assert.equal(normal.errors.length,0);
  assert.equal(normal.posts[0].targetDeviceId,'1003','ordinary upload semantics retained');
  assert.equal(normal.writes.length,0);
  console.log('PASS Expert upload: all3 fresh selected-COM identity, stale form/log/SSE exclusion, preserved Inject-ID intent, explicit ANY recovery, constrained-ID and port/slot/API guards, bounded readback, legacy/ordinary/NVS protection');
})().catch(error=>{console.error(error);process.exitCode=1;});
