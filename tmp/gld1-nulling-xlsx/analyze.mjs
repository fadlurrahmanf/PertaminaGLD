import fs from "node:fs/promises";

const input = "D:/Github/PertaminaGLD/tmp/gld1-nulling-com7-20261019.jsonl";
const output = "D:/Github/PertaminaGLD/tmp/gld1-nulling-xlsx/analysis.json";
const lines = (await fs.readFile(input, "utf8")).trim().split(/\r?\n/).map(JSON.parse);
const names = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"];
// These timestamps were emitted by the live monitoring process as lines arrived.
const intervals = [
  ["14:52:36.787", "14:53:32.553"], ["14:53:32.553", "14:54:10.970"],
  ["14:54:10.970", "14:55:02.766"], ["14:55:02.767", "14:56:04.754"],
  ["14:56:04.755", "14:57:12.697"], ["14:57:12.698", "14:58:25.272"],
  ["14:58:25.272", "14:59:19.575"], ["14:59:19.576", "15:00:33.490"],
];
const sec = (s) => new Date(`2026-10-19T${s}+07:00`).getTime() / 1000;
const parse = (line) => Object.fromEntries([...line.matchAll(/([A-Za-z][\w]*)=([^\s]+)/g)].map((m) => [m[1], m[2]]));
const observations = [];
const group = new Map();
const successes = new Map();
for (const record of lines) {
  const text = record.line;
  if (text.startsWith("NULLING_CH_OK ")) {
    const f = parse(text);
    successes.set(Number(f.ch), f);
  }
  if (!text.startsWith("NULLING_STABILITY ")) continue;
  const f = parse(text);
  const ch = Number(f.ch);
  const observation = {
    sequence: record.sequence, ch: ch + 1, sensor: f.sensor, stage: f.stage,
    code: Number(f.code), stable: Number(f.stable), spreadV: Number(f.spread),
    observeMs: Number(f.observeMs), observedAt: record.observed_at || "",
    timestampBasis: record.timestamp_basis,
  };
  observations.push(observation);
  const key = `${ch}:${f.stage}`;
  const value = group.get(key) || { ch: ch + 1, sensor: f.sensor, stage: f.stage, count: 0, observeMs: 0, stable: 0, minMs: Infinity, maxMs: 0 };
  value.count++;
  value.observeMs += observation.observeMs;
  value.stable += observation.stable;
  value.minMs = Math.min(value.minMs, observation.observeMs);
  value.maxMs = Math.max(value.maxMs, observation.observeMs);
  group.set(key, value);
}
if (successes.size !== 8 || !lines.some((x) => x.line === "NULLING_RUNTIME_RESULT=PASS")) throw new Error("Incomplete nulling evidence");
const channels = names.map((sensor, i) => {
  const f = successes.get(i);
  if (!f || f.sensor !== sensor) throw new Error(`Channel ${i + 1} mismatch`);
  return { ch: i + 1, sensor, start: intervals[i][0], finish: intervals[i][1],
    seconds: Math.round((sec(intervals[i][1]) - sec(intervals[i][0])) * 1000) / 1000,
    dac: Number(f.dac), baselineV: Number(f.baseline), afterV: Number(f.after),
    deltaV: Number(f.delta), thresholdV: Number(f.threshold), status: "OK" };
});
const stages = [...group.values()].sort((a, b) => a.ch - b.ch || a.stage.localeCompare(b.stage));
await fs.writeFile(output, JSON.stringify({ channels, stages, observations, totalServiceSeconds: 476.964, totalCommandSeconds: 480.590, recordCount: lines.length }, null, 2));
console.log(JSON.stringify({ records: lines.length, observations: observations.length, stages: stages.length, perChannelSeconds: channels.map((x) => [x.sensor, x.seconds]), stageSummary: stages }));
