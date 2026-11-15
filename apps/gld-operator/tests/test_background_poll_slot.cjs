const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../js/fleet.js'),'utf8');
const start=source.indexOf('async function setActiveSlot(');const code=source.slice(start,source.indexOf('\n}',start)+2);
const calls=[];const state={activeSlot:1,polling:true,bridgeAvailable:true,history:[{}],info:null,pendingSerialRequest:null,
  fleet:{2:{connected:true,port:'COM999'}}};
const ctx=vm.createContext({state,elements:{activeSlotLabel:{},portLabel:{}},
  stopPolling:async()=>{calls.push('stop');state.polling=false;return true;},togglePolling:()=>{calls.push('start');state.polling=true;},
  ensureFleetSlot(){},resetDeviceSnapshot(){},updateTelemetryCollectionProgress(){},drawChart(){},updateConnectionUi(){},syncDeviceSummary(){},
  sendCommand:async cmd=>{calls.push(cmd);if(cmd==='GET_INFO')state.info={capabilities:{lightweightTelemetry:'GET_TELEMETRY'}}},
  recoverActiveSlotTelemetry:slot=>calls.push(`recover:${slot}`),wait:async()=>{},Date});
vm.runInContext(code,ctx);
(async()=>{await ctx.setActiveSlot(2);assert.equal(state.activeSlot,2);assert.deepEqual(calls,['stop','GET_INFO','GET_STATUS','GET_QC_STATUS','recover:2','start']);
 assert.equal(state.history.length,0);console.log('PASS slot switch transfers polling only after stopping previous owner');})().catch(e=>{console.error(e);process.exitCode=1});
