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
  const frozen={protocol:'gld-dataset-wifi/2',session_id:'direct-owned',state:'stop_pending',
    connected:false,ready:false,cleanup_pending:true,cleanup_paused:false,recovery_active:false,
    complete:false,history:[],count:17,gap_count:0,filename:'direct.csv'};
  const direct=await harness({direct:frozen});
  assert.equal(direct.element('wirelessMode').value,'direct');
  assert.equal(direct.element('wirelessMode').disabled,true,'private cleanup owns GLD while transport is closed');
  assert.equal(direct.element('wirelessStartBtn').disabled,true);
  assert.equal(direct.element('wirelessStopBtn').disabled,true,'Stop already owned by private cleanup');
  assert.equal(direct.element('wirelessConnectBtn').disabled,true);
  assert.equal(direct.element('wirelessDisconnectBtn').disabled,false,'operator can pause waiting');
  assert.equal(direct.element('wirelessDisconnectBtn').textContent,'Batal menunggu');
  assert.match(direct.element('wirelessRecovery').textContent,/CSV tidak ditambah/);
  await direct.select('replay');
  assert.equal(direct.element('wirelessMode').value,'direct','cleanup cannot be bypassed by selecting another mode');
  assert.equal(direct.context.control.get().count,17);
  direct.states.direct={...frozen,cleanup_paused:true};
  await direct.sync();
  assert.equal(direct.element('wirelessConnectBtn').disabled,false,'explicit reconnect resumes owned cleanup');
  assert.equal(direct.element('wirelessConnectBtn').textContent,'Selesaikan sesi');
  assert.equal(direct.element('wirelessPassword').disabled,false);
  assert.equal(direct.element('wirelessDisconnectBtn').disabled,true,'already paused');
  assert.equal(direct.element('wirelessMode').disabled,true);
  assert.equal(direct.element('wirelessStartBtn').disabled,true);
  assert.match(direct.element('wirelessRecovery').textContent,/Selesaikan sesi/);
  direct.states.direct={...frozen,state:'incomplete',cleanup_pending:false,cleanup_paused:false,cleanup_confirmed:true};
  await direct.sync();
  assert.equal(direct.element('wirelessMode').disabled,false,'confirmed cleanup releases mode');
  assert.equal(direct.context.control.get().count,17,'original count remains frozen');
  await direct.select('replay');
  assert.equal(direct.element('wirelessMode').value,'replay');
  console.log('PASS direct2 cutoff cleanup locks, explicit pause/resume controls, frozen count and release to recovery mode');
})().catch(error=>{console.error(error);process.exitCode=1;});
