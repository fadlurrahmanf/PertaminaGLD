#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include <Preferences.h>
#include <esp_task_wdt.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "AlarmQueue.h"
#include "AppFrame.h"
#include "ChBoardPins.h"
#include "ChRuntime.h"
#include "ChTxQueue.h"
#include "ChConfig.h"
#include "FirmwareConfig.h"
#include "FirmwareVersion.h"
#include "NodeCache.h"
#include "ProtocolConstants.h"

namespace {

// ─── Config constants ───────────────────────────────────────────────────────

constexpr uint16_t CH_ID             = pgl::config::ch::CH_ID;
constexpr uint16_t ROOT_GATEWAY_ID   = pgl::config::ch::ROOT_GATEWAY_ID;
constexpr uint16_t DEFAULT_PARENT_ID = pgl::config::ch::DEFAULT_PARENT_ID;
constexpr uint16_t BROADCAST_ID      = 0xFFFF;

constexpr float    STAR_FREQ_MHZ    = pgl::config::ch::STAR_FREQ_MHZ;
constexpr float    STAR_BW_KHZ      = pgl::config::ch::STAR_BW_KHZ;
constexpr uint8_t  STAR_SF          = pgl::config::ch::STAR_SF;
constexpr uint8_t  STAR_CR          = pgl::config::ch::STAR_CR;
constexpr uint8_t  STAR_SYNC_WORD   = pgl::config::ch::STAR_SYNC_WORD;

constexpr float    MESH_FREQ_MHZ    = pgl::config::ch::MESH_FREQ_MHZ;
constexpr float    MESH_BW_KHZ      = pgl::config::ch::MESH_BW_KHZ;
constexpr uint8_t  MESH_SF          = pgl::config::ch::MESH_SF;
constexpr uint8_t  MESH_CR          = pgl::config::ch::MESH_CR;
constexpr uint8_t  MESH_SYNC_WORD   = pgl::config::ch::MESH_SYNC_WORD;

constexpr int8_t   RADIO_TX_POWER_DBM      = pgl::config::ch::RADIO_TX_POWER_DBM;
constexpr uint16_t RADIO_PREAMBLE          = pgl::config::ch::RADIO_PREAMBLE;
constexpr float    RADIO_TCXO_VOLTAGE      = pgl::config::ch::RADIO_TCXO_VOLTAGE;
constexpr float    RADIO_XTAL_TCXO_VOLTAGE = pgl::config::ch::RADIO_XTAL_TCXO_VOLTAGE;
constexpr uint32_t RADIO_SPI_HZ            = pgl::config::ch::RADIO_SPI_HZ;

constexpr size_t   NODE_CACHE_CAPACITY      = pgl::config::ch::NODE_CACHE_CAPACITY;
constexpr size_t   ALARM_QUEUE_CAPACITY     = pgl::config::ch::ALARM_QUEUE_CAPACITY;
constexpr size_t   TX_QUEUE_CAPACITY        = pgl::config::ch::TX_QUEUE_CAPACITY;
constexpr size_t   DOWNLINK_STORE_CAPACITY  = pgl::config::ch::DOWNLINK_STORE_CAPACITY;
constexpr uint32_t CACHE_REPORT_INTERVAL_MS = pgl::config::ch::CACHE_REPORT_INTERVAL_MS;
constexpr uint32_t NODE_STALE_AFTER_MS      = pgl::config::ch::NODE_STALE_AFTER_MS;

constexpr uint16_t BATT_START_MV           = pgl::config::ch::BATT_START_MV;
constexpr uint16_t BATT_RUN_MIN_MV         = pgl::config::ch::BATT_RUN_MIN_MV;
constexpr uint16_t BATT_CRITICAL_MV        = pgl::config::ch::BATT_CRITICAL_MV;
constexpr uint32_t ALARM_ACK_TMO_MS        = pgl::config::ch::ALARM_ACK_TMO_MS;
constexpr uint8_t  PARENT_FAIL_TH          = pgl::config::ch::PARENT_FAIL_TH;
constexpr uint8_t  NO_ACK_RECOVERY_TH      = pgl::config::ch::NO_ACK_RECOVERY_TH;
constexpr uint32_t FAILOVER_CDN_MS         = pgl::config::ch::FAILOVER_CDN_MS;
constexpr uint32_t HELLO_INTERVAL_MS       = pgl::config::ch::HELLO_INTERVAL_MS;
constexpr uint32_t JOINING_TMO_MS          = pgl::config::ch::JOINING_TMO_MS;
constexpr uint32_t CFG_REQUEST_INTERVAL_MS = pgl::config::ch::CFG_REQUEST_INTERVAL_MS;
constexpr uint32_t CFG_RESPONSE_BASE_DELAY_MS = pgl::config::ch::CFG_RESPONSE_BASE_DELAY_MS;
constexpr uint32_t CFG_RESPONSE_SLOT_GAP_MS = pgl::config::ch::CFG_RESPONSE_SLOT_GAP_MS;
constexpr uint8_t  CFG_RESPONSE_SLOT_COUNT = pgl::config::ch::CFG_RESPONSE_SLOT_COUNT;
constexpr uint32_t ROUTE_VERIFY_INTERVAL_MS= pgl::config::ch::ROUTE_VERIFY_INTERVAL_MS;
constexpr uint32_t ROUTE_VERIFY_JITTER_MS  = pgl::config::ch::ROUTE_VERIFY_JITTER_MS;
constexpr uint32_t ROUTE_VERIFY_WINDOW_MS  = pgl::config::ch::ROUTE_VERIFY_WINDOW_MS;
constexpr uint32_t PARENT_HEALTH_TIMEOUT_MS= pgl::config::ch::PARENT_HEALTH_TIMEOUT_MS;
constexpr uint32_t PARENT_MIN_DWELL_MS     = pgl::config::ch::PARENT_MIN_DWELL_MS;
constexpr int16_t  PARENT_SWITCH_MARGIN_DB = pgl::config::ch::PARENT_SWITCH_MARGIN_DB;
constexpr int16_t  GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM = pgl::config::ch::GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM;
constexpr int8_t   GATEWAY_DIRECT_PARENT_MIN_SNR_DB = pgl::config::ch::GATEWAY_DIRECT_PARENT_MIN_SNR_DB;
constexpr int16_t  GATEWAY_PARENT_MIN_RSSI_DBM = pgl::config::ch::GATEWAY_PARENT_MIN_RSSI_DBM;
constexpr int16_t  GATEWAY_ALT_PARENT_MIN_RSSI_DBM = pgl::config::ch::GATEWAY_ALT_PARENT_MIN_RSSI_DBM;
constexpr uint8_t  PARENT_NVS_STABLE_SCANS = pgl::config::ch::PARENT_NVS_STABLE_SCANS;
constexpr uint32_t PENDING_TTL_MS          = pgl::config::ch::PENDING_TTL_MS;
constexpr uint32_t HOUSEKEEPING_INTERVAL_MS= pgl::config::ch::HOUSEKEEPING_INTERVAL_MS;
constexpr uint32_t CACHE_EXPIRE_MS         = pgl::config::ch::CACHE_EXPIRE_MS;

// ─── State machine ──────────────────────────────────────────────────────────

enum class ChState : uint8_t {
    BOOT, WAIT_BATT, RADIO_INIT, JOINING,
    JOINED, LOW_POWER, PARENT_FAILOVER, RECOVERY
};
static ChState chState = ChState::BOOT;

const char* chStateName(ChState s) {
    switch (s) {
        case ChState::BOOT:            return "BOOT";
        case ChState::WAIT_BATT:       return "WAIT_BATT";
        case ChState::RADIO_INIT:      return "RADIO_INIT";
        case ChState::JOINING:         return "JOINING";
        case ChState::JOINED:          return "JOINED";
        case ChState::LOW_POWER:       return "LOW_POWER";
        case ChState::PARENT_FAILOVER: return "PARENT_FAILOVER";
        case ChState::RECOVERY:        return "RECOVERY";
    }
    return "UNKNOWN";
}

// ─── Radio hardware ─────────────────────────────────────────────────────────

struct RadioPins {
    uint8_t cs, dio1, rst, busy, rxen, txen;
};

constexpr RadioPins STAR_PINS{
    pgl::ch::board::PIN_RADIO_A_CS,   pgl::ch::board::PIN_RADIO_A_DIO1,
    pgl::ch::board::PIN_RADIO_A_RST,  pgl::ch::board::PIN_RADIO_A_BUSY,
    pgl::ch::board::PIN_RADIO_A_RXEN, pgl::ch::board::PIN_RADIO_A_TXEN,
};
constexpr RadioPins MESH_PINS{
    pgl::ch::board::PIN_RADIO_B_CS,   pgl::ch::board::PIN_RADIO_B_DIO1,
    pgl::ch::board::PIN_RADIO_B_RST,  pgl::ch::board::PIN_RADIO_B_BUSY,
    pgl::ch::board::PIN_RADIO_B_RXEN, pgl::ch::board::PIN_RADIO_B_TXEN,
};

static Module* starModule = nullptr;
static Module* meshModule = nullptr;
static SX1262* starRadio  = nullptr;
static SX1262* meshRadio  = nullptr;
static bool    starReady  = false;
static bool    meshReady  = false;
static volatile bool starPacketReceived = false;
static volatile bool meshPacketReceived = false;

// ─── Queues & cache ─────────────────────────────────────────────────────────

static pgl::ch::NodeCacheEntry nodeCache[NODE_CACHE_CAPACITY]{};
static pgl::ch::AlarmQueueItem alarmQueue[ALARM_QUEUE_CAPACITY]{};
static pgl::ch::ChTxItem       txQueue[TX_QUEUE_CAPACITY]{};

struct PendingDownlink {
    uint16_t nodeId;
    uint16_t commandId;
    uint8_t  payloadLen;
    uint8_t  payload[8];
    bool     active;
    uint32_t receivedAtMs;
};
static PendingDownlink downlinkStore[DOWNLINK_STORE_CAPACITY]{};

static uint8_t  meshSeq           = 0;
static uint32_t lastCacheReportMs = 0;

// ─── Runtime config (non-const: meshDstId and chBatteryMv updated at runtime) ──

static pgl::config::ChRuntimeConfig runtimeConfig{
    CH_ID,
    DEFAULT_PARENT_ID,
    0xFFFF,
    NODE_STALE_AFTER_MS,
};

// ─── Dynamic parent & failover ──────────────────────────────────────────────

static uint16_t parentId       = DEFAULT_PARENT_ID;
static uint16_t parentAlt      = 0;
static uint8_t  parentFailCnt  = 0;
static uint8_t  noAckBurst     = 0;
static uint32_t lastFailoverMs = 0;
static uint8_t  meshDepth      = 0xFF;
static uint32_t lastCfgReqMs   = 0;
static uint32_t lastParentSeenMs = 0;
static int16_t  lastParentRssiDbm = -32768;
static int8_t   lastParentSnrDb = -128;
static uint32_t lastRouteVerifyMs = 0;
static uint32_t nextRouteVerifyDueMs = 0;
static uint32_t routeVerifyStartedMs = 0;
static bool     routeVerifyActive = false;
static uint32_t lastParentChangedMs = 0;
static uint16_t savedParentId = DEFAULT_PARENT_ID;
static uint16_t savedParentAlt = 0;
static uint16_t nvsPendingParentId = 0;
static uint16_t nvsPendingAltId = 0;
static uint8_t  nvsPendingStableScans = 0;

constexpr size_t   PARENT_CANDIDATE_CAPACITY = 8;

struct ParentCandidate {
    uint16_t id;
    uint16_t advertisedParent;
    uint16_t batteryMv;
    int16_t  rssiDbm;
    int8_t   snrDb;
    int16_t  reverseRssiDbm;
    int8_t   reverseSnrDb;
    uint8_t  depth;
    uint32_t seenAtMs;
    bool     hasReverseLink;
    bool     active;
};

static ParentCandidate parentCandidates[PARENT_CANDIDATE_CAPACITY]{};

// ─── Alarm ACK tracking ─────────────────────────────────────────────────────

struct AlarmAckPending {
    bool     active;
    uint16_t nodeId;
    uint8_t  seq;
    uint8_t  retryCount;
    uint32_t sentAtMs;
    uint8_t  frame[pgl::ch::CH_TX_FRAME_MAX];
    size_t   frameSize;
};
static AlarmAckPending alarmAck{};

// ─── Timing ─────────────────────────────────────────────────────────────────

static uint32_t lastHelloMs       = 0;
static uint32_t lastHousekeepMs   = 0;
static uint32_t lowPowerEnteredMs = 0;
static uint32_t joiningStartMs    = 0;
static uint32_t failoverEnteredMs = 0;

// ─── Battery ────────────────────────────────────────────────────────────────

static uint16_t batteryMv       = 0xFFFF;
static uint8_t  battStableCount = 0;

// ─── Joining flag ───────────────────────────────────────────────────────────

static bool joiningCfgReqSent = false;

// ─── Logging ────────────────────────────────────────────────────────────────

void logPrint(const char* text) {
    Serial.print(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(text);
#endif
}

void logPrintln(const char* text) {
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
#endif
}

void logPrintf(const char* fmt, ...) {
    char buffer[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    logPrint(buffer);
}

// ─── State machine ──────────────────────────────────────────────────────────

void setState(ChState newState, const char* reason) {
    logPrintf("CH_STATE state=%s reason=%s\n", chStateName(newState), reason);
    chState = newState;
}

// ─── NVS (parent persistence) ───────────────────────────────────────────────

void loadParents() {
    Preferences prefs;
    prefs.begin("ch-cfg", true);
    parentId  = prefs.getUShort("parentId",  static_cast<uint16_t>(DEFAULT_PARENT_ID));
    parentAlt = prefs.getUShort("parentAlt", 0);
    prefs.end();
    if (parentId == ROOT_GATEWAY_ID) {
        logPrintf("CH_NVS_PARENT_CLEAR parentId=0x%04X reason=gateway-parent-requires-fresh-rssi minRssi=%d\n",
                  parentId, GATEWAY_PARENT_MIN_RSSI_DBM);
        parentId = DEFAULT_PARENT_ID;
    }
    if (parentAlt != 0) {
        logPrintf("CH_NVS_ALT_CLEAR parentAlt=0x%04X reason=alternate-requires-fresh-depth-rssi gatewayAltMinRssi=%d\n",
                  parentAlt, GATEWAY_ALT_PARENT_MIN_RSSI_DBM);
        parentAlt = 0;
    }
    savedParentId = parentId;
    savedParentAlt = parentAlt;
    logPrintf("CH_NVS_LOAD parentId=0x%04X parentAlt=0x%04X\n", parentId, parentAlt);
}

void saveParents() {
    if (parentId == savedParentId && parentAlt == savedParentAlt) {
        logPrintf("CH_NVS_SAVE_SKIP parentId=0x%04X parentAlt=0x%04X reason=unchanged\n",
                  parentId, parentAlt);
        return;
    }
    Preferences prefs;
    prefs.begin("ch-cfg", false);
    prefs.putUShort("parentId",  parentId);
    prefs.putUShort("parentAlt", parentAlt);
    prefs.end();
    savedParentId = parentId;
    savedParentAlt = parentAlt;
    logPrintf("CH_NVS_SAVE parentId=0x%04X parentAlt=0x%04X\n", parentId, parentAlt);
}

void updateRuntimeParent(uint16_t newId) {
    const bool changed = (parentId != newId);
    parentId                = newId;
    runtimeConfig.meshDstId = newId;
    meshDepth = (newId == ROOT_GATEWAY_ID) ? 1 : 0xFF;
    if (changed) {
        lastParentChangedMs = millis();
    }
}

void clearParentCandidates() {
    memset(parentCandidates, 0, sizeof(parentCandidates));
}

ParentCandidate* findParentCandidate(uint16_t id) {
    for (auto& c : parentCandidates) {
        if (c.active && c.id == id) {
            return &c;
        }
    }
    return nullptr;
}

uint8_t advertisedMeshDepth() {
    if (CH_ID == ROOT_GATEWAY_ID) return 0;
    if (parentId == ROOT_GATEWAY_ID) return 1;
    return meshDepth;
}

int32_t candidateScore(const ParentCandidate& c) {
    // Higher is better. Design policy: parent utama dipilih dari RSSI terbaik.
    return static_cast<int32_t>(c.rssiDbm);
}

bool candidateBetter(const ParentCandidate& a, const ParentCandidate& b) {
    const int32_t aScore = candidateScore(a);
    const int32_t bScore = candidateScore(b);
    if (aScore != bScore) return aScore > bScore;
    if (a.depth != b.depth) return a.depth < b.depth;
    if (a.snrDb != b.snrDb) return a.snrDb > b.snrDb;
    return a.id < b.id;
}

bool directGatewayPreferred(const ParentCandidate& c) {
    return c.id == ROOT_GATEWAY_ID &&
           c.rssiDbm >= GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM &&
           c.hasReverseLink &&
           c.reverseRssiDbm >= GATEWAY_PARENT_MIN_RSSI_DBM &&
           c.snrDb >= GATEWAY_DIRECT_PARENT_MIN_SNR_DB;
}

bool candidateIsUpstreamForDepth(const ParentCandidate& c, uint8_t nodeDepth) {
    return nodeDepth == 0xFF || c.depth < nodeDepth;
}

uint8_t nodeDepthVia(const ParentCandidate& selectedParent) {
    if (selectedParent.depth == 0xFF || selectedParent.depth >= 0xFE) {
        return 0xFF;
    }
    return static_cast<uint8_t>(selectedParent.depth + 1);
}

bool allowedAsRuntimeParent(const ParentCandidate& c) {
    const bool gatewayParentOk = c.id != ROOT_GATEWAY_ID ||
                                 (c.rssiDbm >= GATEWAY_PARENT_MIN_RSSI_DBM &&
                                  c.hasReverseLink &&
                                  c.reverseRssiDbm >= GATEWAY_PARENT_MIN_RSSI_DBM);
    return gatewayParentOk && candidateIsUpstreamForDepth(c, meshDepth);
}

bool allowedAsAlternateForNodeDepth(const ParentCandidate& c, uint8_t nodeDepth) {
    const bool gatewayAltOk = c.id != ROOT_GATEWAY_ID ||
                              (c.rssiDbm >= GATEWAY_ALT_PARENT_MIN_RSSI_DBM &&
                               c.hasReverseLink &&
                               c.reverseRssiDbm >= GATEWAY_ALT_PARENT_MIN_RSSI_DBM);
    return gatewayAltOk && candidateIsUpstreamForDepth(c, nodeDepth);
}

bool allowedAsAlternateParent(const ParentCandidate& c, const ParentCandidate& selectedParent) {
    return allowedAsAlternateForNodeDepth(c, nodeDepthVia(selectedParent));
}

ParentCandidate* bestAlternateFor(const ParentCandidate* selectedParent) {
    ParentCandidate* alt = nullptr;
    if (selectedParent == nullptr) return nullptr;
    if (selectedParent->id == ROOT_GATEWAY_ID) return nullptr;
    for (auto& c : parentCandidates) {
        if (!c.active || &c == selectedParent || !allowedAsAlternateParent(c, *selectedParent)) {
            continue;
        }
        if (alt == nullptr || candidateBetter(c, *alt)) {
            alt = &c;
        }
    }
    return alt;
}

void upsertParentCandidate(uint16_t id, uint16_t advertisedParent, uint8_t depth,
                           uint16_t candidateBatteryMv, int16_t rssiDbm, int8_t snrDb,
                           bool hasReverseLink = false, int16_t reverseRssiDbm = 0, int8_t reverseSnrDb = 0) {
    if (id == 0 || id == CH_ID || id == BROADCAST_ID) return;
    if (advertisedParent == CH_ID) return;
    if (depth == 0xFF) return;

    ParentCandidate* slot = nullptr;
    for (auto& c : parentCandidates) {
        if (c.active && c.id == id) {
            slot = &c;
            break;
        }
        if (!c.active && slot == nullptr) {
            slot = &c;
        }
    }
    if (slot == nullptr) return;

    slot->id = id;
    slot->advertisedParent = advertisedParent;
    slot->batteryMv = candidateBatteryMv;
    slot->rssiDbm = rssiDbm;
    slot->snrDb = snrDb;
    slot->hasReverseLink = hasReverseLink;
    slot->reverseRssiDbm = reverseRssiDbm;
    slot->reverseSnrDb = reverseSnrDb;
    slot->depth = depth;
    slot->seenAtMs = millis();
    slot->active = true;
    if (id == parentId) {
        lastParentSeenMs = slot->seenAtMs;
        lastParentRssiDbm = rssiDbm;
        lastParentSnrDb = snrDb;
    }
    logPrintf("CH_PARENT_CANDIDATE id=0x%04X parent=0x%04X depth=%u rssi=%d snr=%d reverse=%u reverseRssi=%d reverseSnr=%d battMv=%u\n",
              id,
              advertisedParent,
              depth,
              rssiDbm,
              snrDb,
              hasReverseLink ? 1 : 0,
              reverseRssiDbm,
              reverseSnrDb,
              candidateBatteryMv);
}

bool noteStableParentForNvs(uint16_t selectedParent, uint16_t selectedAlt) {
    if (nvsPendingParentId == selectedParent && nvsPendingAltId == selectedAlt) {
        if (nvsPendingStableScans < 0xFF) {
            nvsPendingStableScans++;
        }
    } else {
        nvsPendingParentId = selectedParent;
        nvsPendingAltId = selectedAlt;
        nvsPendingStableScans = 1;
    }
    return nvsPendingStableScans >= PARENT_NVS_STABLE_SCANS;
}

uint32_t routeVerifyJitterMs() {
    if (ROUTE_VERIFY_JITTER_MS == 0) return 0;
    return ((static_cast<uint32_t>(CH_ID) * 997UL) + millis()) % ROUTE_VERIFY_JITTER_MS;
}

void scheduleNextRouteVerify(uint32_t now) {
    nextRouteVerifyDueMs = now + ROUTE_VERIFY_INTERVAL_MS + routeVerifyJitterMs();
}

bool selectDiscoveredParents(const char* reason) {
    ParentCandidate* best = nullptr;
    ParentCandidate* alt = nullptr;
    ParentCandidate* directGateway = nullptr;
    uint8_t downstreamRejected = 0;
    bool rejectedCurrentGatewayParent = false;
    for (auto& c : parentCandidates) {
        if (!c.active) continue;
        if (!allowedAsRuntimeParent(c)) {
            downstreamRejected++;
            const bool gatewayCandidate = c.id == ROOT_GATEWAY_ID;
            const bool weakGateway = gatewayCandidate && c.rssiDbm < GATEWAY_PARENT_MIN_RSSI_DBM;
            const bool noReverseGateway = gatewayCandidate && !c.hasReverseLink;
            const bool weakReverseGateway = gatewayCandidate && c.hasReverseLink && c.reverseRssiDbm < GATEWAY_PARENT_MIN_RSSI_DBM;
            const char* rejectReason = "not-upstream";
            if (noReverseGateway) {
                rejectReason = "gateway-missing-reverse-link";
            } else if (weakGateway) {
                rejectReason = "weak-gateway-downlink";
            } else if (weakReverseGateway) {
                rejectReason = "weak-gateway-uplink";
            }
            if (gatewayCandidate && parentId == ROOT_GATEWAY_ID &&
                (noReverseGateway || weakGateway || weakReverseGateway)) {
                rejectedCurrentGatewayParent = true;
            }
            logPrintf("CH_PARENT_CANDIDATE_REJECT id=0x%04X reason=%s candidateDepth=%u nodeDepth=%u rssi=%d snr=%d reverse=%u reverseRssi=%d reverseSnr=%d gatewayParentMinRssi=%d\n",
                      c.id,
                      rejectReason,
                      c.depth,
                      meshDepth,
                      c.rssiDbm,
                      c.snrDb,
                      c.hasReverseLink ? 1 : 0,
                      c.reverseRssiDbm,
                      c.reverseSnrDb,
                      GATEWAY_PARENT_MIN_RSSI_DBM);
            continue;
        }
        if (directGatewayPreferred(c) &&
            (directGateway == nullptr || candidateBetter(c, *directGateway))) {
            directGateway = &c;
        }
        if (best == nullptr || candidateBetter(c, *best)) {
            best = &c;
        }
    }

    const bool gatewayPriority = directGateway != nullptr;
    if (gatewayPriority) {
        best = directGateway;
    }

    if (best == nullptr) {
        if (rejectedCurrentGatewayParent) {
            logPrintf("CH_PARENT_GATEWAY_DROP reason=weak-bidirectional-gateway oldParent=0x%04X rejected=%u nodeDepth=%u\n",
                      parentId, downstreamRejected, meshDepth);
            updateRuntimeParent(DEFAULT_PARENT_ID);
            parentAlt = 0;
            meshDepth = 0xFF;
            lastParentSeenMs = 0;
            lastParentRssiDbm = 0;
            lastParentSnrDb = 0;
            routeVerifyActive = false;
            setState(ChState::PARENT_FAILOVER, "weak-bidirectional-gateway");
        }
        logPrintf("CH_PARENT_SELECT reason=%s result=no-candidate keepParent=0x%04X alt=0x%04X downstreamRejected=%u nodeDepth=%u\n",
                  reason, parentId, parentAlt, downstreamRejected, meshDepth);
        return false;
    }

    const bool background = strcmp(reason, "background") == 0;
    if (background && parentId != 0 && best->id != parentId && !gatewayPriority) {
        ParentCandidate* currentParent = findParentCandidate(parentId);
        const uint32_t now = millis();
        const uint32_t dwellMs = lastParentChangedMs == 0 ? 0xFFFFFFFFUL : now - lastParentChangedMs;
        if (currentParent != nullptr && dwellMs < PARENT_MIN_DWELL_MS) {
            alt = best;
            best = currentParent;
            logPrintf("CH_PARENT_KEEP reason=background parent=0x%04X candidate=0x%04X dwellMs=%lu minDwellMs=%lu\n",
                      parentId,
                      alt->id,
                      static_cast<unsigned long>(dwellMs),
                      static_cast<unsigned long>(PARENT_MIN_DWELL_MS));
        }
        if (currentParent != nullptr &&
            best->id != parentId &&
            best->rssiDbm < static_cast<int16_t>(currentParent->rssiDbm + PARENT_SWITCH_MARGIN_DB)) {
            alt = best;
            best = currentParent;
            logPrintf("CH_PARENT_KEEP reason=background parent=0x%04X currentRssi=%d candidate=0x%04X candidateRssi=%d marginDb=%d\n",
                      parentId,
                      currentParent->rssiDbm,
                      alt->id,
                      alt->rssiDbm,
                      PARENT_SWITCH_MARGIN_DB);
        }
    }

    alt = bestAlternateFor(best);

    const int32_t bestScore = candidateScore(*best);
    const int32_t altScore = (alt != nullptr) ? candidateScore(*alt) : 0;
    const uint16_t selectedParent = best->id;
    const uint16_t selectedAlt = (alt != nullptr) ? alt->id : 0;
    const bool nvsStable = noteStableParentForNvs(selectedParent, selectedAlt);

    if (background && parentId != 0 && selectedParent != parentId && !gatewayPriority && !nvsStable) {
        parentAlt = (parentId != ROOT_GATEWAY_ID && allowedAsAlternateForNodeDepth(*best, meshDepth)) ? selectedParent : 0;
        logPrintf("CH_PARENT_WAIT_STABLE reason=background keepParent=0x%04X candidate=0x%04X candidateRssi=%d "
                  "candidateDepth=%u nodeDepth=%u stableScans=%u requiredScans=%u altAllowed=%u gatewayAltMinRssi=%d\n",
                  parentId,
                  selectedParent,
                  best->rssiDbm,
                  best->depth,
                  meshDepth,
                  nvsPendingStableScans,
                  PARENT_NVS_STABLE_SCANS,
                  parentAlt != 0 ? 1 : 0,
                  GATEWAY_ALT_PARENT_MIN_RSSI_DBM);
        return true;
    }

    updateRuntimeParent(best->id);
    parentAlt = selectedAlt;
    meshDepth = (best->id == ROOT_GATEWAY_ID) ? 1 : static_cast<uint8_t>(best->depth + 1);
    lastParentSeenMs = millis();
    lastParentRssiDbm = best->rssiDbm;
    lastParentSnrDb = best->snrDb;
    lastHelloMs = millis() - HELLO_INTERVAL_MS;
    if (nvsStable) {
        saveParents();
    }
    logPrintf("CH_PARENT_SELECT reason=%s parent=0x%04X parentRssi=%d parentSnr=%d parentDepth=%u parentScore=%ld "
              "alt=0x%04X altRssi=%d altSnr=%d altDepth=%u altScore=%ld selectedBy=%s directGatewayMinRssi=%d directGatewayMinSnr=%d gatewayAltMinRssi=%d downstreamRejected=%u tieBreak=depth,snr,id nvsStable=%u stableScans=%u\n",
              reason,
              parentId,
              best->rssiDbm,
              best->snrDb,
              best->depth,
              static_cast<long>(bestScore),
              parentAlt,
              (alt != nullptr) ? alt->rssiDbm : 0,
              (alt != nullptr) ? alt->snrDb : 0,
              (alt != nullptr) ? alt->depth : 0,
              static_cast<long>(altScore),
              gatewayPriority ? "gateway-direct-rssi" : "rssi",
              GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM,
              GATEWAY_DIRECT_PARENT_MIN_SNR_DB,
              GATEWAY_ALT_PARENT_MIN_RSSI_DBM,
              downstreamRejected,
              nvsStable ? 1 : 0,
              nvsPendingStableScans);
    return true;
}

// ─── Battery ────────────────────────────────────────────────────────────────

uint16_t readBatteryMv() {
    uint32_t sum = 0;
    analogReadResolution(12);
    analogSetPinAttenuation(pgl::ch::board::PIN_BATMON, ADC_11db);
    for (uint8_t i = 0; i < 16; i++) {
        sum += static_cast<uint32_t>(analogReadMilliVolts(pgl::ch::board::PIN_BATMON));
    }
    return static_cast<uint16_t>((sum / 16) * 3UL + 200UL);
}

bool txAllowed() {
    return batteryMv == 0xFFFF || batteryMv >= BATT_CRITICAL_MV;
}

// ─── Radio pin setup ────────────────────────────────────────────────────────

void setupRadioPinsSafe() {
    pinMode(pgl::ch::board::PIN_RADIO_A_CS,   OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_CS,   HIGH);
    pinMode(pgl::ch::board::PIN_RADIO_B_CS,   OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_CS,   HIGH);
    pinMode(pgl::ch::board::PIN_RADIO_A_RST,  OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_RST,  LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_RST,  OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_RST,  LOW);
    pinMode(pgl::ch::board::PIN_RADIO_A_RXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_RXEN, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_A_TXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_TXEN, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_RXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_RXEN, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_TXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_TXEN, LOW);
}

void releaseRadioReset() {
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, LOW);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, LOW);
    delay(50);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, HIGH);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, HIGH);
    delay(500);
}

bool beginRadio(SX1262*& radio, Module*& module, const RadioPins& pins,
                const char* name, float freq, float bw, uint8_t sf, uint8_t cr, uint8_t sync) {
    module = new Module(pins.cs, pins.dio1, pins.rst, pins.busy,
                        SPI, SPISettings(RADIO_SPI_HZ, MSBFIRST, SPI_MODE0));
    radio  = new SX1262(module);
    int16_t st = radio->begin(freq, bw, sf, cr, sync, RADIO_TX_POWER_DBM,
                               RADIO_PREAMBLE, RADIO_TCXO_VOLTAGE, false);
    logPrintf("CH_%s_BEGIN_TCXO16_STATE=%d\n", name, st);
    if (st == RADIOLIB_ERR_SPI_CMD_FAILED) {
        st = radio->begin(freq, bw, sf, cr, sync, RADIO_TX_POWER_DBM,
                          RADIO_PREAMBLE, RADIO_XTAL_TCXO_VOLTAGE, false);
        logPrintf("CH_%s_BEGIN_XTAL_STATE=%d\n", name, st);
    }
    logPrintf("CH_%s_BEGIN_STATE=%d\n", name, st);
    if (st != RADIOLIB_ERR_NONE) return false;
    radio->setRfSwitchPins(pins.rxen, pins.txen);
    return true;
}

// ─── RX arm ─────────────────────────────────────────────────────────────────

void onStarPacketReceived() { starPacketReceived = true; }
void onMeshPacketReceived() { meshPacketReceived = true; }

bool startStarReceive(const char* reason) {
    if (!starReady || starRadio == nullptr) return false;
    const int16_t st = starRadio->startReceive();
    if (st != RADIOLIB_ERR_NONE) logPrintf("CH_STAR_RX_ARM reason=%s state=%d\n", reason, st);
    return st == RADIOLIB_ERR_NONE;
}

bool startMeshReceive(const char* reason) {
    if (!meshReady || meshRadio == nullptr) return false;
    const int16_t st = meshRadio->startReceive();
    if (st != RADIOLIB_ERR_NONE) logPrintf("CH_MESH_RX_ARM reason=%s state=%d\n", reason, st);
    return st == RADIOLIB_ERR_NONE;
}

// ─── Downlink store ─────────────────────────────────────────────────────────

PendingDownlink* findDownlink(uint16_t nodeId) {
    for (size_t i = 0; i < DOWNLINK_STORE_CAPACITY; ++i)
        if (downlinkStore[i].active && downlinkStore[i].nodeId == nodeId) return &downlinkStore[i];
    return nullptr;
}

PendingDownlink* findOrAllocateDownlink(uint16_t nodeId) {
    PendingDownlink* ex = findDownlink(nodeId);
    if (ex) return ex;
    for (size_t i = 0; i < DOWNLINK_STORE_CAPACITY; ++i)
        if (!downlinkStore[i].active) return &downlinkStore[i];
    return nullptr;
}

bool isNodeExtPower(uint16_t nodeId) {
    for (size_t i = 0; i < NODE_CACHE_CAPACITY; ++i)
        if (nodeCache[i].used && nodeCache[i].nodeId == nodeId)
            return (nodeCache[i].flags & pgl::protocol::NC_FLAG_EXT_POWER) != 0;
    return false;
}

// ─── Utility ────────────────────────────────────────────────────────────────

uint16_t readU16Be(const uint8_t* in) {
    return static_cast<uint16_t>((static_cast<uint16_t>(in[0]) << 8) | in[1]);
}

uint8_t meshHopCount(const pgl::protocol::FrameView& decoded) {
    if (decoded.payload == nullptr || decoded.payloadLen < 4 || ((decoded.payloadLen - 2) % 2) != 0) return 0;
    return static_cast<uint8_t>((decoded.payloadLen - 2) / 2);
}

uint16_t meshHopAt(const pgl::protocol::FrameView& decoded, uint8_t index) {
    return readU16Be(&decoded.payload[2 + (index * 2)]);
}

int8_t findMeshHopIndex(const pgl::protocol::FrameView& decoded, uint16_t chId) {
    const uint8_t hopCount = meshHopCount(decoded);
    for (uint8_t i = 0; i < hopCount; ++i)
        if (meshHopAt(decoded, i) == chId) return static_cast<int8_t>(i);
    return -1;
}

// ─── Cache report ────────────────────────────────────────────────────────────

void reportCache(const char* reason) {
    const uint32_t now = millis();
    size_t used = 0, unsentNormal = 0, unsentAlarm = 0;
    for (size_t i = 0; i < NODE_CACHE_CAPACITY; ++i) {
        const pgl::ch::NodeCacheEntry& entry = nodeCache[i];
        if (!entry.used) continue;
        ++used;
        const bool alarm  = pgl::ch::isNodeCacheEntryAlarm(entry);
        const bool unsent = pgl::ch::isNodeCacheEntryUnsent(entry);
        if (unsent && alarm)  ++unsentAlarm;
        else if (unsent)      ++unsentNormal;
    }
    logPrintf("CH_CACHE_SUMMARY reason=%s used=%u unsentNormal=%u unsentAlarm=%u capacity=%u\n",
              reason, static_cast<unsigned>(used), static_cast<unsigned>(unsentNormal),
              static_cast<unsigned>(unsentAlarm), static_cast<unsigned>(NODE_CACHE_CAPACITY));
    for (size_t i = 0; i < NODE_CACHE_CAPACITY; ++i) {
        const pgl::ch::NodeCacheEntry& entry = nodeCache[i];
        if (!entry.used) continue;
        logPrintf("CH_CACHE_ENTRY idx=%u node=0x%04X flags=0x%02X alarm=%u extPwr=%u unsent=%u ageMs=%lu\n",
                  static_cast<unsigned>(i), entry.nodeId, entry.flags,
                  pgl::ch::isNodeCacheEntryAlarm(entry) ? 1 : 0,
                  (entry.flags & pgl::protocol::NC_FLAG_EXT_POWER) ? 1 : 0,
                  pgl::ch::isNodeCacheEntryUnsent(entry) ? 1 : 0,
                  static_cast<unsigned long>(now - entry.lastSeenMs));
    }
}

void reportCachePeriodic() {
    const uint32_t now = millis();
    if (now - lastCacheReportMs >= CACHE_REPORT_INTERVAL_MS) {
        lastCacheReportMs = now;
        reportCache("periodic");
    }
}

// ─── TX helpers ─────────────────────────────────────────────────────────────

bool transmitRadio(SX1262* radio, const RadioPins& pins,
                   const uint8_t* frame, size_t frameSize, const char* tag) {
    if (radio == nullptr || frame == nullptr || frameSize == 0) return false;
    const int16_t st = radio->transmit(frame, frameSize);
    digitalWrite(pins.rxen, LOW);
    digitalWrite(pins.txen, LOW);
    logPrintf("CH_%s_TX state=%d len=%u\n", tag, st, static_cast<unsigned>(frameSize));
    return st == RADIOLIB_ERR_NONE;
}

bool enqueueRelayFrame(const pgl::protocol::FrameView& decoded, uint16_t nextHopId, const char* reason) {
    uint8_t relayFrame[pgl::ch::CH_TX_FRAME_MAX]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        decoded.typeFlags, CH_ID, nextHopId, decoded.seq,
        decoded.payload, decoded.payloadLen,
        relayFrame, sizeof(relayFrame), pgl::protocol::MESH_MAX_PAYLOAD);
    logPrintf("CH_RELAY_BUILD reason=%s msgType=0x%02X nextHop=0x%04X encStatus=%u\n",
              reason, pgl::protocol::messageType(decoded.typeFlags), nextHopId,
              static_cast<unsigned>(enc.status));
    if (enc.status != pgl::protocol::FrameStatus::Ok) return false;
    const pgl::ch::ChTxQueueStatus qStatus = pgl::ch::enqueueChTxFrame(
        txQueue, TX_QUEUE_CAPACITY,
        pgl::ch::ChTxKind::RelayFrame, 0, 0, nullptr, nullptr, 0,
        relayFrame, enc.size);
    logPrintf("CH_RELAY_ENQUEUE reason=%s status=%s\n", reason, pgl::ch::chTxQueueStatusName(qStatus));
    return qStatus == pgl::ch::ChTxQueueStatus::Ok;
}

bool sendNodeDownlink(uint16_t targetNodeId, PendingDownlink* dl) {
    if (!starReady || starRadio == nullptr || dl == nullptr || !dl->active) return false;
    static uint8_t downlinkSeq = 0;
    uint8_t downlinkFrame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_NODE_DOWNLINK, CH_ID, targetNodeId, downlinkSeq++,
        dl->payload, dl->payloadLen,
        downlinkFrame, sizeof(downlinkFrame), pgl::protocol::STAR_MAX_PAYLOAD);
    logPrintf("CH_NODE_DOWNLINK_TX nodeId=0x%04X encStatus=%u frameSize=%u\n",
              targetNodeId, static_cast<unsigned>(enc.status), static_cast<unsigned>(enc.size));
    if (enc.status != pgl::protocol::FrameStatus::Ok) return false;
    const bool ok = transmitRadio(starRadio, STAR_PINS, downlinkFrame, enc.size, "STAR_DOWNLINK");
    if (ok) {
        dl->active = false;
        startStarReceive("after-downlink-tx");
    }
    return ok;
}

// ─── Alarm ACK & failover ────────────────────────────────────────────────────

void onAlarmAckFromParent() {
    if (!alarmAck.active) return;
    logPrintf("CH_ALARM_ACK_RECV nodeId=0x%04X seq=%u retries=%u\n",
              alarmAck.nodeId, alarmAck.seq, alarmAck.retryCount);
    pgl::ch::markAlarmAcked(alarmAck.nodeId, alarmAck.seq, alarmQueue, ALARM_QUEUE_CAPACITY);
    alarmAck.active = false;
    noAckBurst      = 0;
}

void checkFailover() {
    if (noAckBurst >= NO_ACK_RECOVERY_TH) {
        setState(ChState::RECOVERY, "noAckBurst-threshold");
        return;
    }
    if (parentFailCnt >= PARENT_FAIL_TH && millis() - lastFailoverMs >= FAILOVER_CDN_MS) {
        lastFailoverMs = millis();
        if (parentAlt != 0) {
            const uint16_t tmp = parentId;
            updateRuntimeParent(parentAlt);
            parentAlt = tmp;
            saveParents();
        }
        parentFailCnt = 0;
        setState(ChState::PARENT_FAILOVER, "alarm-ACK-failures");
    }
}

void checkAlarmAckTimeout() {
    if (!alarmAck.active) return;
    if (millis() - alarmAck.sentAtMs < ALARM_ACK_TMO_MS) return;

    logPrintf("CH_ALARM_ACK_TIMEOUT nodeId=0x%04X seq=%u noRetry=1\n",
              alarmAck.nodeId, alarmAck.seq);
    pgl::ch::markAlarmAcked(alarmAck.nodeId, alarmAck.seq, alarmQueue, ALARM_QUEUE_CAPACITY);
    alarmAck.active = false;
    parentFailCnt++;
    noAckBurst++;
    checkFailover();
}

// ─── Drain TX queue ─────────────────────────────────────────────────────────

void drainTxQueue() {
    if (!meshReady || meshRadio == nullptr) return;
    if (alarmAck.active) return;

    const pgl::ch::ChTxItem* item = nullptr;
    bool txAttempted = false;

    while (pgl::ch::peekChTxFrame(txQueue, TX_QUEUE_CAPACITY, item) == pgl::ch::ChTxQueueStatus::Ok
           && item != nullptr) {
        if (!txAllowed()) break;
        txAttempted = true;

        const bool   isAlarmPush = (item->kind == pgl::ch::ChTxKind::AlarmPush);
        const uint16_t txNodeId  = item->nodeId;
        const uint8_t  txSeq     = item->gldSeq;
        const size_t   txSize    = item->frameSize;
        uint8_t frameCopy[pgl::ch::CH_TX_FRAME_MAX]{};
        memcpy(frameCopy, item->frame, txSize);

        logPrintf("CH_MESH_TX_KIND=%u nodeId=0x%04X gldSeq=%u frameSize=%u\n",
                  static_cast<unsigned>(item->kind), txNodeId, txSeq,
                  static_cast<unsigned>(txSize));

        const bool ok = transmitRadio(meshRadio, MESH_PINS, frameCopy, txSize, "MESH");
        const pgl::ch::ChRuntimeStatus markStatus =
            ok ? pgl::ch::markChTxSuccess(txQueue, TX_QUEUE_CAPACITY,
                                           nodeCache, NODE_CACHE_CAPACITY,
                                           alarmQueue, ALARM_QUEUE_CAPACITY, millis())
               : pgl::ch::markChTxFailed(txQueue, TX_QUEUE_CAPACITY);
        logPrintf("CH_MESH_TX_MARK status=%s\n", pgl::ch::chRuntimeStatusName(markStatus));

        if (!ok) break;

        if (isAlarmPush) {
            alarmAck.active     = true;
            alarmAck.nodeId     = txNodeId;
            alarmAck.seq        = txSeq;
            alarmAck.retryCount = 0;
            alarmAck.sentAtMs   = millis();
            alarmAck.frameSize  = txSize;
            memcpy(alarmAck.frame, frameCopy, txSize);
            break;
        }
    }
    if (txAttempted) startMeshReceive("after-drain");
}

// ─── MESH management messages ───────────────────────────────────────────────

void sendHello() {
    if (!meshReady || meshRadio == nullptr || !txAllowed()) return;
    static uint8_t helloSeq = 0;
    const uint32_t uptimeSec = millis() / 1000UL;
    uint8_t payload[11]{};
    payload[0] = static_cast<uint8_t>(CH_ID >> 8);
    payload[1] = static_cast<uint8_t>(CH_ID);
    payload[2] = static_cast<uint8_t>(parentId >> 8);
    payload[3] = static_cast<uint8_t>(parentId);
    payload[4] = static_cast<uint8_t>(batteryMv >> 8);
    payload[5] = static_cast<uint8_t>(batteryMv);
    payload[6] = static_cast<uint8_t>(uptimeSec >> 8);
    payload[7] = static_cast<uint8_t>(uptimeSec);
    payload[8] = meshDepth;
    payload[9] = static_cast<uint8_t>(parentAlt >> 8);
    payload[10] = static_cast<uint8_t>(parentAlt);
    uint8_t frame[pgl::ch::CH_TX_FRAME_MAX]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_HELLO, CH_ID, parentId, helloSeq++,
        payload, sizeof(payload), frame, sizeof(frame), pgl::protocol::MESH_MAX_PAYLOAD);
    if (enc.status != pgl::protocol::FrameStatus::Ok) return;
    transmitRadio(meshRadio, MESH_PINS, frame, enc.size, "MESH_HELLO");
    startMeshReceive("after-hello");
    logPrintf("CH_HELLO_TX parentId=0x%04X parentAlt=0x%04X battMv=%u uptimeSec=%lu depth=%u\n",
              parentId, parentAlt, batteryMv, static_cast<unsigned long>(uptimeSec), meshDepth);
}

void sendConfigRequest() {
    if (!meshReady || meshRadio == nullptr) return;
    static uint8_t cfgReqSeq = 0;
    uint8_t payload[2]{};
    payload[0] = static_cast<uint8_t>(CH_ID >> 8);
    payload[1] = static_cast<uint8_t>(CH_ID);
    uint8_t frame[pgl::ch::CH_TX_FRAME_MAX]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_CONFIG_REQUEST, CH_ID, BROADCAST_ID, cfgReqSeq++,
        payload, sizeof(payload), frame, sizeof(frame), pgl::protocol::MESH_MAX_PAYLOAD);
    if (enc.status != pgl::protocol::FrameStatus::Ok) return;
    delay(20 + ((CH_ID & 0x000F) * 30) + (millis() % 40));
    transmitRadio(meshRadio, MESH_PINS, frame, enc.size, "MESH_CFG_REQ");
    startMeshReceive("after-cfg-req");
    logPrintf("CH_CONFIG_REQUEST_TX parentId=0x%04X\n", parentId);
}

void sendConfigResponse(uint16_t requesterId, uint8_t requestSeq) {
    if (!meshReady || meshRadio == nullptr || requesterId == 0 || requesterId == CH_ID) return;
    const uint8_t depth = advertisedMeshDepth();
    if (depth == 0xFF) {
        logPrintf("CH_CONFIG_RESPONSE_SKIP requester=0x%04X reason=no-root-route\n", requesterId);
        return;
    }

    uint8_t payload[8]{};
    payload[0] = static_cast<uint8_t>(requesterId >> 8);
    payload[1] = static_cast<uint8_t>(requesterId);
    payload[2] = static_cast<uint8_t>(parentId >> 8);
    payload[3] = static_cast<uint8_t>(parentId);
    payload[4] = depth;
    payload[5] = static_cast<uint8_t>(batteryMv >> 8);
    payload[6] = static_cast<uint8_t>(batteryMv);
    payload[7] = 0x01;  // route-to-root capable

    uint8_t frame[pgl::ch::CH_TX_FRAME_MAX]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_CONFIG_RESPONSE, CH_ID, requesterId, requestSeq,
        payload, sizeof(payload), frame, sizeof(frame), pgl::protocol::MESH_MAX_PAYLOAD);
    if (enc.status != pgl::protocol::FrameStatus::Ok) {
        logPrintf("CH_CONFIG_RESPONSE_BUILD_FAIL requester=0x%04X status=%u\n",
                  requesterId, static_cast<unsigned>(enc.status));
        return;
    }

    const uint8_t slotCount = CFG_RESPONSE_SLOT_COUNT == 0 ? 1 : CFG_RESPONSE_SLOT_COUNT;
    const uint8_t responseSlot = static_cast<uint8_t>(CH_ID % slotCount);
    const uint32_t responseDelayMs = CFG_RESPONSE_BASE_DELAY_MS +
                                     (static_cast<uint32_t>(responseSlot) * CFG_RESPONSE_SLOT_GAP_MS);
    delay(responseDelayMs);
    transmitRadio(meshRadio, MESH_PINS, frame, enc.size, "MESH_CFG_RESP");
    startMeshReceive("after-cfg-resp-tx");
    logPrintf("CH_CONFIG_RESPONSE_TX requester=0x%04X parent=0x%04X depth=%u battMv=%u slot=%u delayMs=%lu slotGapMs=%lu\n",
              requesterId,
              parentId,
              depth,
              batteryMv,
              responseSlot,
              static_cast<unsigned long>(responseDelayMs),
              static_cast<unsigned long>(CFG_RESPONSE_SLOT_GAP_MS));
}

// ─── Housekeeping ────────────────────────────────────────────────────────────

void runHousekeeping() {
    const uint32_t now = millis();
    if (now - lastHousekeepMs < HOUSEKEEPING_INTERVAL_MS) return;
    lastHousekeepMs = now;

    uint8_t expiredDl = 0;
    for (size_t i = 0; i < DOWNLINK_STORE_CAPACITY; ++i) {
        PendingDownlink& dl = downlinkStore[i];
        if (dl.active && (now - dl.receivedAtMs) >= PENDING_TTL_MS) {
            logPrintf("CH_DOWNLINK_TTL_EXPIRED nodeId=0x%04X ageMs=%lu\n",
                      dl.nodeId, static_cast<unsigned long>(now - dl.receivedAtMs));
            dl.active = false;
            ++expiredDl;
        }
    }

    uint8_t expiredCache = 0;
    for (size_t i = 0; i < NODE_CACHE_CAPACITY; ++i) {
        pgl::ch::NodeCacheEntry& entry = nodeCache[i];
        if (entry.used && (now - entry.lastSeenMs) >= CACHE_EXPIRE_MS) {
            logPrintf("CH_CACHE_EXPIRED node=0x%04X ageMs=%lu\n",
                      entry.nodeId, static_cast<unsigned long>(now - entry.lastSeenMs));
            entry.used = false;
            ++expiredCache;
        }
    }
    logPrintf("CH_HOUSEKEEPING expiredDl=%u expiredCache=%u\n", expiredDl, expiredCache);
}

// ─── STAR RX handler ─────────────────────────────────────────────────────────

void handleStarPacketReceived() {
    if (!starPacketReceived || starRadio == nullptr) return;
    starPacketReceived = false;
    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD]{};
    const size_t  packetLen = starRadio->getPacketLength();
    const int16_t st        = starRadio->readData(frame, sizeof(frame));
    logPrintf("CH_STAR_RX state=%d len=%u rssi=%.2f snr=%.2f\n",
              st, static_cast<unsigned>(packetLen), starRadio->getRSSI(), starRadio->getSNR());
    if (st != RADIOLIB_ERR_NONE) {
        startStarReceive("after-star-error");
        return;
    }

    uint8_t ack[pgl::protocol::APPFRAME_OVERHEAD]{};
    pgl::ch::ChRuntimeProcessResult result{};
    const pgl::ch::ChRuntimeStatus status = pgl::ch::processGldStarFrame(
        runtimeConfig, frame, packetLen, millis(), meshSeq++,
        nodeCache, NODE_CACHE_CAPACITY,
        alarmQueue, ALARM_QUEUE_CAPACITY,
        txQueue, TX_QUEUE_CAPACITY,
        ack, sizeof(ack), result);
    logPrintf("CH_STAR_PROCESS status=%s ackBuilt=%u ackSize=%u onwardQueued=%u recoveryQueued=%u\n",
              pgl::ch::chRuntimeStatusName(status),
              result.ackBuilt ? 1 : 0, static_cast<unsigned>(result.ackSize),
              result.onwardQueued ? 1 : 0, result.recoveryQueued ? 1 : 0);
    reportCache("star-rx");

    if (result.ackBuilt) transmitRadio(starRadio, STAR_PINS, ack, result.ackSize, "STAR_ACK");

    const uint16_t srcNodeId = (static_cast<uint16_t>(frame[2]) << 8) | frame[3];
    PendingDownlink* dl = findDownlink(srcNodeId);
    if (dl != nullptr && !isNodeExtPower(srcNodeId)) {
        logPrintf("CH_DOWNLINK_BATTERY_WINDOW nodeId=0x%04X commandId=%u\n", srcNodeId, dl->commandId);
        sendNodeDownlink(srcNodeId, dl);
    }

    startStarReceive("after-star-rx");
    if (chState == ChState::JOINED) drainTxQueue();
}

// ─── MESH RX handler ─────────────────────────────────────────────────────────

void handleMeshPacketReceived() {
    if (!meshPacketReceived || meshRadio == nullptr) return;
    meshPacketReceived = false;
    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD]{};
    const size_t  packetLen = meshRadio->getPacketLength();
    const int16_t st        = meshRadio->readData(frame, sizeof(frame));
    const int16_t rxRssiDbm = static_cast<int16_t>(meshRadio->getRSSI());
    const int8_t  rxSnrDb   = static_cast<int8_t>(meshRadio->getSNR());
    logPrintf("CH_MESH_RX state=%d len=%u rssi=%.2f snr=%.2f\n",
              st, static_cast<unsigned>(packetLen), meshRadio->getRSSI(), meshRadio->getSNR());
    if (st != RADIOLIB_ERR_NONE) {
        startMeshReceive("after-mesh-error");
        return;
    }

    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus frameStatus =
        pgl::protocol::decodeAppFrame(frame, packetLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    logPrintf("CH_MESH_PARSE frameStatus=%u typeFlags=0x%02X src=0x%04X dst=0x%04X seq=%u len=%u\n",
              static_cast<unsigned>(frameStatus), decoded.typeFlags,
              decoded.srcId, decoded.dstId, decoded.seq, decoded.payloadLen);
    if (frameStatus != pgl::protocol::FrameStatus::Ok) {
        startMeshReceive("after-mesh-parse-error");
        return;
    }

    const uint8_t msgType = pgl::protocol::messageType(decoded.typeFlags);

    if (msgType == pgl::protocol::MSG_CH_CONFIG_REQUEST &&
        decoded.dstId == BROADCAST_ID &&
        decoded.srcId != CH_ID) {
        if (parentId != 0 && decoded.srcId == parentId) {
            logPrintf("CH_CONFIG_REQUEST_IGNORE srcId=0x%04X reason=current-parent\n", decoded.srcId);
            startMeshReceive("after-cfg-req-parent-ignore");
            return;
        }
        logPrintf("CH_CONFIG_REQUEST_RECV srcId=0x%04X seq=%u\n", decoded.srcId, decoded.seq);
        sendConfigResponse(decoded.srcId, decoded.seq);
        return;
    }

    if (decoded.dstId != CH_ID && decoded.dstId != BROADCAST_ID) {
        logPrintf("CH_MESH_IGNORE dst=0x%04X reason=not-local\n", decoded.dstId);
        startMeshReceive("after-mesh-not-local");
        return;
    }

    // Alarm ACK from parent
    if (decoded.srcId == parentId && decoded.dstId == CH_ID &&
        pgl::protocol::hasAlarmAckFlag(decoded.typeFlags)) {
        onAlarmAckFromParent();
    }

    // CH_CONFIG_RESPONSE: learn/update parent
    if (msgType == pgl::protocol::MSG_CH_CONFIG_RESPONSE && decoded.dstId == CH_ID) {
        uint16_t advertisedParent = 0;
        uint16_t candidateBatteryMv = 0xFFFF;
        uint8_t candidateDepth = (decoded.srcId == ROOT_GATEWAY_ID) ? 0 : 0xFF;
        bool hasReverseLink = false;
        int16_t reverseRssiDbm = 0;
        int8_t reverseSnrDb = 0;
        if (decoded.payloadLen >= 8 && decoded.payload != nullptr) {
            advertisedParent = (static_cast<uint16_t>(decoded.payload[2]) << 8) | decoded.payload[3];
            candidateDepth = decoded.payload[4];
            candidateBatteryMv = (static_cast<uint16_t>(decoded.payload[5]) << 8) | decoded.payload[6];
            if (decoded.srcId == ROOT_GATEWAY_ID && decoded.payloadLen >= 10) {
                hasReverseLink = true;
                reverseRssiDbm = static_cast<int8_t>(decoded.payload[8]);
                reverseSnrDb = static_cast<int8_t>(decoded.payload[9]);
            }
        }
        logPrintf("CH_CONFIG_RESPONSE_RECV srcId=0x%04X parent=0x%04X depth=%u rssi=%d snr=%d reverse=%u reverseRssi=%d reverseSnr=%d\n",
                  decoded.srcId,
                  advertisedParent,
                  candidateDepth,
                  rxRssiDbm,
                  rxSnrDb,
                  hasReverseLink ? 1 : 0,
                  reverseRssiDbm,
                  reverseSnrDb);
        upsertParentCandidate(decoded.srcId, advertisedParent, candidateDepth,
                              candidateBatteryMv, rxRssiDbm, rxSnrDb,
                              hasReverseLink, reverseRssiDbm, reverseSnrDb);
        startMeshReceive("after-cfg-resp");
        return;
    }

    // Pull relay or handle
    if (msgType == pgl::protocol::MSG_SERVER_PULL_REQUEST) {
        const int8_t  localHopIndex = findMeshHopIndex(decoded, CH_ID);
        const uint8_t hopCount      = meshHopCount(decoded);
        if (decoded.dstId == CH_ID && localHopIndex >= 0 &&
            static_cast<uint8_t>(localHopIndex) + 1 < hopCount) {
            const uint16_t nextHopId = meshHopAt(decoded, static_cast<uint8_t>(localHopIndex + 1));
            const bool queued = enqueueRelayFrame(decoded, nextHopId, "pull-downstream");
            logPrintf("CH_PULL_RELAY localHop=%d nextHop=0x%04X queued=%u\n",
                      static_cast<int>(localHopIndex), nextHopId, queued ? 1 : 0);
            if (chState == ChState::JOINED) drainTxQueue();
            startMeshReceive("after-pull-relay");
            return;
        }
        pgl::ch::ChRuntimeProcessResult result{};
        const pgl::ch::ChRuntimeStatus status = pgl::ch::handleServerPullRequestFrame(
            runtimeConfig, frame, packetLen, millis(),
            nodeCache, NODE_CACHE_CAPACITY,
            txQueue, TX_QUEUE_CAPACITY, result);
        logPrintf("CH_PULL_PROCESS status=%s onwardQueued=%u pullStatus=%u txStatus=%u\n",
                  pgl::ch::chRuntimeStatusName(status),
                  result.onwardQueued ? 1 : 0,
                  static_cast<unsigned>(result.pullStatus),
                  static_cast<unsigned>(result.txQueueStatus));
        reportCache("pull");
        if (chState == ChState::JOINED) drainTxQueue();
        return;
    }

    // Uplink relay to parent
    if (decoded.dstId == CH_ID &&
        (msgType == pgl::protocol::MSG_CLUSTER_DATA_RESPONSE ||
         msgType == pgl::protocol::MSG_SENSOR_DATA ||
         msgType == pgl::protocol::MSG_CH_HELLO) &&
        parentId != CH_ID) {
        const bool queued = enqueueRelayFrame(decoded, parentId, "uplink-to-parent");
        logPrintf("CH_UPLINK_RELAY msgType=0x%02X from=0x%04X parent=0x%04X queued=%u\n",
                  msgType, decoded.srcId, parentId, queued ? 1 : 0);
        if (chState == ChState::JOINED) drainTxQueue();
        startMeshReceive("after-uplink-relay");
        return;
    }

    // SERVER_NODE_COMMAND: store pending downlink
    if (msgType == pgl::protocol::MSG_SERVER_NODE_COMMAND) {
        if (decoded.payloadLen >= 5 && decoded.payload != nullptr) {
            const uint16_t targetNodeId = (static_cast<uint16_t>(decoded.payload[0]) << 8) | decoded.payload[1];
            const uint16_t commandId    = (static_cast<uint16_t>(decoded.payload[2]) << 8) | decoded.payload[3];
            const uint8_t  commandLen   = decoded.payload[4];
            if (commandLen <= 8 && decoded.payloadLen >= static_cast<uint8_t>(5u + commandLen)) {
                PendingDownlink* dl = findOrAllocateDownlink(targetNodeId);
                if (dl != nullptr) {
                    dl->nodeId       = targetNodeId;
                    dl->commandId    = commandId;
                    dl->payloadLen   = commandLen;
                    dl->receivedAtMs = millis();
                    memcpy(dl->payload, decoded.payload + 5, commandLen);
                    dl->active = true;
                    logPrintf("CH_DOWNLINK_STORED nodeId=0x%04X commandId=%u payloadLen=%u\n",
                              targetNodeId, commandId, static_cast<unsigned>(commandLen));
                    if (isNodeExtPower(targetNodeId) && starReady && starRadio != nullptr) {
                        logPrintf("CH_DOWNLINK_EXT_POWER_IMMEDIATE nodeId=0x%04X\n", targetNodeId);
                        sendNodeDownlink(targetNodeId, dl);
                    }
                } else {
                    logPrintf("CH_DOWNLINK_STORE_FULL nodeId=0x%04X\n", targetNodeId);
                }
            }
        }
        startMeshReceive("after-node-cmd");
        return;
    }

    startMeshReceive("after-mesh-rx");
}

// ─── Boot header ─────────────────────────────────────────────────────────────

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina CH STAR+MESH runtime");
    logPrintf("Firmware name: %s\n",    pgl::firmware::CH_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::CH_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("CH_IDS ch=0x%04X rootGateway=0x%04X defaultParent=0x%04X\n",
              CH_ID, ROOT_GATEWAY_ID, DEFAULT_PARENT_ID);
}

// ─── State handlers ──────────────────────────────────────────────────────────

void handleWaitBatt() {
    batteryMv = readBatteryMv();
    logPrintf("CH_BATT_MV=%u stableCount=%u threshold=%u\n",
              batteryMv, battStableCount, BATT_START_MV);
    if (batteryMv >= BATT_START_MV) {
        battStableCount++;
        if (battStableCount >= 8) {
            runtimeConfig.chBatteryMv = batteryMv;
            setState(ChState::RADIO_INIT, "batt-stable");
        }
    } else {
        battStableCount = 0;
    }
    delay(1000);
}

void handleRadioInit() {
    releaseRadioReset();
    pgl::ch::clearNodeCache(nodeCache, NODE_CACHE_CAPACITY);
    pgl::ch::clearAlarmQueue(alarmQueue, ALARM_QUEUE_CAPACITY);
    pgl::ch::clearChTxQueue(txQueue, TX_QUEUE_CAPACITY);

    starReady = beginRadio(starRadio, starModule, STAR_PINS, "STAR",
                           STAR_FREQ_MHZ, STAR_BW_KHZ, STAR_SF, STAR_CR, STAR_SYNC_WORD);
    meshReady = beginRadio(meshRadio, meshModule, MESH_PINS, "MESH",
                           MESH_FREQ_MHZ, MESH_BW_KHZ, MESH_SF, MESH_CR, MESH_SYNC_WORD);
    logPrintf("CH_RUNTIME_READY star=%u mesh=%u\n", starReady ? 1 : 0, meshReady ? 1 : 0);

    if (!starReady || !meshReady) {
        setState(ChState::RECOVERY, "radio-init-failed");
        return;
    }

    starRadio->setPacketReceivedAction(onStarPacketReceived);
    meshRadio->setPacketReceivedAction(onMeshPacketReceived);
    startStarReceive("boot");
    startMeshReceive("boot");
    reportCache("boot");

    joiningCfgReqSent = false;
    lastCfgReqMs      = 0;
    clearParentCandidates();
    joiningStartMs    = millis();
    setState(ChState::JOINING, "radio-ready");
}

void handleJoining() {
    handleMeshPacketReceived();
    handleStarPacketReceived();

    if (!joiningCfgReqSent || millis() - lastCfgReqMs >= CFG_REQUEST_INTERVAL_MS) {
        sendConfigRequest();
        joiningCfgReqSent = true;
        lastCfgReqMs = millis();
    }

    if (millis() - joiningStartMs >= JOINING_TMO_MS) {
        if (!selectDiscoveredParents("joining")) {
            joiningStartMs = millis();
            joiningCfgReqSent = false;
            logPrintf("CH_JOINING_RETRY no-parent parentId=0x%04X\n", parentId);
            return;
        }
        joiningCfgReqSent = false;
        logPrintf("CH_JOINING_TMO proceed parentId=0x%04X\n", parentId);
        setState(ChState::JOINED, "joining-timeout");
        lastHelloMs = millis() - HELLO_INTERVAL_MS;
    }
}

void handleJoined() {
    handleStarPacketReceived();
    handleMeshPacketReceived();
    drainTxQueue();
    checkAlarmAckTimeout();

    const uint32_t now = millis();
    if (nextRouteVerifyDueMs == 0) {
        scheduleNextRouteVerify(now);
    }
    if (!routeVerifyActive && static_cast<int32_t>(now - nextRouteVerifyDueMs) >= 0) {
        routeVerifyActive = true;
        routeVerifyStartedMs = now;
        lastRouteVerifyMs = now;
        scheduleNextRouteVerify(now);
        lastCfgReqMs = now;
        clearParentCandidates();
        sendConfigRequest();
        logPrintf("CH_ROUTE_VERIFY_START parent=0x%04X alt=0x%04X lastParentSeenAgeMs=%lu nextDueInMs=%lu\n",
                  parentId,
                  parentAlt,
                  lastParentSeenMs == 0 ? 0UL : static_cast<unsigned long>(now - lastParentSeenMs),
                  static_cast<unsigned long>(nextRouteVerifyDueMs - now));
    }
    if (routeVerifyActive &&
        now - lastCfgReqMs >= CFG_REQUEST_INTERVAL_MS &&
        now - routeVerifyStartedMs < ROUTE_VERIFY_WINDOW_MS) {
        sendConfigRequest();
        lastCfgReqMs = now;
    }
    if (routeVerifyActive && now - routeVerifyStartedMs >= ROUTE_VERIFY_WINDOW_MS) {
        selectDiscoveredParents("background");
        routeVerifyActive = false;
        clearParentCandidates();
    }
    if (parentId != 0 && lastParentSeenMs != 0 && now - lastParentSeenMs >= PARENT_HEALTH_TIMEOUT_MS) {
        logPrintf("CH_PARENT_HEALTH_FAIL parent=0x%04X ageMs=%lu timeoutMs=%lu lastRssi=%d lastSnr=%d\n",
                  parentId,
                  static_cast<unsigned long>(now - lastParentSeenMs),
                  static_cast<unsigned long>(PARENT_HEALTH_TIMEOUT_MS),
                  lastParentRssiDbm,
                  lastParentSnrDb);
        setState(ChState::PARENT_FAILOVER, "parent-health-timeout");
        return;
    }

    if (now - lastHelloMs >= HELLO_INTERVAL_MS) {
        lastHelloMs = now;
        sendHello();
    }

    runHousekeeping();
    reportCachePeriodic();

    batteryMv                 = readBatteryMv();
    runtimeConfig.chBatteryMv = batteryMv;
    if (batteryMv < BATT_RUN_MIN_MV) {
        logPrintf("CH_BATT_LOW battMv=%u threshold=%u\n", batteryMv, BATT_RUN_MIN_MV);
        lowPowerEnteredMs = millis();
        setState(ChState::LOW_POWER, "batt-low");
    }

    delay(20);
}

void handleParentFailover() {
    handleMeshPacketReceived();

    if (failoverEnteredMs == 0) {
        failoverEnteredMs    = millis();
        joiningCfgReqSent    = false;
        lastCfgReqMs         = 0;
        clearParentCandidates();
    }
    if (!joiningCfgReqSent || millis() - lastCfgReqMs >= CFG_REQUEST_INTERVAL_MS) {
        sendConfigRequest();
        joiningCfgReqSent = true;
        lastCfgReqMs = millis();
    }

    if (millis() - failoverEnteredMs >= JOINING_TMO_MS) {
        if (!selectDiscoveredParents("failover")) {
            failoverEnteredMs = millis();
            joiningCfgReqSent = false;
            logPrintf("CH_FAILOVER_RETRY no-parent parentId=0x%04X\n", parentId);
            return;
        }
        failoverEnteredMs = 0;
        joiningCfgReqSent = false;
        logPrintf("CH_FAILOVER_TMO proceed parentId=0x%04X\n", parentId);
        setState(ChState::JOINED, "failover-timeout");
        lastHelloMs = millis() - HELLO_INTERVAL_MS;
    }
}

void handleLowPower() {
    handleStarPacketReceived();
    handleMeshPacketReceived();
    if (txAllowed()) drainTxQueue();

    batteryMv = readBatteryMv();
    logPrintf("CH_LOW_POWER battMv=%u critical=%u\n", batteryMv, BATT_CRITICAL_MV);

    if (batteryMv >= BATT_RUN_MIN_MV) {
        setState(ChState::JOINED, "batt-recovered");
        return;
    }
    if (batteryMv < BATT_CRITICAL_MV || millis() - lowPowerEnteredMs >= 300000UL) {
        setState(ChState::RECOVERY, "low-power-timeout");
    }
    delay(1000);
}

}  // namespace

// ─── Arduino entry points ────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
    delay(1000);

    esp_task_wdt_init(60, true);
    esp_task_wdt_add(NULL);
    logPrintln("CH_WDT_INIT ok");

    setupRadioPinsSafe();
    SPI.begin(pgl::ch::board::PIN_SPI_SCK,
              pgl::ch::board::PIN_SPI_MISO,
              pgl::ch::board::PIN_SPI_MOSI);

    printBootHeader();
    loadParents();
    updateRuntimeParent(parentId);

    setState(ChState::WAIT_BATT, "boot");
}

void loop() {
    esp_task_wdt_reset();

    switch (chState) {
        case ChState::BOOT:
            setState(ChState::WAIT_BATT, "boot");
            break;
        case ChState::WAIT_BATT:
            handleWaitBatt();
            break;
        case ChState::RADIO_INIT:
            handleRadioInit();
            break;
        case ChState::JOINING:
            handleJoining();
            break;
        case ChState::JOINED:
            handleJoined();
            break;
        case ChState::LOW_POWER:
            handleLowPower();
            break;
        case ChState::PARENT_FAILOVER:
            handleParentFailover();
            break;
        case ChState::RECOVERY:
            logPrintln("CH_RECOVERY_RESTART");
            delay(500);
            ESP.restart();
            break;
    }
}
