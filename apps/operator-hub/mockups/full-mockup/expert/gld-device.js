/*
  GLD Operator mockup: the GLD Operator ships its own device simulator
  (js/mock.js, "Mock" mode), which the mockup starts automatically. This file
  supplies the local-bridge side (ports, dataset folder, AES status, firmware
  packages) and lets a COM-port connection be answered by that same simulator.
*/
(() => {
  "use strict";
  const v = (firmwareVersion) => ({ firmwareVersion });
  const packages = {
    gld: v("0.8.38"), gld_model_1: v("0.8.36"), gld_model_2: v("0.8.36"), gld_model_3: v("0.8.36"),
    gld_model_1_dataset_wifi: v("0.8.36"), gld_model_2_dataset_wifi: v("0.8.36"), gld_model_3_dataset_wifi: v("0.8.36"),
    gld_model_1_dataset_replay_wifi: v("0.8.36"), gld_model_2_dataset_replay_wifi: v("0.8.36"), gld_model_3_dataset_replay_wifi: v("0.8.36"),
    gld_model_1_dataset_workflow_wifi: v("0.8.36"), gld_model_2_dataset_workflow_wifi: v("0.8.36"), gld_model_3_dataset_workflow_wifi: v("0.8.36"),
    gld_v2: v("0.8.30"), gld_v3: v("0.8.31"), gld_atex: v("0.8.30"), gldFieldtest: v("0.8.14"), gldRealField: v("0.8.18"), gldRealTest: v("0.8.18")
  };
  let statusTimer = null;
  const DATASET_DIR = "C:\\PertaminaGLD\\dataset (mockup - tidak ditulis)";
  window.__expertDevice = {
    appId: "gld-operator",
    ports: [["COM10", "USB-Enhanced-SERIAL CH343 (COM10)", "wch.cn"], ["COM9", "Silicon Labs CP210x USB to UART Bridge (COM9)", "Silicon Labs"], ["COM1", "Communications Port (COM1)", "(Standard port types)"]],
    packages,
    rejectPort: (port) => (port === "COM1" ? `${port} is a system port; no GLD responded` : ""),
    // A COM connection is answered by the console's own simulator module
    // (same module instance the app imported), so responses are exactly the
    // ones Mock mode produces, now arriving as if over the serial port.
    async onConnect() {
      const mock = await import("@gld-operator/js/mock.js");
      clearInterval(statusTimer);
      statusTimer = setInterval(() => mock.emitMockStatus(), 2000);
    },
    onDisconnect() { clearInterval(statusTimer); },
    async onCommand(line) {
      const mock = await import("@gld-operator/js/mock.js");
      mock.handleMockCommand(line);
    },
    routes: {
      "GET /api/dataset/output-dir": () => ({ path: DATASET_DIR }),
      "POST /api/dataset/create": (body) => ({ ok: true, path: `${DATASET_DIR}\\${body.name || "session"}.csv`, file: `${body.name || "session"}.csv` }),
      "POST /api/dataset/append": () => ({ ok: true, rows: 1 }),
      "POST /api/dataset/open-folder": () => ({ ok: true, path: DATASET_DIR }),
      "GET /api/gld-key-status": () => ({ configured: true, keyId: 1, source: "mockup" }),
      "GET /api/network": () => ({ ip: "192.168.1.10", ips: ["192.168.1.10"], hostname: "BENCH-LAPTOP" }),
      "POST /api/mqtt/dataset": () => ({ ok: true }),
      "POST /api/mqtt/test": () => ({ ok: true, latencyMs: 12 })
    }
  };
})();
