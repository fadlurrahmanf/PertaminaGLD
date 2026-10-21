// Exercise the real nulling-detail renderer for new GLD1 rejection messages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../../apps/gld-operator/js/nulling.js'), 'utf8');
const first = source.indexOf('const NULLING_FAIL_REASON_TEXT =');
const end = source.indexOf('function initNullingStages()', first);
assert(first >= 0 && end > first);
const body = source.slice(first, end);
const context = {
  tokenValue(line, key) {
    return new RegExp(`(?:^|\\s)${key}=([^\\s]+)`).exec(line)?.[1];
  }
};
vm.createContext(context);
vm.runInContext(body, context);
for (const [reason, expected] of [
  ['crossing_unstable_or_invalid', 'cek ulang crossing'],
  ['verify_unstable_or_invalid', 'verifikasi kandidat'],
  ['final_unstable_or_invalid', 'Pembacaan akhir tidak stabil'],
  ['baseline_incomplete', 'Baseline tidak lengkap'],
  ['dac_search_write_failed', 'Penulisan DAC gagal'],
  ['adc_search_read_invalid', 'Pembacaan ADC tidak valid']
]) {
  const message = context.nullingDetail(`NULLING_CH_FAIL ch=0 stage=confirm reason=${reason}`);
  assert(message.includes(expected), message);
}
assert(context.nullingDetail('NULLING_CH_FAIL ch=0 stage=baseline reason=baseline_no_valid_samples').includes('No valid ADC'));
console.log('PASS: six GLD1 stability/search errors are readable; existing error text remains available');
