#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <cstring>
#include <cmath>
#include "ChBoardPinsRectangle.h"
#include "LoRaTesterSession.h"
#include "LoRaTesterWire.h"
#include "DiscoveryBinding.h"
#include "SlotSchedule.h"
#include "AppFrame.h"

// Dedicated bench firmware: it does not run the original CH mesh or alarm.
// It operates on the same physical radio and can still interfere with nearby
// deployments. No RF transmissions occur until an explicit paired START.
namespace b = pgl::ch::board;
using namespace loratester;
constexpr uint16_t kRadioMagic = 0x544c; // test marker, not authentication
constexpr uint16_t kCh1 = 0x0010, kCh2 = 0x00f2;
constexpr uint32_t kSessionTimeoutMs = 230000;
// Packets arrive every 2 s per direction. Tolerate up to five missed slots;
// silence is a failed/incomplete test, never a 100-packet final result.
constexpr uint32_t kPeerSilenceMs = 12000;
constexpr uint32_t kPairWindowMs = 60000;
enum RadioType : uint8_t { RadioStart = 1, RadioStartAck = 2, RadioData = 3, RadioStop = 5, RadioStopAck = 6, RadioReverseData = 9, RadioReverseEnd = 10, RadioReport = 11, RadioCommit = 12, RadioCommitAck = 13, RadioGo = 14, RadioReportAck = 15, RadioStartRealtime = 16 };
struct __attribute__((packed)) RadioMessage {
  uint32_t magic;
  uint8_t version, type;
  uint16_t src, dst;
  uint32_t session;
  uint16_t seq;
  DirectionStats stats;
};
static_assert(sizeof(RadioMessage) == 36, "Unexpected LoRa packet size");
// Test-only type, not a guarantee that production receivers will ignore it.
constexpr uint8_t kTestFrameType = 0x3f;
constexpr uint8_t kShortPayload = 29, kLongPayload = 40;
struct __attribute__((packed)) RadioPayload {
  uint16_t magic;
  uint8_t version, type;
  uint32_t session;
  DirectionStats stats;
  uint8_t sampleAgeSec; // 255 unavailable; conservative whole seconds
};
static_assert(sizeof(RadioPayload) == 29, "Unexpected test metadata size");
static_assert(sizeof(RadioPayload) <= kShortPayload, "metadata exceeds 39-byte AppFrame");

Module radioModule(b::PIN_RADIO_B_CS, b::PIN_RADIO_B_DIO1,
                   b::PIN_RADIO_B_RST, b::PIN_RADIO_B_BUSY,
                   SPI, SPISettings(2000000, MSBFIRST, SPI_MODE0));
SX1262 radio(&radioModule);
volatile bool radioRx = false;
volatile uint32_t radioRxAt = 0;
volatile bool radioRxTimeKnown = false;
portMUX_TYPE radioRxMux = portMUX_INITIALIZER_UNLOCKED;
void IRAM_ATTR onRadioRx() {
  const uint32_t at = millis();
  portENTER_CRITICAL_ISR(&radioRxMux);
  if (!radioRx) { radioRxAt = at; radioRxTimeKnown = true; }
  radioRx = true;
  portEXIT_CRITICAL_ISR(&radioRxMux);
}
ReceiverSession receiver;
bool radioReady = false, nowReady = false;
TestState state = TestState::Idle;
uint32_t session = 0, stateStarted = 0, lastRadioTx = 0, lastNow = 0, lastWdt = 0;
uint16_t senderCount = 0, senderOk = 0;
uint8_t startAttempts = 0;
uint8_t phase = 0;
bool forwardFinal = false, reverseStarted = false;
bool finalPartial = false;
uint16_t finalPeerSenderOk = 0;
DirectionStats remoteStats{};
SlotSchedule slots;
LiveSlotSchedule liveSlots;
bool realtime = false;
bool realtimeStarted = false;
uint32_t epoch = 0, lastLocalSample = 0, lastRemoteSample = 0;
uint16_t observedCh2 = 0xffff, lastRemoteSequence = 0xffff;
bool localSampleSeen = false, remoteSampleSeen = false;
uint8_t handshake = 0;
uint16_t commitToken = 0;
bool stopAfterStartupFailure = false;

uint16_t sampleAge(bool seen, uint32_t then) {
  if (!seen) return 0xffff;
  uint32_t age = millis() - then;
  return age >= 65534 ? 65534 : static_cast<uint16_t>(age);
}

DirectionStats localStats(bool isFinal) {
  DirectionStats s{};
  s.received = receiver.received();
  s.avgRssiDbm10 = receiver.averageRssiDbm10();
  s.minRssiDbm = receiver.minRssiDbm();
  s.maxRssiDbm = receiver.maxRssiDbm();
  s.avgSnrDb10 = receiver.averageSnrDb10();
  s.minSnrDb10 = receiver.minSnrDb10();
  s.maxSnrDb10 = receiver.maxSnrDb10();
  s.latestRssiDbm = receiver.latestRssiDbm();
  s.latestSnrDb10 = receiver.latestSnrDb10();
  s.available = 1;
  s.final = isFinal ? 1 : 0;
  return s;
}

#if LT_ROLE == 1
#if defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
constexpr uint8_t kTemporaryStaMac[6] = {0x02, 0x4c, 0x54, 0x31, 0x06, 0x01};
int altMacStorageResult = -1, altMacStopResult = -1, altMacSetResult = -1;
int altMacStartResult = -1, altMacReadResult = -1;
bool altMacReady = false;
#endif
portMUX_TYPE nowMux = portMUX_INITIALIZER_UNLOCKED;
volatile bool incomingStart = false;
uint8_t incomingType = 0;
uint8_t incomingMac[6] = {};
uint32_t incomingSession = 0;
uint8_t monitorMac[6] = {};
bool paired = false, pairing = false;
uint32_t pairingStarted = 0, lastSession = 0;
uint32_t lastPresence = 0;
DiscoveryBinding discovery;
SessionOwner sessionOwner;
uint32_t nowRawCount = 0, nowValidCount = 0, statusSendCount = 0;
uint32_t txQueued = 0, txRejected = 0, txAck = 0, txNoAck = 0;
int txCallbackResult = -1;
uint32_t reportSequence = 0;
uint32_t bootNonce = 0;
int lastStatusResult = 0, channelSetResult = -1, nowInitResult = -1, callbackResult = -1, peerAddResult = -1;
void onNowSend(const uint8_t*, esp_now_send_status_t result) {
  portENTER_CRITICAL(&nowMux);
  if (result == ESP_NOW_SEND_SUCCESS) ++txAck; else ++txNoAck;
  portEXIT_CRITICAL(&nowMux);
}
int sendMonitorMessage(const uint8_t* mac, const NowMessage& msg) {
  const int result = esp_now_send(mac, reinterpret_cast<const uint8_t*>(&msg), sizeof(msg));
  portENTER_CRITICAL(&nowMux);
  if (result == ESP_OK) ++txQueued; else ++txRejected;
  portEXIT_CRITICAL(&nowMux);
  return result;
}
void onNowReceive(const uint8_t* mac, const uint8_t* data, int len) {
  portENTER_CRITICAL(&nowMux);
  ++nowRawCount;
  portEXIT_CRITICAL(&nowMux);
  if (!mac || !data || len != static_cast<int>(sizeof(NowMessage))) return;
  NowMessage msg;
  memcpy(&msg, data, sizeof(msg));
  if (msg.magic != kNowMagic || msg.version != kNowVersion) return;
  const bool discover = msg.type == kNowDiscover && msg.session == 0;
  const bool control = (msg.type == kNowStart || msg.type == kNowStartRealtime || msg.type == kNowStop) && msg.session != 0;
  if (!discover && !control) return;
  portENTER_CRITICAL(&nowMux);
  ++nowValidCount;
  if (!incomingStart || (incomingType == kNowDiscover && control) ||
      (incomingType != kNowStop && msg.type == kNowStop)) {
    memcpy(incomingMac, mac, 6);
    incomingSession = msg.session;
    incomingType = msg.type;
    incomingStart = true;
  }
  portEXIT_CRITICAL(&nowMux);
}
bool ensureMonitorPeer(const uint8_t* mac) {
  if (paired && memcmp(monitorMac, mac, 6) == 0) return true;
  if (paired) esp_now_del_peer(monitorMac);
  memcpy(monitorMac, mac, 6);
  esp_now_peer_info_t peer{}; memcpy(peer.peer_addr, mac, 6);
  peer.channel = 0; peer.encrypt = false;
  peerAddResult = esp_now_is_peer_exist(mac) ? ESP_OK : esp_now_add_peer(&peer);
  paired = peerAddResult == ESP_OK;
  if (!paired) discovery.clear();
  return paired;
}
void reportPresence() {
  if (!paired || !nowReady) return;
  NowMessage m{};
  m.magic = kNowMagic; m.version = kNowVersion; m.type = kNowPresence;
  m.bootNonce = bootNonce;
  m.session = 0; m.expected = realtime ? 0 : kPacketCount;
  m.state = static_cast<uint8_t>(state); m.phase = phase;
  ++statusSendCount;
  lastStatusResult = sendMonitorMessage(monitorMac, m);
}
void reportStatus() {
  if (!paired || !nowReady || !sessionOwner.matches(monitorMac)) return;
  NowMessage m{};
  m.magic = kNowMagic; m.version = kNowVersion; m.type = kNowStatus; m.session = session;
  m.bootNonce = bootNonce;
  m.received = receiver.received(); m.expected = kPacketCount;
  m.rssiDbm = receiver.metricsValid() ? receiver.latestRssiDbm() : int16_t(0);
  m.snrDb = receiver.metricsValid() ? static_cast<int8_t>(receiver.latestSnrDb10() / 10) : int8_t(0);
  m.state = static_cast<uint8_t>(state); m.phase = phase;
  m.fromCh2 = localStats(forwardFinal); m.fromCh1 = remoteStats;
  m.ageCh2Ms = sampleAge(localSampleSeen, lastLocalSample);
  m.ageCh1Ms = sampleAge(remoteSampleSeen, lastRemoteSample);
  m.sentCh2 = observedCh2; m.sentCh1 = senderCount;
  if (realtime) { m.expected = 0; m.sentCh2 = m.sentCh1 = 0xffff; }
  m.reportSeq = ++reportSequence;
  ++statusSendCount;
  lastStatusResult = sendMonitorMessage(monitorMac, m);
}
#endif

void keepAlive() {
  if (millis() - lastWdt >= 10000) {
    lastWdt = millis();
    digitalWrite(b::PIN_WDT_KEEPALIVE, HIGH);
    delay(5);
    digitalWrite(b::PIN_WDT_KEEPALIVE, LOW);
  }
}
bool startRx() {
  portENTER_CRITICAL(&radioRxMux);
  radioRx = false; radioRxTimeKnown = false;
  portEXIT_CRITICAL(&radioRxMux);
  int result = radio.startReceive();
  if (result != RADIOLIB_ERR_NONE) {
    Serial0.printf("RX_ERROR %d\n", result);
    radioReady = false;
    state = TestState::Error;
  }
  return result == RADIOLIB_ERR_NONE;
}
bool transmit(uint8_t type, uint32_t sid, uint16_t seq, const DirectionStats* stats = nullptr) {
  if (!radioReady) return false;
  if (radioRx) return false; // Service the already-completed frame first.
  const uint16_t src = LT_ROLE == 1 ? kCh1 : kCh2;
  const uint16_t dst = LT_ROLE == 1 ? kCh2 : kCh1;
  if (seq > 255) return false;
  RadioPayload m{};
  m.magic = kRadioMagic; m.version = 5; m.type = type; m.session = sid;
  if (stats) m.stats = *stats;
  m.sampleAgeSec = 255;
  if (LT_ROLE == 2 && stats && stats->received && localSampleSeen) {
    uint32_t ageSeconds = (millis() - lastLocalSample + 999) / 1000 + 1;
    m.sampleAgeSec = ageSeconds > 254 ? 254 : static_cast<uint8_t>(ageSeconds);
  }
  uint8_t payload[kLongPayload]{};
  memcpy(payload, &m, sizeof(m));
  uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + kLongPayload]{};
  const uint8_t payloadLen = LT_ROLE == 1 ? kShortPayload : kLongPayload;
  const auto encoded = pgl::protocol::encodeAppFrame(kTestFrameType, src, dst, static_cast<uint8_t>(seq),
      payload, payloadLen, frame, sizeof(frame), pgl::protocol::MESH_MAX_PAYLOAD);
  if (encoded.status != pgl::protocol::FrameStatus::Ok) return false;
  radio.clearPacketReceivedAction();
  // Freeze RX before inspecting the chip's latched IRQ, so a frame completed
  // between the loop's RX check and detach is not silently discarded by TX.
  if (radio.standby() != RADIOLIB_ERR_NONE) {
    radio.setPacketReceivedAction(onRadioRx);
    radioReady = false;
    state = TestState::Error;
    return false;
  }
  // SX126x::getIrqFlags() drops SPI errors in this RadioLib version. Use the
  // same public Module SPI command with a checked return code instead.
  uint8_t irqBytes[2]{};
  if (radioModule.SPIreadStream(RADIOLIB_SX126X_CMD_GET_IRQ_STATUS, irqBytes, 2) != RADIOLIB_ERR_NONE) {
    radio.setPacketReceivedAction(onRadioRx);
    radioReady = false;
    state = TestState::Error;
    return false;
  }
  const uint16_t irqFlags = (uint16_t(irqBytes[0]) << 8) | irqBytes[1];
  if (radioRx || (irqFlags & RADIOLIB_SX126X_IRQ_RX_DONE)) {
    radio.setPacketReceivedAction(onRadioRx);
    portENTER_CRITICAL(&radioRxMux);
    // If the callback was detached, the exact RX_DONE time is unknown; use
    // observation time later rather than guessing it arrived before deadline.
    if (!radioRx) radioRxTimeKnown = false;
    radioRx = true;
    portEXIT_CRITICAL(&radioRxMux);
    return false;
  }
  int result = radio.transmit(frame, encoded.size);
  digitalWrite(b::PIN_RADIO_B_RXEN, LOW);
  digitalWrite(b::PIN_RADIO_B_TXEN, LOW);
  radio.setPacketReceivedAction(onRadioRx);
  const bool rxReady = startRx();
  if (result != RADIOLIB_ERR_NONE) Serial0.printf("TX_ERROR %d\n", result);
  return result == RADIOLIB_ERR_NONE && rxReady;
}
void setup() {
  Serial0.begin(115200);
  pinMode(b::PIN_WDT_KEEPALIVE, OUTPUT);
  digitalWrite(b::PIN_WDT_KEEPALIVE, LOW);
  pinMode(b::PIN_RADIO_A_CS, OUTPUT); digitalWrite(b::PIN_RADIO_A_CS, HIGH);
  pinMode(b::PIN_RADIO_A_RST, OUTPUT); digitalWrite(b::PIN_RADIO_A_RST, HIGH);
  pinMode(b::PIN_RADIO_A_RXEN, OUTPUT); digitalWrite(b::PIN_RADIO_A_RXEN, LOW);
  pinMode(b::PIN_RADIO_A_TXEN, OUTPUT); digitalWrite(b::PIN_RADIO_A_TXEN, LOW);
  pinMode(b::PIN_RADIO_B_CS, OUTPUT); digitalWrite(b::PIN_RADIO_B_CS, HIGH);
  pinMode(b::PIN_RADIO_B_RXEN, OUTPUT); digitalWrite(b::PIN_RADIO_B_RXEN, LOW);
  pinMode(b::PIN_RADIO_B_TXEN, OUTPUT); digitalWrite(b::PIN_RADIO_B_TXEN, LOW);
  pinMode(b::PIN_RADIO_B_RST, OUTPUT); digitalWrite(b::PIN_RADIO_B_RST, LOW);
  delay(20); digitalWrite(b::PIN_RADIO_B_RST, HIGH); delay(50);
  SPI.begin(b::PIN_SPI_SCK, b::PIN_SPI_MISO, b::PIN_SPI_MOSI);
  // Dedicated test frequency; test traffic remains isolated by its application magic.
  int result = radio.begin(922.0, 125.0, 9, 5, 0x34, 10, 8, 0.0, false);
  if (result == RADIOLIB_ERR_SPI_CMD_INVALID || result == RADIOLIB_ERR_SPI_CMD_FAILED)
    result = radio.begin(922.0, 125.0, 9, 5, 0x34, 10, 8, 1.6, false);
  radioReady = result == RADIOLIB_ERR_NONE;
  if (radioReady) {
    radio.setRfSwitchPins(b::PIN_RADIO_B_RXEN, b::PIN_RADIO_B_TXEN);
    radio.setPacketReceivedAction(onRadioRx);
    radioReady = startRx();
  }
  Serial0.printf("LT role=%d radio=%d state=%d\n", LT_ROLE, radioReady, result);
#if LT_ROLE == 1
#if defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
  // This build is for a temporary bench diagnosis only. Prevent Wi-Fi
  // configuration writes to flash and verify the selected station MAC.
  WiFi.persistent(false);
#endif
  WiFi.mode(WIFI_STA);
#if defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
  altMacStopResult = altMacSetResult = altMacStartResult = altMacReadResult = -1;
  altMacStorageResult = esp_wifi_set_storage(WIFI_STORAGE_RAM);
  if (altMacStorageResult == ESP_OK)
    altMacStopResult = esp_wifi_stop();
  if (altMacStopResult == ESP_OK)
    altMacSetResult = esp_wifi_set_mac(WIFI_IF_STA, kTemporaryStaMac);
  if (altMacSetResult == ESP_OK)
    altMacStartResult = esp_wifi_start();
  uint8_t actualMac[6]{};
  if (altMacStartResult == ESP_OK)
    altMacReadResult = esp_wifi_get_mac(WIFI_IF_STA, actualMac);
  altMacReady = altMacStorageResult == ESP_OK && altMacStopResult == ESP_OK &&
                altMacSetResult == ESP_OK && altMacStartResult == ESP_OK &&
                altMacReadResult == ESP_OK && memcmp(actualMac, kTemporaryStaMac, 6) == 0;
  Serial0.printf("LT_ALT_MAC ready=%d storage=%d stop=%d set=%d start=%d read=%d actual=%02x:%02x:%02x:%02x:%02x:%02x\n",
                 altMacReady, altMacStorageResult, altMacStopResult, altMacSetResult, altMacStartResult, altMacReadResult,
                 actualMac[0], actualMac[1], actualMac[2], actualMac[3], actualMac[4], actualMac[5]);
#endif
  WiFi.disconnect();
  // Wi-Fi is active before requesting entropy; reserve zero as invalid.
  bootNonce = esp_random();
  if (bootNonce == 0) bootNonce = 1;
#if defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
  channelSetResult = nowInitResult = callbackResult = -1;
  if (altMacReady) channelSetResult = esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
#else
  channelSetResult = esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
#endif
  if (channelSetResult == ESP_OK) nowInitResult = esp_now_init();
  if (nowInitResult == ESP_OK) callbackResult = esp_now_register_recv_cb(onNowReceive);
  txCallbackResult = -1;
  if (nowInitResult == ESP_OK) txCallbackResult = esp_now_register_send_cb(onNowSend);
  nowReady = channelSetResult == ESP_OK && nowInitResult == ESP_OK && callbackResult == ESP_OK;
  Serial0.printf("LT now=%d; automatic discovery enabled\n", nowReady);
#endif
}
// Drain a completed receive before any slot can transmit and clear radioRx.
void serviceRadio() {
  const uint32_t observedAt = millis();
  portENTER_CRITICAL(&radioRxMux);
  const bool pending = radioReady && radioRx;
  const uint32_t receivedAt = radioRxTimeKnown ? radioRxAt : observedAt;
  if (pending) { radioRx = false; radioRxTimeKnown = false; }
  portEXIT_CRITICAL(&radioRxMux);
  if (pending) {
    RadioMessage msg{};
    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + kLongPayload]{};
    size_t packetLen = radio.getPacketLength();
    if (packetLen < pgl::protocol::APPFRAME_OVERHEAD || packetLen > sizeof(frame)) { startRx(); return; }
    int result = radio.readData(frame, packetLen);
    int16_t rssi = static_cast<int16_t>(radio.getRSSI());
    // Keep hundredths internally (SX1262 reports quarter-dB steps), so the
    // average is rounded only after accumulation, not for each packet.
    int16_t snr = static_cast<int16_t>(std::lround(radio.getSNR() * 100.0f));
    if (!startRx()) return;
    pgl::protocol::FrameView view{};
    const uint8_t expectedPayload = LT_ROLE == 1 ? kLongPayload : kShortPayload;
    if (result != RADIOLIB_ERR_NONE ||
        pgl::protocol::decodeAppFrame(frame, packetLen, view, pgl::protocol::MESH_MAX_PAYLOAD) != pgl::protocol::FrameStatus::Ok ||
        view.typeFlags != kTestFrameType || view.payloadLen != expectedPayload) return;
    RadioPayload payload{}; memcpy(&payload, view.payload, sizeof(payload));
    msg.magic = payload.magic; msg.version = payload.version; msg.type = payload.type;
    msg.session = payload.session; msg.stats = payload.stats;
    msg.src = view.srcId; msg.dst = view.dstId; msg.seq = view.seq;
    if (msg.magic != kRadioMagic || msg.version != 5 || msg.session == 0) return;
    // Only an on-time packet may extend the peer watchdog. Validation of the
    // AppFrame, session, peer and uniqueness still happens before any update.
    const uint32_t reference = localSampleSeen ? lastLocalSample : epoch;
    const int32_t sampleElapsed = static_cast<int32_t>(receivedAt - reference);
    const bool sampleOnTime = sampleElapsed < static_cast<int32_t>(kPeerSilenceMs) &&
                              (!localSampleSeen || sampleElapsed >= 0);
#if LT_ROLE == 1
    if (msg.src != kCh2 || msg.dst != kCh1 || msg.session != session) return;
    if (msg.type == RadioStopAck && state == TestState::Stopping)
      state = stopAfterStartupFailure ? TestState::Timeout : TestState::Stopped;
    else if (msg.type == RadioStartAck && state == TestState::Starting && handshake == 0) {
      handshake = 1; startAttempts = 0; lastRadioTx = millis() - 2000;
    } else if (msg.type == RadioCommitAck && state == TestState::Starting && handshake == 1 && msg.seq == commitToken) {
      handshake = 2; slots.begin(epoch, 1000); liveSlots.begin(epoch, 1000); lastRadioTx = millis() - 700;
    } else if (msg.type == RadioData && sampleOnTime && (realtime || msg.seq < kPacketCount) &&
               ((state == TestState::Running && phase == (realtime ? 5 : 4)) || (state == TestState::Starting && handshake == 2))) {
      if (state == TestState::Starting) { state = TestState::Running; phase = realtime ? 5 : 4; realtimeStarted = realtime; }
      const ReceiveResult accepted = realtime
          ? receiver.receiveLive(msg.session, msg.src, static_cast<uint8_t>(msg.seq), rssi, snr)
          : receiver.receive(msg.session, msg.src, msg.seq, rssi, snr);
      if (accepted == ReceiveResult::Accepted) {
        localSampleSeen = true; lastLocalSample = receivedAt;
        if (observedCh2 == 0xffff || msg.seq + 1 > observedCh2) observedCh2 = msg.seq + 1;
        if (msg.stats.available == 1 && msg.stats.final == 0 &&
            ((realtime && msg.stats.received <= 1) ||
             (!realtime && msg.stats.received <= msg.seq && (lastRemoteSequence == 0xffff || msg.seq > lastRemoteSequence)))) {
          remoteStats = msg.stats; lastRemoteSequence = msg.seq;
          remoteSampleSeen = msg.stats.received > 0 && payload.sampleAgeSec != 255;
          if (remoteSampleSeen) lastRemoteSample = receivedAt - uint32_t(payload.sampleAgeSec) * 1000;
        }
        reportStatus();
      }
    } else if (msg.type == RadioReport && (state == TestState::Running || state == TestState::Done || state == TestState::Error) && phase == 3 &&
               msg.stats.available == 1 && msg.stats.received <= kPacketCount && msg.stats.final == 1 && msg.seq <= kPacketCount) {
      remoteStats = msg.stats;
      remoteSampleSeen = msg.stats.received > 0 && payload.sampleAgeSec != 255;
      if (remoteSampleSeen) lastRemoteSample = receivedAt - uint32_t(payload.sampleAgeSec) * 1000;
      observedCh2 = kPacketCount; forwardFinal = true;
      state = msg.seq == kPacketCount && senderOk == kPacketCount ? TestState::Done : TestState::Error;
      transmit(RadioReportAck, session, 0); reportStatus();
    }
#else
    if (msg.src != kCh1 || msg.dst != kCh2) return;
    if (msg.type == RadioStop && msg.session == session && (state == TestState::Starting || state == TestState::Running || state == TestState::Stopped || state == TestState::Done)) {
      state = TestState::Stopped; transmit(RadioStopAck, session, 0); return;
    }
    if (msg.type == RadioStart || msg.type == RadioStartRealtime) {
      if (state == TestState::Starting && msg.session == session && realtime == (msg.type == RadioStartRealtime)) { transmit(RadioStartAck, session, 0); return; }
      if (state == TestState::Starting || state == TestState::Running || msg.session == session) return;
      realtime = msg.type == RadioStartRealtime;
      session = msg.session; senderCount = senderOk = 0; phase = realtime ? 5 : 4; state = TestState::Starting;
      finalPartial = false;
      finalPeerSenderOk = 0;
      handshake = 0; stateStarted = millis(); receiver.start(session, kCh1);
      localSampleSeen = false;
      transmit(RadioStartAck, session, 0); return;
    }
    if (msg.session != session) return;
    if (msg.type == RadioCommit && state == TestState::Starting) {
      commitToken = msg.seq; epoch = millis() + 4000; slots.begin(epoch, 0); liveSlots.begin(epoch, 0); handshake = 1;
      transmit(RadioCommitAck, session, commitToken); return;
    }
    if (msg.type == RadioGo && state == TestState::Starting && handshake == 1 && msg.seq == commitToken && static_cast<int32_t>(epoch - millis()) > 0) {
      state = TestState::Running; return;
    }
    if (msg.type == RadioReverseData && sampleOnTime && state == TestState::Running && phase == (realtime ? 5 : 4)) {
      const ReceiveResult accepted = realtime
          ? receiver.receiveLive(msg.session, msg.src, static_cast<uint8_t>(msg.seq), rssi, snr)
          : receiver.receive(msg.session, msg.src, msg.seq, rssi, snr);
      if (accepted == ReceiveResult::Accepted) {
        localSampleSeen = true; lastLocalSample = receivedAt;
      }
      return;
    }
    if (!realtime && msg.type == RadioReverseEnd && (state == TestState::Running || state == TestState::Done || (state == TestState::Error && phase == 3)) && senderCount == kPacketCount) {
      if (phase == 3 && msg.seq != finalPeerSenderOk) return;
      if (phase != 3) {
        finalPeerSenderOk = msg.seq;
        finalPartial = msg.seq != kPacketCount || senderOk != kPacketCount;
      }
      DirectionStats finalStats = localStats(true); transmit(RadioReport, session, senderOk, &finalStats);
      if (state == TestState::Running) { phase = 3; lastRadioTx = millis(); }
      return;
    }
    if (msg.type == RadioReportAck && state == TestState::Running && phase == 3) { state = finalPartial ? TestState::Error : TestState::Done; return; }

#endif
  }
}

#if LT_ROLE == 1
// Never wait for a newline in the radio loop; discard oversized lines.
bool readSerialCommand(String& command) {
  static char line[64]{};
  static size_t used = 0;
  static bool overflow = false;
  for (unsigned n = 0; n < 32 && Serial0.available(); ++n) {
    const int value = Serial0.read();
    if (value < 0) break;
    const char c = static_cast<char>(value);
    if (c == '\n') {
      if (overflow) { used = 0; overflow = false; continue; }
      line[used] = '\0'; command = String(line); command.trim(); used = 0;
      return true;
    }
    if (c == '\r') continue;
    if (used + 1 < sizeof(line)) line[used++] = c;
    else overflow = true;
  }
  return false;
}
#endif

void loop() {
  keepAlive();
  serviceRadio();
  if (state == TestState::Running && phase == (realtime ? 5 : 4)) {
    const uint32_t reference = localSampleSeen ? lastLocalSample : epoch;
    if (static_cast<int32_t>(millis() - reference) >= static_cast<int32_t>(kPeerSilenceMs)) {
      #if LT_ROLE == 1
      stopAfterStartupFailure = true; state = TestState::Stopping;
      startAttempts = 0; lastRadioTx = millis() - 2000;
      #else
      state = TestState::Timeout;
      #endif
    }
  }
#if LT_ROLE == 1
  String cmd;
  if (readSerialCommand(cmd)) {
    if (cmd == "PAIR" && state != TestState::Running && state != TestState::Starting) {
      pairing = true; pairingStarted = millis(); Serial0.println("PAIR_WINDOW_OPEN");
    } else if (cmd == "INFO") {
      uint32_t raw, valid, queued, rejected, acked, noAck;
      portENTER_CRITICAL(&nowMux);
      raw = nowRawCount; valid = nowValidCount;
      queued = txQueued; rejected = txRejected; acked = txAck; noAck = txNoAck;
      portEXIT_CRITICAL(&nowMux);
      uint8_t channel = 0; wifi_second_chan_t second;
      int channelRead = esp_wifi_get_channel(&channel, &second);
      uint8_t infoStaMac[6]{};
      const int staMacRead = esp_wifi_get_mac(WIFI_IF_STA, infoStaMac);
      int8_t maxTxQuarterDbm = 0;
      const int maxTxRead = esp_wifi_get_max_tx_power(&maxTxQuarterDbm);
      const int resetReason = static_cast<int>(esp_reset_reason());
      Serial0.printf("LT_INFO radio=%d now=%d pair=%d paired=%d state=%u channel=%u channel_read=%d channel_set=%d now_init=%d callback=%d peer_add=%d rx_raw=%lu rx_valid=%lu status_calls=%lu status_result=%d\n",
                     radioReady, nowReady, pairing, paired, static_cast<unsigned>(state), channel, channelRead,
                     channelSetResult, nowInitResult, callbackResult, peerAddResult,
                     static_cast<unsigned long>(raw), static_cast<unsigned long>(valid),
                     static_cast<unsigned long>(statusSendCount), lastStatusResult);
      Serial0.printf("LT_NOW_TX cb_register=%d queued=%lu rejected=%lu ack=%lu no_ack=%lu peer=%02x:%02x:%02x:%02x:%02x:%02x boot=%08lx\n",
                     txCallbackResult, static_cast<unsigned long>(queued), static_cast<unsigned long>(rejected),
                     static_cast<unsigned long>(acked), static_cast<unsigned long>(noAck),
                     monitorMac[0], monitorMac[1], monitorMac[2], monitorMac[3], monitorMac[4], monitorMac[5],
                     static_cast<unsigned long>(bootNonce));
      // API max power unit is 0.25 dBm; report status separately so a
      // failed read cannot be mistaken for a measured zero.
      Serial0.printf("LT_WIFI_INFO mac_read=%d sta=%02x:%02x:%02x:%02x:%02x:%02x max_tx_read=%d max_tx_qdbm=%d reset_reason=%d\n",
                     staMacRead, infoStaMac[0], infoStaMac[1], infoStaMac[2],
                     infoStaMac[3], infoStaMac[4], infoStaMac[5], maxTxRead,
                     static_cast<int>(maxTxQuarterDbm), resetReason);
#if defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
      uint8_t infoMac[6]{};
      int infoMacResult = esp_wifi_get_mac(WIFI_IF_STA, infoMac);
      Serial0.printf("LT_ALT_MAC ready=%d read=%d actual=%02x:%02x:%02x:%02x:%02x:%02x\n",
                     altMacReady, infoMacResult, infoMac[0], infoMac[1], infoMac[2],
                     infoMac[3], infoMac[4], infoMac[5]);
#endif
    }
  }
  if (pairing && millis() - pairingStarted >= kPairWindowMs) pairing = false;
  uint8_t mac[6], messageType = 0; uint32_t sid = 0; bool hasStart;
  portENTER_CRITICAL(&nowMux);
  hasStart = incomingStart;
  if (hasStart) { memcpy(mac, incomingMac, 6); sid = incomingSession; messageType = incomingType; incomingStart = false; }
  portEXIT_CRITICAL(&nowMux);
  const bool activeTest = state == TestState::Running || state == TestState::Starting || state == TestState::Stopping;
  if (discovery.expire(millis(), activeTest)) {
    if (paired) esp_now_del_peer(monitorMac);
    paired = false;
  }
  if (hasStart && messageType == kNowDiscover && nowReady && discovery.consider(mac, millis(), activeTest)) {
    if (ensureMonitorPeer(mac)) {
      lastPresence = millis(); reportPresence();
      if (session != 0 && sessionOwner.matches(mac)) reportStatus();
    }
  }
  if (hasStart && messageType == kNowStop && paired && memcmp(monitorMac, mac, 6) == 0 && sid == session &&
      (state == TestState::Starting || state == TestState::Running)) {
    state = TestState::Stopping; startAttempts = 0; lastRadioTx = millis() - 2000; reportStatus();
  }
  if (hasStart && (messageType == kNowStart || messageType == kNowStartRealtime) && nowReady && state != TestState::Running && state != TestState::Starting && state != TestState::Stopping && sid != lastSession) {
    const bool same = paired && discovery.matches(mac);
    if (same || (pairing && discovery.consider(mac, millis(), false))) {
      if (!same) ensureMonitorPeer(mac);
      pairing = false;
      if (paired) {
        session = sid; lastSession = sid; sessionOwner.set(mac); receiver.start(session, kCh2);
        reportSequence = 0;
        realtime = messageType == kNowStartRealtime;
        realtimeStarted = false;
        phase = realtime ? 5 : 4; forwardFinal = false; reverseStarted = false; remoteStats = DirectionStats{};
        handshake = 0; commitToken = 0; observedCh2 = lastRemoteSequence = 0xffff;
        stopAfterStartupFailure = false;
        localSampleSeen = remoteSampleSeen = false;
        senderCount = 0; senderOk = 0;
        state = radioReady ? TestState::Starting : TestState::Error;
        stateStarted = millis(); startAttempts = 0;
        lastRadioTx = millis() - 2000;
        reportStatus();
      }
    }
  }
  if (state == TestState::Starting && handshake == 0 && millis() - lastRadioTx >= 2000 && startAttempts < 3) {
    lastRadioTx = millis(); ++startAttempts; transmit(realtime ? RadioStartRealtime : RadioStart, session, 0);
  }
  if (state == TestState::Starting && handshake == 0 && startAttempts >= 3 && millis() - lastRadioTx >= 3000) {
    stopAfterStartupFailure = true; state = TestState::Stopping;
    startAttempts = 0; lastRadioTx = millis() - 2000;
  }
  if (state == TestState::Starting && handshake == 1 && millis() - lastRadioTx >= 2000 && startAttempts < 3) {
    ++commitToken; ++startAttempts; transmit(RadioCommit, session, commitToken);
    epoch = millis() + 4000; lastRadioTx = millis();
  }
  if (state == TestState::Starting && handshake == 1 && startAttempts >= 3 && millis() - lastRadioTx >= 2000) {
    stopAfterStartupFailure = true; state = TestState::Stopping;
    startAttempts = 0; lastRadioTx = millis() - 2000;
  }
  // A GO without first data is not proof that CH2 entered the session.
  if (state == TestState::Starting && handshake == 2 && millis() - lastRadioTx >= 700 &&
      static_cast<int32_t>(epoch - millis()) > 1200) {
    transmit(RadioGo, session, commitToken); lastRadioTx = millis();
  }
  if (state == TestState::Starting && handshake == 2 && static_cast<int32_t>(millis() - epoch) >= 0) {
    // Begin our own slots even when initial peer packets are lost. Silence
    // after the epoch is bounded by the peer watchdog, not by two packets.
    state = TestState::Running;
    phase = realtime ? 5 : 4;
    realtimeStarted = realtime;
  }
  if (state == TestState::Stopping && millis() - lastRadioTx >= 2000 && startAttempts < 3) {
    // After the common epoch, use CH1's transmit half-slot so CH2 is
    // nominally listening. Before epoch/after the test, transmit normally.
    const bool beforeEpoch = !realtimeStarted && static_cast<int32_t>(millis() - epoch) < 0;
    const bool liveWindow = beforeEpoch || liveSlots.stopWindow(millis());
    if (realtime ? (handshake != 2 || liveWindow) : stopWindow(millis(), epoch, handshake == 2)) {
      lastRadioTx = millis(); ++startAttempts; transmit(RadioStop, session, 0);
    }
  }
  if (state == TestState::Stopping && startAttempts >= 3 && millis() - lastRadioTx >= 3000)
    state = TestState::Timeout;
  if (state == TestState::Running && phase == 4) {
    uint16_t seq = 0; SlotDecision decision = slots.next(millis(), seq);
    if (decision == SlotDecision::Send || decision == SlotDecision::Skip) {
      senderCount = seq + 1;
      if (decision == SlotDecision::Send && transmit(RadioReverseData, session, seq)) ++senderOk;
      reportStatus();
    } else if (decision == SlotDecision::Finished) {
      phase = 3; lastRadioTx = millis() - 2000;
    }
  }
  if (state == TestState::Running && phase == 5 && realtime) {
    uint16_t seq = 0; SlotDecision decision = liveSlots.next(millis(), seq);
    if (decision == SlotDecision::Send) transmit(RadioReverseData, session, seq);
  }
  if (state == TestState::Running && phase == 3 && millis() - lastRadioTx >= 2000) {
    lastRadioTx = millis(); transmit(RadioReverseEnd, session, senderOk);
  }
  if ((state == TestState::Starting || (state == TestState::Running && !realtime)) && millis() - stateStarted >= kSessionTimeoutMs)
    state = TestState::Timeout;
  if (paired && millis() - lastPresence >= 2000) { lastPresence = millis(); reportPresence(); }
  if (paired && session != 0 && millis() - lastNow >= 1000) { lastNow = millis(); reportStatus(); }
#else
  if (state == TestState::Running && phase == 4) {
    uint16_t seq = 0; SlotDecision decision = slots.next(millis(), seq);
    if (decision == SlotDecision::Send || decision == SlotDecision::Skip) {
      senderCount = seq + 1;
      DirectionStats progress = localStats(false);
      if (decision == SlotDecision::Send && transmit(RadioData, session, seq, &progress)) ++senderOk;
    }
  }
  if (state == TestState::Running && phase == 5 && realtime) {
    uint16_t seq = 0; SlotDecision decision = liveSlots.next(millis(), seq);
    if (decision == SlotDecision::Send) {
      DirectionStats latest = localStats(false);
      transmit(RadioData, session, seq, &latest);
    }
  }
  if (state == TestState::Running && phase == 3 && millis() - lastRadioTx >= 3000) {
    DirectionStats finalStats = localStats(true);
    lastRadioTx = millis(); transmit(RadioReport, session, senderOk, &finalStats);
  }
  if ((state == TestState::Starting || (state == TestState::Running && !realtime)) && millis() - stateStarted >= kSessionTimeoutMs)
    state = TestState::Timeout;
#endif
}
