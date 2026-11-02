// Real UI async stale-response isolation; fake state transport, no network.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const app=path.resolve(__dirname,'..');
const tick=async()=>{for(let index=0;index<15;index++)await Promise.resolve();};
const element=()=>({value:'',dataset:{},style:{},children:[],listeners:{},clientWidth:0,clientHeight:0,
  disabled:false,replaceChildren(){this.children=[];},append(...items){this.children.push(...items);},
  addEventListener(name,callback){this.listeners[name]=callback;},setAttribute(){},classList:{toggle(){},add(){},remove(){}}});
(async()=>{
  const modelSource=fs.readFileSync(path.join(app,'js/wireless-dataset-model.js'),'utf8');
  const model=await import(`data:text/javascript;base64,${Buffer.from(modelSource).toString('base64')}`);
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  get('wirelessMode').value='direct';
  const events={};
  const context={document:{getElementById:get,createElement:element,createTextNode:text=>({textContent:String(text)})},legacyState:Object.freeze({bridgeAvailable:true}),
    CHART_COLORS:Array(8).fill('#aaa'),ResizeObserver:class{observe(){}},
    window:{setInterval(){},setTimeout(){},addEventListener(name,callback){events[name]=callback;}},
    bridgeFetch:async route=>({protocol:route.includes('wireless-replay')?'gld-dataset-wifi/2':'gld-dataset-wifi/1',
      connected:false,state:'disconnected',history:[],count:0}),...model};
  vm.createContext(context);
  const source=fs.readFileSync(path.join(app,'js/wireless-dataset.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,'');
  vm.runInContext(source+'\nglobalThis.control={sync,action,get:()=>snapshot};',context);
  context.initWirelessDataset();await tick();
  let resolveOld;
  const old=new Promise(resolve=>{resolveOld=resolve;});
  context.bridgeFetch=async route=>route==='/api/wireless-dataset/state'?old:
    {protocol:'gld-dataset-wifi/2',state:'disconnected',connected:false,session_id:'replay-view',history:[],count:0};
  const delayed=context.control.sync();
  get('wirelessMode').value='replay';
  await get('wirelessMode').listeners.change({target:get('wirelessMode')});await tick();
  resolveOld({protocol:'gld-dataset-wifi/1',session_id:'late-direct',state:'complete',history:[],count:999});
  await delayed;await tick();await context.control.sync();
  assert.equal(get('wirelessMode').value,'replay');
  assert.equal(context.control.get().protocol,'gld-dataset-wifi/2');
  assert.notEqual(context.control.get().session_id,'late-direct','late old-mode snapshot must not cross transport boundary');
  assert.notEqual(context.control.get().count,999);
  console.log('PASS late Stage1 response cannot replace selected Stage2 session/history/counters');
})().catch(error=>{console.error(error);process.exitCode=1;});
