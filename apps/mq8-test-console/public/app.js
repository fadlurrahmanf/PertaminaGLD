let token = "", viewResetAtElapsed = null, latestPoints = [], gldLogSequence = 0, gldLogLines = [], realtimePoints = [], realtimePhase = "", realtimeOriginSampleMs = null, lastStatus = null, gldEventSource = null, mq8DirectionState = null;
const $ = (id) => document.getElementById(id);

async function api(path, body = null) {
  const response = await fetch(path, { method: body ? "POST" : "GET", headers: body ? { "Content-Type": "application/json", "X-MQ8-Test-Token": token } : {}, body: body ? JSON.stringify(body) : undefined });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Permintaan gagal");
  return payload;
}

function notice(text, cls = "") { const el = $("notice"); el.textContent = text; el.className = `notice ${cls}`; }
function phasePlan(duties) { const result = ["BASELINE_100"]; duties.forEach((duty, index) => { result.push(`TEST_${duty}`); if (index < duties.length - 1) result.push(`RECOVERY_100_AFTER_${duty}`); }); return result; }

function renderSequence(status) {
  const active = (status.progress?.phase || "").split(" ")[0];
  const plan = phasePlan(status.duties || []);
  const activeIndex = plan.indexOf(active);
  $("sequence").innerHTML = plan.map((phase, index) => `<li class="${phase === active ? "current" : activeIndex > index ? "done" : ""}">${index + 1}. ${phase.replaceAll("_", " ")}</li>`).join("");
}

// Adaptasi satu seri yang sengaja mempertahankan renderer Running GLD:
// grid, skala-Y, range waktu bergerak, arah awal, dan label akhir.
const MQ8_CHART_COLOR = "#ffa400";
const RUNNING_Y_AXIS_TICK_COUNT = 10;

function drawRunningGrid(ctx, pad, width, height) {
  ctx.strokeStyle = "#5a5135";
  ctx.lineWidth = 1;
  ctx.strokeRect(pad.left, pad.top, width, height);
  ctx.beginPath();
  for (let i = 1; i < RUNNING_Y_AXIS_TICK_COUNT - 1; i += 1) {
    const y = pad.top + (height / (RUNNING_Y_AXIS_TICK_COUNT - 1)) * i;
    ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + width, y);
  }
  for (let i = 1; i < 5; i += 1) {
    const x = pad.left + (width / 5) * i;
    ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + height);
  }
  ctx.stroke();
}

function drawRunningYAxisTicks(ctx, pad, width, height, min, max) {
  const fraction = 1 / (RUNNING_Y_AXIS_TICK_COUNT - 1);
  const decimals = Math.abs(max - min) < 0.001 ? 6 : 4;
  const tickValues = Array.from({ length: RUNNING_Y_AXIS_TICK_COUNT }, (_, tick) => max - (max - min) * fraction * tick);
  const zeroTolerance = Math.abs(max - min) / 100000;
  if (!tickValues.some((value) => Math.abs(value) <= zeroTolerance)) tickValues.push(0);
  tickValues.sort((a, b) => b - a);
  const zeroY = pad.top + (1 - (0 - min) / (max - min)) * height;
  ctx.beginPath(); ctx.strokeStyle = "#f3c969"; ctx.lineWidth = 1.75; ctx.setLineDash([7, 5]); ctx.moveTo(pad.left, zeroY); ctx.lineTo(pad.left + width, zeroY); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = "#d1cab8"; ctx.font = "600 14px 'Cascadia Mono', monospace"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (const value of tickValues) {
    const y = pad.top + (1 - (value - min) / (max - min)) * height;
    ctx.fillText(`${value.toFixed(decimals)} V`, pad.left - 8, y);
  }
  ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
}

function drawRunningXAxisTicks(ctx, pad, width, height, rangeMs, latestElapsed) {
  ctx.fillStyle = "#d1cab8"; ctx.font = "600 14px 'Cascadia Mono', monospace"; ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (let index = 0; index <= 5; index += 1) {
    const x = pad.left + (width / 5) * index;
    const phaseSeconds = Math.max(0, latestElapsed - (rangeMs / 1000) * (1 - index / 5));
    ctx.fillText(formatPhaseTime(phaseSeconds), x, pad.top + height + 13);
  }
  ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
}

function chart(points) {
  const canvas = $("chart");
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, parent.clientWidth);
  const cssHeight = Math.max(490, Math.min(735, Math.round(window.innerHeight * .84)));
  canvas.width = Math.round(cssWidth * dpr); canvas.height = Math.round(cssHeight * dpr); canvas.style.height = `${cssHeight}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, cssWidth, cssHeight); ctx.fillStyle = "#14110d"; ctx.fillRect(0, 0, cssWidth, cssHeight);
  const pad = { left: 96, right: 58, top: 18, bottom: 56 };
  const width = cssWidth - pad.left - pad.right, height = cssHeight - pad.top - pad.bottom;
  const now = Date.now(), rangeMs = Number($("rangeMinutes").value) * 60 * 1000, rangeStart = now - rangeMs;
  const latestElapsed = points.at(-1)?.elapsed ?? 0;
  // Semua titik menggunakan satu basis waktu fase. Ini setara dengan `ts`
  // tunggal di history Running GLD dan mencegah log SSE lama tergambar pada
  // waktu browser yang sama saat halaman baru dibuka.
  const history = points.map((point) => ({ ts: now - (latestElapsed - point.elapsed) * 1000, value: point.mv / 1000 }));
  const visible = history.filter((point) => point.ts >= rangeStart);
  drawRunningGrid(ctx, pad, width, height);
  drawRunningXAxisTicks(ctx, pad, width, height, rangeMs, latestElapsed);
  if (!visible.length) { ctx.fillStyle = "#8a8272"; ctx.font = "14px 'Segoe UI', sans-serif"; ctx.fillText("Waiting for telemetry", pad.left + 12, pad.top + 24); return; }
  let min = Infinity, max = -Infinity;
  for (const point of visible) { if (Number.isFinite(point.value)) { min = Math.min(min, point.value); max = Math.max(max, point.value); } }
  if (!Number.isFinite(min) || !Number.isFinite(max)) { min = -0.01; max = 0.01; }
  if (Math.abs(max - min) < 0.00001) { max += 0.001; min -= 0.001; }
  const margin = (max - min) * 0.12; min -= margin; max += margin; min = Math.min(min, 0); max = Math.max(max, 0);
  drawRunningYAxisTicks(ctx, pad, width, height, min, max);
  ctx.beginPath(); ctx.lineWidth = 1.8; ctx.strokeStyle = MQ8_CHART_COLOR;
  let started = false, firstValue = null, firstY = null, lastValue = null, lastY = null;
  for (const point of visible) {
    if (!Number.isFinite(point.value)) continue;
    const x = pad.left + ((point.ts - rangeStart) / rangeMs) * width;
    const y = pad.top + (1 - (point.value - min) / (max - min)) * height;
    if (!started) { ctx.moveTo(x, y); started = true; firstValue = point.value; firstY = y; } else ctx.lineTo(x, y);
    lastValue = point.value; lastY = y;
  }
  ctx.stroke();
  if (firstY != null && Number.isFinite(firstValue) && Number.isFinite(lastValue)) { ctx.fillStyle = MQ8_CHART_COLOR; ctx.font = "700 15px 'Cascadia Mono', monospace"; ctx.textBaseline = "middle"; ctx.fillText(firstValue > lastValue ? "−" : lastValue > firstValue ? "+" : "=", pad.left + 5, firstY); }
  if (lastY != null) { ctx.fillStyle = MQ8_CHART_COLOR; ctx.font = "600 14px 'Cascadia Mono', monospace"; ctx.textBaseline = "middle"; ctx.fillText("MQ8", pad.left + width + 4, lastY); }
  ctx.textBaseline = "alphabetic";
}

function calculateMetrics(points) {
  const recent = points.filter((p) => p.elapsed >= Math.max(0, (points.at(-1)?.elapsed || 0) - 60));
  if (recent.length < 2) return null;
  const values = recent.map((p) => p.mv), range = Math.max(...values) - Math.min(...values), first = recent[0], last = recent.at(-1), minutes = (last.elapsed - first.elapsed) / 60, trend = minutes ? (last.mv - first.mv) / minutes : 0;
  return { range, trend, first, last };
}

function diagnostics(metrics) {
  if (!metrics) { $("metricRange").textContent = "Rentang 60 dtk: -"; $("metricTrend").textContent = "Tren 1 menit: -"; return; }
  const { range, trend } = metrics;
  $("metricRange").textContent = `Rentang 60 dtk: ${range.toFixed(3)} mV`; $("metricTrend").textContent = `Tren 1 menit: ${trend.toFixed(3)} mV/menit`;
}

function mq8DirectionReference(points, last) { const target = last.elapsed - 5; for (let index = points.length - 1; index >= 0; index -= 1) if (points[index].elapsed <= target) return points[index]; return null; }
function directionConfirmSeconds() { const value = Number($("directionConfirmSeconds").value); return Number.isFinite(value) && value >= 1 && value <= 120 ? value : 10; }
function renderDirectionRule(seconds = directionConfirmSeconds()) { $("autoRuleHint").textContent = `Mode Auto: fase minimal 10 menit, lalu status MQ8 harus Stabil 3 menit berturut-turut. Stabil = arah belum konsisten selama ${seconds} detik.`; }
function mq8RunningDirection(points) {
  const last = points.at(-1), phase = String(last?.phase || "");
  const reference = last && mq8DirectionReference(points, last);
  if (!last || !reference) return { direction: "-", delta: NaN, durationSeconds: NaN, status: { text: "Mengumpulkan", tone: "collecting" } };
  const delta = last.mv - reference.mv, direction = delta > 0 ? "+" : delta < 0 ? "-" : "=";
  if (!mq8DirectionState || mq8DirectionState.phase !== phase || last.elapsed < mq8DirectionState.lastElapsed || mq8DirectionState.direction !== direction) mq8DirectionState = { phase, direction, since: last.elapsed, lastElapsed: last.elapsed };
  else mq8DirectionState.lastElapsed = last.elapsed;
  const durationSeconds = Math.max(0, last.elapsed - mq8DirectionState.since), stable = direction === "=" || durationSeconds < directionConfirmSeconds();
  return { direction, delta, durationSeconds, status: stable ? { text: "Stabil", tone: "stable" } : direction === "+" ? { text: "Menaik", tone: "up" } : { text: "Menurun", tone: "down" } };
}
function formatDirectionDuration(seconds) { if (!Number.isFinite(seconds)) return "-"; const rounded = Math.floor(seconds); return rounded < 60 ? `${String(rounded).padStart(2, "0")}s` : `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`; }
function observationPoints(points) { return viewResetAtElapsed === null ? points : points.filter((point) => point.elapsed > viewResetAtElapsed); }
function observationDuration(points, fallback) { if (viewResetAtElapsed === null) return fallback || "-"; const last = points.at(-1); return last ? `${Math.max(0, (last.elapsed - viewResetAtElapsed) / 60).toFixed(2)} menit` : "0.00 menit"; }
function renderMq8RunningRow(progress, points, metrics, duration) {
  const last = points.at(-1), first = points[0];
  const range = metrics?.range;
  const trend = metrics?.trend;
  const analysis = mq8RunningDirection(points), delta = analysis.delta, direction = analysis.direction, stability = analysis.status;
  const value = last ? `${last.mv.toFixed(3)} mV (${(last.mv / 1000).toFixed(9)} V)` : "-";
  const deltaText = Number.isFinite(delta) ? `${delta >= 0 ? "+" : ""}${delta.toFixed(3)} mV` : "-";
  const rangeText = Number.isFinite(range) ? `${range.toFixed(3)} mV` : "-";
  const trendText = Number.isFinite(trend) ? `${trend >= 0 ? "+" : ""}${trend.toFixed(3)} mV/min` : "-";
  const gainText = Number.isFinite(last?.gain) ? `x${last.gain}` : "-";
  $("mq8RunningRow").innerHTML = `<tr><td><strong>MQ8</strong></td><td>${value}</td><td>${gainText}</td><td>${deltaText}</td><td>${direction}</td><td>${formatDirectionDuration(analysis.durationSeconds)}</td><td>${rangeText}</td><td>${trendText}</td><td class="status ${stability.tone}">${stability.text}</td></tr>`;
}

function phaseDurationSeconds(value) { const match = String(value || "").match(/([-+0-9.,]+)/); return match ? Number(match[1].replace(",", ".")) * 60 : 0; }
function phaseRecordedPoints(recordedPoints, progress) {
  const phase = String(progress?.phase || "").split(" ")[0];
  const current = recordedPoints.filter((point) => !phase || point.phase === phase);
  if (!current.length) return current;
  const phaseStart = current.at(-1).elapsed - phaseDurationSeconds(progress?.duration);
  return current.map((point) => ({ ...point, elapsed: Math.max(0, point.elapsed - phaseStart) }));
}
function mergePhasePoints(recordedPoints, currentRealtime) {
  const merged = new Map();
  [...recordedPoints, ...currentRealtime].forEach((point) => merged.set(Math.round(point.elapsed * 1000), point));
  return [...merged.values()].sort((a, b) => a.elapsed - b.elapsed);
}

function displayedSeriesPoints(points) {
  const lastElapsed = points.at(-1)?.elapsed ?? 0;
  return points.filter((point) => point.elapsed >= Math.max(0, lastElapsed - Number($("rangeMinutes").value) * 60));
}

function formatPhaseTime(seconds) {
  const total = Math.max(0, Math.round(seconds)), minutes = Math.floor(total / 60), remainder = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function renderSeriesTable(points) {
  $("seriesRowCount").textContent = `${points.length} baris`;
  if (!points.length) { $("seriesDataRows").innerHTML = '<tr><td colspan="4">Menunggu data valid.</td></tr>'; return; }
  $("seriesDataRows").innerHTML = points.slice().reverse().map((point) => `<tr><td>${formatPhaseTime(point.elapsed)}</td><td>${point.mv.toFixed(3)}</td><td>${(point.mv / 1000).toFixed(9)}</td><td>${Number.isFinite(point.gain) ? `x${point.gain}` : "-"}</td></tr>`).join("");
}

function renderMode(status, running) {
  const auto = /^auto/i.test(String(status.progress?.phaseMode || ""));
  $("autoMode").checked = auto;
  $("autoMode").disabled = !running;
  $("modeLabel").textContent = auto ? "Auto" : "Manual";
  const seconds = Number(status.progress?.directionConfirmSeconds) || directionConfirmSeconds();
  if (document.activeElement !== $("directionConfirmSeconds")) $("directionConfirmSeconds").value = seconds;
  $("modeHint").textContent = auto ? `Auto: >=10 menit dan status Stabil 3 menit.` : "Manual: menunggu tombol Stabil.";
  renderDirectionRule(seconds);
  $("nextBtn").disabled = !running || auto;
}

function renderAutoProgress(progress) {
  const phaseMinutes = Math.max(0, phaseDurationSeconds(progress.duration) / 60);
  const stableMinutes = Math.max(0, Number(progress.stableHoldMinutes) || 0);
  const phaseTarget = 10, stableTarget = 3;
  $("phaseGateProgress").max = phaseTarget; $("phaseGateProgress").value = Math.min(phaseMinutes, phaseTarget);
  $("stableGateProgress").max = stableTarget; $("stableGateProgress").value = Math.min(stableMinutes, stableTarget);
  $("phaseGateText").textContent = `${phaseMinutes.toFixed(2).replace(".", ",")} / ${phaseTarget} menit`;
  $("stableGateText").textContent = `${stableMinutes.toFixed(2).replace(".", ",")} / ${stableTarget} menit`;
  $("autoGateStatus").textContent = `Gate Auto: ${progress.mq8Status || "Mengumpulkan"}`;
}

function render(status) {
  const progress = status.progress || {}, running = status.active, runnerError = status.runnerError || "";
  $("runnerBadge").textContent = running ? "MENUNGGU OPERATOR" : status.state; $("runnerBadge").className = `badge ${running ? "live" : "neutral"}`;
  $("phaseName").textContent = progress.phase || "Belum ada sesi";
  const directionSeconds = Number(progress.directionConfirmSeconds) || directionConfirmSeconds();
  $("phaseDetail").textContent = running ? (/^auto/i.test(String(progress.phaseMode || "")) ? `Auto aktif: pindah setelah fase >=10 menit dan status Stabil ${directionSeconds} detik.` : "Tekan Stabil hanya setelah Anda menyatakan grafik sudah stabil.") : runnerError ? `Runner gagal: ${runnerError.split("\n").at(-1)}` : status.finalIo8 ? `Sesi selesai. IO8 akhir: ${status.finalIo8}` : "Tekan Mulai untuk merekam baseline 100%.";
  $("startBtn").disabled = running; $("stopBtn").disabled = !running; $("restartBtn").disabled = !running; renderMode(status, running); renderAutoProgress(progress);
  $("progressPath").textContent = status.progressFile || status.outputDir || "Belum ada file progress.";
  $("fileList").innerHTML = (status.files?.length ? status.files : ["CSV fase akan muncul setelah fase dimulai."]).map((file) => `<li>${file}</li>`).join("");
  if (!running && runnerError) notice(`Runner gagal: ${runnerError.split("\n").at(-1)}`, "bad");
  if (!running && !runnerError && status.finalIo8) notice(`Sesi selesai. IO8 akhir terkonfirmasi: ${status.finalIo8}`, "ok");
  lastStatus = status;
  const recordedPoints = phaseRecordedPoints(status.points || [], progress);
  const points = running ? mergePhasePoints(recordedPoints, realtimePoints) : recordedPoints;
  const observed = observationPoints(points); latestPoints = observed;
  const duration = observationDuration(points, progress.duration);
  $("phaseDuration").textContent = duration;
  $("dutyValue").textContent = progress.duty || "-"; $("sampleCount").textContent = `${viewResetAtElapsed === null ? progress.samples || 0 : observed.length} sampel valid`;
  const metrics = calculateMetrics(observed), series = displayedSeriesPoints(observed);
  renderSequence(status); chart(observed); diagnostics(metrics); renderMq8RunningRow(progress, observed, metrics, duration); renderSeriesTable(series);
}

async function refresh() { try { render(await api("/api/status")); } catch (error) { notice(error.message, "bad"); } }
$("startBtn").onclick = async () => { const mode = $("autoMode").checked ? "auto" : "manual", directionSeconds = directionConfirmSeconds(); if (!confirm(`Mulai sesi ${mode} baru dari baseline 100%? Output akan dibuat di folder sesi baru.`)) return; try { notice("Memulai baseline 100%..."); render(await api("/api/start", { mode, directionConfirmSeconds: directionSeconds })); notice(mode === "auto" ? "Sesi Auto dimulai." : "Baseline 100% sedang direkam. Anda yang menentukan kapan stabil.", "ok"); } catch (error) { notice(error.message, "bad"); } };
$("nextBtn").onclick = async () => { if (!confirm("Tandai fase ini stabil dan pindah ke tahap berikutnya?")) return; $("nextBtn").disabled = true; try { const result = await api("/api/next", {}); notice(result.message, "ok"); setTimeout(refresh, 900); } catch (error) { notice(error.message, "bad"); $("nextBtn").disabled = false; } };
$("stopBtn").onclick = async () => { if (!confirm("Hentikan sesi? Runner akan mengembalikan IO8 ke HIGH 100%.")) return; try { const result = await api("/api/stop", {}); notice(result.message, "ok"); setTimeout(refresh, 900); } catch (error) { notice(error.message, "bad"); } };
$("restartBtn").onclick = async () => { if (!confirm("Hentikan sesi ini dengan aman? Data sesi tetap tersimpan. Setelah IO8 HIGH 100% terkonfirmasi, tekan Mulai baseline untuk membuat sesi baru dari awal.")) return; try { const result = await api("/api/restart", {}); notice(result.message, "ok"); setTimeout(refresh, 900); } catch (error) { notice(error.message, "bad"); } };
$("autoMode").onchange = async () => { const mode = $("autoMode").checked ? "auto" : "manual"; if (!lastStatus?.active) { $("modeLabel").textContent = mode === "auto" ? "Auto" : "Manual"; $("modeHint").textContent = mode === "auto" ? "Auto: >=10 menit dan status Stabil 3 menit." : "Manual: menunggu tombol Stabil."; return; } try { const result = await api("/api/mode", { mode }); notice(result.message, "ok"); setTimeout(refresh, 600); } catch (error) { $("autoMode").checked = !$("autoMode").checked; notice(error.message, "bad"); } };
$("directionConfirmSeconds").onchange = async () => { const seconds = directionConfirmSeconds(); $("directionConfirmSeconds").value = seconds; renderDirectionRule(seconds); if (!lastStatus?.active) return; try { const result = await api("/api/direction-confirmation", { seconds }); notice(result.message, "ok"); setTimeout(refresh, 600); } catch (error) { notice(error.message, "bad"); } };
$("rangeMinutes").oninput = () => { $("rangeMinutesLabel").textContent = `${$("rangeMinutes").value} min`; refresh(); };
$("clearViewBtn").onclick = () => { viewResetAtElapsed = latestPoints.at(-1)?.elapsed ?? 0; chart([]); if (lastStatus) render(lastStatus); notice("Observasi di-reset: grafik, durasi, dan sampel tampilan mulai dari nol. CSV dan sesi tetap berjalan.", "ok"); };
$("exportCsvBtn").onclick = async () => { try { const response = await fetch("/api/export", { method: "POST", headers: { "Content-Type": "application/json", "X-MQ8-Test-Token": token }, body: "{}" }); if (!response.ok) { const payload = await response.json(); throw new Error(payload.error || "Ekspor CSV gagal"); } const link = document.createElement("a"); link.href = URL.createObjectURL(await response.blob()); link.download = response.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] || "MQ8_live_valid.csv"; link.click(); URL.revokeObjectURL(link.href); notice("CSV live valid lengkap berhasil diekspor.", "ok"); } catch (error) { notice(error.message, "bad"); } };
function renderGldLog() { const log = $("gldSerialLog"); log.textContent = gldLogLines.length ? gldLogLines.join("\n") : "Menunggu log baru dari GLD Operator..."; $("gldLogCount").textContent = `${gldLogLines.length} baris`; log.scrollTop = log.scrollHeight; }
function appendGldLog(line) { gldLogLines.push(line); if (gldLogLines.length > 500) gldLogLines.splice(0, gldLogLines.length - 500); renderGldLog(); }
function consumeGldSerialLine(line) {
  appendGldLog(line);
  if (!line.startsWith("GLD_STATUS_JSON ")) return;
  try {
    const payload = JSON.parse(line.slice(16)), telemetry = payload.telemetry || {}, order = telemetry.featureOrder || [];
    const index = order.indexOf("MQ8"), values = telemetry.sensorVoltage || [], statuses = telemetry.sensorStatus || [], gains = telemetry.sensorGain || [];
    if (!telemetry.valid || index < 0 || !Number.isFinite(values[index]) || statuses[index] !== 0) return;
    const sampleMs = Number(telemetry.sampleMs), phase = String(lastStatus?.progress?.phase || "").split(" ")[0];
    if (!Number.isFinite(sampleMs)) return;
    if (realtimePhase !== phase) { realtimePoints = []; realtimePhase = phase; realtimeOriginSampleMs = sampleMs - phaseDurationSeconds(lastStatus?.progress?.duration) * 1000; viewResetAtElapsed = null; }
    const elapsed = (sampleMs - realtimeOriginSampleMs) / 1000;
    if (realtimePoints.at(-1)?.elapsed === elapsed) return;
    realtimePoints.push({ elapsed, mv: Number(values[index]) * 1000, gain: Number(gains[index]), phase, duty: lastStatus?.progress?.duty || "" });
    realtimePoints = realtimePoints.filter((point) => point.elapsed >= elapsed - 3600);
    if (lastStatus?.active) render(lastStatus);
  } catch { /* Ignore unrelated/incomplete serial JSON. */ }
}
async function refreshGldLog() { try { const response = await api(`/api/gld-log?after=${gldLogSequence}`); gldLogSequence = Math.max(gldLogSequence, response.sequence || 0); if (response.lines?.length) response.lines.forEach((item) => consumeGldSerialLine(item.line)); } catch (error) { $("gldSerialLog").textContent = `Log GLD tidak tersedia: ${error.message}`; } }
function startGldEventStream() { if (gldEventSource) gldEventSource.close(); gldEventSource = new EventSource("/api/gld-events"); gldEventSource.addEventListener("serial_line", (event) => { try { consumeGldSerialLine(JSON.parse(event.data).line); } catch { /* Keep stream alive on malformed event. */ } }); }
$("clearGldLogBtn").onclick = () => { gldLogLines = []; renderGldLog(); };
(async () => { try { const boot = await api("/api/bootstrap"); token = boot.apiToken; await refresh(); await refreshGldLog(); startGldEventStream(); setInterval(refresh, 500); } catch (error) { notice(error.message, "bad"); } })();
