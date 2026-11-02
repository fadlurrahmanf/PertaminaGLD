// Wireless Dataset has its own session/history: never mutate COM/MQTT state.
export const WIRELESS_SENSOR_NAMES = ['MQ8', 'MQ135', 'MQ3', 'MQ5', 'MQ4', 'MQ7', 'MQ6', 'MQ2'];
export const WIRELESS_HISTORY_LIMIT = 7200;

export function validWirelessSample(row, sessionId) {
  return Boolean(row && row.session_id === sessionId && sessionId
    && Number.isInteger(row.seq) && row.seq >= 0
    && Number.isFinite(row.timestamp_ms) && row.timestamp_ms >= 0
    && Array.isArray(row.sensor_voltage) && row.sensor_voltage.length === 8
    && row.sensor_voltage.every(Number.isFinite)
    && Array.isArray(row.feature_order)
    && row.feature_order.length === 8
    && row.feature_order.every((name, index) => name === WIRELESS_SENSOR_NAMES[index]));
}

export function mergeWirelessSnapshot(previous, incoming) {
  const next = { ...previous, ...incoming };
  const changed = previous.session_id !== next.session_id;
  const records = new Map();
  for (const row of changed ? [] : (previous.history || [])) records.set(row.seq, row);
  for (const row of incoming.history || []) {
    if (validWirelessSample(row, next.session_id)) records.set(row.seq, row);
  }
  next.history = [...records.values()].sort((a, b) => a.seq - b.seq).slice(-WIRELESS_HISTORY_LIMIT);
  return next;
}

export function applyWirelessEvent(previous, event) {
  if (event.type === 'state') return mergeWirelessSnapshot(previous, event);
  if (event.type !== 'sample' || !validWirelessSample(event.sample, previous.session_id)) return previous;
  return mergeWirelessSnapshot(previous, {
    history: [event.sample],
    count: Math.max(previous.count || 0, event.count || 0),
    gap_count: event.gap_count ?? previous.gap_count,
  });
}
