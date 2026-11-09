// Local PIN lock for Expert Terminal and Firmware Upload/Inject ID. This is
// a deterrent against accidental bench mistakes, not enterprise auth - PIN
// hash lives in localStorage, unlock state itself is never persisted.

import { $, elements, state, encoder } from "./state.js";
import { hideBanner } from "./ui.js";

async function sha256Hex(text) {
  const bytes = encoder.encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

const PIN_STORAGE_KEY = "gldOperatorWeb.pinHash";

function hasStoredPin() {
  return Boolean(localStorage.getItem(PIN_STORAGE_KEY));
}

let pinRequest = null;

function requestPin(setNewPin) {
  if (pinRequest) return pinRequest;
  const dialog = $("operatorPinDialog");
  const form = $("operatorPinForm");
  const input = $("operatorPinInput");
  const confirmation = $("operatorPinConfirm");
  const error = $("operatorPinError");
  const previousFocus = document.activeElement;
  $("operatorPinTitle").textContent = setNewPin ? "Atur PIN Operator" : "Buka kunci Operator";
  $("operatorPinHelp").textContent = setNewPin
    ? "Buat PIN lokal minimal 4 karakter untuk Expert Terminal dan tindakan firmware."
    : "Masukkan PIN lokal untuk membuka Expert Terminal dan tindakan firmware.";
  $("operatorPinConfirmField").hidden = !setNewPin;
  confirmation.required = setNewPin;
  $("operatorPinSubmit").textContent = setNewPin ? "Simpan PIN" : "Buka kunci";
  input.value = "";
  confirmation.value = "";
  error.hidden = true;
  dialog.classList.add("open");
  dialog.setAttribute("aria-hidden", "false");
  input.focus();

  pinRequest = new Promise((resolve) => {
    let settled = false;
    function finish(ok) {
      if (settled) return;
      settled = true;
      form.removeEventListener("submit", submit);
      dialog.removeEventListener("click", cancel);
      dialog.removeEventListener("keydown", escape);
      dialog.classList.remove("open");
      dialog.setAttribute("aria-hidden", "true");
      input.value = "";
      confirmation.value = "";
      previousFocus?.focus?.();
      pinRequest = null;
      resolve(ok);
    }
    function cancel(event) {
      if (event.target.closest("[data-pin-cancel], #operatorPinCancel")) finish(false);
    }
    function escape(event) {
      if (event.key === "Escape") { event.preventDefault(); finish(false); }
    }
    async function submit(event) {
      event.preventDefault();
      if (settled) return;
      const entered = input.value.trim();
      if (entered.length < 4) {
        error.textContent = "PIN minimal 4 karakter.";
        error.hidden = false;
        return;
      }
      if (setNewPin) {
        if (confirmation.value.trim() !== entered) {
          error.textContent = "Konfirmasi PIN tidak cocok.";
          error.hidden = false;
          return;
        }
        const digest = await sha256Hex(entered);
        if (settled) return;
        localStorage.setItem(PIN_STORAGE_KEY, digest);
      } else if (await sha256Hex(entered) !== localStorage.getItem(PIN_STORAGE_KEY)) {
        if (settled) return;
        error.textContent = "PIN salah.";
        error.hidden = false;
        input.select();
        return;
      }
      if (settled) return;
      finish(true);
    }
    form.addEventListener("submit", submit);
    dialog.addEventListener("click", cancel);
    dialog.addEventListener("keydown", escape);
  });
  return pinRequest;
}

export async function requireUnlock() {
  if (state.expertUnlocked) return true;
  const ok = await requestPin(!hasStoredPin());
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
