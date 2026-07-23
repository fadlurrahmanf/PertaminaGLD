export const GATEWAY_ID_MIN = 0x0001;
export const GATEWAY_ID_MAX = 0x000F;

export function normalizeGatewayId(value) {
  const text = String(value ?? "").trim().toUpperCase();
  return text.startsWith("0X") ? text.slice(2) : text;
}

export function validateGatewayId(value) {
  const normalized = normalizeGatewayId(value);
  if (!/^[0-9A-F]{4}$/.test(normalized)) {
    throw new Error("Gateway ID must be exactly four hexadecimal digits (0001-000F).");
  }
  const numeric = Number.parseInt(normalized, 16);
  if (numeric < GATEWAY_ID_MIN || numeric > GATEWAY_ID_MAX) {
    throw new Error("Gateway ID must be in the 0001-000F range.");
  }
  return normalized;
}

export function gatewayIdFromRuntime(value) {
  if (Number.isInteger(value)) return validateGatewayId(value.toString(16).padStart(4, "0"));
  return validateGatewayId(value);
}
