/*
  Expert Console mockup chrome inside the console document:
  - "← Simple Hub" and other links that would leave the console go back to the
    Simple Hub mockup (parent page) instead of navigating.
  - Sandboxed previews block alert/confirm/prompt (they return instantly).
    When that happens the action is auto-confirmed (Expert PIN prompts get the
    mockup PIN 0000) and a toast explains it, so flows such as "Restart" and
    Firmware Upload stay usable. With real dialogs nothing changes.
*/
(() => {
  "use strict";
  const toParent = (message) => { try { window.parent.postMessage({ source: "operator-hub-mockup", ...message }, "*"); } catch { /* standalone */ } };
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link) return;
    const href = link.getAttribute("href") || "";
    if (href.startsWith("#") || href.startsWith("javascript:")) return;
    event.preventDefault();
    event.stopPropagation();
    toParent(link.classList.contains("return-simple-hub") || /:5173\/?$/.test(href) ? { type: "close-expert" } : { type: "external-link", href });
  }, true);

  function toast(text) {
    const node = document.createElement("div");
    node.textContent = text;
    node.setAttribute("role", "status");
    node.style.cssText = "position:fixed;z-index:2147483647;left:50%;bottom:24px;transform:translateX(-50%);max-width:min(560px,calc(100vw - 32px));padding:12px 16px;border:1px solid #985a28;border-radius:12px;background:#2b1b10;color:#f1c4a4;font:600 14px/1.45 system-ui,sans-serif;box-shadow:0 14px 40px #0009";
    document.body.append(node);
    setTimeout(() => node.remove(), 4200);
  }
  const MOCK_PIN = "0000";
  const blocked = (started) => performance.now() - started < 8;
  const nativeConfirm = window.confirm.bind(window);
  const nativeAlert = window.alert.bind(window);
  const nativePrompt = window.prompt.bind(window);
  window.confirm = (message) => {
    const started = performance.now();
    const answer = nativeConfirm(message);
    if (answer || !blocked(started)) return answer;
    toast(`Mockup: konfirmasi disetujui otomatis — ${message}`);
    return true;
  };
  window.alert = (message) => {
    const started = performance.now();
    nativeAlert(message);
    if (blocked(started)) toast(String(message));
  };
  window.prompt = (message, value = "") => {
    const started = performance.now();
    const answer = nativePrompt(message, value);
    if (answer !== null || !blocked(started)) return answer;
    // The consoles only prompt for the local Expert PIN (a bench deterrent).
    const pin = /PIN/i.test(String(message)) ? MOCK_PIN : value;
    toast(/PIN/i.test(String(message)) ? `Mockup: PIN lokal diisi otomatis (${MOCK_PIN}).` : `Mockup: input memakai nilai bawaan — ${message}`);
    return pin;
  };
})();
