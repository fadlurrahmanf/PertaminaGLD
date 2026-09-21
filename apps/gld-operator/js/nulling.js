// Nulling tab: parses the firmware's per-stage nulling log into structured
// per-channel state, renders the channel cards, an expandable per-stage
// detail breakdown (baseline/exponential/binary/confirm + DAC source), and
// the signature sweep-meter visualizing the binary-search bracket live.

import { $, elements, state, SENSOR_NAMES, SENSOR_MUX_CHANNELS } from "./state.js";
import { appendLog, downloadText, numberField, setPanelOpen, stamp, showAlert, showConfirm } from "./ui.js";
import { tokenValue, channelIndexFromLog, applyAndAlert, sendCommand, sendCommandAndWaitAck } from "./serial-protocol.js";
import { saveSessionLog } from "./dataset.js";
import { renderQcNullingViews } from "./qc.js";

export const DAC_CODE_MAX = 4095;

// Session-only snapshot of the profile that existed immediately before a full
// Nulling run. This supports an old-to-new MCP comparison without persisting
// another profile on the GLD.
let previousNullingProfile = null;

function capturePreviousNullingProfile() {
  const profile = state.qc?.nullingProfile;
  if (!profile?.valid || !Array.isArray(profile.dacCode) || profile.dacCode.length !== 8) {
    previousNullingProfile = null;
    return;
  }
  previousNullingProfile = {
    profileId: profile.profileId,
    dacCode: profile.dacCode.map((value) => Number(value))
  };
}

function previousMcpForChannel(index) {
  const value = Number(previousNullingProfile?.dacCode?.[index]);
  return Number.isFinite(value) ? value : null;
}

export function latestFeatureOrderForNulling() {
  const statusOrder = state.status?.telemetry?.featureOrder;
  const historyOrder = state.history.length ? state.history[state.history.length - 1].featureOrder : [];
  return Array.isArray(statusOrder) && statusOrder.length ? statusOrder : historyOrder.length ? historyOrder : SENSOR_NAMES;
}

function summarizeNulling(line) {
  const ch = /ch=(\d+)/.exec(line)?.[1];
  if (line.startsWith("NULLING_WARMUP_START")) {
    const total = Number(tokenValue(line, "totalSec"));
    return Number.isFinite(total) ? `Pemanasan sensor dimulai: ${total} detik.` : "Pemanasan sensor dimulai.";
  }
  if (line.startsWith("NULLING_WARMUP remainingSec=")) {
    const remaining = Number(tokenValue(line, "remainingSec"));
    return Number.isFinite(remaining) ? `Pemanasan sensor: ${remaining} detik lagi.` : "Pemanasan sensor berlangsung.";
  }
  if (line.startsWith("NULLING_WARMUP_DONE")) return "Pemanasan sensor selesai; kalibrasi dimulai.";
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
  exponential_range_not_found: "Exponential search never met both the zero-margin and baseline-rise thresholds",
  confirm_failed: "No code in the confirm window met both the zero-margin and baseline-rise thresholds",
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
    baseline: { started: false, done: false, steps: 0, codeMin: null, codeMax: null, avgCount: null, value: null, validSamples: null, rows: [] },
    exponential: { started: false, done: false, failed: false, steps: 0, baselineRef: null, threshold: null, minFinalV: null, minBracketDac: null, lastCode: null, lastVoltage: null, lastDelta: null, low: null, high: null, failCode: null, maxCode: null, rows: [] },
    binary: { started: false, done: false, steps: 0, initialLow: null, initialHigh: null, selected: null, rows: [] },
    confirm: {
      started: false, done: false, failed: false, steps: 0, selected: null, start: null, end: null, sampleCount: null, belowCount: null, aboveCount: null, baselineRef: null, minFinalV: null, threshold: null,
      thresholdCount: 0, verifyCode: null, verifyVoltage: null, okCode: null, okVoltage: null, okMode: null, bumps: 0, rows: []
    },
    failStage: "", failReason: ""
  };
}

function savedProfileChannel(index) {
  const profile = state.qc?.nullingProfile;
  if (!profile?.valid || !profile.channelOk?.[index]) return null;
  const dac = Number(profile.dacCode?.[index]);
  const baseline = Number(profile.baselineV?.[index]);
  const after = Number(profile.afterV?.[index]);
  if (![dac, baseline, after].every(Number.isFinite)) return null;
  return { profileId: profile.profileId, dac, baseline, after };
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
      s.baseline.rows.push({
        dac: tokenValue(line, "code"),
        voltage: tokenValue(line, "voltage")
      });
    } else if (line.startsWith("NULLING_BASELINE_DONE")) {
      s.baseline.done = true;
      s.baseline.value = tokenValue(line, "baseline");
      s.baseline.validSamples = tokenValue(line, "validSamples");
    } else if (line.startsWith("NULLING_EXP_START")) {
      s.exponential.started = true;
      s.exponential.baselineRef = tokenValue(line, "baseline");
      s.exponential.threshold = tokenValue(line, "threshold");
      s.exponential.minFinalV = tokenValue(line, "minFinalV");
      s.exponential.minBracketDac = tokenValue(line, "minBracketDac");
    } else if (line.startsWith("NULLING_EXP_STEP")) {
      s.exponential.steps += 1;
      s.exponential.lastCode = tokenValue(line, "code");
      s.exponential.lastVoltage = tokenValue(line, "voltage");
      s.exponential.lastDelta = tokenValue(line, "delta");
      s.exponential.rows.push({
        dac: tokenValue(line, "code"),
        voltage: tokenValue(line, "voltage"),
        delta: tokenValue(line, "delta")
      });
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
      s.binary.rows.push({
        high: tokenValue(line, "high"),
        low: tokenValue(line, "low"),
        mid: tokenValue(line, "mid"),
        voltage: tokenValue(line, "voltage"),
        delta: tokenValue(line, "delta")
      });
    } else if (line.startsWith("NULLING_BIN_DONE")) {
      s.binary.done = true;
      s.binary.selected = tokenValue(line, "selected");
    } else if (line.startsWith("NULLING_CONFIRM_START")) {
      s.confirm.started = true;
      s.confirm.selected = tokenValue(line, "selected");
      s.confirm.start = tokenValue(line, "start");
      s.confirm.end = tokenValue(line, "end");
      s.confirm.sampleCount = tokenValue(line, "samples");
      s.confirm.belowCount = tokenValue(line, "below");
      s.confirm.aboveCount = tokenValue(line, "above");
      s.confirm.baselineRef = tokenValue(line, "baseline");
      s.confirm.minFinalV = tokenValue(line, "minFinalV");
      s.confirm.threshold = tokenValue(line, "threshold");
    } else if (line.startsWith("NULLING_CONFIRM_STEP")) {
      s.confirm.steps += 1;
      const v = Number.parseFloat(tokenValue(line, "voltage"));
      const explicitZeroMargin = tokenValue(line, "zeroMargin");
      const threshold = Number.parseFloat(s.confirm.threshold ?? s.exponential.threshold);
      const baseline = Number.parseFloat(s.confirm.baselineRef ?? s.exponential.baselineRef);
      const zeroMargin = explicitZeroMargin === "1"
        ? true
        : explicitZeroMargin === "0"
          ? false
          : Number.isFinite(v) && Number.isFinite(threshold) ? v >= -threshold : null;
      if (zeroMargin === true) s.confirm.thresholdCount += 1;
      const explicitOutBaseline = tokenValue(line, "outBaseline");
      const outBaseline = explicitOutBaseline === "1"
        ? true
        : explicitOutBaseline === "0"
          ? false
          : Number.isFinite(v) && Number.isFinite(baseline) && Number.isFinite(threshold)
            ? v - baseline >= threshold : null;
      s.confirm.rows.push({
        dac: tokenValue(line, "code"),
        voltage: tokenValue(line, "voltage"),
        delta: tokenValue(line, "delta"),
        zeroMargin,
        outBaseline
      });
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

  // A channel with no log lines this session ("Waiting") doesn't mean the
  // GLD was never nulled - the nulling result lives in the GLD's own NVS and
  // survives app reconnects/refreshes. GET_QC_STATUS reports that persisted
  // truth (state.qc.channels[i].nullingOk); when this session's logs are
  // silent for a channel, fall back to it instead of showing a stale
  // "Waiting/No nulling data" for a channel that is actually already OK.
  for (const channel of channels) {
    channel.saved = savedProfileChannel(channel.index);
    if (channel.tone === "idle" && channel.saved) {
      channel.stage = "Done (saved)";
      channel.tone = "pass";
      channel.detail = `Saved profile: #${channel.saved.profileId}`;
    } else if (channel.tone === "idle" && state.qc.channels[channel.index]?.nullingOk) {
      // Compatibility with an older firmware that reports the boolean QC
      // status but cannot yet provide its saved numeric profile.
      channel.stage = "Done (saved)";
      channel.tone = "pass";
      channel.detail = "Nulling OK - update firmware to view saved values";
    }
  }

  return channels;
}

const CONFIRM_MODE_TAG = {
  baseline_threshold_verified: "verified",
  positive_verified: "verified",
  fallback_above_min: "fallback"
};

// Short label/value rows instead of long sentences - one row per stage,
// meant to be scanned at a glance rather than read like a report. Each row
// keeps only the number a technician actually checks (step count, the
// resulting code/voltage, or the failure reason).
function nullingStageDetailRows(stages) {
  const rows = [];

  const b = stages.baseline;
  if (b.started) {
    rows.push({
      label: "Baseline",
      value: b.done ? `${b.value ?? "?"} V (${b.steps} steps)` : `scanning... (${b.steps} steps)`
    });
  }

  const e = stages.exponential;
  if (e.started && (e.threshold != null || e.minFinalV != null)) {
    rows.push({
      label: "Syarat bracket",
      value: `DAC bracket ≥ ${e.minBracketDac ?? "?"}; V ≥ −${e.threshold ?? "?"} V; V − baseline ≥ ${e.threshold ?? "?"} V; final ≥ ${e.minFinalV ?? "?"} V`
    });
  }

  if (e.started) {
    rows.push({
      label: "Exponential",
      value: e.done
        ? `range ${e.low ?? "?"}-${e.high ?? "?"} (${e.steps} steps)`
        : e.failed
          ? `failed (${e.steps} steps)`
          : `searching... (${e.steps} steps)`,
      fail: e.failed
    });
  }

  const bi = stages.binary;
  if (bi.started) {
    rows.push({
      label: "Binary search",
      value: bi.done ? `code ${bi.selected} (${bi.steps} steps)` : `narrowing... (${bi.steps} steps)`
    });
  }

  const c = stages.confirm;
  if (c.started) {
    rows.push({
      label: "Confirm",
      value: c.done
        ? `code ${c.okCode} @ ${c.okVoltage ?? "?"} V (${CONFIRM_MODE_TAG[c.okMode] || "ok"})`
        : c.failed
          ? "failed"
          : `checking... (${c.steps}/${c.sampleCount ?? "?"} codes; −${c.belowCount ?? "?"}/+${c.aboveCount ?? "?"})`,
      fail: c.failed
    });
  }

  if (stages.failStage) {
    rows.push({
      label: "Failed at",
      value: `${nullingStageLabel(stages.failStage)} - ${NULLING_FAIL_REASON_TEXT[stages.failReason] || stages.failReason || "unknown reason"}`,
      fail: true
    });
  }

  return rows;
}

function nullingDacSourceRow(channel) {
  const c = channel.stages.confirm;
  if (channel.stage !== "Done" || !c.done) return null;
  const bumpText = c.bumps > 0 ? ` (+${c.bumps} bump)` : "";
  return { label: "Final DAC", value: `${channel.dac}${bumpText}` };
}

function nullingMcpRow(channel) {
  // The service log supplies the final DAC before GET_QC_STATUS returns the
  // newly saved NVS profile. Prefer it so a completed run never briefly shows
  // the preceding profile as its own result.
  const current = Number(channel.tone === "pass" && channel.stage === "Done" ? channel.dac : channel.saved?.dac);
  if (!Number.isFinite(current)) return null;
  const previous = previousMcpForChannel(channel.index);
  if (!Number.isFinite(previous)) return `MCP: ${current}`;
  const delta = current - previous;
  const deltaText = delta > 0 ? `+${delta}` : String(delta);
  const previousProfile = Number(previousNullingProfile?.profileId);
  const previousLabel = Number.isFinite(previousProfile) ? `previous #${previousProfile}: ${previous}` : `previous ${previous}`;
  return `MCP: ${current} · ${previousLabel} · Δ ${deltaText}`;
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

function makeNullingDetailsStage(title, columns, rows, emptyText = "Tahap ini tidak dijalankan.") {
  const section = document.createElement("section");
  section.className = "nulling-details-stage";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.append(heading);

  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "nulling-details-empty";
    empty.textContent = emptyText;
    section.append(empty);
    return section;
  }

  const wrap = document.createElement("div");
  wrap.className = "nulling-details-table-wrap";
  const table = document.createElement("table");
  table.className = "nulling-details-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column.label;
    headRow.append(cell);
  }
  thead.append(headRow);
  table.append(thead);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const cell = document.createElement("td");
      const value = typeof column.value === "function" ? column.value(row) : row[column.value];
      cell.textContent = value == null || value === "" ? "—" : String(value);
      if (column.className) cell.className = typeof column.className === "function" ? column.className(row) : column.className;
      tr.append(cell);
    }
    body.append(tr);
  }
  table.append(body);
  wrap.append(table);
  section.append(wrap);
  return section;
}

async function copyNullingDetails(title, summary, content, button) {
  const text = [title.textContent, summary.textContent, content.innerText]
    .filter(Boolean)
    .join("\n\n");
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.append(fallback);
    fallback.select();
    const copied = document.execCommand("copy");
    fallback.remove();
    if (!copied) {
      button.textContent = "Copy gagal";
      setTimeout(() => { button.textContent = "Copy Details"; }, 1800);
      return;
    }
  }
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy Details"; }, 1800);
}

export function openNullingDetails(channel) {
  const modal = $("nullingDetailsModal");
  const title = $("nullingDetailsTitle");
  const summary = $("nullingDetailsSummary");
  const content = $("nullingDetailsContent");
  const copyButton = $("copyNullingDetailsBtn");
  if (!modal || !title || !summary || !content) return;

  title.textContent = `Nulling Details · CH${channel.index + 1} ${channel.sensor}`;
  summary.textContent = channel.tone === "pass"
    ? `Selesai berhasil · DAC akhir ${channel.dac || "—"} · ${channel.detail}`
    : `Selesai gagal · ${channel.detail}`;
  const threshold = channel.stages.confirm.threshold ?? channel.stages.exponential.threshold;
  const minFinalV = channel.stages.confirm.minFinalV ?? channel.stages.exponential.minFinalV;
  const minBracketDac = channel.stages.exponential.minBracketDac;
  const criteria = document.createElement("p");
  criteria.className = "status-line";
  if (threshold == null) {
    criteria.textContent = "Threshold run ini tidak tersedia pada log lama.";
  } else {
    const thresholdV = Number.parseFloat(threshold);
    const thresholdText = Number.isFinite(thresholdV)
      ? `${thresholdV.toFixed(6)} V (${(thresholdV * 1000).toFixed(3)} mV)`
      : `${threshold} V`;
    criteria.textContent = `Threshold run ini: ${thresholdText} · DAC bracket Exponential ≥ ${minBracketDac ?? "—"} · Batas nol: V ≥ −${threshold} V · Naik dari baseline: V − baseline ≥ ${threshold} V · Minimum final: V ≥ ${minFinalV ?? "—"} V`;
  }
  content.replaceChildren(
    criteria,
    makeNullingDetailsStage("1. Baseline", [
      { label: "DAC", value: "dac" },
      { label: "Voltage (V)", value: "voltage" }
    ], channel.stages.baseline.rows),
    makeNullingDetailsStage("2. Exponential", [
      { label: "DAC", value: "dac" },
      { label: "Voltage (V)", value: "voltage" },
      { label: "Naik dari baseline (V)", value: "delta" }
    ], channel.stages.exponential.rows),
    makeNullingDetailsStage("3. Binary Search", [
      { label: "High", value: "high" },
      { label: "Low", value: "low" },
      { label: "Mid", value: "mid" },
      { label: "Voltage (V)", value: "voltage" },
      { label: "Naik dari baseline (V)", value: "delta" }
    ], channel.stages.binary.rows, channel.stages.binary.started && channel.stages.binary.done
      ? `Tidak ada iterasi: braket ${channel.stages.binary.initialLow}–${channel.stages.binary.initialHigh} sudah selebar 1 DAC, sehingga tidak ada nilai tengah untuk diuji.`
      : undefined),
    makeNullingDetailsStage("4. Confirm", [
      { label: "DAC", value: "dac" },
      { label: "Voltage (V)", value: "voltage" },
      { label: "Naik dari baseline (V)", value: "delta" },
      {
        label: "Lewati batas nol",
        value: (row) => row.zeroMargin == null ? "—" : row.zeroMargin ? "Ya" : "Tidak",
        className: (row) => row.zeroMargin == null ? "" : row.zeroMargin ? "is-ok" : "is-fail"
      },
      {
        label: "Naik ≥ threshold dari baseline",
        value: (row) => row.outBaseline == null ? "—" : row.outBaseline ? "Ya" : "Tidak",
        className: (row) => row.outBaseline == null ? "" : row.outBaseline ? "is-ok" : "is-fail"
      }
    ], channel.stages.confirm.rows)
  );
  if (copyButton) {
    copyButton.textContent = "Copy Details";
    copyButton.onclick = () => { void copyNullingDetails(title, summary, content, copyButton); };
  }
  setPanelOpen(modal, true);
}

// ---- rendering ----

// `container` defaults to the Nulling tab's own grid; the QC tab reuses this
// same rendering (cards, sweep meter, expandable stage detail) by passing
// its own grid elements. `channelFilter` (array of indices) restricts which
// channels get a card - the QC tab's per-sensor sub-tabs pass a single index
// so only that channel's nulling progress shows there.
export function renderNullingChannels(container = elements.nullingChannels, channelFilter = null) {
  if (!container) return;
  const featureOrder = latestFeatureOrderForNulling();
  const allChannels = nullingChannelsFromLogs(state.nullingLogs, featureOrder);
  const channels = channelFilter ? allChannels.filter((c) => channelFilter.includes(c.index)) : allChannels;
  container.innerHTML = "";
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

    const mcpRow = nullingMcpRow(channel);
    if (mcpRow) {
      const savedLine = document.createElement("small");
      savedLine.textContent = mcpRow;
      card.append(savedLine);
    }

    const stageRows = nullingStageDetailRows(channel.stages);
    const sourceRow = nullingDacSourceRow(channel);
    const hasTerminalResult = channel.stage === "Done" || channel.tone === "fail";
    if (container === elements.nullingChannels && hasTerminalResult) {
      const detailsButton = document.createElement("button");
      detailsButton.type = "button";
      detailsButton.className = "nulling-details-button";
      detailsButton.textContent = "Details";
      detailsButton.addEventListener("click", () => openNullingDetails(channel));
      card.append(detailsButton);
    } else if (stageRows.length || sourceRow) {
      const alwaysVisible = container === elements.nullingChannels;
      const disclosure = document.createElement(alwaysVisible ? "section" : "details");
      disclosure.className = "disclosure nulling-stage-detail";
      if (alwaysVisible) {
        const label = document.createElement("strong");
        label.className = "nulling-stage-label";
        label.textContent = "Stage detail";
        disclosure.append(label);
      } else {
        disclosure.open = state.nullingExpandedChannels.has(channel.index);
        disclosure.addEventListener("toggle", () => {
          if (disclosure.open) state.nullingExpandedChannels.add(channel.index);
          else state.nullingExpandedChannels.delete(channel.index);
        });
        const summary = document.createElement("summary");
        summary.textContent = "Stage detail";
        disclosure.append(summary);
      }

      const kv = document.createElement("dl");
      kv.className = "kv";
      for (const row of stageRows) {
        const item = document.createElement("div");
        if (row.fail) item.className = "fail";
        const dt = document.createElement("dt");
        dt.textContent = row.label;
        const dd = document.createElement("dd");
        dd.textContent = row.value;
        item.append(dt, dd);
        kv.append(item);
      }
      if (sourceRow) {
        const item = document.createElement("div");
        item.className = "nulling-dac-source";
        const dt = document.createElement("dt");
        dt.textContent = sourceRow.label;
        const dd = document.createElement("dd");
        dd.textContent = sourceRow.value;
        item.append(dt, dd);
        kv.append(item);
      }
      disclosure.append(kv);
      card.append(disclosure);
    }

    container.append(card);
  }
}

function setNullingMcpIndicator(tone, text) {
  const indicator = $("nullingMcpIndicator");
  if (!indicator) return;
  indicator.classList.toggle("is-online", tone === "online");
  indicator.classList.toggle("is-offline", tone === "offline");
  indicator.classList.toggle("is-unknown", tone === "unknown");
  const label = indicator.querySelector("span:last-child");
  if (label) label.textContent = text;
}

export function resetNullingMcpIndicator() {
  setNullingMcpIndicator("unknown", "MCP4725 · 0x60: menunggu channel Nulling");
}

function updateNullingMcpIndicator(line) {
  const channel = channelIndexFromLog(line);
  if (channel === undefined) return;
  const sensor = tokenValue(line, "sensor") || SENSOR_NAMES[channel] || `CH${channel + 1}`;
  const mux = tokenValue(line, "mux") ?? SENSOR_MUX_CHANNELS[channel] ?? "?";
  const prefix = `MCP4725 · 0x60 · CH${channel + 1} ${sensor} · TCA mux ${mux}`;

  if (line.startsWith("NULLING_CH_START")) {
    setNullingMcpIndicator("unknown", `${prefix}: menunggu ACK write DAC`);
    return;
  }

  const ack = tokenValue(line, "ack") ?? tokenValue(line, "write");
  if (ack === "1") {
    setNullingMcpIndicator("online", `${prefix}: ACK write DAC terakhir`);
  } else if (ack === "0" || line.includes("_WRITE_FAIL") || tokenValue(line, "reason")?.includes("dac_")) {
    setNullingMcpIndicator("offline", `${prefix}: tidak ACK saat write DAC`);
  }
}

export function appendNulling(line) {
  if (line.startsWith("NULLING_SERVICE_START")) {
    state.nullingLogs = [];
    state.nullingLogPausedCount = 0;
    resetNullingMcpIndicator();
  }
  state.nullingLogs.push(line);
  if (state.nullingLogs.length > 1200) state.nullingLogs.splice(0, state.nullingLogs.length - 1200);
  if (state.nullingLogPaused) {
    state.nullingLogPausedCount += 1;
    applyNullingLogPauseVisibility();
  } else {
    renderNullingLog();
  }
  updateNullingMcpIndicator(line);
  elements.nullingSummary.textContent = summarizeNulling(line);
  renderNullingChannels();
  renderQcNullingViews();
  if (line.startsWith("NULLING_SERVICE_DONE") || line.startsWith("NULLING_RUNTIME_RESULT")) {
    saveSessionLog(stamp(), "nulling");
  }
}

export function updateNullingMeta() {
  const nulling = state.status?.nulling || {};
  const retry = nulling.retryArmed === true ? "yes" : "no";
  const retryAvailable = nulling.retryAvailable === true;
  const retryFailedAvailable = nulling.retryFailedAvailable === true;
  const attempts = Number.isFinite(nulling.attemptCount) ? nulling.attemptCount : 0;
  const suffix = nulling.done === true ? " - Done" : nulling.running === true ? " - Running" : "";
  elements.nullingMeta.textContent = retryAvailable
    ? `Nulling belum lengkap — tinjau Details, lalu pilih Retry All atau Retry Failed. Attempts: ${attempts}`
    : `Retry armed: ${retry} - Attempts: ${attempts}${suffix}`;
  const retryButton = $("retryNullingBtn");
  if (retryButton) {
    retryButton.hidden = !retryAvailable;
    retryButton.disabled = !retryAvailable;
  }
  const retryFailedButton = $("retryFailedNullingBtn");
  if (retryFailedButton) {
    retryFailedButton.hidden = !retryAvailable || !retryFailedAvailable;
    retryFailedButton.disabled = !retryAvailable || !retryFailedAvailable;
  }
  if (Number.isFinite(nulling.thresholdV) && document.activeElement !== $("nullingThresholdV")) {
    $("nullingThresholdV").value = nulling.thresholdV * 1000;
  }
  if (Number.isFinite(nulling.minFinalV) && document.activeElement !== $("nullingMinFinalV")) {
    $("nullingMinFinalV").value = nulling.minFinalV;
  }
}

export async function applyNullingConfig() {
  const thresholdMv = numberField("nullingThresholdV");
  const thresholdV = thresholdMv / 1000;
  const minFinalV = numberField("nullingMinFinalV");
  if (!Number.isFinite(thresholdV) || thresholdV <= 0) {
    appendLog("NULLING_CONFIG_REJECTED rise threshold must be > 0 mV", "in");
    return;
  }
  if (!Number.isFinite(minFinalV) || minFinalV < -2.497 || minFinalV > 2.497) {
    appendLog("NULLING_CONFIG_REJECTED minFinalV must be within -2.497..2.497 V", "in");
    return;
  }
  await applyAndAlert(`SET_NULLING_CONFIG_JSON ${JSON.stringify({ thresholdV, minFinalV })}`, "SET_NULLING_CONFIG", "Apply Nulling Limits");
}

export async function requestFullNulling() {
  const alarmLatched = state.status?.alarmLatched === true;
  const confirmed = await showConfirm(
    alarmLatched
      ? "Alarm latch aktif. Konfirmasi hanya jika Anda sudah memastikan area/sensor clean air secara fisik. Ini dicatat sebagai acknowledgement operator, tidak menguji sensor dan tidak mematikan output alarm saat ini. Lanjutkan Nulling?"
      : "Pastikan area/sensor clean air secara fisik sebelum melanjutkan. GLD akan restart dan menjalankan nulling pada seluruh 8 channel. Lanjutkan Nulling?",
    "Confirm Clean Air Before Nulling"
  );
  if (!confirmed) return;

  try {
    capturePreviousNullingProfile();
    const ack = await sendCommandAndWaitAck("VERIFY_CLEAN_AIR_FOR_NULLING", "VERIFY_CLEAN_AIR_FOR_NULLING");
    if (ack.status !== "ok") {
      await showAlert(`Nulling dibatalkan: ${ack.message || ack.status}`, "error", "Alarm Latch");
      return;
    }
    const modeAck = await sendCommandAndWaitAck("SET_MODE nulling", "SET_MODE");
    if (modeAck.status !== "ok") {
      await showAlert(`Nulling tidak dimulai: ${modeAck.message || modeAck.status}`, "error", "Mode Nulling");
      return;
    }
    appendLog("NULLING_APP_STARTED ESP will reboot; waiting for calibration result and saved profile", "in");
  } catch (error) {
    await showAlert(`Nulling dibatalkan: ${error.message}`, "error", "Alarm Latch");
  }
}

function renderNullingLog() {
  if (!elements.nullingLog) return;
  elements.nullingLog.textContent = state.nullingLogs.join("\n");
  elements.nullingLog.scrollTop = elements.nullingLog.scrollHeight;
}

export function applyNullingLogPauseVisibility() {
  const button = elements.pauseNullingLogBtn;
  if (!button) return;
  button.textContent = state.nullingLogPaused
    ? `Resume${state.nullingLogPausedCount ? ` (${state.nullingLogPausedCount} new)` : ""}`
    : "Pause";
  button.classList.toggle("primary", state.nullingLogPaused);
}

export function toggleNullingLogPause() {
  state.nullingLogPaused = !state.nullingLogPaused;
  if (!state.nullingLogPaused) {
    state.nullingLogPausedCount = 0;
    renderNullingLog();
  }
  applyNullingLogPauseVisibility();
}

export function exportNullingLog() {
  downloadText(`GLD_nulling_${stamp()}.log`, `${state.nullingLogs.join("\n")}\n`);
}

export async function copyNullingLog() {
  const button = elements.copyNullingLogBtn;
  if (!state.nullingLogs.length) {
    if (button) {
      button.textContent = "Log kosong";
      setTimeout(() => { button.textContent = "Copy Log"; }, 1800);
    }
    return;
  }
  const text = `${state.nullingLogs.join("\n")}\n`;
  let copied = false;
  try {
    await navigator.clipboard.writeText(text);
    copied = true;
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.append(fallback);
    fallback.select();
    copied = document.execCommand("copy");
    fallback.remove();
  }
  if (button) {
    button.textContent = copied ? "Copied" : "Copy gagal";
    setTimeout(() => { button.textContent = "Copy Log"; }, 1800);
  }
}

export async function requestManualNullingRetry() {
  const ack = await sendCommandAndWaitAck("RETRY_NULLING", "RETRY_NULLING");
  if (ack.status !== "ok") {
    throw new Error(ack.message || ack.status || "Retry nulling ditolak");
  }
  appendLog("NULLING_APP_RETRY_REQUESTED full nulling retry queued", "in");
}

export async function requestFailedNullingRetry() {
  const ack = await sendCommandAndWaitAck("RETRY_FAILED_NULLING", "RETRY_FAILED_NULLING");
  if (ack.status !== "ok") {
    throw new Error(ack.message || ack.status || "Retry channel gagal ditolak");
  }
  appendLog("NULLING_APP_RETRY_REQUESTED failed-channel nulling retry queued", "in");
}
