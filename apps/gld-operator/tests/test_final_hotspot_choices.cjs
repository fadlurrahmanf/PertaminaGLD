// Menu-only contract. No COM, network, flash, dialogs or firmware changes.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../..');
const html=fs.readFileSync(path.join(root,'apps/gld-operator/index.html'),'utf8');
const select=html.match(/<select id="firmwareUploadModel"[^>]*>([\s\S]*?)<\/select>/)[1];
const choices=[...select.matchAll(/<option value="([^"]+)"([^>]*)>([^<]+)<\/option>/g)].map(m=>({value:m[1],disabled:m[2].includes('disabled'),label:m[3]}));
const final=[1,2,3].map(n=>`model_${n}_dataset_workflow_wifi`);
assert.deepEqual(choices.filter(o=>o.value.includes('dataset')).map(o=>o.value),final);
assert.deepEqual(choices.filter(o=>!o.disabled&&!o.value.includes('dataset')).map(o=>o.value),['model_1','model_2','model_3']);
assert(choices.find(o=>o.value==='model_4').disabled);
const source=fs.readFileSync(path.join(root,'apps/gld-operator/js/firmware.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,'');
const node={value:'model_1'},context={$:()=>node};vm.createContext(context);vm.runInContext(source+'\nglobalThis.selected=selectedModelSlot;',context);
for(const key of final){node.value=key;assert.equal(context.selected().environment,'gld_'+key);assert(context.selected().available);}
for(const key of ['model_1','model_2','model_3']){node.value=key;assert.equal(context.selected().environment,'gld_'+key);}
node.value='removed-or-invalid';assert.equal(context.selected().available,false,'Missing choice must not silently fall back to normal Model1');
const hub=fs.readFileSync(path.join(root,'apps/operator-hub/public/js/hub.js'),'utf8');
const start=hub.indexOf('${(packageOptions.models || []).filter(');assert(start>=0);const expression=hub.slice(start+2,hub.indexOf('.map((option)',start));
const models=['gld','gld_model_1','gld_model_2','gld_model_3','gld_v2','gld_atex',...['wifi','replay_wifi','workflow_wifi'].flatMap(v=>[1,2,3].map(n=>`gld_model_${n}_dataset_${v}`))].map(environment=>({environment}));
const visible=vm.runInNewContext(expression,{packageOptions:{models}}).map(o=>o.environment);
assert.deepEqual(Array.from(visible.filter(e=>e.includes('_dataset_'))),final.map(v=>'gld_'+v));
for(const env of ['gld','gld_model_1','gld_model_2','gld_model_3','gld_v2','gld_atex'])assert(visible.includes(env));
console.log('PASS Expert/Simple menus expose exactly3finalhotspotchoices; normalchoices/legacyAPImetadata preserved; invalidselectionfailsclosed');
