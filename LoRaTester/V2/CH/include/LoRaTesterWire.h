#pragma once
#include <cstdint>

// V2 ESP-NOW v8. Packed little-endian ESP32 wire format; no floating point.
// Source-MAC/session binding limits accidental cross-talk but does not
// authenticate a sender. This is a bench-only, unencrypted test protocol.
namespace loratester {
constexpr uint16_t kNowMagic = 0x4C54;
constexpr uint8_t kNowVersion = 8;
constexpr uint8_t kNowStart = 1;
constexpr uint8_t kNowStatus = 2;
constexpr uint8_t kNowStop = 3;
constexpr uint8_t kNowDiscover = 4;
constexpr uint8_t kNowPresence = 5;
constexpr uint8_t kNowStartRealtime = 6;
constexpr uint8_t kNowCh2Presence = 7;
constexpr uint16_t kCh2NodeId = 0x00f2;
constexpr uint32_t kHealthSession = 0x3254484c;
constexpr uint8_t kHealthRadioReady = 0x01;
constexpr uint8_t kHealthAdcCalibrated = 0x02;
constexpr uint8_t kHealthBatteryValid = 0x04;
struct __attribute__((packed)) NodeHealth {
  uint16_t batteryMv;       // 0xffff unknown
  uint8_t batteryPct;       // 0xff unknown
  uint8_t flags;
  uint16_t ageSeconds;      // 0xffff unknown
  uint32_t nodeBootNonce;   // probabilistic identity, not authentication
};
static_assert(sizeof(NodeHealth) == 10, "node health format changed");
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
  int16_t minSnrDb10;
  int16_t maxSnrDb10;
  uint8_t available;
  uint8_t final;
  int16_t latestRssiDbm;
  int16_t latestSnrDb10;
};
static_assert(sizeof(DirectionStats) == 20, "direction stats length changed");
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
  uint32_t reportSeq; // STATUS ordering within this session, modulo 2^32
  uint32_t bootNonce; // CH1 random boot identity; not authentication
  NodeHealth ch1Health, ch2Health;
  uint8_t sampleSeqFromCh2, sampleSeqFromCh1;
  uint8_t sampleSeqValid; // bit 0 CH2->CH1, bit 1 CH1->CH2, realtime only
};
static_assert(sizeof(NowMessage) == 96, "ESP-NOW wire length changed");
}  // namespace loratester
