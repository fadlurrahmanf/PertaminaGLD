import fs from 'node:fs/promises';

const root = 'D:/Github/PertaminaGLD';
const outputDir = `${root}/outputs/gld1-mcp-sweep-20261021`;
const logPath = `${root}/tmp/gld1-com7-nulling-20261021-1125.log`;
const phasePrefix = {
  BASELINE: 'Baseline',
  EXP: 'Exponential',
  BIN: 'Binary',
  CONFIRM: 'Confirm',
};

const text = await fs.readFile(logPath, 'utf8');
const bySensor = new Map();
let sequence = 1;
for (const line of text.split(/\r?\n/)) {
  const match = line.match(/^NULLING_(BASELINE|EXP|BIN|CONFIRM)_STEP ch=(\d+) sensor=([^ ]+) code=(\d+) voltage=([-+\d.eE]+)(?: target=([-+\d.eE]+))? valid=(\d+)(?: samples=(\d+))?/);
  if (!match) continue;
  const [, stage, channel, sensor, code, voltage, inlineTarget, valid, samples] = match;
  const item = {
    sequence: sequence++,
    channel: Number(channel),
    sensor,
    phase: phasePrefix[stage],
    dacCode: Number(code),
    voltageV: Number(voltage),
    targetV: inlineTarget === undefined ? null : Number(inlineTarget),
    valid: valid === '1',
    samples: samples === undefined ? (stage === 'CONFIRM' ? 10 : 8) : Number(samples),
  };
  if (!bySensor.has(sensor)) bySensor.set(sensor, []);
  bySensor.get(sensor).push(item);
}

for (const [sensor, points] of bySensor) {
  const done = text.match(new RegExp(`NULLING_BASELINE_DONE ch=\\d+ sensor=${sensor} baseline=([-+\\d.eE]+) target=([-+\\d.eE]+) threshold=([-+\\d.eE]+)`));
  if (!done) throw new Error(`Missing baseline summary for ${sensor}`);
  const [, baselineText, targetText, thresholdText] = done;
  for (const point of points) {
    point.baselineV = Number(baselineText);
    point.targetV = Number(targetText);
    point.thresholdV = Number(thresholdText);
    point.crossing = point.valid && point.voltageV >= point.targetV;
  }
  const chosen = text.match(new RegExp(`NULLING_CONFIRM_OK ch=\\d+ sensor=${sensor} code=(\\d+) voltage=([-+\\d.eE]+) target=([-+\\d.eE]+)`));
  if (!chosen) throw new Error(`Missing chosen confirm candidate for ${sensor}`);
  const [, dacCode, voltageV, targetV] = chosen;
  for (const point of points) point.selected = point.phase === 'Confirm' && point.dacCode === Number(dacCode) && point.voltageV === Number(voltageV) && point.targetV === Number(targetV);
}

const required = ['MQ8', 'MQ135', 'MQ3', 'MQ5', 'MQ4', 'MQ7', 'MQ6', 'MQ2'];
for (const sensor of required) {
  const rows = bySensor.get(sensor) ?? [];
  if (!rows.some((row) => row.selected)) throw new Error(`No selected raw confirm row for ${sensor}`);
}
await fs.mkdir(outputDir, { recursive: true });
const points = required.flatMap((sensor) => bySensor.get(sensor));
await fs.writeFile(`${outputDir}/nulling-measured-points.json`, JSON.stringify(points, null, 2));
console.log(JSON.stringify({ points: points.length, sensors: required.map((sensor) => ({ sensor, selected: bySensor.get(sensor).find((row) => row.selected).dacCode })) }, null, 2));
