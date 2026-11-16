const fs=require('fs'), vm=require('vm'), assert=require('assert/strict'), path=require('path');
const text=fs.readFileSync(path.join(__dirname,'../js/gw-bridge.js'),'utf8');
const source=text.slice(text.indexOf('export async function useLocalPc()'),text.indexOf('export async function publishPull')).replace('export ', '');
const elements={mqttHost:{value:''},mqttPort:{value:'1883'},mqttUsername:{value:'operator'},mqttPassword:{value:'existing'}};
let address='192.0.2.4', error='';
const ctx=vm.createContext({elements,state:{bridgeAvailable:true},appendLog(){},showBanner(s){error=s},bridgeFetch:async url=>{assert.equal(url,'/api/network');return {ipv4:address}}});
vm.runInContext(source,ctx);
(async()=>{
  await ctx.useLocalPc();
  assert.equal(elements.mqttHost.value,'192.0.2.4');
  assert.equal(elements.mqttPort.value,'1883');
  assert.equal(elements.mqttUsername.value,'operator');
  assert.equal(elements.mqttPassword.value,'existing');
  address='127.0.0.1'; await ctx.useLocalPc();
  assert.match(error,/LAN IP unavailable/);
  assert.equal(elements.mqttHost.value,'192.0.2.4');
  console.log('PC IP autofill preserves Aedes credentials: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
