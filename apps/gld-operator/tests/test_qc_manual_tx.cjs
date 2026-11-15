// Inert UI/ACK/event mocks: no serial, Wi-Fi or radio access.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../js/qc.js'), 'utf8');
function extract(signature) {
  const start = source.indexOf(signature), end = source.indexOf('\n}', start);
  if (start < 0 || end < 0) throw Error('function missing: '+signature);
  return source.slice(start,end+2).replace(/^export /, '');
}
async function scenario({ack={status:'ok',completion:'pending'}, board='GLD ATEX', error, event, early=false, statusError=false, auto=false}={}) {
  const logs=[], writes=[], indicators=[];
  const context = vm.createContext({state:{info:{boardProfile:board}}, loraFocus:{lastPayload:null,activeIntervalMs:5000},
    $:()=>({checked:auto}), LORA_BEGIN_ACK_TIMEOUT_MS:15000,
    loraFocusLog:(...args)=>logs.push(args), normalizeLoraPayloadHex:()=>'', renderLoraPayloadPreview(){},
    armLoraCountdown(){}, flashLoraTxSuccess:()=>indicators.push('success'),
    sendCommandAndWaitAck:async (command)=>{writes.push(command);if(early&&event) context.appendQcLoraEvent(event);if(error)throw Error(error);return ack;},
    sendCommand:async command=>{writes.push(command);if(statusError)throw Error('status unavailable');}});
  vm.runInContext(extract('async function manualLoraTransmit(')+'\n'+extract('export function appendQcLoraEvent('), context);
  await context.manualLoraTransmit();
  if(event&&!early)context.appendQcLoraEvent(event);
  return {logs,writes,indicators};
}
(async()=>{
 const event={sequence:1,ok:true,target:'ch',payload:'ch_normal'};
 let result=await scenario();assert.match(result.logs[0][0],/DITERIMA/);assert(!JSON.stringify(result.logs).includes('SUCCESS'));assert.deepEqual(result.writes,['MANUAL_LORA_TX','GET_STATUS']);
 result=await scenario({event});assert.match(result.logs[0][0],/DITERIMA/);assert.match(result.logs.at(-1)[0],/TX #0001 SUCCESS/);
 result=await scenario({event:{...event,ok:false,reason:'radio fault'}});assert.match(result.logs.at(-1)[0],/GAGAL/);assert(!result.indicators.length);
 result=await scenario({early:true,event});assert.match(result.logs[0][0],/SUCCESS/);assert.match(result.logs[1][0],/DITERIMA/);assert(!result.logs.some(row=>row[0]==='MANUAL TX SUCCESS'));
 result=await scenario({statusError:true});assert.match(result.logs.at(-1)[0],/STATUS RADIO BELUM TERBACA/);assert(!result.logs.some(row=>row[0]==='MANUAL TX GAGAL'));
 result=await scenario({ack:{status:'ok',completion:'future'}});assert.match(result.logs[0][0],/BELUM PASTI/);
 result=await scenario({error:'timeout'});assert.match(result.logs[0][0],/BELUM PASTI/);assert.equal(result.writes.length,1);
 result=await scenario({ack:{status:'busy',message:'occupied'}});assert.match(result.logs[0][0],/DITOLAK/);
 result=await scenario({board:'GLD1',ack:{status:'ok'}});assert.equal(result.logs[0][0],'MANUAL TX SUCCESS');
 result=await scenario({auto:true});assert.match(result.logs[0][0],/DITOLAK/);assert.equal(result.writes.length,0);
 console.log('PASS manual TX sync/async ACK, independent events, uncertain outcome and no automatic retry');
})().catch(error=>{console.error(error);process.exitCode=1;});
