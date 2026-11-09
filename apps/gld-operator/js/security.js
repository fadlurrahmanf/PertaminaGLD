// Local confirmation gate for Expert Terminal and firmware actions. This is
// a deterrent against accidental bench mistakes, not enterprise authentication.

import { $, elements, state } from "./state.js";
import { hideBanner } from "./ui.js";

// Shared across browsers and handover PCs. A former browser-local PIN hash is
// intentionally ignored so an unknown old PIN cannot block an operator.
const OPERATOR_PIN = "1234";

let pinRequest = null;

function requestPin() {
  if (pinRequest) return pinRequest;
  const dialog = $("operatorPinDialog");
  const form = $("operatorPinForm");
  const input = $("operatorPinInput");
  const error = $("operatorPinError");
  const previousFocus = document.activeElement;
  $("operatorPinTitle").textContent = "Buka kunci Operator";
  $("operatorPinHelp").textContent = "Masukkan PIN Operator untuk Expert Terminal dan tindakan firmware.";
  $("operatorPinSubmit").textContent = "Buka kunci";
  input.value = "";
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
    function submit(event) {
      event.preventDefault();
      if (settled) return;
      if (input.value.trim() !== OPERATOR_PIN) {
        error.textContent = "PIN salah.";
        error.hidden = false;
        input.select();
        return;
      }
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
  const ok = await requestPin();
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
