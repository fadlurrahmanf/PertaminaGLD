// Telemetry chart: hand-rolled canvas line chart (kept dependency-free per
// the "stay lightweight" constraint) + CSV export. Drawn twice from the same
// state.history feed - once on the Running tab, once on the Dataset tab
// (with START/STOP session markers overlaid) - via drawOneChart() so both
// stay pixel-for-pixel consistent.

import { $, elements, state, CHART_COLORS, SENSOR_NAMES } from "./state.js";
import { csvCell, downloadText, stamp } from "./ui.js";

// The range dropdowns are display zoom only. Keep enough browser-side history
// for the largest offered zoom (one hour) so widening a range never loses
// samples that were collected while a shorter view was selected.
const HISTORY_RETENTION_MS = 60 * 60 * 1000;
const Y_AXIS_TICK_COUNT = 10;
const ALL_SENSOR_CHANNELS = [0, 1, 2, 3, 4, 5, 6, 7];

export function isSensorChartSeriesVisible(channel) {
  return Number.isInteger(channel) && channel >= 0 && channel < ALL_SENSOR_CHANNELS.length &&
    !state.hiddenSensorChartChannels.has(channel);
}

// This affects the Running chart display only; it never removes collected
// telemetry or changes the Dataset chart, export, model, or firmware values.
export function toggleSensorChartSeries(channel) {
  if (!Number.isInteger(channel) || channel < 0 || channel >= ALL_SENSOR_CHANNELS.length) return;
  if (state.hiddenSensorChartChannels.has(channel)) state.hiddenSensorChartChannels.delete(channel);
  else state.hiddenSensorChartChannels.add(channel);
  drawChart();
}

export function pruneHistory() {
  const cutoff = Date.now() - HISTORY_RETENTION_MS;
  while (state.history.length && state.history[0].ts < cutoff) state.history.shift();
}

function drawGrid(ctx, pad, width, height) {
  ctx.strokeStyle = "#35301f";
  ctx.lineWidth = 1;
  ctx.strokeRect(pad.left, pad.top, width, height);
  ctx.beginPath();
  for (let i = 1; i < Y_AXIS_TICK_COUNT - 1; i += 1) {
    const y = pad.top + (height / (Y_AXIS_TICK_COUNT - 1)) * i;
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + width, y);
  }
  for (let i = 1; i < 5; i += 1) {
    const x = pad.left + (width / 5) * i;
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + height);
  }
  ctx.stroke();
}

function drawYAxisTicks(ctx, pad, width, height, min, max) {
  const fraction = 1 / (Y_AXIS_TICK_COUNT - 1);
  const decimals = Math.abs(max - min) < 0.001 ? 6 : 4;
  const tickValues = Array.from({ length: Y_AXIS_TICK_COUNT }, (_, tick) => (
    max - (max - min) * fraction * tick
  ));
  const zeroTolerance = Math.abs(max - min) / 100000;
  if (!tickValues.some((value) => Math.abs(value) <= zeroTolerance)) tickValues.push(0);
  tickValues.sort((a, b) => b - a);

  const zeroY = pad.top + (1 - (0 - min) / (max - min)) * height;
  ctx.beginPath();
  ctx.strokeStyle = "#f3c969";
  ctx.lineWidth = 1.75;
  ctx.setLineDash([7, 5]);
  ctx.moveTo(pad.left, zeroY);
  ctx.lineTo(pad.left + width, zeroY);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "#8a8272";
  ctx.font = "13.5px 'Cascadia Mono', monospace";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const value of tickValues) {
    const y = pad.top + (1 - (value - min) / (max - min)) * height;
    ctx.fillText(value.toFixed(decimals), pad.left - 8, y);
  }
  ctx.textAlign = "start";
  ctx.textBaseline = "alphabetic";
}

function latestFeatureOrder(points) {
  for (let i = points.length - 1; i >= 0; i -= 1) {
    if (points[i].featureOrder.length) return points[i].featureOrder;
  }
  return ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"];
}

// `channelIndices` (default all 8) restricts which channels get a legend
// entry - used by the QC tab's single-channel charts, which only ever show
// one series.
export function renderLegend(labels, legendEl = elements.legend, channelIndices = null) {
  if (!legendEl) return;
  legendEl.innerHTML = "";
  const list = labels.length ? labels : ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"];
  const indices = channelIndices || list.map((_, index) => index);
  indices.forEach((index) => {
    const item = document.createElement("span");
    item.className = "legend-item";
    const swatch = document.createElement("i");
    swatch.className = "legend-swatch";
    swatch.style.background = CHART_COLORS[index];
    item.append(swatch, document.createTextNode(list[index] || `CH${index + 1}`));
    legendEl.appendChild(item);
  });
}

const ANALYSIS_MIN_SAMPLES = 5;
const ANALYSIS_ONE_MINUTE_MS = 60 * 1000;
const ANALYSIS_DIRECTION_WINDOW_MS = 5 * 1000;
const analysisDirectionState = new Map();

function analysisCell(text, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  return cell;
}

function formatAnalysisVoltage(value) {
  return Number.isFinite(value) ? `${value.toFixed(6)} V` : "-";
}

function formatAnalysisMilliVolts(value) {
  return Number.isFinite(value) ? `${(value * 1000).toFixed(2)} mV` : "-";
}

function formatAnalysisDuration(milliseconds) {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "-";
  const totalSeconds = Math.floor(milliseconds / 1000);
  const seconds = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  if (totalMinutes < 1) return `${String(seconds).padStart(2, "0")}s`;
  const minutes = totalMinutes % 60;
  const hours = Math.floor(totalMinutes / 60);
  if (hours < 1) return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function analysisDirection(delta) {
  return delta > 0 ? "+" : delta < 0 ? "-" : "=";
}

function directionReferencePoint(points, latestTimestamp) {
  if (!Number.isFinite(latestTimestamp)) return null;
  const target = latestTimestamp - ANALYSIS_DIRECTION_WINDOW_MS;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    if (points[index].ts <= target) return points[index];
  }
  return null;
}

function trackedAnalysisDirectionDuration(channel, direction, timestamp, sampleCount) {
  if (!Number.isFinite(timestamp)) return { duration: NaN, changed: false };
  const previous = analysisDirectionState.get(channel);
  // A fresh/cleared history begins a new direction session. Otherwise only a
  // displayed direction change resets its clock; zoom changes do not impose a
  // one-minute ceiling on the duration.
  if (sampleCount < 2 || !previous || previous.direction !== direction || timestamp < previous.lastTimestamp) {
    const changed = Boolean(previous && previous.direction !== direction && previous.direction !== "=" && direction !== "=" && sampleCount >= 2);
    analysisDirectionState.set(channel, { direction, since: timestamp, lastTimestamp: timestamp });
    return { duration: 0, changed };
  }
  previous.lastTimestamp = timestamp;
  return { duration: timestamp - previous.since, changed: false };
}

function analysisTrend(points, now) {
  const minutePoints = points.filter((point) => point.ts >= now - ANALYSIS_ONE_MINUTE_MS);
  if (minutePoints.length < 2) return { value: NaN, text: "Mengumpulkan", tone: "collecting" };
  const first = minutePoints[0];
  const last = minutePoints.at(-1);
  const elapsedMinutes = (last.ts - first.ts) / 60000;
  if (!Number.isFinite(elapsedMinutes) || elapsedMinutes <= 0) return { value: NaN, text: "Mengumpulkan", tone: "collecting" };
  const value = (last.value - first.value) / elapsedMinutes;
  const sign = value > 0 ? "+" : value < 0 ? "-" : "=";
  return { value, text: `${sign}${Math.abs(value * 1000).toFixed(2)} mV/min`, tone: value > 0 ? "up" : value < 0 ? "down" : "flat" };
}

function analysisStability(current, peakToPeak, trend, sampleCount) {
  if (sampleCount < ANALYSIS_MIN_SAMPLES || !Number.isFinite(peakToPeak) || !Number.isFinite(trend.value)) {
    return { text: "Mengumpulkan", tone: "collecting" };
  }
  // Relative limits let every MQ channel use a tolerance proportional to its
  // present voltage, with small absolute floors for low-voltage channels.
  const reference = Math.max(Math.abs(current), 0.002);
  const stableSpan = Math.max(0.00020, reference * 0.015);
  const warnSpan = stableSpan * 3;
  const stableTrend = Math.max(0.00010, reference * 0.006);
  const warnTrend = stableTrend * 3;
  const absTrend = Math.abs(trend.value);
  if (peakToPeak <= stableSpan && absTrend <= stableTrend) return { text: "Stabil", tone: "stable" };
  if (peakToPeak <= warnSpan && absTrend <= warnTrend) return { text: "Bergerak", tone: "moving" };
  return { text: "Fluktuatif", tone: "unstable" };
}

function renderRunningAnalysisTable() {
  const body = $("chartAnalysisBody");
  if (!body || !elements.rangeSelect) return;
  const now = Date.now();
  const rangeMs = Number(elements.rangeSelect.value) * 1000;
  const visible = state.history.filter((point) => point.ts >= now - rangeMs);
  const labels = latestFeatureOrder(visible);
  body.replaceChildren();
  if (!visible.length) {
    const row = document.createElement("tr");
    row.append(analysisCell("Menunggu telemetri.", "chart-analysis-empty"));
    row.firstChild.colSpan = 9;
    body.append(row);
    return;
  }

  for (const ch of ALL_SENSOR_CHANNELS) {
    const points = visible
      .map((point) => ({ ts: point.ts, value: Number(point.sensorVoltage?.[ch]), gain: Number(point.sensorGain?.[ch]) }))
      .filter((point) => Number.isFinite(point.value));
    // Direction is deliberately independent from the chart zoom: it always
    // compares the present sample with the newest valid sample at least five
    // seconds earlier in the retained telemetry stream.
    const historyPoints = state.history
      .map((point) => ({ ts: point.ts, value: Number(point.sensorVoltage?.[ch]) }))
      .filter((point) => Number.isFinite(point.value));
    const row = document.createElement("tr");
    if (!isSensorChartSeriesVisible(ch)) row.classList.add("is-hidden");
    const last = points.at(-1);
    const current = last?.value;
    const directionReference = directionReferencePoint(historyPoints, last?.ts);
    const delta = directionReference && last ? last.value - directionReference.value : NaN;
    const direction = Number.isFinite(delta) ? analysisDirection(delta) : "—";
    const previousDirection = analysisDirectionState.get(ch);
    const directionState = direction === "—"
      ? { duration: previousDirection && Number.isFinite(last?.ts) ? last.ts - previousDirection.since : NaN, changed: false }
      : trackedAnalysisDirectionDuration(ch, direction, last?.ts, points.length);
    const min = points.length ? Math.min(...points.map((point) => point.value)) : NaN;
    const max = points.length ? Math.max(...points.map((point) => point.value)) : NaN;
    const peakToPeak = Number.isFinite(min) && Number.isFinite(max) ? max - min : NaN;
    const trend = analysisTrend(points, now);
    const evaluatedStability = analysisStability(current, peakToPeak, trend, points.length);
    // Status intentionally communicates just the confirmed five-second
    // direction. A direction younger than ten seconds is not confirmed yet.
    const directionConfirmed = Number.isFinite(directionState.duration) && directionState.duration >= 10_000;
    const status = !directionConfirmed || direction === "=" || direction === "—"
      ? { text: "Stabil", tone: "stable" }
      : direction === "+"
        ? { text: "Menaik", tone: "up" }
        : { text: "Menurun", tone: "down" };
    const gainValues = [...new Set(points.map((point) => point.gain).filter(Number.isFinite))];
    const gain = Number.isFinite(last?.gain) ? `x${last.gain}` : "-";
    const gainTone = gainValues.length > 1 ? "gain-shift" : "";
    row.classList.add(`status-${status.tone}`);
    if (directionState.changed) row.classList.add("direction-flash");
    row.style.setProperty("--series-color", CHART_COLORS[ch]);
    row.append(
      analysisCell(labels[ch] || SENSOR_NAMES[ch] || `CH${ch + 1}`, "sensor"),
      analysisCell(formatAnalysisVoltage(current), "current"),
      analysisCell(gain, gainTone),
      analysisCell(formatAnalysisMilliVolts(delta), delta > 0 ? "up" : delta < 0 ? "down" : "flat"),
      analysisCell(direction, direction === "+" ? "up" : direction === "-" ? "down" : "flat"),
      analysisCell(formatAnalysisDuration(directionState.duration)),
      analysisCell(formatAnalysisMilliVolts(peakToPeak), evaluatedStability.tone),
      analysisCell(trend.text, trend.tone),
      analysisCell(status.text, status.tone)
    );
    body.append(row);
  }
}

// Draws one chart instance into `canvas`, reading its zoom range from
// `rangeSelect` and its legend into `legendEl`. `markers` is an optional
// list of { ts, color, label } vertical lines (used for dataset START/STOP).
// `channelIndices` (default all 8) restricts which sensor series get drawn -
// the QC tab's per-sensor sub-tabs pass a single-element array so only that
// channel's line appears, while its "All Sensor" view passes all 8.
export function drawOneChart(canvas, rangeSelect, legendEl, markers = [], channelIndices = null) {
  if (!canvas || !rangeSelect) return;
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, parent.clientWidth);
  // 0.7x of the previous 700-1050 range (which was itself 2.5x the
  // original 280-420), dialed back down after the chart read as too tall.
  const cssHeight = Math.max(490, Math.min(735, Math.round(window.innerHeight * 0.84)));
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  canvas.style.height = `${cssHeight}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = "#14110d";
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const channels = channelIndices || ALL_SENSOR_CHANNELS;
  const pad = { left: 58, right: 58, top: 18, bottom: 34 };
  const width = cssWidth - pad.left - pad.right;
  const height = cssHeight - pad.top - pad.bottom;
  const now = Date.now();
  const rangeMs = Number(rangeSelect.value) * 1000;
  const rangeStart = now - rangeMs;
  const visible = state.history.filter((point) => point.ts >= rangeStart);

  drawGrid(ctx, pad, width, height);

  if (!visible.length) {
    ctx.fillStyle = "#8a8272";
    ctx.font = "14px 'Segoe UI', sans-serif";
    ctx.fillText("Waiting for telemetry", pad.left + 12, pad.top + 24);
    renderLegend([], legendEl, channelIndices);
    return;
  }

  // Y-axis: either locked to the operator's Running-settings range (so the
  // chart stops rescaling as readings move) or auto-fit to what's visible -
  // auto-fit only considers the channels actually being drawn, so a
  // single-channel QC chart zooms to that sensor's own range instead of
  // being flattened by the other 7 channels' scale.
  let min;
  let max;
  const fixedAxis = $("chartYAxisFixed")?.checked === true;
  if (fixedAxis) {
    const fixedMin = Number($("chartYAxisMin")?.value);
    const fixedMax = Number($("chartYAxisMax")?.value);
    min = Number.isFinite(fixedMin) ? fixedMin : 0;
    max = Number.isFinite(fixedMax) && fixedMax > min ? fixedMax : min + 1;
  } else {
    min = Infinity;
    max = -Infinity;
    for (const point of visible) {
      for (const ch of channels) {
        const value = point.sensorVoltage[ch];
        if (Number.isFinite(value)) {
          min = Math.min(min, value);
          max = Math.max(max, value);
        }
      }
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      min = -0.01;
      max = 0.01;
    }
    if (Math.abs(max - min) < 0.00001) {
      max += 0.001;
      min -= 0.001;
    }
    const margin = (max - min) * 0.12;
    min -= margin;
    max += margin;
  }

  min = Math.min(min, 0);
  max = Math.max(max, 0);

  drawYAxisTicks(ctx, pad, width, height, min, max);

  // Vertical session markers (dataset START/STOP) drawn under the series
  // lines so the traces stay legible on top of them.
  for (const marker of markers) {
    if (!Number.isFinite(marker.ts) || marker.ts < rangeStart || marker.ts > now) continue;
    const x = pad.left + ((marker.ts - rangeStart) / rangeMs) * width;
    ctx.beginPath();
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = marker.color;
    ctx.lineWidth = 1.5;
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + height);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = marker.color;
    ctx.font = "600 13px 'Cascadia Mono', monospace";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(marker.label, x + 4, pad.top + 13);
  }

  const labels = latestFeatureOrder(visible);
  for (const ch of channels) {
    ctx.beginPath();
    ctx.lineWidth = 1.8;
    ctx.strokeStyle = CHART_COLORS[ch];
    let started = false;
    let firstValue = null;
    let firstY = null;
    let lastValue = null;
    let lastY = null;
    for (const point of visible) {
      const value = point.sensorVoltage[ch];
      if (!Number.isFinite(value)) continue;
      const x = pad.left + ((point.ts - rangeStart) / rangeMs) * width;
      const y = pad.top + (1 - (value - min) / (max - min)) * height;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
        firstValue = value;
        firstY = y;
      } else {
        ctx.lineTo(x, y);
      }
      lastValue = value;
      lastY = y;
    }
    ctx.stroke();

    // Direction at the left edge uses exactly the visible chart range: a
    // minus means the series began higher than its present value, a plus
    // means it rose, and equals means no net change in the displayed range.
    if (firstY != null && Number.isFinite(firstValue) && Number.isFinite(lastValue)) {
      const direction = firstValue > lastValue ? "−" : lastValue > firstValue ? "+" : "=";
      ctx.fillStyle = CHART_COLORS[ch];
      ctx.font = "700 15px 'Cascadia Mono', monospace";
      ctx.textBaseline = "middle";
      ctx.fillText(direction, pad.left + 5, firstY);
    }

    // End-of-series label at the chart's right edge, pinned to that
    // channel's most recent value so it rides up/down with the live line.
    if (lastY != null) {
      const label = labels[ch] || `CH${ch + 1}`;
      ctx.fillStyle = CHART_COLORS[ch];
      ctx.font = "600 14px 'Cascadia Mono', monospace";
      ctx.textBaseline = "middle";
      ctx.fillText(label, pad.left + width + 4, lastY);
    }
  }
  ctx.textBaseline = "alphabetic";
  renderLegend(labels, legendEl, channelIndices);
}

// Full Scale MCP Sweep popup chart: X axis is DAC/MCP code (0..codeMax), Y axis
// is measured voltage - unlike drawOneChart's time-indexed X axis, this plots
// one channel's voltage-vs-DAC-code response curve as a sweep streams in.
export function drawFullScaleSweepChart(canvas, points, codeMax, color = "#3ecf8e") {
  if (!canvas) return;
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, parent.clientWidth);
  const cssHeight = Math.max(320, Math.min(480, Math.round(window.innerHeight * 0.5)));
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  canvas.style.height = `${cssHeight}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = "#14110d";
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const pad = { left: 66, right: 20, top: 18, bottom: 34 };
  const width = cssWidth - pad.left - pad.right;
  const height = cssHeight - pad.top - pad.bottom;
  drawGrid(ctx, pad, width, height);

  if (!points.length) {
    ctx.fillStyle = "#8a8272";
    ctx.font = "14px 'Segoe UI', sans-serif";
    ctx.fillText("Click Start to sweep MCP min to max", pad.left + 12, pad.top + 24);
    return;
  }

  let min = Infinity;
  let max = -Infinity;
  for (const point of points) {
    if (!Number.isFinite(point.voltage)) continue;
    min = Math.min(min, point.voltage);
    max = Math.max(max, point.voltage);
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) { min = -0.01; max = 0.01; }
  if (Math.abs(max - min) < 0.00001) { max += 0.001; min -= 0.001; }
  const margin = (max - min) * 0.12;
  min -= margin;
  max += margin;

  min = Math.min(min, 0);
  max = Math.max(max, 0);

  drawYAxisTicks(ctx, pad, width, height, min, max);
  ctx.fillStyle = "#8a8272";
  ctx.font = "13.5px 'Cascadia Mono', monospace";
  ctx.fillText("0", pad.left, pad.top + height + 18);
  ctx.fillText(String(codeMax), pad.left + width - 24, pad.top + height + 18);

  ctx.beginPath();
  ctx.lineWidth = 1.8;
  ctx.strokeStyle = color;
  let started = false;
  for (const point of points) {
    if (!Number.isFinite(point.voltage)) continue;
    const x = pad.left + (point.code / codeMax) * width;
    const y = pad.top + (1 - (point.voltage - min) / (max - min)) * height;
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}

// Dataset session START/STOP markers, sourced from the same session object
// the Dataset tab's progress cards already read (state.dataset).
function datasetSessionMarkers() {
  const session = state.dataset;
  const markers = [];
  if (Number.isFinite(session?.startedAt)) {
    markers.push({ ts: session.startedAt, color: "#3ecf8e", label: "START" });
  }
  if (Number.isFinite(session?.endedAt)) {
    markers.push({ ts: session.endedAt, color: "#ff4d3d", label: "STOP" });
  }
  return markers;
}

export function drawChart() {
  const visibleRunningChannels = ALL_SENSOR_CHANNELS.filter(isSensorChartSeriesVisible);
  drawOneChart(elements.sensorChart, elements.rangeSelect, elements.legend, [], visibleRunningChannels);
  renderRunningAnalysisTable();
  drawOneChart(elements.datasetChart, elements.datasetRangeSelect, elements.datasetLegend, datasetSessionMarkers());
}

function historyToCsv() {
  const headers = [
    "timeIso",
    "deviceId",
    "mode",
    "gasName",
    "gasClass",
    "confidence",
    "alarm",
    ...SENSOR_NAMES
  ];
  const rows = state.history.map((point) => [
    new Date(point.ts).toISOString(),
    point.deviceId,
    point.mode,
    point.gasName,
    point.gasClass ?? "",
    point.confidence ?? "",
    point.alarm ? 1 : 0,
    ...Array.from({ length: 8 }, (_, index) => point.sensorVoltage[index] ?? "")
  ]);
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}

export function exportCsv() {
  downloadText(`GLD_telemetry_${stamp()}.csv`, `${historyToCsv()}\n`, "text/csv");
}
