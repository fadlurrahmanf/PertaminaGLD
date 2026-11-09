const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  const listeners = new Map();
  return {
    value: '', hidden: false, disabled: true, textContent: '',
    listeners,
    classList: { add() {}, remove() {} },
    addEventListener(name, handler) { listeners.set(name, handler); },
    removeEventListener(name) { listeners.delete(name); },
    setAttribute() {}, removeAttribute(name) { if (name === 'disabled') this.disabled = false; },
    focus() {}, select() {},
  };
}

async function main() {
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  let bannerHides = 0;
  const state = { expertUnlocked: false };
  const context = {
    $: get, elements: { firmwareLockStatus: element() }, state,
    document: { activeElement: element() },
    hideBanner() { bannerHides += 1; },
  };
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../js/security.js'), 'utf8')
    .replace(/^import .*;\r?\n/gm, '')
    .replace(/^export /gm, '');
  vm.runInContext(`${source}\nglobalThis.requireUnlock = requireUnlock;`, context);

  const pending = context.requireUnlock();
  const form = get('operatorPinForm');
  const input = get('operatorPinInput');
  input.value = '0000';
  form.listeners.get('submit')({ preventDefault() {} });
  assert.equal(get('operatorPinError').textContent, 'PIN salah.');
  assert.equal(state.expertUnlocked, false);
  assert.equal(form.listeners.has('submit'), true);

  input.value = '1234';
  form.listeners.get('submit')({ preventDefault() {} });
  assert.equal(await pending, true);
  assert.equal(state.expertUnlocked, true);
  assert.equal(get('uploadFirmwareBtn').disabled, false);
  assert.equal(get('sendRawBtn').disabled, false);
  assert.equal(bannerHides, 1);
  assert.equal(await context.requireUnlock(), true);
  assert.equal(bannerHides, 1, 'session unlock is reused');
  console.log('Operator PIN gate: wrong PIN rejected; 1234 unlocks Expert and Upload; no browser storage required.');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
