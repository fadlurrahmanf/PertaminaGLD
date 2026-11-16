#pragma once
#include <cstdint>
#include "LoRaTesterWire.h"

namespace loratester {
inline NodeHealth unknownHealth() {
  NodeHealth h{};
  h.batteryMv = 0xffff; h.batteryPct = 0xff; h.ageSeconds = 0xffff;
  return h;
}
inline bool validHealth(const NodeHealth& h) {
  if (!h.nodeBootNonce || h.ageSeconds == 0xffff || (h.flags & ~uint8_t(7))) return false;
  const bool valid = h.flags & kHealthBatteryValid;
  if (!valid) return h.batteryMv == 0xffff && h.batteryPct == 0xff;
  return (h.flags & kHealthAdcCalibrated) && h.batteryMv >= 2500 && h.batteryMv <= 5000 && h.batteryPct <= 100;
}

// Voltage-derived percentage is an estimate and requires an explicitly
// configured cell profile. Never infer a cell from a floating ADC reading.
inline bool calibratedBattery(uint16_t pinMv, uint16_t emptyMv, uint16_t fullMv,
                              int16_t offsetMv, uint16_t& mv, uint8_t& pct) {
  if (emptyMv < 2500 || fullMv > 5000 || fullMv <= emptyMv || pinMv == 0) return false;
  const int32_t battery = int32_t(pinMv) * 3 + offsetMv;
  if (battery < 2500 || battery > 5000) return false;
  mv = static_cast<uint16_t>(battery);
  if (battery <= emptyMv) pct = 0;
  else if (battery >= fullMv) pct = 100;
  else pct = static_cast<uint8_t>((uint32_t(battery - emptyMv) * 100U + (fullMv-emptyMv)/2U) / (fullMv-emptyMv));
  return true;
}
}
