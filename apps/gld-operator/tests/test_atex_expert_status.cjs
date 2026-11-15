// Snapshot-only tests; no board, serial, hardware, or services.
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const root=path.resolve(__dirname,'../../..');const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const strip=s=>s.replace(/^import .*\r?\n/gm,'').replace(/^export /gm,'');
function node(){return {textContent:'',className:'',dataset:{},children:[],append(...v){this.children.push(...v)},replaceChildren(...v){this.children=v}};}
const nodes=new Map(), get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
const state={info:null};const ctx=vm.createContext({state,$:get,document:{createElement(){return node()}}});
vm.runInContext(strip(read('apps/gld-operator/js/model-binding.js')),ctx);vm.runInContext(strip(read('apps/gld-operator/js/expert.js')),ctx);
const exact='GLD ATEX MotherBoardGLDVer2';
const sample=()=>({sensorPower:{available:true},bootHealth:{mlReady:true,nullingProfileApplied:true,dacReady:true},telemetry:{sensorStatus:Array(8).fill(0)},model:{profileId:'fixture',productionApproved:true,boundNullingProfileId:1,activeNullingProfileId:1,bindingValid:true,bindingModelMatches:true,profileReady:true,inferenceValid:true}});
const rows=()=>get('expertStatusRows').children;
state.info={boardProfile:exact};let s=sample();ctx.renderExpertStatus(s);
assert.notEqual(get('expertStatusSummary').textContent,'KHUSUS GLD1');
assert.equal(get('expertStatusSummary').textContent,'INFERENCE MENUNGGU DATA');
assert.equal(rows()[0].children[1].textContent,'BELUM TERSEDIA','zero-initialized sensor status alone cannot prove scan');
assert.equal(rows()[1].children[1].textContent,'BELUM TERSEDIA','missing primed state is unknown');
assert.equal(rows()[5].children[1].textContent,'BELUM TERSEDIA','dacReady alone is not DAC verification');
assert.match(get('expertStatusHint').textContent,/belum membuktikan kondisi fisik/);
// Contradictory positive sensor flag does not outrank an unobserved scan.
s.model.readiness={scanObserved:false,allSensorsValid:true};ctx.renderExpertStatus(s);
assert.equal(rows()[0].children[1].textContent,'BELUM TERSEDIA');assert.notEqual(get('expertStatusSummary').textContent,'INFERENCE SIAP');
s.model.readiness.allSensorsValid=false;ctx.renderExpertStatus(s);assert.equal(rows()[0].children[1].textContent,'BELUM SIAP');

s.model.readiness={scanObserved:true,sensorsPrimed:true,dacVerificationReady:true};ctx.renderExpertStatus(s);
assert.equal(rows()[0].children[1].textContent,'SIAP');assert.equal(get('expertStatusSummary').textContent,'INFERENCE SIAP');
s.model.readiness.mlReady=true;s.model.mlReady=false;ctx.renderExpertStatus(s);assert.equal(rows()[2].children[1].textContent,'BELUM SIAP','explicit false must take priority on ATEX');delete s.model.mlReady;
s.telemetry.sensorStatus[3]=null;ctx.renderExpertStatus(s);assert.equal(rows()[0].children[1].textContent,'BELUM TERSEDIA');assert.notEqual(get('expertStatusSummary').textContent,'INFERENCE SIAP');
s.telemetry.sensorStatus[3]=1;ctx.renderExpertStatus(s);assert.equal(rows()[0].children[1].textContent,'BELUM SIAP');
state.info={boardProfile:exact};ctx.renderExpertStatus({});assert.equal(get('expertStatusSummary').textContent,'STATUS BELUM LENGKAP');assert.doesNotMatch(get('expertStatusHint').textContent,/paket GLD1/);
for(const board of ['GLD2 WROOM-1U-N16R8','GLD3 Motherboard','GLD ATEX MotherBoardGLDVer2x']) {state.info={boardProfile:board};ctx.renderExpertStatus(sample());assert.equal(get('expertStatusSummary').textContent,'KHUSUS GLD1');}
state.info={boardProfile:'GLD1'};s=sample();delete s.sensorPower;s.model.readiness={allSensorsValid:true,sensorsPrimed:true,dacVerificationReady:true};ctx.renderExpertStatus(s);assert.equal(get('expertStatusSummary').textContent,'INFERENCE SIAP');

// Exercise the production INFO/STATUS dispatch in the same order as serial lines.
const serial=read('apps/gld-operator/js/serial-protocol.js');
const begin=serial.indexOf('export function handleLine('), end=serial.indexOf('\n}',begin);
assert(begin>=0&&end>begin);
let renderCount=0;const originalRender=ctx.renderExpertStatus;ctx.renderExpertStatus=(snapshot)=>{renderCount++;return originalRender(snapshot)};
Object.assign(ctx,{
 appendLog(){},trackDatasetRuntimeLine(){},parseBootDiagnosticLine(){},recordSerialResponse(){},updateInfo(){},updateQcLoraFromDevice(){},maybeAppendTelemetry(){},
 parseJsonAfter(prefix,line){return line.startsWith(prefix+' ')?JSON.parse(line.slice(prefix.length+1)):null;},
 updateStatus(status){ctx.renderExpertStatus(status)}
});
vm.runInContext(strip(serial.slice(begin,end+2)),ctx);
state.info=null;state.status=null;renderCount=0;
const incoming={...sample(),deviceId:'1001'};
ctx.handleLine('GLD_STATUS_JSON '+JSON.stringify(incoming));assert.equal(renderCount,1);assert.equal(get('expertStatusSummary').textContent,'KHUSUS GLD1');
ctx.handleLine('GLD_INFO_JSON '+JSON.stringify({boardProfile:exact,deviceId:'1001'}));assert.equal(renderCount,2);assert.equal(get('expertStatusSummary').textContent,'INFERENCE MENUNGGU DATA');
state.info=null;state.status=incoming;renderCount=0;
ctx.handleLine('GLD_INFO_JSON '+JSON.stringify({boardProfile:exact,deviceId:'1002'}));assert.equal(renderCount,0,'mismatched device must not rerender cached status');
ctx.handleLine('GLD_INFO_JSON '+JSON.stringify({boardProfile:'GLD1',deviceId:'1001'}));assert.equal(renderCount,0,'GLD1 INFO path unchanged');
state.status={...incoming};delete state.status.deviceId;ctx.handleLine('GLD_INFO_JSON '+JSON.stringify({boardProfile:exact,deviceId:'1001'}));assert.equal(renderCount,0,'unidentified status must not be paired');
console.log('PASS ATEX conservative Expert status, GLD1 and GLD2/GLD3 isolation');
