const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../js/serial-protocol.js'),'utf8');const a=src.indexOf('function syncRunningModeUi(');const code=src.slice(a,src.indexOf('\n}',a)+2);
let starts=0, stops=0; const state={mode:'dataset',mock:false,polling:true,connected:true};
const ctx=vm.createContext({state,backgroundPollSession:{},pollingGeneration:0,$:()=>null,document:{querySelector:()=>null},
  telemetryPollCommand:()=> 'GET_TELEMETRY',
  stopPolling:()=>{stops++;state.polling=false;ctx.pollingGeneration++;return Promise.resolve(true)},
  togglePolling:()=>{starts++;state.polling=true;ctx.pollingGeneration++}});
vm.runInContext(code,ctx);
(async()=>{ctx.syncRunningModeUi();await Promise.resolve();assert.equal(stops,1);assert.equal(starts,1);assert.equal(state.polling,true);
 state.polling=true;ctx.backgroundPollSession={};ctx.syncRunningModeUi();ctx.pollingGeneration++;await Promise.resolve();
 assert.equal(starts,1,'new operator intent must prevent automatic restart');
 state.mode='inference';state.bridgeAvailable=true;state.polling=true;state.pollTimer=1;ctx.backgroundPollSession=null;
 ctx.syncRunningModeUi();await Promise.resolve();assert.equal(starts,2,'returning to Running restores bridge polling');
 console.log('PASS leaving Running switches to legacy polling without overriding newer intent');})().catch(e=>{console.error(e);process.exitCode=1});
