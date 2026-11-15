// Optional firmware capability. Older firmware has no sensorWarmup field and
// keeps the existing Running display unchanged.
export function warmupBlocksPrediction(status) {
  const phase = status?.sensorWarmup?.state;
  return status?.mode === 'inference' &&
    (phase === 'warming' || phase === 'fault' ||
      (phase === 'ready' && status?.model?.inferenceValid !== true));
}

// Once a device advertises the capability, missing readiness in a newer
// lightweight packet is unknown, not evidence that an earlier READY persists.
export function mergeWarmupTelemetry(previous, message) {
  if (message && Object.prototype.hasOwnProperty.call(message, 'sensorWarmup'))
    return message.sensorWarmup ?? { state: 'warming' };
  return previous?.sensorWarmup ? { state: 'warming' } : undefined;
}

export function createWarmupNotice(element, sensorNames, schedule = setTimeout, cancel = clearTimeout) {
  let timer = null;
  let showingSuccess = false;
  let successDismissed = false;
  function reset() {
    if (timer !== null) cancel(timer);
    timer = null;
    showingSuccess = false;
    successDismissed = false;
    if (element) { element.hidden = true; element.textContent = ''; }
  }
  function render(status) {
    if (!element) return;
    const warmup = status?.sensorWarmup;
    if (status?.mode !== 'inference' || !warmup ||
        !['warming', 'ready', 'fault'].includes(warmup.state)) {
      reset();
      return;
    }
    if (warmup.state !== 'ready') {
      if (timer !== null) cancel(timer);
      timer = null;
      showingSuccess = false;
      successDismissed = false;
      const elapsed = Number.isFinite(warmup.elapsedMs) && warmup.elapsedMs >= 0
        ? Math.floor(warmup.elapsedMs / 1000) : null;
      const elapsedText = elapsed === null ? '—' : `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
      const mask = Number.isInteger(warmup.stableMask) && warmup.stableMask >= 0 && warmup.stableMask <= 255
        ? warmup.stableMask : 0;
      const stable = sensorNames.filter((_, i) => mask & (1 << i)).length;
      const waiting = sensorNames.filter((_, i) => !(mask & (1 << i)));
      const heading = warmup.state === 'fault' ? 'Sensor bermasalah — belum siap' : 'Sensor sedang pemanasan';
      element.textContent = `${heading} · Waktu berjalan ${elapsedText} · Stabil ${stable}/${sensorNames.length}${waiting.length ? ` · Belum siap: ${waiting.join(', ')}` : ''} · Deteksi gas belum tersedia.`;
      element.hidden = false;
      return;
    }
    if (status.model?.inferenceValid !== true) {
      if (timer !== null) cancel(timer);
      timer = null;
      showingSuccess = false;
      successDismissed = false;
      element.textContent = 'Sensor siap · Menunggu inferensi valid; deteksi gas belum tersedia.';
      element.hidden = false;
      return;
    }
    if (successDismissed) return;
    element.hidden = false;
    element.textContent = 'Sensor siap — inferensi aktif.';
    if (!showingSuccess) {
      showingSuccess = true;
      timer = schedule(() => {
        timer = null;
        successDismissed = true;
        element.hidden = true;
      }, 5000);
    }
  }
  return { render, reset };
}
