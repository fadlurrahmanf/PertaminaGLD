const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../../..');
const src=fs.readFileSync(path.join(root,'apps/gld-operator/js/firmware.js'),'utf8').replace(/^import .*\r?\n/gm,'').replace(/\bexport /g,'');
async function run(opts={}) {
 let calls=[];
 const state={activeSlot:1};
 const context=vm.createContext({state,console,
 bridgeFetch:async (url,config={})=>{
  calls.push(url);
  if(url.startsWith('/api/serial/status')) return {connected:true,port:opts.wrongPort?'COM888':'COM999',telemetryStream:'stream-a'};
  if(url==='/api/serial/atex-identity') {
   const payload=JSON.parse(config.body);
   assert.deepEqual(payload,{slot:1,port:'COM999',targetDeviceId:'1001'});
   if(opts.stale) throw Error('backend nonce timeout');
   const identity={nonce:opts.badNonce?'bad':'ab'.repeat(16),boardProfile:opts.board||'GLD ATEX MotherBoardGLDVer2',deviceId:opts.id||'1001',modelProfileId:opts.model||'profile-1',firmwareVersion:opts.version||'1.2.3'};
   if(opts.omitVersion) delete identity.firmwareVersion;
   return {ok:true,telemetryStream:opts.streamChange?'stream-b':'stream-a',identity};
  }
  throw Error('unexpected stale GET_INFO or write: '+url);
 },isGldId:id=>/^[0-9A-F]{4}$/.test(id)});
 vm.runInContext(src,context);vm.runInContext('verifiedAtexPackage={environment:"gld_atex_model_1_dataset_workflow_wifi",profileId:"profile-1"}',context);
 let error=null;try {await context.verifyNativeWorkflowReadback({environment:'gld_atex_model_1_dataset_workflow_wifi',firmwareVersion:'1.2.3'},'1001','COM999',1)} catch(e){error=e}
 return {error,calls};
}
(async()=>{
 const good=await run();assert.equal(good.error,null);assert.deepEqual(good.calls,['/api/serial/status?slot=1','/api/serial/atex-identity']);
 for(const opts of [{stale:true},{badNonce:true},{id:'1002'},{board:'GLD2'},{model:'profile-2'},{version:'1.2.2'},{omitVersion:true},{streamChange:true},{wrongPort:true}]) {let result=await run(opts);assert(result.error,JSON.stringify(opts));}
 console.log('PASS Expert leased nonce identity, stream/port, board/device/model and stale rejection');
})().catch(e=>{console.error(e);process.exitCode=1});
