// Apply only a previously tested profile. Never clear manually entered values
// when no local profile exists or a profile is unavailable.
export function applyLocalBrokerProfile(fields, profile) {
  if (!profile?.available) return false;
  fields.mqttPort.value = profile.port;
  fields.mqttUsername.value = profile.username;
  fields.mqttPassword.value = profile.password;
  fields.mqttTopicRoot.value = profile.topicRoot || "gld/gateway";
  return true;
}
