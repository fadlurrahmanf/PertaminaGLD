// Local PIN lock for Expert Terminal and Firmware Upload/Inject ID. This is
// a deterrent against accidental bench mistakes, not enterprise auth - PIN
// hash lives in localStorage, unlock state itself is never persisted.

import { $, elements, state, encoder } from "./state.js";
import { showBanner, hideBanner } from "./ui.js";

async function sha256Hex(text) {
  const bytes = encoder.encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

const PIN_STORAGE_KEY = "gldOperatorWeb.pinHash";

function hasStoredPin() {
  return Boolean(localStorage.getItem(PIN_STORAGE_KEY));
}

async function promptSetPin() {
  const first = window.prompt("Set a local PIN to protect Expert Terminal and Firmware Upload/Inject ID (4+ chars). Cancel to skip locking.");
  if (first == null) return false;
  if (first.trim().length < 4) {
    showBanner("PIN must be at least 4 characters.", "warn");
    return false;
  }
  const confirmPin = window.prompt("Confirm the PIN.");
  if (confirmPin !== first) {
    showBanner("PIN confirmation did not match. Try again.", "warn");
    return false;
  }
  localStorage.setItem(PIN_STORAGE_KEY, await sha256Hex(first.trim()));
  return true;
}

async function promptVerifyPin() {
  const entered = window.prompt("Enter the local PIN to unlock Expert Terminal and Firmware actions.");
  if (entered == null) return false;
  const expected = localStorage.getItem(PIN_STORAGE_KEY);
  const actual = await sha256Hex(entered.trim());
  if (actual !== expected) {
    showBanner("Incorrect PIN.", "error");
    return false;
  }
  return true;
}

export async function requireUnlock() {
  if (state.expertUnlocked) return true;
  const ok = hasStoredPin() ? await promptVerifyPin() : await promptSetPin();
  if (!ok) return false;
  onUnlocked();
  return true;
}

export function onUnlocked() {
  state.expertUnlocked = true;
  $("rawCommand").disabled = false;
  $("sendRawBtn").disabled = false;
  $("unlockExpertBtn").disabled = true;
  $("unlockExpertBtn").textContent = "Unlocked";
  $("uploadFirmwareBtn")?.removeAttribute("disabled");
  $("injectIdBtn").disabled = false;
  $("injectChBtn").disabled = false;
  if (elements.firmwareLockStatus) elements.firmwareLockStatus.textContent = "Firmware actions unlocked for this session.";
  hideBanner();
}
