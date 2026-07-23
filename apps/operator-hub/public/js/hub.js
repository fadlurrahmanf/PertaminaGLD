// Operator Hub: tab switcher that iframes the GLD/CH/Gateway bridge UIs,
// each already running as its own local bridge.py on its own port. This
// module never talks to those bridges directly (their CORS allowlists are
// same-origin only) - status comes from the hub's own /api/status, which the
// hub bridge checks server-side.

const APPS = {
  gld: { label: "GLD", port: 5174 },
  ch: { label: "CH", port: 5273 },
  gw: { label: "Gateway", port: 5373 }
};

const frame = document.getElementById("appFrame");
const banner = document.getElementById("stageBanner");
const readiness = document.getElementById("readiness");
const refreshButton = document.getElementById("refreshReadinessBtn");
const landing = document.getElementById("landing");
const homeButton = document.getElementById("homeBtn");
const tabButtons = Array.from(document.querySelectorAll(".tab"));
const launchButtons = Array.from(document.querySelectorAll("[data-launch-app]"));
let activeApp = null;
let lastStatus = {};
let mqttDegraded = false;

function updateReadiness(report) {
  if (!readiness) return;
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const problems = checks.filter((check) => check.state !== "ok");
  readiness.classList.toggle("ready", report.readyForFlash === true);
  readiness.classList.toggle("attention", report.readyForFlash !== true);
  readiness.textContent = report.readyForFlash === true
    ? "Upload setup: ready"
    : `Upload setup: ${problems.length} warning${problems.length === 1 ? "" : "s"}`;
  readiness.title = checks.map((check) => `[${check.state.toUpperCase()}] ${check.label}: ${check.detail}`).join("\n");
}

async function loadPreflight() {
  try {
    const res = await fetch("/api/preflight", { cache: "no-store" });
    updateReadiness(await res.json());
  } catch {
    if (readiness) readiness.textContent = "Upload setup: unavailable";
  }
}

function urlFor(app) {
  return `${location.protocol}//${location.hostname}:${APPS[app].port}/`;
}

function selectTab(app, { force = false } = {}) {
  if (!APPS[app]) return;
  if (activeApp === app && !force) return;
  activeApp = app;
  landing.hidden = true;
  frame.hidden = false;
  for (const btn of tabButtons) {
    btn.classList.toggle("active", btn.dataset.app === app);
  }
  const targetUrl = urlFor(app);
  if (frame.dataset.loadedUrl !== targetUrl) {
    frame.src = targetUrl;
    frame.dataset.loadedUrl = targetUrl;
  }
  updateBanner();
}

function showHome() {
  activeApp = null;
  landing.hidden = false;
  frame.hidden = true;
  frame.removeAttribute("src");
  delete frame.dataset.loadedUrl;
  banner.hidden = true;
  for (const btn of tabButtons) btn.classList.remove("active");
}

function updateBanner() {
  if (!activeApp) {
    banner.hidden = true;
    return;
  }
  const status = lastStatus[activeApp];
  if (!status || status.up !== true) {
    banner.hidden = false;
    banner.textContent = `${APPS[activeApp].label} bridge not reachable on port ${APPS[activeApp].port}. Start it (its run-*.bat) and reload this tab.`;
  } else if (status.identityOk === false) {
    banner.hidden = false;
    banner.textContent = `Something other than the ${APPS[activeApp].label} bridge is answering on port ${APPS[activeApp].port}. Close that process and reload this tab.`;
  } else if (activeApp === "gw" && mqttDegraded) {
    banner.hidden = false;
    banner.textContent = "MQTT unavailable: no LAN connection was detected at startup. Gateway topology/MQTT features are degraded; reconnect to a LAN and restart the Hub.";
  } else {
    banner.hidden = true;
  }
}

function isAppReady(status) {
  return !!status && status.up === true && status.identityOk !== false;
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    const payload = await res.json();
    lastStatus = payload.apps || {};
    mqttDegraded = payload.mqttDegraded === true;
    for (const [app, status] of Object.entries(lastStatus)) {
      const dot = document.querySelector(`[data-dot="${app}"]`);
      if (dot) {
        const ready = isAppReady(status);
        dot.classList.toggle("up", ready);
        dot.classList.toggle("down", !ready);
      }
    }
    updateBanner();
  } catch {
    // Hub bridge itself unreachable - leave dots in their last known state.
  }
}

function init() {
  for (const btn of tabButtons) {
    btn.addEventListener("click", () => selectTab(btn.dataset.app));
  }
  for (const btn of launchButtons) {
    btn.addEventListener("click", () => selectTab(btn.dataset.launchApp));
  }
  homeButton.addEventListener("click", showHome);
  if (refreshButton) {
    refreshButton.addEventListener("click", loadPreflight);
  }
  showHome();
  pollStatus();
  loadPreflight();
  setInterval(pollStatus, 4000);
  // /api/preflight recomputes on every request (packages can go bad or get
  // fixed after startup), so poll it too, not just once at load.
  setInterval(loadPreflight, 20000);
}

init();
