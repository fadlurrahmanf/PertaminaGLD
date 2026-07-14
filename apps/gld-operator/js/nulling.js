// Nulling tab: parses the firmware's per-stage nulling log into structured
// per-channel state, renders the channel cards, an expandable per-stage
// detail breakdown (baseline/exponential/binary/confirm + DAC source), and
// the signature sweep-meter visualizing the binary-search bracket live.

import { $, elements, state, SENSOR_NAMES } from "./state.js";
import { appendLog, numberField, stamp } from "./ui.js";
import { tokenValue, channelIndexFromLog, sendCommand } from "./serial-protocol.js";
import { saveSessionLog } from "./dataset.js";

const DAC_CODE_MAX = 4095;

export function latestFeatureOrderForNulling() {
  const statusOrder = state.status?.telemetry?.featureOrder;
  const historyOrder = state.history.length ? state.history[state.history.length - 1].featureOrder : [];
  return Array.isArray(statusOrder) && statusOrder.length ? statusOrder : historyOrder.length ? historyOrder : SENSOR_NAMES;
}

function summarizeNulling(line) {
  const ch = /ch=(\d+)/.exec(line)?.[1];
  if (line.includes("SERVICE_START")) return "Nulling service started.";
  if (line.includes("BASELINE")) return ch ? `Channel ${Number(ch) + 1} baseline scan.` : "Baseline scan.";
  if (line.includes("EXP_")) return ch ? `Channel ${Number(ch) + 1} exponential range search.` : "Exponential range search.";
  if (line.includes("BIN_")) return ch ? `Channel ${Number(ch) + 1} binary search.` : "Binary search.";
  if (line.includes("CONFIRM")) return ch ? `Channel ${Number(ch) + 1} confirmation.` : "Confirmation.";
  if (line.includes("SERVICE_DONE")) return line.includes("status=Ok") ? "Nulling complete: PASS." : line;
  if (line.includes("RUNTIME_RESULT")) return line.replaceAll("_", " ");
  return line;
}

const NULLING_FAIL_REASON_TEXT = {
  dac_zero_write_failed: "Could not zero the DAC before the baseline scan",
  baseline_no_valid_samples: "No valid ADC samples during the baseline scan",
  exponential_range_not_found: "Exponential search never crossed the delta threshold",
  confirm_failed: "No code in the confirm window crossed the baseline-relative threshold",
  dac_final_write_failed: "Could not write the final DAC code",
  after_read_invalid: "Final voltage read was invalid",
  after_threshold_not_met: "Final voltage did not reconfirm the baseline-relative threshold",
  after_voltage_negative: "Final voltage was below the configured minimum",
  none: "Unknown failure"
};

function nullingStageLabel(stage) {
  const labels = { zero: "Start", baseline: "Baseline", exponential: "Exponential", binary: "Binary", confirm: "Confirm", final_write: "Final write", after_read: "After-read", final_check: "Final check" };
  return labels[stage] || stage || "Unknown";
}

function nullingDetail(line) {
  if (line.startsWith("NULLING_CH_START")) return "Channel started";
  if (line.startsWith("NULLING_STAGE_TRANSITION")) {
    const from = tokenValue(line, "from");
    const to = tokenValue(line, "to");
    return `Moving from ${nullingStageLabel(from)} to ${nullingStageLabel(to)}...`;
  }
  if (line.startsWith("NULLING_BASELINE_START")) return "Searching baseline";
  if (line.startsWith("NULLING_EXP_START")) return "Finding exponential range";
  if (line.startsWith("NULLING_EXP_RANGE")) return "Range locked";
  if (line.startsWith("NULLING_BIN_START")) return "Binary search started";
  if (line.startsWith("NULLING_BIN_DONE")) return "Binary selected";
  if (line.startsWith("NULLING_CONFIRM_START")) return "Confirmation window";
  if (line.startsWith("NULLING_CONFIRM_OK")) return "Confirmation OK";
  if (line.startsWith("NULLING_CH_OK")) return "Channel OK";
  if (line.startsWith("NULLING_CH_FAIL")) {
    const stage = tokenValue(line, "stage");
    const reason = tokenValue(line, "reason");
    const reasonText = NULLING_FAIL_REASON_TEXT[reason] || reason || "Unknown failure";
    return `Failed at ${nullingStageLabel(stage)}: ${reasonText}`;
  }

  const delta = tokenValue(line, "delta");
  const low = tokenValue(line, "low");
  const high = tokenValue(line, "high");
  const valid = tokenValue(line, "valid");
  const sample = tokenValue(line, "sample");
  const parts = [
    sample ? `sample ${sample}` : undefined,
    low && high ? `range ${low}-${high}` : undefined,
    delta ? `delta ${delta}` : undefined,
    valid ? `valid ${valid}` : undefined
  ].filter(Boolean);
  if (parts.length) return parts.join(" - ");
  return line.replace(/^NULLING_[A-Z_]+=?\s*/, "").slice(0, 72);
}

function initNullingStages() {
  return {
    baseline: { started: false, done: false, steps: 0, codeMin: null, codeMax: null, avgCount: null, value: null, validSamples: null },
    exponential: { started: false, done: false, failed: false, steps: 0, baselineRef: null, threshold: null, target: null, lastCode: null, lastVoltage: null, lastDelta: null, low: null, high: null, failCode: null, maxCode: null },
    binary: { started: false, done: false, steps: 0, initialLow: null, initialHigh: null, selected: null },
    confirm: {
      started: false, done: false, failed: false, steps: 0, start: null, end: null, minFinalV: null, threshold: null, target: null, wide: null,
      thresholdCount: 0, verifyCode: null, verifyVoltage: null, okCode: null, okVoltage: null, okMode: null, bumps: 0
    },
    failStage: "", failReason: ""
  };
}

function nullingChannelsFromLogs(logs, featureOrder = SENSOR_NAMES) {
  const channels = Array.from({ length: 8 }, (_, index) => ({
    index,
    sensor: featureOrder[index] || SENSOR_NAMES[index] || `CH${index + 1}`,
    stage: "Waiting",
    tone: "idle",
    detail: "No nulling data",
    dac: "",
    baseline: "",
    after: "",
    stages: initNullingStages()
  }));

  for (const line of logs) {
    const index = channelIndexFromLog(line);
    if (index === undefined) continue;
    const channel = channels[index];
    const s = channel.stages;
    channel.sensor = tokenValue(line, "sensor") ?? channel.sensor;
    channel.detail = nullingDetail(line);

    if (line.startsWith("NULLING_CH_START")) {
      channel.stage = "Start";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_BASELINE_")) {
      channel.stage = "Baseline";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_EXP_")) {
      channel.stage = "Exponential";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_BIN_")) {
      channel.stage = "Binary";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_CONFIRM_")) {
      channel.stage = "Confirm";
      channel.tone = "active";
    }

    const status = tokenValue(line, "status")?.toUpperCase();
    if (line.startsWith("NULLING_CH_OK") || status === "PASS" || status === "OK") {
      channel.stage = "Done";
      channel.tone = "pass";
    } else if (line.startsWith("NULLING_CH_FAIL") || status === "FAIL" || status === "ERROR") {
      const failStage = tokenValue(line, "stage");
      channel.stage = failStage ? `Failed (${nullingStageLabel(failStage)})` : "Failed";
      channel.tone = "fail";
      s.failStage = failStage || "";
      s.failReason = tokenValue(line, "reason") || "";
    }

    channel.dac = tokenValue(line, "dac") ?? tokenValue(line, "selected") ?? tokenValue(line, "code") ?? channel.dac;
    channel.baseline = tokenValue(line, "baseline") ?? channel.baseline;
    channel.after = tokenValue(line, "after") ?? tokenValue(line, "voltage") ?? channel.after;

    if (line.startsWith("NULLING_BASELINE_START")) {
      s.baseline.started = true;
      s.baseline.codeMin = tokenValue(line, "codeMin");
      s.baseline.codeMax = tokenValue(line, "codeMax");
      s.baseline.avgCount = tokenValue(line, "avgCount");
    } else if (line.startsWith("NULLING_BASELINE_STEP")) {
      s.baseline.steps += 1;
    } else if (line.startsWith("NULLING_BASELINE_DONE")) {
      s.baseline.done = true;
      s.baseline.value = tokenValue(line, "baseline");
      s.baseline.validSamples = tokenValue(line, "validSamples");
    } else if (line.startsWith("NULLING_EXP_START")) {
      s.exponential.started = true;
      s.exponential.baselineRef = tokenValue(line, "baseline");
      s.exponential.threshold = tokenValue(line, "threshold");
      s.exponential.target = tokenValue(line, "target");
    } else if (line.startsWith("NULLING_EXP_STEP")) {
      s.exponential.steps += 1;
      s.exponential.lastCode = tokenValue(line, "code");
      s.exponential.lastVoltage = tokenValue(line, "voltage");
      s.exponential.lastDelta = tokenValue(line, "delta");
    } else if (line.startsWith("NULLING_EXP_RANGE")) {
      s.exponential.done = true;
      s.exponential.low = tokenValue(line, "low");
      s.exponential.high = tokenValue(line, "high");
    } else if (line.startsWith("NULLING_EXP_FAIL")) {
      s.exponential.failed = true;
      s.exponential.failCode = tokenValue(line, "lastCode");
      s.exponential.maxCode = tokenValue(line, "maxCode");
    } else if (line.startsWith("NULLING_BIN_START")) {
      s.binary.started = true;
      s.binary.initialLow = tokenValue(line, "low");
      s.binary.initialHigh = tokenValue(line, "high");
    } else if (line.startsWith("NULLING_BIN_STEP")) {
      s.binary.steps += 1;
    } else if (line.startsWith("NULLING_BIN_DONE")) {
      s.binary.done = true;
      s.binary.selected = tokenValue(line, "selected");
    } else if (line.startsWith("NULLING_CONFIRM_START")) {
      s.confirm.started = true;
      s.confirm.start = tokenValue(line, "start");
      s.confirm.end = tokenValue(line, "end");
      s.confirm.minFinalV = tokenValue(line, "minFinalV");
      s.confirm.threshold = tokenValue(line, "threshold");
      s.confirm.target = tokenValue(line, "target");
      s.confirm.wide = tokenValue(line, "wide") === "1";
    } else if (line.startsWith("NULLING_CONFIRM_STEP")) {
      s.confirm.steps += 1;
      const v = Number.parseFloat(tokenValue(line, "voltage"));
      const crossed = tokenValue(line, "crossed");
      if (crossed === "1" || (crossed === undefined && Number.isFinite(v) && v >= 0)) s.confirm.thresholdCount += 1;
    } else if (line.startsWith("NULLING_CONFIRM_VERIFY")) {
      s.confirm.verifyCode = tokenValue(line, "code");
      s.confirm.verifyVoltage = tokenValue(line, "voltage");
    } else if (line.startsWith("NULLING_CONFIRM_OK")) {
      s.confirm.done = true;
      s.confirm.okCode = tokenValue(line, "code");
      s.confirm.okVoltage = tokenValue(line, "voltage");
      s.confirm.okMode = tokenValue(line, "mode");
    } else if (line.startsWith("NULLING_CONFIRM_FAIL")) {
      s.confirm.failed = true;
    } else if (line.startsWith("NULLING_FINAL_BUMP")) {
      const bumpNumber = Number.parseInt(tokenValue(line, "bump"), 10);
      if (Number.isFinite(bumpNumber)) s.confirm.bumps = bumpNumber;
    }
  }

  return channels;
}

const CONFIRM_MODE_TEXT = {
  baseline_threshold_verified: "baseline-relative threshold, re-verified on an independent read",
  positive_verified: "positive reading, re-verified on an independent read",
  fallback_above_min: "no positive candidate reconfirmed; used the closest code that still cleared the configured minimum"
};

function nullingStageDetailLines(stages) {
  const lines = [];
  const b = stages.baseline;
  if (b.started) {
    lines.push(
      b.done
        ? `Baseline: averaged ${b.avgCount ?? "?"} sample(s) per code across codes ${b.codeMin ?? "0"}-${b.codeMax ?? "?"} (${b.steps} step(s) logged) -> ${b.value ?? "?"} V from ${b.validSamples ?? "?"} valid sample(s).`
        : `Baseline: scanning codes ${b.codeMin ?? "0"}-${b.codeMax ?? "?"}, ${b.steps} step(s) so far.`
    );
  }
  const e = stages.exponential;
  if (e.started) {
    if (e.done) {
      lines.push(`Exponential: searched from baseline ${e.baselineRef ?? "?"} V to target ${e.target ?? "?"} V (dynamic threshold ${e.threshold ?? "?"} V) in ${e.steps} step(s), code doubling up to ${e.lastCode ?? "?"} -> found bracket [${e.low ?? "?"}, ${e.high ?? "?"}] at ${e.lastVoltage ?? "?"} V.`);
    } else if (e.failed) {
      lines.push(`Exponential: FAILED after ${e.steps} step(s) - never crossed the threshold up to code ${e.failCode ?? "?"} (max ${e.maxCode ?? "?"}).`);
    } else {
      lines.push(`Exponential: searching, ${e.steps} step(s) so far, last code ${e.lastCode ?? "?"} at ${e.lastVoltage ?? "?"} V (delta ${e.lastDelta ?? "?"}).`);
    }
  }
  const bi = stages.binary;
  if (bi.started) {
    lines.push(
      bi.done
        ? `Binary search: narrowed bracket [${bi.initialLow ?? "?"}, ${bi.initialHigh ?? "?"}] in ${bi.steps} step(s) -> selected code ${bi.selected ?? "?"}.`
        : `Binary search: narrowing bracket [${bi.initialLow ?? "?"}, ${bi.initialHigh ?? "?"}], ${bi.steps} step(s) so far.`
    );
  }
  const c = stages.confirm;
  if (c.started) {
    const windowText = `window [${c.start ?? "?"}, ${c.end ?? "?"}] (${c.wide ? "wide" : "normal"} search, target ${c.target ?? "?"} V, threshold ${c.threshold ?? "?"} V)`;
    if (c.done) {
      const modeText = CONFIRM_MODE_TEXT[c.okMode] || c.okMode || "unknown mode";
      const bumpText = c.bumps > 0
        ? ` -> ${c.bumps} final bump(s) of +1 DAC code because the independent final read was still below threshold`
        : "";
      lines.push(`Confirm: scanned ${c.steps} code(s) in ${windowText}, ${c.thresholdCount} threshold candidate(s) found -> chose code ${c.okCode ?? "?"} at ${c.okVoltage ?? "?"} V (${modeText})${bumpText}.`);
    } else if (c.failed) {
      lines.push(`Confirm: FAILED after scanning ${c.steps} code(s) in ${windowText} - no candidate reconfirmed the baseline-relative threshold.`);
    } else {
      lines.push(`Confirm: scanning ${windowText}, ${c.steps} code(s) checked so far, ${c.thresholdCount} threshold candidate(s).`);
    }
  }
  if (stages.failStage) {
    const reasonText = NULLING_FAIL_REASON_TEXT[stages.failReason] || stages.failReason || "unknown reason";
    lines.push(`Failed at stage "${nullingStageLabel(stages.failStage)}": ${reasonText}.`);
  }
  return lines;
}

function nullingDacSourceText(channel) {
  const c = channel.stages.confirm;
  if (channel.stage !== "Done" || !c.done) return "";
  const modeText = CONFIRM_MODE_TEXT[c.okMode] || c.okMode || "unknown mode";
  if (c.bumps > 0) {
    return `DAC source: Confirm stage chose code ${c.okCode} (${modeText}), then +${c.bumps} final bump(s) -> final DAC code ${channel.dac}.`;
  }
  return `DAC source: Confirm stage chose code ${c.okCode} (${modeText}) -> final DAC code ${channel.dac}.`;
}

// ---- signature element: sweep meter ----
// Visualizes the actual algorithm state: the search bracket currently in
// play (exponential range / binary bisection / confirm window) and a
// needle at the most recent code tried, scaled to the DAC's 0-4095 range.

function sweepMeterState(channel) {
  const s = channel.stages;
  let low = null;
  let high = null;
  let needle = null;
  if (s.confirm.started) {
    low = Number(s.confirm.start);
    high = Number(s.confirm.end);
    needle = Number(s.confirm.done ? s.confirm.okCode : (s.confirm.verifyCode ?? channel.dac));
  } else if (s.binary.started) {
    low = Number(s.binary.initialLow);
    high = Number(s.binary.initialHigh);
    needle = Number(s.binary.done ? s.binary.selected : channel.dac);
  } else if (s.exponential.started) {
    low = 0;
    high = Number(s.exponential.done ? s.exponential.high : DAC_CODE_MAX);
    needle = Number(s.exponential.lastCode ?? channel.dac);
  } else if (s.baseline.started) {
    low = Number(s.baseline.codeMin ?? 0);
    high = Number(s.baseline.codeMax ?? 10);
    needle = Number(channel.dac);
  }
  return {
    active: s.baseline.started || s.exponential.started || s.binary.started || s.confirm.started,
    low,
    high,
    needle,
    pass: channel.stage === "Done"
  };
}

function renderSweepMeter(channel) {
  const info = sweepMeterState(channel);
  if (!info.active) return null;

  const wrap = document.createElement("div");
  const meter = document.createElement("div");
  meter.className = "sweep-meter";

  if (Number.isFinite(info.low) && Number.isFinite(info.high) && info.high > info.low) {
    const bracket = document.createElement("div");
    bracket.className = "sweep-meter-bracket";
    const left = Math.max(0, info.low);
    const right = Math.min(DAC_CODE_MAX, info.high);
    bracket.style.left = `${(left / DAC_CODE_MAX) * 100}%`;
    bracket.style.width = `${Math.max(0.6, ((right - left) / DAC_CODE_MAX) * 100)}%`;
    meter.append(bracket);
  }
  if (Number.isFinite(info.needle)) {
    const needle = document.createElement("div");
    needle.className = `sweep-meter-needle${info.pass ? " pass" : ""}`;
    const pct = (Math.min(DAC_CODE_MAX, Math.max(0, info.needle)) / DAC_CODE_MAX) * 100;
    needle.style.left = `${pct}%`;
    meter.append(needle);
  }

  const caption = document.createElement("div");
  caption.className = "sweep-meter-caption";
  caption.textContent = `DAC 0-${DAC_CODE_MAX}${Number.isFinite(info.needle) ? ` - code ${info.needle}` : ""}`;
  wrap.append(meter, caption);
  return wrap;
}

// ---- rendering ----

export function renderNullingChannels() {
  const featureOrder = latestFeatureOrderForNulling();
  const channels = nullingChannelsFromLogs(state.nullingLogs, featureOrder);
  elements.nullingChannels.innerHTML = "";
  for (const channel of channels) {
    const card = document.createElement("article");
    card.className = `channel-card ${channel.tone}`.trim();

    const head = document.createElement("div");
    head.className = "channel-card-head";
    const title = document.createElement("strong");
    title.textContent = `CH${channel.index + 1}`;
    const sensor = document.createElement("span");
    sensor.textContent = channel.sensor;
    head.append(title, sensor);

    const stage = document.createElement("span");
    stage.className = "channel-stage";
    stage.textContent = channel.stage;

    const detail = document.createElement("small");
    detail.textContent = channel.detail;

    card.append(head, stage);
    const sweepMeter = renderSweepMeter(channel);
    if (sweepMeter) card.append(sweepMeter);
    card.append(detail);

    const extra = [channel.dac ? `DAC ${channel.dac}` : "", channel.baseline ? `base ${channel.baseline}` : "", channel.after ? `after ${channel.after}` : ""].filter(Boolean);
    if (extra.length) {
      const extraLine = document.createElement("small");
      extraLine.textContent = extra.join(" - ");
      card.append(extraLine);
    }

    const stageLines = nullingStageDetailLines(channel.stages);
    const sourceText = nullingDacSourceText(channel);
    if (stageLines.length || sourceText) {
      const disclosure = document.createElement("details");
      disclosure.className = "disclosure nulling-stage-detail";
      disclosure.open = state.nullingExpandedChannels.has(channel.index);
      disclosure.addEventListener("toggle", () => {
        if (disclosure.open) state.nullingExpandedChannels.add(channel.index);
        else state.nullingExpandedChannels.delete(channel.index);
      });
      const summary = document.createElement("summary");
      summary.textContent = "Stage detail";
      disclosure.append(summary);
      for (const line of stageLines) {
        const p = document.createElement("small");
        p.textContent = line;
        disclosure.append(p);
      }
      if (sourceText) {
        const sourceLine = document.createElement("small");
        sourceLine.className = "nulling-dac-source";
        sourceLine.textContent = sourceText;
        disclosure.append(sourceLine);
      }
      card.append(disclosure);
    }

    elements.nullingChannels.append(card);
  }
}

export function appendNulling(line) {
  if (line.startsWith("NULLING_SERVICE_START")) {
    state.nullingLogs = [];
  }
  state.nullingLogs.push(line);
  if (state.nullingLogs.length > 1200) state.nullingLogs.splice(0, state.nullingLogs.length - 1200);
  elements.nullingLog.textContent = state.nullingLogs.join("\n");
  elements.nullingLog.scrollTop = elements.nullingLog.scrollHeight;
  elements.nullingSummary.textContent = summarizeNulling(line);
  renderNullingChannels();
  if (line.startsWith("NULLING_SERVICE_DONE") || line.startsWith("NULLING_RUNTIME_RESULT")) {
    saveSessionLog(stamp(), "nulling");
  }
}

export function updateNullingMeta() {
  const nulling = state.status?.nulling || {};
  const retry = nulling.retryArmed === true ? "yes" : "no";
  const attempts = Number.isFinite(nulling.attemptCount) ? nulling.attemptCount : 0;
  const suffix = nulling.done === true ? " - Done" : nulling.running === true ? " - Running" : "";
  elements.nullingMeta.textContent = `Retry armed: ${retry} - Attempts: ${attempts}${suffix}`;
  if (Number.isFinite(nulling.thresholdV) && document.activeElement !== $("nullingThresholdV")) {
    $("nullingThresholdV").value = nulling.thresholdV;
  }
  if (Number.isFinite(nulling.minFinalV) && document.activeElement !== $("nullingMinFinalV")) {
    $("nullingMinFinalV").value = nulling.minFinalV;
  }
}

export async function applyNullingConfig() {
  const thresholdV = numberField("nullingThresholdV");
  const minFinalV = numberField("nullingMinFinalV");
  if (!Number.isFinite(thresholdV) || thresholdV <= 0) {
    appendLog("NULLING_CONFIG_REJECTED thresholdV must be > 0", "in");
    return;
  }
  if (!Number.isFinite(minFinalV)) {
    appendLog("NULLING_CONFIG_REJECTED minFinalV must be a number", "in");
    return;
  }
  await sendCommand(`SET_NULLING_CONFIG_JSON ${JSON.stringify({ thresholdV, minFinalV })}`);
}
