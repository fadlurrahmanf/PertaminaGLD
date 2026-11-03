// Isolated headless Chrome over local CDP; never attaches to user browsers.
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {setTimeout:delay} = require('node:timers/promises');

async function eventually(check, description, seconds=20) {
  const end = Date.now()+seconds*1000;
  while(Date.now()<end) { if(await check()) return; await delay(100); }
  throw new Error(`Timed out: ${description}`);
}

async function launch(directory) {
  fs.mkdirSync(directory,{recursive:true});
  const profile=fs.mkdtempSync(path.join(directory,'chrome-profile-'));
  const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',[
    '--headless=new','--no-proxy-server','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',
    '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',`--user-data-dir=${profile}`,
    '--window-size=1600,1100','about:blank'
  ],{windowsHide:true,stdio:'ignore'});
  let ws;
  try {
    const active=path.join(profile,'DevToolsActivePort');
    await eventually(()=>fs.existsSync(active),'isolated Chrome startup');
    const port=fs.readFileSync(active,'utf8').split('\n')[0];
    const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const target=targets.find(t=>t.type==='page');
    if(!target) throw new Error('No headless page');
    ws=new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((ok,no)=>{ws.onopen=ok;ws.onerror=no;});
    let next=0;
    const pending=new Map();
    ws.onmessage=({data})=>{
      const value=JSON.parse(data);
      if(!value.id) return;
      const task=pending.get(value.id); if(!task) return;
      pending.delete(value.id); clearTimeout(task.timer);
      value.error ? task.reject(new Error(value.error.message)) : task.resolve(value.result);
    };
    const call=(method,params={})=>new Promise((resolve,reject)=>{
      const id=++next;
      const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout ${method}`));},20000);
      pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
    });
    const evaluate=async expression=>{
      const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
      if(result.exceptionDetails) throw new Error(result.exceptionDetails.text+': '+result.exceptionDetails.exception?.description);
      return result.result.value;
    };
    return {call,evaluate,
      async click(selector){await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n||n.disabled)throw Error('Control unavailable');n.click();return true})()`);},
      async fill(selector,value){await eventually(()=>evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});return !!n&&!n.disabled})()`),'input enabled: '+selector);await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});n.value=${JSON.stringify(value)};n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}));return true})()`);},
      async screenshot(file){const result=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(file,Buffer.from(result.data,'base64'));},
      async close(){try{await call('Browser.close');}catch{}finally{ws.close();if(child.exitCode===null)child.kill();}},
    };
  } catch(error) {if(ws)ws.close();child.kill();throw error;}
}
module.exports={launch,eventually,delay};
