// Running tab telemetry chart: hand-rolled canvas line chart (kept
// dependency-free per the "stay lightweight" constraint) + CSV export.

import { elements, state, CHART_COLORS, SENSOR_NAMES } from "./state.js";
import { csvCell, downloadText, stamp } from "./ui.js";

export function pruneHistory() {
  const rangeMs = Number(elements.rangeSelect.value) * 1000;
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

export function renderLegend(labels) {
  elements.legend.innerHTML = "";
  const list = labels.length ? labels : ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"];
  list.slice(0, 8).forEach((label, index) => {
    const item = document.createElement("span");
    item.className = "legend-item";
    const swatch = document.createElement("i");
    swatch.className = "legend-swatch";
    swatch.style.background = CHART_COLORS[index];
    item.append(swatch, document.createTextNode(label || `CH${index + 1}`));
    elements.legend.appendChild(item);
  });
}

export function drawChart() {
  const canvas = elements.sensorChart;
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, parent.clientWidth);
  const cssHeight = Math.max(280, Math.min(420, Math.round(window.innerHeight * 0.48)));
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  canvas.style.height = `${cssHeight}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = "#14110d";
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const pad = { left: 58, right: 18, top: 18, bottom: 34 };
  const width = cssWidth - pad.left - pad.right;
  const height = cssHeight - pad.top - pad.bottom;
  const now = Date.now();
  const rangeMs = Number(elements.rangeSelect.value) * 1000;
  const visible = state.history.filter((point) => point.ts >= now - rangeMs);

  drawGrid(ctx, pad, width, height);

  if (!visible.length) {
    ctx.fillStyle = "#8a8272";
    ctx.font = "13px 'Segoe UI', sans-serif";
    ctx.fillText("Waiting for telemetry", pad.left + 12, pad.top + 24);
    renderLegend([]);
    return;
  }

  let min = Infinity;
  let max = -Infinity;
  for (const point of visible) {
    for (const value of point.sensorVoltage) {
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

  ctx.fillStyle = "#8a8272";
  ctx.font = "12px 'Cascadia Mono', monospace";
  ctx.fillText(max.toFixed(4), 8, pad.top + 5);
  ctx.fillText(min.toFixed(4), 8, pad.top + height);

  const labels = latestFeatureOrder(visible);
  for (let ch = 0; ch < 8; ch += 1) {
    ctx.beginPath();
    ctx.lineWidth = 1.8;
    ctx.strokeStyle = CHART_COLORS[ch];
    let started = false;
    for (const point of visible) {
      const value = point.sensorVoltage[ch];
      if (!Number.isFinite(value)) continue;
      const x = pad.left + ((point.ts - (now - rangeMs)) / rangeMs) * width;
      const y = pad.top + (1 - (value - min) / (max - min)) * height;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  }
  renderLegend(labels);
}

export function exportCsv() {
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
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
  downloadText(`GLD_telemetry_${stamp()}.csv`, `${csv}\n`, "text/csv");
}
