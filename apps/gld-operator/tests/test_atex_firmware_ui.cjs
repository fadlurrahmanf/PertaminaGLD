// Inert DOM/bridge mocks only. No serial ports, sockets, or flash operations.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '../../..');
const source = fs.readFileSync(path.join(root, 'apps/gld-operator/js/firmware.js'), 'utf8')
  .replace(/^import .*\r?\n/gm, '').replace(/\bexport /g, '');
function element() { return {value:'',checked:false,disabled:false,hidden:false,textContent:'',dataset:{},
  classList:{toggle(){},add(){},remove(){}},setAttribute(){},focus(){},replaceChildren(){},addEventListener(){}}; }
async function run() {
  const nodes = new Proxy({}, {get(o,k){return o[k] ||= element();}});
  nodes.firmwareUploadEnv.value = 'gld_atex';
  nodes.firmwareUploadPort.value = 'COM999';
  const state = {activeSlot:1, bridgeAvailable:true, connected:true};
  let model = 1, packageValid = true, infoBoard = 'GLD ATEX MotherBoardGLDVer2', nonceBoard = infoBoard, statusProfile = 'profile-1';
  let lastCommand = '', commandWrites = [], packageGets = 0, posts = 0;
  let stream = 'stream-one', changeAt = '', infoStatusChecks = 0, allStatusChecks = 0, nonceVersion = '0.8.30', wrongNonce = false, clock = 0;
  const ctx = vm.createContext({Map, Uint8Array, crypto:{getRandomValues(a){a.fill(0xab);return a;}},
    Date:{now:()=>clock},setTimeout(fn,ms){clock+=ms;fn();}, Option:class{}, state, $:id=>nodes[id], elements:{portSelect:element()},
    appendLog(){}, switchTab(){}, showBanner(){}, getField:()=> '1001', requireUnlock:async()=>true,
    connectSerial:async()=>{}, disconnectSerial:async()=>{}, updateSelectedPortDetail(){},
    bridgeFetch:async(url,options)=>{
      if (url.startsWith('/api/firmware/package')) {
        packageGets++;
        if (!packageValid) throw Error('validator rejected');
        const env = `gld_atex_model_${model}_dataset_workflow_wifi`, hash='a'.repeat(64);
        return {manifest:{environment:env, firmwareVersion:'0.8.30', deviceId:'ANY', boardProfile:'GLD ATEX MotherBoardGLDVer2 / GPIO7 fan',
          capabilities:{nativeSerial:true,datasetWifi:true},flashFiles:[{path:'firmware.bin',sha256:hash}]},
          packageFiles:{'firmware.bin':'synthetic'}, atexEvidence:{environment:env,model,profileId:`profile-${model}`,firmwareSha256:hash,boardProfile:'GLD ATEX MotherBoardGLDVer2 / GPIO7 fan'}};
      }
      if (url.startsWith('/api/serial/status')) {
        if (++allStatusChecks === 2 && changeAt === 'before-challenge') stream='stream-two';
        if (lastCommand === 'GET_INFO' && ++infoStatusChecks === 3 && changeAt === 'between-info-status') stream='stream-two';
        return {connected:true,port:'COM999',telemetryStream:stream};
      }
      if (url.startsWith('/api/serial/recent')) {
        if (!url.includes('&after=')) return {sequence:100};
        const info = lastCommand==='GET_INFO';
        const request = info ? null : JSON.parse(lastCommand.slice('GET_ATEX_IDENTITY_JSON '.length));
        const data=info ? {deviceId:'1001',firmwareVersion:'0.8.30',boardProfile:infoBoard}
          : {nonce:wrongNonce?'0'.repeat(32):request.nonce,deviceId:'1001',boardProfile:nonceBoard,modelProfileId:statusProfile,firmwareVersion:nonceVersion};
        return {lines:[{sequence:101,line:`${info?'GLD_INFO_JSON':'GLD_ATEX_IDENTITY_JSON'} ${JSON.stringify(data)}`} ]};
      }
      if (url === '/api/serial/atex-identity') {
        const body=JSON.parse(options.body);
        assert.equal(body.targetDeviceId,'1001');
        commandWrites.push('LEASED_NONCE');
        if (wrongNonce) throw Error('ATEX nonce identity response timed out');
        if (changeAt==='before-challenge' || changeAt==='after-status-write') stream='stream-two';
        return {ok:true,telemetryStream:stream,identity:{nonce:'ab'.repeat(16),deviceId:'1001',boardProfile:nonceBoard,modelProfileId:statusProfile,firmwareVersion:nonceVersion}};
      }
      if (url === '/api/serial/write') {
        lastCommand=JSON.parse(options.body).line; commandWrites.push(lastCommand);
        if(lastCommand==='GET_INFO') {infoStatusChecks=0; if(changeAt==='after-info-write') stream='stream-two';}
        if(lastCommand.startsWith('GET_ATEX_IDENTITY_JSON ') && changeAt==='after-status-write') stream='stream-two';
        return {ok:true};
      }
      if (url === '/api/firmware/upload') {posts++; throw Error('must not flash');}
      throw Error('unexpected bridge call: '+url);
    }});
  vm.runInContext(source,ctx);
  // Real production gate: even an otherwise valid package is not fetched or
  // exposed for flashing before a reviewed release change.
  nodes.firmwareUploadModel.value='model_1_dataset_workflow_wifi';
  await ctx.loadBuiltinPackage('gld_atex');
  assert.equal(state.manifest,null);
  assert.equal(nodes.firmwareUploadConfirmBtn.disabled,true);
  assert.equal(packageGets,0);
  await ctx.performFirmwareUpload();
  assert.equal(posts,0);
  // Exercise the staged code in the isolated VM only; production stays gated.
  vm.runInContext('Object.values(ATEX_MODEL_SLOTS).forEach(slot => slot.available = true)',ctx);
  for (model=1; model<=3; model++) {
    nodes.firmwareUploadModel.value=`model_${model}_dataset_workflow_wifi`;
    await ctx.loadBuiltinPackage('gld_atex');
    const env=`gld_atex_model_${model}_dataset_workflow_wifi`;
    assert.equal(state.manifest.environment,env);
    assert.equal(ctx.hasNativeWorkflowSerial(state.manifest),true);
    assert.equal(ctx.isDatasetWifiEnvironment(env),true);
    assert.equal(nodes.firmwareUploadConfirmBtn.disabled,false);
  }
  assert.equal(posts,0);
  packageValid=false;
  await ctx.loadBuiltinPackage('gld_atex');
  assert.equal(state.manifest,null);
  assert.equal(nodes.firmwareUploadConfirmBtn.disabled,true);
  assert.match(nodes.firmwareUploadPackage.textContent,/validator rejected/);
  await ctx.performFirmwareUpload();
  assert.equal(posts,0);
  packageValid=true; model=1;
  nodes.firmwareUploadModel.value='model_1_dataset_workflow_wifi';
  await ctx.loadBuiltinPackage('gld_atex');
  statusProfile='profile-1'; infoBoard='GLD ATEX MotherBoardGLDVer2';
  await ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1);
  assert.equal(commandWrites.at(-1),'LEASED_NONCE');
  infoBoard='stale old board';
  const beforeStale=commandWrites.length;
  await ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1);
  assert.equal(commandWrites.length,beforeStale+1,'ATEX proof must not depend on stale GET_INFO');
  infoBoard='GLD ATEX MotherBoardGLDVer2';
  nonceVersion='0.8.29';
  await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1), /versi firmware nonce ATEX/);
  nonceVersion='0.8.30'; wrongNonce=true;
  await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1), /nonce identity response timed out/);
  wrongNonce=false;
  for (const timing of ['before-challenge', 'after-status-write']) {
    stream='stream-one'; changeAt=timing; lastCommand=''; allStatusChecks=0;
    await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1), /Koneksi serial ATEX berubah/,
      `same COM must reject changed generation at ${timing}`);
  }
  stream=undefined; changeAt=''; lastCommand='';
  await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1), /Identitas koneksi serial ATEX tidak tersedia/);
  // Existing GLD1 readback does not acquire the new ATEX stream requirement.
  await ctx.verifyNativeWorkflowReadback({environment:'gld_model_1_dataset_workflow_wifi',firmwareVersion:'0.8.30'},'1001','COM999',1);
  stream='stream-one'; lastCommand='';
  nonceBoard='GLD2';
  await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1),/identitas board atau ID ATEX/);
  infoBoard='GLD2';
  vm.runInContext('validateManifestForUpload = () => ""', ctx);
  await ctx.performFirmwareUpload();
  assert.equal(posts,0,'legacy board identity must fail before flash');
  assert.match(nodes.firmwareUploadStatus.textContent,/identitas board ATEX belum terbukti/);
  infoBoard='GLD ATEX MotherBoardGLDVer2'; nonceBoard=infoBoard; statusProfile='other';
  await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1),/profil model/);
  state.activeSlot=2;
  await assert.rejects(ctx.verifyNativeWorkflowReadback(state.manifest,'1001','COM999',1),/Slot GLD berubah/);
  assert.equal(ctx.hasNativeWorkflowSerial({environment:'gld_model_1_dataset_workflow_wifi',capabilities:{nativeSerial:true}}),true);
  assert.equal(posts,0); assert(packageGets>=5);
  console.log('PASS ATEX release gate, same-COM stream pin and board/model readback; GLD1 native gate retained');
}
run().catch(err=>{console.error(err);process.exitCode=1;});
