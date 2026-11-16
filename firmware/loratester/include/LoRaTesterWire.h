#pragma once
#include <cstdint>

// ESP-NOW v4. Packed little-endian ESP32 wire format; no floating point.
// Source-MAC/session binding limits accidental cross-talk but does not
// authenticate a sender. This is a bench-only, unencrypted test protocol.
namespace loratester {
constexpr uint16_t kNowMagic = 0x4C54;
constexpr uint8_t kNowVersion = 4;
constexpr uint8_t kNowStart = 1;
constexpr uint8_t kNowStatus = 2;
constexpr uint8_t kNowStop = 3;
constexpr uint8_t kNowDiscover = 4;
constexpr uint8_t kNowPresence = 5;
enum class TestState : uint8_t {
  Idle = 0, Starting = 1, Running = 2, Done = 3, Timeout = 4, Error = 5,
  Stopping = 6, Stopped = 7
};
struct __attribute__((packed)) DirectionStats {
  uint16_t received;
  int16_t avgRssiDbm10;
  int16_t minRssiDbm;
  int16_t maxRssiDbm;
  int16_t avgSnrDb10;
  int8_t minSnrDb;
  int8_t maxSnrDb;
  uint8_t available;
  uint8_t final;
};
static_assert(sizeof(DirectionStats) == 14, "direction stats length changed");
struct __attribute__((packed)) NowMessage {
  uint16_t magic;
  uint8_t version;
  uint8_t type;
  uint32_t session;
  uint16_t received;
  uint16_t expected;
  int16_t rssiDbm;
  int8_t snrDb;
  uint8_t state;
  uint8_t phase;
  DirectionStats fromCh2;
  DirectionStats fromCh1;
  uint16_t ageCh2Ms, ageCh1Ms; // 0xffff means unknown
  uint16_t sentCh2, sentCh1; // observed CH2 sequence / local CH1 slots
};
static_assert(sizeof(NowMessage) == 53, "ESP-NOW wire length changed");
}  // namespace loratester
