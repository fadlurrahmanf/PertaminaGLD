const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../js/gw-main.js'), 'utf8');
const section = source.slice(source.indexOf('let uploadPackageRequest'), source.indexOf('// ---- Event wiring'));
const nodes = new Proxy({}, { get(o, k) { return o[k] ||= {value:'', disabled:false, checked:false, dataset:{}, setAttribute(){}, replaceChildren(){}}; } });
nodes.firmwareUploadPort.value = 'COM99';
const state = {manifest:null, manifestFiles:new Map(), activeSlot:1, serialConnected:false};
const elements = {fwTargetId:{value:'0001'}, portSelect:{value:'COM99'}};
let requested = [], sent = [];
const context = vm.createContext({state, elements, manualUploadPackage:null, Map, Object, Option:class{},
  $: id => nodes[id], DEFAULT_GATEWAY_ID:'0001', normalizeHexId:x=>x,
  switchTab(){}, appendLog(){}, showBanner(){}, setFirmwareUploadDialog(){},
  setFirmwareUploadStatus(s){nodes.firmwareUploadStatus.textContent=s;},
  disconnectSerial:async()=>{}, connectSerial:async()=>{},
  bridgeFetch:async(url, opts)=>{
    if (opts) { sent.push(JSON.parse(opts.body)); return {firmwareVersion:'1.0.0'}; }
    requested.push(url);
    const env = new URL('http://localhost'+url).searchParams.get('env');
    if (env === 'gw_large_tls') throw Error('missing');
    return {manifest:{environment:env, firmwareVersion:'1.0.0', boardProfile:env},packageFiles:{'firmware.bin':'abc'}};
  }
});
vm.runInContext(section, context);
(async()=>{
  for (const env of ['gw_small','gw_small_tls','gw_large']) {
    nodes.firmwareUploadProfile.value=env;
    await context.loadUploadProfile();
    assert.equal(state.manifest.environment,env);
    assert.equal(nodes.firmwareUploadConfirmBtn.disabled,false);
    assert.match(requested.at(-1),/package=current-source-20261116/);
    await context.uploadFirmware();
    assert.equal(sent.at(-1).env,env);
    assert.equal(sent.at(-1).manifest.environment,env);
    assert.equal(sent.at(-1).resetNvs,false);
  }
  nodes.firmwareUploadProfile.value='gw_large_tls';
  await context.loadUploadProfile();
  assert.equal(state.manifest,null);
  assert.equal(nodes.firmwareUploadConfirmBtn.disabled,true);
  assert.match(nodes.firmwareUploadStatus.textContent,/missing/);
  console.log('Gateway upload profile contract: PASS');
})().catch(e=>{console.error(e); process.exitCode=1;});
