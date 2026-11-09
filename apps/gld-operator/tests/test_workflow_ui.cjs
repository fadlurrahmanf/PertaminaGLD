// Actual wizard module in a VM. Transport and DOM are inert; browser proof separate.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function node(){return {value:'',checked:false,disabled:false,hidden:false,textContent:'',dataset:{},style:{},children:[],listeners:{},clientWidth:0,clientHeight:0,
 get options(){return this.children;},replaceChildren(...items){this.children=items;},append(...items){this.children.push(...items);},
 setAttribute(name,value){this[name]=value;},addEventListener(name,fn){this.listeners[name]=fn;},click(){},classList:{contains(){return false;}}};}
async function settle(){for(let i=0;i<20;i++)await Promise.resolve();}
(async()=>{
 const nodes=new Map(),steps=new Map(),events={},calls=[],notices=[];
 const get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
 for(const name of ['connection','file','fields','mode','label'])steps.set(name,node());
 get('wfLabel').value='clear_air_test';get('wfModeDirect').checked=true;get('wfModeReplay').checked=false;get('wfGain').checked=get('wfSensorStatus').checked=false;
 let backend={revision:0,state:'idle',devices:[],history:[],count:0,steps:{},fields:{gain:false,status:false,prediction:false,timing:false}};
 const context={document:{getElementById:get,createElement:node,createTextNode:t=>({textContent:t}),querySelector:s=>steps.get(s.match(/"(.*?)"/)[1])},
  Option:class{constructor(text,value){this.textContent=text;this.value=value;}},ResizeObserver:class{observe(){}},Event:class{},
  window:{addEventListener:(name,fn)=>events[name]=fn,setInterval(){},setTimeout(){},devicePixelRatio:1},
  drawOneChart(){},formatGas:n=>'gas-'+n,CHART_COLORS:Array(8).fill('#aaa'),legacyState:{bridgeAvailable:true},showAlert:(...args)=>{notices.push(args);return Promise.resolve();},
  bridgeFetch:async(route,options)=>{calls.push({route,body:options?JSON.parse(options.body):null});
   if(route.endsWith('/lock'))backend={...backend,revision:backend.revision+1,locked:true};
   if(route.endsWith('/pause'))backend={...backend,revision:backend.revision+1,state:'paused'};
   if(route.endsWith('/resume'))backend={...backend,revision:backend.revision+1,state:'recording'};
   if(route.endsWith('/start'))backend={...backend,revision:backend.revision+1,state:'recording',verification:{verified:false}};
   if(route.endsWith('/stop'))backend={...backend,revision:backend.revision+1,state:'stop_pending',count:4,verification:{verified:false}};
   return structuredClone(backend);
  }};
 vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../js/dataset-workflow.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,'');
 vm.runInContext(source+'\nglobalThis.control={apply,action,sync,render,get:()=>snapshot};',context);
 context.initDatasetWorkflow();await settle();
 assert(!get('wfGain').checked&&!get('wfSensorStatus').checked);assert(!nodes.has('wfTiming'),'technical timing is internal only');assert(get('wfControls').hidden);assert(get('wfLock').disabled);assert(!get('wfReset').disabled);
 assert([...steps.values()].every(s=>s.dataset.ready==='false'),'no later default may be green before connection');
 assert(get('wfGain').disabled&&get('wfModeDirect').disabled&&get('wfLabel').disabled);
 assert(get('wfDefaultFile').disabled,'default destination requires GLD readiness');
 context.control.apply({...backend,steps:{scan:true,device:true,connection:true,file:false,fields:true,mode:true,label:true},connected:true,ready:true});
 assert.equal(steps.get('connection').dataset.ready,'true');assert([...steps.entries()].filter(([name])=>name!=='connection').every(([,s])=>s.dataset.ready==='false'),'file is the prerequisite for all remaining gates');
 backend={...backend,revision:1,state:'ready',devices:[{device_id:'1002',ssid:'GLD-DATASET-1002',name:'GLD-1002'}],selected_device_id:'1002',device_id:'1002',connected:true,ready:true,prediction_available:true,csv_path:'C:/synthetic/data.csv',label_timestamp:'07:35 Selasa 03/11/26',steps:{scan:true,device:true,...Object.fromEntries([...steps.keys()].map(k=>[k,true]))}};
 context.control.apply(backend);assert.equal(get('wfLabelStamp').textContent,'07:35 Selasa 03/11/26');assert(!get('wfPrediction').disabled);assert([...steps.values()].every(s=>s.dataset.ready==='true'));assert(!get('wfLock').disabled);
 assert(!get('wfDefaultFile').disabled,'default destination is available after Connect');
 await context.control.action('lock',{locked:true});
 assert.equal(calls.slice(-3)[0].route,'/api/dataset-workflow/configure');
 assert(!get('wfControls').hidden);assert(!get('wfPrimary').disabled);assert.equal(get('wfPrimaryLabel').textContent,'Start');assert(get('wfStop').disabled);assert(!get('wfPrimaryPlay').hidden&&get('wfPrimaryPause').hidden);
 assert(get('wfDevice').disabled&&get('wfLabel').disabled&&get('wfMode').disabled);
 await get('wfPrimary').listeners.click();await settle();assert.equal(calls.filter(c=>c.route.endsWith('/start')).length,1);assert.equal(get('wfPrimaryLabel').textContent,'Pause');assert(!get('wfPrimary').disabled&&!get('wfStop').disabled);assert(get('wfPrimaryPlay').hidden&&!get('wfPrimaryPause').hidden);assert(get('wfLock').disabled&&get('wfReset').disabled);
 backend={...backend,configuration_frozen:true,ledger_path:'C:/synthetic/ledger.jsonl',segment_id:1};context.control.apply(backend);
 assert.equal(get('wfPrimaryLabel').textContent,'Pause','primary pauses the active first recording');
 await get('wfPrimary').listeners.click();await settle();assert.equal(get('wfPrimaryLabel').textContent,'Resume');assert(calls.some(c=>c.route.endsWith('/pause')));
 await get('wfPrimary').listeners.click();await settle();assert.equal(get('wfPrimaryLabel').textContent,'Pause');assert(calls.some(c=>c.route.endsWith('/resume')));
 backend={...backend,revision:backend.revision+1,state:'paused'};context.control.apply(backend);
 assert.equal(get('wfPrimaryLabel').textContent,'Resume');assert(!get('wfStop').disabled&&!get('wfReset').disabled);assert(get('wfLock').disabled);
 context.control.apply({...backend,revision:backend.revision-1,state:'recording'});assert.equal(get('wfPrimaryLabel').textContent,'Resume','stale update cannot resume UI');
 backend={...backend,revision:backend.revision+1,state:'recording'};context.control.apply(backend);
 await context.control.action('stop');assert.equal(notices.length,0,'Stop ACK/pending is not verified CSV');assert(get('wfPrimary').disabled&&get('wfStop').disabled);
 backend={...backend,revision:backend.revision+1,state:'stopped',count:4,can_continue:true,complete:true,verification:{verified:true,count:4}};
 events['gld-dataset-workflow']({detail:backend});await settle();assert.equal(notices.length,1);assert.equal(get('wfPrimaryLabel').textContent,'Continue');assert(!get('wfPrimary').disabled);assert(get('wfStop').disabled);
 events['gld-dataset-workflow']({detail:backend});assert.equal(notices.length,1,'verification notice only once');
 await get('wfPrimary').listeners.click();await settle();assert(calls.some(c=>c.route.endsWith('/continue')),'same primary continues verified CSV');
 for(const state of ['pausing','resuming','recovering','replaying','stopping']){context.control.apply({...backend,revision:backend.revision,state});assert(get('wfPrimary').disabled,'primary disabled during '+state);}
 context.control.apply(backend);
 backend={...backend,revision:backend.revision+1,locked:false,configuration_frozen:true,ledger_path:'C:/synthetic/ledger.jsonl'};
 backend={...backend,label:'backend_label',mode:'replay',fields:{...backend.fields,prediction:true}};
 context.control.apply(backend);
 assert.equal(get('wfLabel').value,'backend_label','frozen session shows backend label');
 assert(get('wfModeReplay').checked&&get('wfPrediction').checked,'frozen session shows backend mode and fields');
 assert(!get('wfLock').disabled,'verified CSV can be relocked');
 assert(get('wfMode').disabled&&get('wfLabel').disabled&&get('wfChooseFile').disabled&&get('wfDefaultFile').disabled,'existing CSV schema/label/destination requires Reset');
 await context.control.action('lock',{locked:true});
 assert(!get('wfPrimary').disabled&&get('wfPrimaryLabel').textContent==='Continue','unlock/relock preserves Continue');
 backend={...backend,revision:backend.revision+1,locked:true,can_continue:false,verification:{verified:false}};
 context.control.apply(backend);
 assert.equal(get('wfPrimaryLabel').textContent,'Continue');assert(get('wfPrimary').disabled,'invalid CSV must not offer a misleading fresh Start');
 backend={...backend,revision:backend.revision+1,state:'incomplete',connected:false,cleanup_pending:true,cleanup_paused:true};
 context.control.apply(backend);
 assert(!get('wfConnect').disabled,'explicit owned-session recovery remains available while locked');assert(!nodes.has('wfPassword'),'credentials never require a password DOM input');
 assert.equal(get('wfConnect').textContent,'Hubungkan ulang');
 assert(get('wfDevice').disabled&&get('wfMode').disabled&&get('wfChooseFile').disabled&&get('wfLock').disabled,'recovery cannot change owned device/schema/file');
 assert(get('wfStop').disabled&&get('wfReset').disabled&&get('wfPrimary').disabled,'cleanup must finish before controls reopen');
 backend={...backend,revision:backend.revision+1,cleanup_paused:false};context.control.apply(backend);
 assert(get('wfConnect').disabled,'active recovery cannot be started twice');
 context.bridgeFetch=async route=>{if(route.endsWith('/state'))return structuredClone(backend);throw Error('CSV changed; Reset required');};
 await context.control.action('continue');
 assert.equal(get('wfMessage').textContent,'CSV changed; Reset required','successful polling must preserve the rejected action explanation');
 context.bridgeFetch=async()=>structuredClone(backend);await context.control.action('lock',{locked:false});
 assert.notEqual(get('wfMessage').textContent,'CSV changed; Reset required','next operator action clears prior action error');
 context.bridgeFetch=async()=>{throw Error('temporary bridge interruption');};await context.control.sync();
 assert.match(get('wfMessage').textContent,/Status Dataset belum tersedia/);
 context.bridgeFetch=async()=>structuredClone(backend);await context.control.sync();
 assert.doesNotMatch(get('wfMessage').textContent,/Status Dataset belum tersedia/,'transient status errors clear after recovery');
 assert.equal(get('wfReadings').children.length,8);assert(!nodes.has('wfSensorsLeft')&&!nodes.has('wfSensorsRight'));
 assert(!nodes.has('wfStart')&&!nodes.has('wfPause'),'one primary button owns Start/Pause/Resume/Continue');
 context.bridgeFetch=async(route,options)=>{calls.push({route,body:options?JSON.parse(options.body):null});return structuredClone(backend);};await context.control.action('connect',{device_id:'1002'});
 const connect=calls.filter(c=>c.route.endsWith('/connect')).at(-1);assert.deepEqual(connect.body,{device_id:'1002'},'Connect sends no password');
 get('wfModeReplay').checked=true;get('wfModeDirect').checked=false;await get('wfModeReplay').listeners.change();await settle();
 assert.equal(calls.filter(c=>c.route.endsWith('/configure')).at(-1).body.mode,'replay','radio selects one recording policy');
 backend={...backend,revision:backend.revision+1,fields:{...backend.fields,prediction:true},history:[{session_id:'s',seq:0,timestamp_ms:500,sensor_voltage:Array(8).fill(.2),prediction:{valid:true,gas_class:3,predicted_class:1,confidence:.875,status:'valid'}}]};context.control.apply(backend);
 assert.equal(get('wfConfidenceScore').textContent,'87.5%');assert.match(get('wfPredictedClass').textContent,/Class 1.*gas-3/);
 backend={...backend,revision:backend.revision+1,state:'complete',connected:false};context.control.apply(backend);
 assert.match(get('wfPredictionState').textContent,/rekaman selesai/,'normal Stop closes the socket but is not a lost-link warning');
 backend={...backend,revision:backend.revision+1,history:[{...backend.history[0],prediction:{valid:false,status:'warmup',confidence:null}}]};context.control.apply(backend);
 assert.equal(get('wfPredictedClass').textContent,'Pemanasan');assert.equal(get('wfConfidenceScore').textContent,'—','invalid latest prediction must not retain a previous valid confidence');
 console.log('PASS wizard cumulative five gates/password-free connection/radios/timestamp/prediction and, locked inputs, recording/pause/stop/continue controls, stale updates and verified-only popup');
})().catch(error=>{console.error(error);process.exitCode=1;});
