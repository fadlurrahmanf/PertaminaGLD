// Real display formatter with DOM-free operator states; no serial/network.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(path.join(__dirname,'../js/dataset-workflow.js'),'utf8');
const begin=code.indexOf('function radioAutoTxText('),end=code.indexOf('\n}',begin);
assert(begin>=0 && end>begin);const ctx=vm.createContext({});vm.runInContext(code.slice(begin,end+2),ctx);
assert.equal(ctx.radioAutoTxText({connected:false,radio_auto_tx:false}),'');
let off=ctx.radioAutoTxText({connected:true,radio_auto_tx:false});assert.match(off,/Auto TX OFF/);assert.match(off,/rekaman sensor tetap bisa/);assert.match(off,/serial bila diperlukan/);assert.match(off,/Connect ulang/);
let on=ctx.radioAutoTxText({connected:true,radio_auto_tx:true});assert.match(on,/Auto TX ON/);assert.match(on,/bukan bukti penerimaan RX/);
let old=ctx.radioAutoTxText({connected:true});assert.match(old,/belum diketahui atau sudah lama/);assert.match(old,/tidak diketahui|belum diketahui/);
let malformed=ctx.radioAutoTxText({connected:true,radio_auto_tx:'false'});assert.match(malformed,/belum diketahui/);
assert.match(code,/radioHint\.textContent=text/);
console.log('PASS radio Auto TX ON/OFF/unknown/disconnected display, no forced serial');
