const fs=require('fs'), vm=require('vm'), assert=require('assert/strict'), path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../js/gw-main.js'),'utf8');
const handler=source.slice(source.indexOf('async function handleApplyMqttConfig()'),source.indexOf('function populateMeshLoraForm'));
const element=(value='')=>({value,textContent:'',disabled:false});
const elements={mqttHost:element('broker.example'),mqttPort:element('8883'),mqttUsername:element('user'),mqttPassword:element('secret'),
  mqttTransport:element('tls'),mqttTlsCa:element(''),mqttNtpHost:element('pool.ntp.org'),gwApplyMqttStatus:element(),gwApplyMqttBtn:element()};
const sent=[]; const state={wifiVerified:true};
const ctx=vm.createContext({elements,state,TextEncoder,applyMqttConfig:async c=>{sent.push(c);return {status:'ok'};}});
vm.runInContext(handler,ctx);
(async()=>{
  await ctx.handleApplyMqttConfig(); assert.equal(sent.length,0); assert.match(elements.gwApplyMqttStatus.textContent,/Root CA/);
  elements.mqttTlsCa.value='-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----';
  await ctx.handleApplyMqttConfig(); assert.equal(sent.length,1); assert.equal(sent[0].ntpHost,'pool.ntp.org'); assert.match(sent[0].tlsCaPem,/BEGIN CERTIFICATE/);
  elements.mqttTransport.value='non_tls'; await ctx.handleApplyMqttConfig(); assert.equal(sent.length,2); assert.equal(sent[1].tlsCaPem,undefined); assert.equal(sent[1].ntpHost,undefined);
  console.log('Gateway TLS provisioning contract: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
