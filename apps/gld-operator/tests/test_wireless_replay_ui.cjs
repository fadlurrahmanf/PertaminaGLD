// Real UI module with inert DOM/transport. No browser, service, COM or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const app = path.resolve(__dirname, '..');

function node() {
  return {value:'',disabled:false,hidden:false,textContent:'',dataset:{},style:{},children:[],listeners:{},
    clientWidth:0,clientHeight:0,replaceChildren(){this.children=[];},append(...items){this.children.push(...items);},
    addEventListener(name,callback){this.listeners[name]=callback;},setAttribute(){},click(){},
    classList:{add(){},remove(){},toggle(){}}};
}
async function settle() { for(let index=0;index<15;index++) await Promise.resolve(); }
async function harness(overrides={}) {
  const text = fs.readFileSync(path.join(app,'js/wireless-dataset-model.js'),'utf8');
  const model = await import(`data:text/javascript;base64,${Buffer.from(text).toString('base64')}`);
  const elements = new Map(), events = {}, calls = [];
  const element = id => {if(!elements.has(id)) elements.set(id,node());return elements.get(id);};
  element('wirelessMode').value='direct';
  const states = {
    direct:{protocol:'gld-dataset-wifi/1',state:'disconnected',connected:false,ready:false,history:[],count:0,gap_count:0},
    replay:{protocol:'gld-dataset-wifi/2',state:'disconnected',connected:false,ready:false,history:[],count:0,gap_count:0,recovery_active:false},
    ...overrides,
  };
  const context={document:{getElementById:element,createElement:node,createTextNode:text=>({textContent:String(text)})},
    legacyState:Object.freeze({bridgeAvailable:true,connected:false,mock:false}),CHART_COLORS:Array(8).fill('#aaa'),
    ResizeObserver:class{observe(){}},Event:class{},CustomEvent:class{},
    window:{addEventListener(name,callback){events[name]=callback;},setInterval(){},setTimeout(){},devicePixelRatio:1},
    bridgeFetch:async(route,options)=>{
      calls.push({route,options});
      const mode=route.startsWith('/api/wireless-replay/')?'replay':'direct';
      if(options && route.endsWith('/stop')) {
        states[mode]={...states[mode],state:'stop_pending',stop_requested:true};
      }
      return structuredClone(states[mode]);
    },...model};
  vm.createContext(context);
  const source=fs.readFileSync(path.join(app,'js/wireless-dataset.js'),'utf8')
    .replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,'');
  vm.runInContext(source+'\nglobalThis.control={sync,action,get:()=>snapshot};',context);
  context.initWirelessDataset();
  await settle();
  return {context,elements,element,events,calls,states,
    async select(mode){const selector=element('wirelessMode');selector.value=mode;
      assert.equal(typeof selector.listeners.change,'function','explicit mode selector must be wired');
      await selector.listeners.change({target:selector});await settle();},
    async sync(){await context.control.sync();await settle();}};
}

(async()=>{
  const fresh=await harness();
  assert.equal(fresh.element('wirelessMode').value,'direct','fresh UI defaults to Stage1');
  assert(fresh.calls.some(call=>call.route==='/api/wireless-dataset/state'));
  await fresh.select('replay');
  assert(fresh.calls.some(call=>call.route==='/api/wireless-replay/state'));
  assert.equal(fresh.context.control.get().protocol,'gld-dataset-wifi/2');

  const recovering=await harness({replay:{protocol:'gld-dataset-wifi/2',session_id:'kept-session',
    state:'recovering',connected:false,ready:false,recovery_active:true,stop_requested:false,
    filename:'retained.csv',count:21,history:[],gap_count:0,buffered_samples:17}});
  assert.equal(recovering.element('wirelessMode').value,'replay','browser reload must restore active replay context');
  assert.equal(recovering.element('wirelessMode').disabled,true,'active recovery must lock mode');
  assert.equal(recovering.element('wirelessStartBtn').disabled,true);
  assert.equal(recovering.element('wirelessConnectBtn').disabled,true);
  assert.equal(recovering.element('wirelessDisconnectBtn').disabled,false,'recovery must allow explicit cancellation');
  assert.equal(recovering.element('wirelessStopBtn').disabled,false,'recovery must allow queued Stop intent');
  const beforeCalls=recovering.calls.length;
  await recovering.select('direct');
  assert.equal(recovering.element('wirelessMode').value,'replay','disabled programmatic mode change must not replace recorder');
  assert.equal(recovering.context.control.get().session_id,'kept-session');
  assert(!recovering.calls.slice(beforeCalls).some(call=>call.route.includes('/disconnect') || call.route.startsWith('/api/wireless-dataset/')));
  await recovering.context.control.action('stop');
  assert(recovering.calls.some(call=>call.route==='/api/wireless-replay/stop'));
  assert.equal(recovering.context.control.get().state,'stop_pending');
  assert.match(recovering.element('wirelessState').textContent,/stop_pending|pending|menunggu/i);
  assert.doesNotMatch(recovering.element('wirelessState').textContent,/sesi lengkap/);

  assert.equal(typeof recovering.events['gld-wireless-dataset-replay'],'function','Stage2 event listener required');
  const kept=recovering.context.control.get().session_id;
  recovering.events['gld-wireless-dataset']({detail:{type:'state',session_id:'stage1-other',state:'recording',history:[]}});
  assert.equal(recovering.context.control.get().session_id,kept,'Stage1 SSE must not overwrite replay session');
  recovering.events['gld-wireless-dataset-replay']({detail:{type:'state',session_id:kept,state:'replaying',
    connected:true,recovery_active:true,count:22,buffered_samples:16,history:[]}});
  assert.equal(recovering.context.control.get().state,'replaying');
  assert.equal(recovering.element('wirelessMode').disabled,true);
  console.log('PASS fresh Stage1 default, explicit Stage2 route, browser recovery restoration and mode lock');
  console.log('PASS Stop intent/cancel availability during recovery, pending status and SSE namespace isolation');
})().catch(error=>{console.error(error);process.exitCode=1;});
