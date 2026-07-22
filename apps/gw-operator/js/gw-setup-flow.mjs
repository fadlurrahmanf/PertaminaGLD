export function setupAccess({ serialConnected, wifiVerified, mqttConnected }) {
  const wifiUnlocked = Boolean(serialConnected);
  const mqttUnlocked = wifiUnlocked && Boolean(wifiVerified);
  return {
    wifiUnlocked,
    mqttUnlocked,
    mqttPanelEnabled: mqttUnlocked || Boolean(mqttConnected)
  };
}
