const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../js/gw-main.js'), 'utf8');
const handler = source.slice(source.indexOf('async function handleTestGatewayWifi()'),
  source.indexOf('async function handleApplyMqttConfig()'));
const state = {serialConnected:true, wifiVerified:false, wifiIp:''};
const elements = {gwTestWifiBtn:{disabled:false}, gwApplyWifiStatus:{textContent:''}};
let ack;
const context = vm.createContext({state, elements, Number,
  testGatewayWifi: async () => ack, updateSetupFlowUi() {}});
vm.runInContext(handler, context);
(async () => {
  ack = {status:'ok', connected:'1', ip:'192.0.2.3', rssi:'-95'};
  await context.handleTestGatewayWifi();
  assert.match(elements.gwApplyWifiStatus.textContent, /-95 dBm.*Sinyal lemah/);
  assert.equal(state.wifiVerified, true);
  ack = {status:'ok', connected:'1', ip:'192.0.2.3', rssi:'-60'};
  await context.handleTestGatewayWifi();
  assert.match(elements.gwApplyWifiStatus.textContent, /-60 dBm/);
  assert.doesNotMatch(elements.gwApplyWifiStatus.textContent, /Sinyal lemah/);
  ack = {status:'ok', connected:'1', ip:'192.0.2.3'};
  await context.handleTestGatewayWifi();
  assert.equal(state.wifiVerified, true, 'older firmware without RSSI remains compatible');
  assert.doesNotMatch(elements.gwApplyWifiStatus.textContent, /dBm/);
  console.log('Gateway Wi-Fi signal guidance: PASS');
})().catch(error => {console.error(error); process.exitCode=1;});
