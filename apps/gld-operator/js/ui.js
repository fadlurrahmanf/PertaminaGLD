// Generic DOM helpers: text/badge updates, banners, busy-spinner wrapper,
// tab switching, form field helpers, small download/format utilities.

import { $, elements, state } from "./state.js";
import { drawChart } from "./chart.js";

export function nowText() {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

export function setBadge(el, text, kind = "") {
  el.textContent = text;
  el.className = `tag ${kind ? `tag--${kind}` : ""}`.trim();
}

export function setText(id, value) {
  const element = $(id);
  if (!element) return;
  element.textContent = value == null || value === "" ? "Unknown" : String(value);
}

let bannerHideTimer = null;

export function showBanner(message, kind = "error") {
  elements.globalBannerText.textContent = message;
  elements.globalBanner.className = `alert-bar ${kind !== "error" ? `alert-bar--${kind}` : ""}`.trim();
  elements.globalBanner.hidden = false;
  clearTimeout(bannerHideTimer);
  if (kind !== "error") {
    bannerHideTimer = setTimeout(() => hideBanner(), 6000);
  }
}

export function hideBanner() {
  elements.globalBanner.hidden = true;
}

export async function withBusy(button, busyLabel, fn) {
  if (!button) return fn();
  const original = button.textContent;
  const wasDisabled = button.disabled;
  button.disabled = true;
  button.classList.add("is-busy");
  button.textContent = busyLabel;
  try {
    return await fn();
  } finally {
    button.disabled = wasDisabled;
    button.classList.remove("is-busy");
    button.textContent = original;
  }
}

export function appendLog(line, direction = "in") {
  const prefix = direction === "out" ? ">>" : "<<";
  const entry = `${nowText()} ${prefix} ${line}`;
  state.logs.push(entry);
  if (state.logs.length > 3000) state.logs.splice(0, state.logs.length - 3000);
  elements.serialLog.textContent = state.logs.join("\n");
  elements.serialLog.scrollTop = elements.serialLog.scrollHeight;
}

export function setPanelOpen(panel, open) {
  if (!panel) return;
  panel.classList.toggle("open", open);
  panel.setAttribute("aria-hidden", open ? "false" : "true");
}

export function setSetupOpen(open) {
  setPanelOpen(elements.setupPanel, open);
}

// ---- app modal (centered popup - replaces window.alert/window.confirm) ----

let modalResolve = null;

function modalEls() {
  return {
    modal: $("appModal"),
    title: $("appModalTitle"),
    message: $("appModalMessage"),
    cancelBtn: $("appModalCancelBtn"),
    okBtn: $("appModalOkBtn")
  };
}

function closeModal(result) {
  const { modal } = modalEls();
  setPanelOpen(modal, false);
  if (modalResolve) {
    const resolve = modalResolve;
    modalResolve = null;
    resolve(result);
  }
}

function openModal({ title, message, kind, showCancel, okLabel, cancelLabel }) {
  const els = modalEls();
  els.title.textContent = title;
  els.title.className = `modal-title--${kind}`;
  els.message.textContent = message;
  els.cancelBtn.hidden = !showCancel;
  els.cancelBtn.textContent = cancelLabel;
  els.okBtn.textContent = okLabel;
  setPanelOpen(els.modal, true);
  els.okBtn.focus();
  return new Promise((resolve) => {
    modalResolve = resolve;
  });
}

// One-button notice popup, replaces window.alert(). Resolves once dismissed.
export function showAlert(message, kind = "info", title) {
  const defaultTitle = { ok: "Success", warn: "Warning", error: "Error", info: "Notice" }[kind] || "Notice";
  return openModal({ title: title || defaultTitle, message, kind, showCancel: false, okLabel: "OK" }).then(() => {});
}

// Confirm/cancel popup, replaces window.confirm(). Resolves true/false.
export function showConfirm(message, kind = "warn", title = "Confirm") {
  return openModal({ title, message, kind, showCancel: true, okLabel: "Confirm", cancelLabel: "Cancel" });
}

export function initAppModal() {
  const { modal, cancelBtn, okBtn } = modalEls();
  okBtn.addEventListener("click", () => closeModal(true));
  cancelBtn.addEventListener("click", () => closeModal(false));
  modal.querySelector("[data-modal-dismiss]").addEventListener("click", () => closeModal(false));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal.classList.contains("open")) closeModal(false);
  });
}

export function switchTab(tabId) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === tabId);
  });
  drawChart();
}

export function getField(id) {
  return $(id).value.trim();
}

export function setField(id, value) {
  if (value != null && value !== "") $(id).value = value;
}

export function numberField(id) {
  return Number($(id).value);
}

export function downloadText(filename, text, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function csvCell(value) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function stamp() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "");
}

export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function exportLog() {
  downloadText(`GLD_serial_${stamp()}.log`, `${state.logs.join("\n")}\n`);
}

const FORM_STORAGE_IDS = ["datasetLabel", "targetSamples", "sampleIntervalMs", "maxDurationMs", "fanOnMs", "postFanSettleMs", "wifiSsid", "mqttHost", "mqttPort", "mqttUser", "topicRoot", "firmwareEnv", "targetDeviceId", "targetChAddress", "manualPortInput", "pollIntervalMs", "chartYAxisMin", "chartYAxisMax"];

export function saveForm() {
  const data = Object.fromEntries(FORM_STORAGE_IDS.map((id) => [id, $(id).value]));
  localStorage.setItem("gldOperatorWeb.form", JSON.stringify(data));
}

export function loadForm() {
  try {
    const data = JSON.parse(localStorage.getItem("gldOperatorWeb.form") || "{}");
    Object.entries(data).forEach(([id, value]) => {
      if ($(id)) $(id).value = value;
    });
  } catch {}
}
