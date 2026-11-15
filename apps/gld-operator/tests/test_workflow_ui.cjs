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
 get('wfAverageByCount').checked=true;get('wfAverageCount').value='10';get('wfAverageHours').value='0';get('wfAverageMinutes').value='1';
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
 vm.runInContext(source+'\nglobalThis.control={apply,action,sync,render,chartFeed,movingAverageHistory,maybeBackfillVisualHistory,appendVisualRows,get:()=>snapshot,visualCount:()=>visualHistory.length,firstVisualSeq:()=>visualHistory[0]?.seq,lastVisualRowId:()=>visualHistory.at(-1)?.row_id};',context);
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
 assert.match(get('wfVerification').textContent,/4\/4 baris tersimpan terverifikasi terhadap ledger/);
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
 backend={...backend,revision:backend.revision+1,state:'incomplete',complete:false,count:46,
  verification:{verified:true,count:46,matched_count:46,stored_count:46},
  cause:{code:'',description:'',evidence:'unknown'},device_final_total:{status:'unknown',count:null},
  reconciliation_status:'unconfirmed',diagnostic_path:'C:/synthetic/workflow_test.diagnostics.jsonl'};
 context.control.apply(backend);
 assert.match(get('wfVerification').textContent,/46\/46 baris tersimpan terverifikasi terhadap ledger/);
 assert.match(get('wfSessionStatus').textContent,/tidak lengkap/);
 assert.match(get('wfCause').textContent,/belum diketahui/);
 assert.match(get('wfDeviceTotal').textContent,/belum diketahui/);
 assert.match(get('wfDiagnosticPath').textContent,/workflow_test\.diagnostics\.jsonl/);
 backend={...backend,revision:backend.revision+1,verification:{verified:false,attempted:true,matched_count:44,stored_count:46,message:'Isi baris berbeda.'},
  cause:{code:'csv_ledger_verification_failed',description:'Ketidakcocokan baris tercatat.'},
  device_final_total:{status:'reported',count:50},diagnostic_error:'Catatan diagnostik gagal disimpan.'};
 context.control.apply(backend);
 assert.match(get('wfVerification').textContent,/44\/46.*verifikasi keseluruhan gagal/);
 assert.doesNotMatch(get('wfVerification').textContent,/44\/46 baris tersimpan terverifikasi/);
 assert.match(get('wfCause').textContent,/csv_ledger_verification_failed/);
 assert.match(get('wfDeviceTotal').textContent,/50.*belum terkonfirmasi/);
 assert.match(get('wfDiagnosticError').textContent,/gagal disimpan/);
 backend={...backend,revision:backend.revision+1,diagnostic_path:'',recent_diagnostic_path:'',
  cause:{code:'',description:'',evidence:'unknown'},diagnostic_error:''};
 context.control.apply(backend);
 assert.match(get('wfDiagnosticPath').textContent,/historis tidak tersedia/);
 assert.match(get('wfCause').textContent,/belum diketahui/);
 backend={...backend,revision:backend.revision+1,count:0,start_rejected:true,
  start_reject_detail:'native_operation_busy',can_continue:true,
  verification:{verified:true,matched_count:0,stored_count:0},
  error:'GLD menolak Mulai sebelum ada sampel. Perintah Start bertepatan dengan operasi kontrol GLD.',
  cause:{code:'native_operation_busy',description:'Perintah Start bertepatan dengan operasi kontrol GLD.',evidence:'device_ack'},
  session_closure_status:'not_started',reconciliation_status:'not_started'};
 context.control.apply(backend);
 assert.equal(get('wfState').textContent,'Mulai ditolak');
 assert.match(get('wfSessionStatus').textContent,/belum ada sampel atau sesi perangkat/);
 assert.match(get('wfMessage').textContent,/Perintah Start bertepatan/);
 assert.equal(get('wfPrimaryLabel').textContent,'Continue');
 context.control.apply({...backend,revision:backend.revision+1,state:'starting',start_rejected:false,
  start_retry_count:1,error:'',count:0,cleanup_pending:false,cleanup_paused:false});
 assert.match(get('wfMessage').textContent,/penolakan yang terkonfirmasi/);
 const points=Array.from({length:5},(_,i)=>({ts:i*500,sensorVoltage:Array.from({length:8},(_,ch)=>i*(ch+1)),breakBefore:i===3}));
 const countAverage=context.control.movingAverageHistory(points,{enabled:true,byDuration:false,count:2});
 assert.equal(countAverage[2].sensorVoltage[0],1.5,'two-sample average uses latest two measurements');
 assert.equal(countAverage[2].sensorVoltage[7],12,'each sensor has its own average');
 assert.equal(countAverage[3].sensorVoltage[0],3,'session/gap boundary clears the average window');
 const durationAverage=context.control.movingAverageHistory(points,{enabled:true,byDuration:true,durationMs:1000});
 assert.equal(durationAverage[2].sensorVoltage[0],1,'duration window includes samples within one second');
 assert.equal(durationAverage[4].sensorVoltage[0],3.5,'duration average restarts after a gap');
 assert.equal(context.control.movingAverageHistory(points,{enabled:false}),points,'disabled average preserves raw chart feed');
 get('wfAverageToggle').listeners.click();
 assert.equal(get('wfAverageToggle')['aria-pressed'],'true');
 assert.equal(get('wfAverageToggle').textContent,'Average: Aktif');
 assert.equal(get('wfAverageOptions').hidden,false);
 assert.match(get('wfAverageStatus').textContent,/Average 10 data/);
 get('wfAverageCount').value='180000';get('wfAverageCount').listeners.change();
 assert.equal(get('wfAverageCount').value,'172800','count beyond a day is normalized visibly');
 assert.match(get('wfAverageStatus').textContent,/Average 172800 data/);
 get('wfAverageByCount').checked=false;get('wfAverageByDuration').checked=true;
 get('wfAverageHours').value='1';get('wfAverageMinutes').value='15';get('wfAverageByDuration').listeners.change();
 assert.equal(get('wfAverageCountField').hidden,true);
 assert.equal(get('wfAverageDurationField').hidden,false);
 assert.match(get('wfAverageStatus').textContent,/1 jam 15 menit/);
 get('wfAverageHours').value='24';get('wfAverageMinutes').value='45';get('wfAverageMinutes').listeners.change();
 assert.equal(get('wfAverageHours').value,'24');
 assert.equal(get('wfAverageMinutes').value,'0','duration above the supported history is visibly clamped');
 assert.match(get('wfAverageStatus').textContent,/Average 24 jam/);
 get('wfAverageToggle').listeners.click();
 assert.equal(get('wfAverageToggle')['aria-pressed'],'false');
 assert.equal(get('wfAverageToggle').textContent,'Average: Mati');
 assert.equal(get('wfAverageStatus').textContent,'Grafik mentah');
 const visualRows=Array.from({length:4},(_,i)=>({boot_id:'boot',session_id:'session',seq:i,
  timestamp_ms:500*i,sensor_voltage:Array.from({length:8},(_,ch)=>i*(ch+1))}));
 backend={...backend,revision:backend.revision+1,ledger_path:'C:/synthetic/other-ledger.jsonl',history:visualRows};
 context.control.apply(backend);
 assert.equal(context.control.chartFeed().history[2].sensorVoltage[0],2,'raw chart remains raw when Average is off');
 get('wfAverageByDuration').checked=false;get('wfAverageByCount').checked=true;get('wfAverageCount').value='2';
 get('wfAverageToggle').listeners.click();
 assert.equal(context.control.chartFeed().history[2].sensorVoltage[0],1.5,'chart feed uses moving average when enabled');
 assert.equal(context.control.get().history[2].sensor_voltage[0],2,'stored UI rows stay raw');
 assert.match(get('wfReadings').children[0].children[1].textContent,/3\.000000 V/,'sensor reading stays raw');
 const twoHours=Array.from({length:14401},(_,i)=>({boot_id:'boot',session_id:'session',seq:i,
  timestamp_ms:i*500,sensor_voltage:Array(8).fill(i)}));
 backend={...backend,revision:backend.revision+1,history:twoHours};context.control.apply(backend);
 backend={...backend,revision:backend.revision+1,history:twoHours.slice(-7200)};context.control.apply(backend);
 assert.equal(context.control.visualCount(),14401,'visual history survives a shorter backend snapshot');
 get('wfAverageByCount').checked=false;get('wfAverageByDuration').checked=true;
 get('wfAverageHours').value='2';get('wfAverageMinutes').value='0';
 assert.equal(context.control.chartFeed().history.at(-1).sensorVoltage[0],7200,'two-hour window averages the complete visual history');
 const threeHours=Array.from({length:21601},(_,i)=>({boot_id:'boot',session_id:'session',seq:i,
  timestamp_ms:i*500,sensor_voltage:Array(8).fill(i)}));
 backend={...backend,revision:backend.revision+1,history:threeHours.slice(-7200)};context.control.apply(backend);
 get('wfAverageHours').value='3';get('wfAverageMinutes').value='0';
 assert.equal(context.control.visualCount(),21601,'three-hour visual history includes both endpoints');
 assert.equal(context.control.chartFeed().history.at(-1).sensorVoltage[0],10800,'three-hour duration uses all available raw samples');
 const fourHours=Array.from({length:28801},(_,i)=>({boot_id:'boot',session_id:'session',seq:i,
  timestamp_ms:i*500,sensor_voltage:Array(8).fill(i)}));
 backend={...backend,revision:backend.revision+1,history:fourHours.slice(-7200)};context.control.apply(backend);
 get('wfAverageHours').value='4';get('wfAverageMinutes').value='0';
 assert.equal(context.control.visualCount(),28801,'history continues beyond the earlier three-hour boundary');
 assert.equal(context.control.chartFeed().history.at(-1).sensorVoltage[0],14400,'four-hour duration uses the complete raw window');
 assert(context.control.chartFeed().history.length<8000,'renderer receives only the visible part of long history');
 const {history:discardHistory,...resetSnapshot}=backend;
 context.control.apply({...resetSnapshot,revision:backend.revision+1,ledger_path:'',state:'idle'});
 assert.equal(context.control.get().history.length,0,'Reset clears stale raw chart and table rows');
 assert.equal(context.control.visualCount(),0,'Reset clears extended visual average history');
 const reloadedRows=Array.from({length:6},(_,i)=>({boot_id:'boot2',session_id:'session2',seq:i,
  timestamp_ms:i*500,sensor_voltage:Array(8).fill(i)}));
 backend={...backend,revision:backend.revision+2,ledger_path:'C:/synthetic/reloaded-ledger.jsonl',
  state:'complete',count:6,history:reloadedRows.slice(-2)};
 context.control.apply(backend);
 get('wfAverageByDuration').checked=false;get('wfAverageByCount').checked=true;get('wfAverageCount').value='6';
 context.bridgeFetch=async route=>route.endsWith('/chart-history')
  ?{ledger_path:backend.ledger_path,history:reloadedRows}:structuredClone(backend);
 await context.control.maybeBackfillVisualHistory();
 assert.equal(context.control.chartFeed().history.length,6,'read-only backfill restores older visual samples');
 assert.equal(context.control.chartFeed().history.at(-1).sensorVoltage[0],2.5,'reloaded six-sample average uses the full window');
 assert.equal(context.control.get().history.length,2,'backfill does not change the raw table snapshot');
 const longCapture=Array.from({length:180004},(_,i)=>({boot_id:'long-boot',session_id:'long-session',seq:i,row_id:i,
  timestamp_ms:i*500,sensor_voltage:Array(8).fill(i)}));
 context.control.appendVisualRows(longCapture);
 assert.equal(context.control.visualCount(),180001,'long capture retains the bounded 25-hour chart window');
 assert.equal(context.control.firstVisualSeq(),3,'oldest chart rows are trimmed in one batch');
 const nextSession0={boot_id:'next-boot',session_id:'next-session',seq:0,row_id:180004,
  timestamp_ms:0,sensor_voltage:Array(8).fill(100)};
 const nextSession1={...nextSession0,seq:1,row_id:180005,timestamp_ms:500,
  sensor_voltage:Array(8).fill(200)};
 context.control.appendVisualRows([nextSession0]);
 get('wfAverageByCount').checked=false;get('wfAverageByDuration').checked=true;
 get('wfAverageHours').value='24';get('wfAverageMinutes').value='0';
 context.bridgeFetch=async route=>route.endsWith('/chart-history')
  ?{ledger_path:backend.ledger_path,history:[...longCapture.slice(5),nextSession0,nextSession1]}:structuredClone(backend);
 await context.control.maybeBackfillVisualHistory();
 assert.equal(context.control.lastVisualRowId(),180005,'a bounded backfill cannot move older live rows after the newest ledger row');
 assert.equal(context.control.chartFeed().history.at(-1).sensorVoltage[0],150,
  'long-duration Average restarts at the new session boundary');
 console.log('PASS wizard, Start diagnostics, and visual-only Average by count or duration beyond three hours');
})().catch(error=>{console.error(error);process.exitCode=1;});
