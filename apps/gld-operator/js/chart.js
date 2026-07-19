// Telemetry chart: hand-rolled canvas line chart (kept dependency-free per
// the "stay lightweight" constraint) + CSV export. Drawn twice from the same
// state.history feed - once on the Running tab, once on the Dataset tab
// (with START/STOP session markers overlaid) - via drawOneChart() so both
// stay pixel-for-pixel consistent.

import { $, elements, state, CHART_COLORS, SENSOR_NAMES } from "./state.js";
import { csvCell, downloadText, stamp } from "./ui.js";

export function pruneHistory() {
  const rangeMs = Math.max(
    Number(elements.rangeSelect?.value) || 0,
    Number(elements.datasetRangeSelect?.value) || 0
  ) * 1000;
  const cutoff = Date.now() - rangeMs;
  while (state.history.length && state.history[0].ts < cutoff) state.history.shift();
}

function drawGrid(ctx, pad, width, height) {
  ctx.strokeStyle = "#35301f";
  ctx.lineWidth = 1;
  ctx.strokeRect(pad.left, pad.top, width, height);
  ctx.beginPath();
  for (let i = 1; i < 4; i += 1) {
    const y = pad.top + (height / 4) * i;
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

  const channels = channelIndices || [0, 1, 2, 3, 4, 5, 6, 7];
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

  ctx.fillStyle = "#8a8272";
  ctx.font = "13.5px 'Cascadia Mono', monospace";
  ctx.fillText(max.toFixed(4), 8, pad.top + 6);
  ctx.fillText(min.toFixed(4), 8, pad.top + height);

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
    let lastY = null;
    for (const point of visible) {
      const value = point.sensorVoltage[ch];
      if (!Number.isFinite(value)) continue;
      const x = pad.left + ((point.ts - rangeStart) / rangeMs) * width;
      const y = pad.top + (1 - (value - min) / (max - min)) * height;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
      lastY = y;
    }
    ctx.stroke();

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

  ctx.fillStyle = "#8a8272";
  ctx.font = "13.5px 'Cascadia Mono', monospace";
  ctx.fillText(max.toFixed(4), 8, pad.top + 6);
  ctx.fillText(min.toFixed(4), 8, pad.top + height);
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
  drawOneChart(elements.sensorChart, elements.rangeSelect, elements.legend, []);
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
