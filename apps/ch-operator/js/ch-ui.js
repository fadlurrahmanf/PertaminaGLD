// Small DOM helpers: badges, log terminal, banner, tabs, drawers, and the
// local PIN lock that gates the Expert terminal + firmware upload.

import { elements, state } from "./ch-state.js";

const MAX_LOG_LINES = 4000;

export function setBadge(el, text, kind = "") {
  if (!el) return;
  const b = el.querySelector("b");
  if (b) b.textContent = text;
  else el.textContent = text;
  el.classList.remove("ok", "warn", "error", "alarm");
  if (kind) el.classList.add(kind);
}

export function appendLog(line, direction = "in") {
  if (line == null) return;
  state.logs.push(line);
  if (state.logs.length > MAX_LOG_LINES) state.logs.splice(0, state.logs.length - MAX_LOG_LINES);
  if (state.logPaused) {
    state.logPausedCount += 1;
    return;
  }
  flushLog(direction);
}

function flushLog(direction = "in") {
  const el = elements.serialLog;
  if (!el) return;
  const div = document.createElement("div");
  const last = state.logs[state.logs.length - 1] || "";
  div.textContent = last;
  if (direction === "out" || direction === "tx") div.className = "tx";
  else if (direction === "err") div.className = "err";
  el.appendChild(div);
  while (el.childElementCount > MAX_LOG_LINES) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

export function rerenderLog() {
  const el = elements.serialLog;
  if (!el) return;
  el.textContent = "";
  const start = Math.max(0, state.logs.length - MAX_LOG_LINES);
  for (let i = start; i < state.logs.length; i += 1) {
    const div = document.createElement("div");
    div.textContent = state.logs[i];
    el.appendChild(div);
  }
  el.scrollTop = el.scrollHeight;
}

let bannerTimer = null;
export function showBanner(text, kind = "warn", autoHideMs = 6000) {
  const el = elements.banner;
  if (!el) return;
  elements.bannerText.textContent = text;
  el.classList.remove("ok", "warn", "error");
  el.classList.add(kind, "show");
  clearTimeout(bannerTimer);
  if (autoHideMs) bannerTimer = setTimeout(hideBanner, autoHideMs);
}

export function hideBanner() {
  elements.banner?.classList.remove("show");
}

export function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
}

export function setDrawer(which, open) {
  const panel = which === "settings" ? elements.settingsPanel : elements.setupPanel;
  const backdrop = which === "settings" ? elements.settingsBackdrop : elements.setupBackdrop;
  panel?.classList.toggle("open", open);
  backdrop?.classList.toggle("open", open);
}

export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---- Local PIN lock (deterrent only, mirrors the GLD app's security.js) ----
const PIN_KEY = "chOperatorWeb.pinHash";

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function isExpertLocked() {
  return !state.expertUnlocked;
}

export async function unlockExpert() {
  const stored = localStorage.getItem(PIN_KEY);
  if (!stored) {
    const pin = prompt("Set an Expert PIN (min 4 chars). This is a local deterrent, not real security.");
    if (!pin || pin.length < 4) return false;
    localStorage.setItem(PIN_KEY, await sha256Hex(pin));
    state.expertUnlocked = true;
    return true;
  }
  const entered = prompt("Enter Expert PIN.");
  if (!entered) return false;
  if ((await sha256Hex(entered)) !== stored) {
    showBanner("Incorrect PIN.", "error");
    return false;
  }
  state.expertUnlocked = true;
  return true;
}

export function lockExpert() {
  state.expertUnlocked = false;
}

export function applyExpertLockUi() {
  const locked = isExpertLocked();
  document.querySelectorAll(".quickcmd").forEach((b) => (b.disabled = locked || !state.connected));
  if (elements.expertInput) elements.expertInput.disabled = locked || !state.connected;
  if (elements.expertSendBtn) elements.expertSendBtn.disabled = locked || !state.connected;
  if (elements.fwTargetId) elements.fwTargetId.disabled = locked;
  if (elements.fwPickBtn) elements.fwPickBtn.disabled = locked;
  if (elements.fwUploadBtn) elements.fwUploadBtn.disabled = locked || !state.manifest;
  if (elements.lockBtn) elements.lockBtn.textContent = locked ? "Unlock" : "Lock";
  if (elements.expertLockNote) {
    elements.expertLockNote.textContent = locked
      ? "Locked. Click Unlock and enter the PIN to send raw commands or flash firmware."
      : "Unlocked. Send any line to the CH over serial.";
  }
}
