#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include <Preferences.h>
#include <esp_task_wdt.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "AlarmQueue.h"
#include "AppFrame.h"
#if defined(PGL_CH_BOARD_CH3)
#include "ChBoardPinsCh3.h"
#else
#include "ChBoardPins.h"
#endif
#include "ChCommandParser.h"
#include "ChRuntime.h"
#include "ChTxQueue.h"
#include "ChConfig.h"
#include "LoraStarConfig.h"
#include "LoraMeshConfig.h"
#include "FirmwareConfig.h"
#include "FirmwareVersion.h"
#include "NodeCache.h"
#include "ProtocolConstants.h"
#include "ServerNodeCommandRoute.h"

namespace {

// ─── Config constants ───────────────────────────────────────────────────────

// Runtime identity. The build-time value is only the factory/provisioning
// fallback; the operator app persists the actual CH ID in NVS.
static uint16_t CH_ID                = pgl::config::ch::CH_ID;
// Root gateway ID and STAR/MESH LoRa params are also only factory fallbacks;
// the operator app persists the actual values in NVS (see loadRootGateway(),
// loadStarLoraConfig(), loadMeshLoraConfig()).
static uint16_t ROOT_GATEWAY_ID      = pgl::config::ch::ROOT_GATEWAY_ID;
constexpr uint16_t DEFAULT_PARENT_ID = pgl::config::ch::DEFAULT_PARENT_ID;
constexpr uint16_t BROADCAST_ID      = 0xFFFF;

static float    STAR_FREQ_MHZ    = pgl::config::ch::STAR_FREQ_MHZ;
static float    STAR_BW_KHZ      = pgl::config::ch::STAR_BW_KHZ;
static uint8_t  STAR_SF          = pgl::config::ch::STAR_SF;
static uint8_t  STAR_CR          = pgl::config::ch::STAR_CR;
static uint8_t  STAR_SYNC_WORD   = pgl::config::ch::STAR_SYNC_WORD;
static int8_t   STAR_TX_POWER_DBM = pgl::config::ch::RADIO_TX_POWER_DBM;

static float    MESH_FREQ_MHZ    = pgl::config::ch::MESH_FREQ_MHZ;
static float    MESH_BW_KHZ      = pgl::config::ch::MESH_BW_KHZ;
static uint8_t  MESH_SF          = pgl::config::ch::MESH_SF;
static uint8_t  MESH_CR          = pgl::config::ch::MESH_CR;
static uint8_t  MESH_SYNC_WORD   = pgl::config::ch::MESH_SYNC_WORD;
static int8_t   MESH_TX_POWER_DBM = pgl::config::ch::RADIO_TX_POWER_DBM;

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
constexpr uint8_t  ALARM_RETRY_MAX         = pgl::config::ch::ALARM_RETRY_MAX;
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
#ifndef PGL_CH_EXTERNAL_WDT_KEEPALIVE_INTERVAL_MS
#define PGL_CH_EXTERNAL_WDT_KEEPALIVE_INTERVAL_MS 10000
#endif
#ifndef PGL_CH_EXTERNAL_WDT_KEEPALIVE_PULSE_MS
#define PGL_CH_EXTERNAL_WDT_KEEPALIVE_PULSE_MS 5
#endif
#ifndef PGL_CH_USE_RF_SWITCH
#define PGL_CH_USE_RF_SWITCH 1
#endif
#ifndef PGL_CH_USE_EXTERNAL_WDT_KEEPALIVE
#define PGL_CH_USE_EXTERNAL_WDT_KEEPALIVE 1
#endif
#ifndef PGL_CH_BOOT_SETTLE_MS
#define PGL_CH_BOOT_SETTLE_MS 0
#endif
#ifndef PGL_CH_USE_REFERENCE_RADIO_RESET
#define PGL_CH_USE_REFERENCE_RADIO_RESET 0
#endif
#ifndef PGL_CH_RADIO_INIT_RETRY_MS
#define PGL_CH_RADIO_INIT_RETRY_MS 0
#endif
constexpr uint32_t CH_EXTERNAL_WDT_KEEPALIVE_INTERVAL_MS = PGL_CH_EXTERNAL_WDT_KEEPALIVE_INTERVAL_MS;
constexpr uint32_t CH_EXTERNAL_WDT_KEEPALIVE_PULSE_MS = PGL_CH_EXTERNAL_WDT_KEEPALIVE_PULSE_MS;
constexpr bool USE_RF_SWITCH = PGL_CH_USE_RF_SWITCH != 0;
constexpr bool USE_EXTERNAL_WDT_KEEPALIVE = PGL_CH_USE_EXTERNAL_WDT_KEEPALIVE != 0;
constexpr bool USE_REFERENCE_RADIO_RESET = PGL_CH_USE_REFERENCE_RADIO_RESET != 0;
constexpr uint32_t CH_BOOT_SETTLE_MS = PGL_CH_BOOT_SETTLE_MS;
constexpr uint32_t RADIO_INIT_RETRY_MS = PGL_CH_RADIO_INIT_RETRY_MS;
constexpr uint32_t HELLO_JITTER_MS = pgl::config::ch::HELLO_JITTER_MS;
constexpr uint32_t HELLO_ACK_TMO_MS = pgl::config::ch::HELLO_ACK_TMO_MS;
constexpr uint8_t HELLO_RETRY_MAX = pgl::config::ch::HELLO_RETRY_MAX;
constexpr uint8_t HELLO_FAILURE_THRESHOLD = pgl::config::ch::HELLO_FAILURE_THRESHOLD;
constexpr uint32_t HELLO_REPROBE_MS = pgl::config::ch::HELLO_REPROBE_MS;
constexpr bool VBAT_READ_ONLY = pgl::config::ch::VBAT_READ_ONLY;
#ifndef PGL_CH_FIELD_TEST_BUILD
#define PGL_CH_FIELD_TEST_BUILD 0
#endif
constexpr bool FIELD_TEST_BUILD = PGL_CH_FIELD_TEST_BUILD != 0;

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

struct LoraConfigValues {
    float   freqMHz;
    float   bwKHz;
    uint8_t sf;
    uint8_t cr;
    uint8_t syncWord;
    int8_t  txPowerDbm;
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
    uint32_t ttlMs;
    uint8_t  payloadLen;
    uint8_t  payload[pgl::protocol::NODE_DOWNLINK_COMMAND_MAX_SIZE];
    bool     active;
    uint32_t receivedAtMs;
};
static PendingDownlink downlinkStore[DOWNLINK_STORE_CAPACITY]{};

static uint8_t  meshSeq           = 0;
static uint32_t lastCacheReportMs = 0;
static uint32_t lastBattReadonlyLogMs = 0;

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
static uint8_t  parentRouteFlags = 0;
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
    uint8_t  routeFlags;
    uint32_t seenAtMs;
    bool     hasReverseLink;
    bool     active;
};

static ParentCandidate parentCandidates[PARENT_CANDIDATE_CAPACITY]{};

// ─── Alarm ACK tracking ─────────────────────────────────────────────────────

enum class MeshAckKind : uint8_t {
    None,
    LocalAlarm,
    RelayAlarm,
    Hello,
};

struct MeshAckPending {
    MeshAckKind kind;
    uint16_t expectedParent;
    uint8_t  expectedParentFlags;
    uint16_t alarmNodeId;
    uint16_t helloToken;
    uint8_t  frameSeq;
    uint8_t  gldSeq;
    uint8_t  retryCount;
    uint32_t sentAtMs;
    uint8_t  frame[pgl::ch::CH_TX_FRAME_MAX];
    size_t   frameSize;
};
static MeshAckPending meshAck{};
static uint8_t helloAckFailureCount = 0;

// ─── Timing ─────────────────────────────────────────────────────────────────

static uint32_t nextHelloDueMs    = 0;
static uint32_t lastHousekeepMs   = 0;
static uint32_t lowPowerEnteredMs = 0;
static uint32_t joiningStartMs    = 0;
static uint32_t failoverEnteredMs = 0;
static bool     bootHelloPending = true;
static uint32_t lastBootHelloAttemptMs = 0;
static uint32_t lastExternalWdtKeepaliveMs = 0;
static uint8_t helloSeq = 0;
static bool     taskWdtReady = false;

// ─── Battery ────────────────────────────────────────────────────────────────

static uint16_t batteryMv       = 0xFFFF;
static uint8_t  battStableCount = 0;

// ─── Joining flag ───────────────────────────────────────────────────────────

static bool joiningCfgReqSent = false;

struct RecentHello {
    bool active;
    uint16_t origin;
    uint16_t token;
    uint8_t seq;
    uint32_t seenAtMs;
};
constexpr size_t RECENT_HELLO_CAPACITY = 8;
constexpr uint32_t RECENT_HELLO_TTL_MS = 60000;
static RecentHello recentHellos[RECENT_HELLO_CAPACITY]{};

void handleMeshAckParentChange(uint16_t oldParent, uint16_t newParent);
void clearMeshAckTransaction(const char* reason);

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

// Periodic TPL5010 DONE keepalive on GPIO47, independent from the ESP32 task WDT.
void setupExternalWdtKeepalivePin() {
    if (!USE_EXTERNAL_WDT_KEEPALIVE) {
        logPrintln("CH_TPL5010_DONE_SKIP reason=build-disabled");
        return;
    }
    pinMode(pgl::ch::board::PIN_WDT_KEEPALIVE, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_WDT_KEEPALIVE, LOW);
}

void pulseExternalWdtKeepaliveNow() {
    if (!USE_EXTERNAL_WDT_KEEPALIVE) return;
    digitalWrite(pgl::ch::board::PIN_WDT_KEEPALIVE, HIGH);
    delay(CH_EXTERNAL_WDT_KEEPALIVE_PULSE_MS);
    digitalWrite(pgl::ch::board::PIN_WDT_KEEPALIVE, LOW);
    lastExternalWdtKeepaliveMs = millis();
    logPrintf("CH_TPL5010_DONE_PULSE high_ms=%lu\n",
              static_cast<unsigned long>(CH_EXTERNAL_WDT_KEEPALIVE_PULSE_MS));
}

void maintainExternalWdtKeepalive() {
    if (!USE_EXTERNAL_WDT_KEEPALIVE) return;
    const uint32_t now = millis();
    if (now - lastExternalWdtKeepaliveMs >= CH_EXTERNAL_WDT_KEEPALIVE_INTERVAL_MS) {
        pulseExternalWdtKeepaliveNow();
    }
}

void resetTaskWdtIfReady() {
    if (taskWdtReady) {
        esp_task_wdt_reset();
    }
}

void serviceTick() {
    resetTaskWdtIfReady();
    maintainExternalWdtKeepalive();
}

void serviceDelay(uint32_t durationMs) {
    const uint32_t startedMs = millis();
    while (millis() - startedMs < durationMs) {
        serviceTick();
        const uint32_t elapsedMs = millis() - startedMs;
        const uint32_t remainingMs = durationMs > elapsedMs ? durationMs - elapsedMs : 0;
        delay(remainingMs > 50 ? 50 : remainingMs);
    }
    serviceTick();
}

// ─── State machine ──────────────────────────────────────────────────────────

void setState(ChState newState, const char* reason) {
    logPrintf("CH_STATE state=%s reason=%s\n", chStateName(newState), reason);
    chState = newState;
}

// ─── NVS (parent persistence) ───────────────────────────────────────────────

bool isAcceptedStoredChIdentity(uint16_t id) {
    return pgl::config::isValidNodeId(id) && id != ROOT_GATEWAY_ID;
}

bool isProvisionableChIdentity(uint16_t id) {
    return pgl::config::isProvisionableChId(id);
}

void loadChIdentity() {
    Preferences prefs;
    prefs.begin("ch-cfg", true);
    const uint16_t storedId = prefs.getUShort("chId", CH_ID);
    prefs.end();

    if (isAcceptedStoredChIdentity(storedId)) {
        CH_ID = storedId;
        logPrintf("CH_NVS_ID_LOAD chId=0x%04X\n", CH_ID);
    } else {
        logPrintf("CH_NVS_ID_INVALID stored=0x%04X fallback=0x%04X\n",
                  storedId, CH_ID);
    }
    runtimeConfig.chId = CH_ID;
}

bool saveChIdentity(uint16_t newId) {
    if (!isProvisionableChIdentity(newId)) return false;

    Preferences prefs;
    if (!prefs.begin("ch-cfg", false)) return false;
    const size_t written = prefs.putUShort("chId", newId);
    // Parent discovery belongs to the old identity and must not survive an ID
    // change. A fresh boot will rediscover the route safely.
    prefs.remove("parentId");
    prefs.remove("parentAlt");
    prefs.end();
    if (written != sizeof(uint16_t)) return false;

    Preferences verify;
    if (!verify.begin("ch-cfg", true)) return false;
    const uint16_t readBack = verify.getUShort("chId", 0);
    verify.end();
    if (readBack != newId) return false;

    return true;
}

bool isAcceptedStoredGatewayId(uint16_t id) {
    return pgl::config::isValidNodeId(id) && id != CH_ID;
}

bool isProvisionableGatewayId(uint16_t id) {
    return pgl::config::isProvisionableGatewayId(id);
}

void loadRootGateway() {
    Preferences prefs;
    prefs.begin("ch-cfg", true);
    const uint16_t stored = prefs.getUShort("rootGw", ROOT_GATEWAY_ID);
    prefs.end();

    if (isAcceptedStoredGatewayId(stored)) {
        ROOT_GATEWAY_ID = stored;
        logPrintf("CH_NVS_ROOTGW_LOAD rootGw=0x%04X\n", ROOT_GATEWAY_ID);
    } else {
        logPrintf("CH_NVS_ROOTGW_INVALID stored=0x%04X fallback=0x%04X\n",
                  stored, ROOT_GATEWAY_ID);
    }
}

bool saveRootGateway(uint16_t newId) {
    if (!isProvisionableGatewayId(newId)) return false;

    Preferences prefs;
    if (!prefs.begin("ch-cfg", false)) return false;
    const size_t written = prefs.putUShort("rootGw", newId);
    prefs.end();
    if (written != sizeof(uint16_t)) return false;

    Preferences verify;
    if (!verify.begin("ch-cfg", true)) return false;
    const uint16_t readBack = verify.getUShort("rootGw", 0);
    verify.end();
    if (readBack != newId) return false;

    return true;
}

bool isValidLoraConfig(const LoraConfigValues& cfg) {
    return cfg.freqMHz >= 900.0f && cfg.freqMHz <= 930.0f &&
           cfg.bwKHz >= 1.0f && cfg.bwKHz <= 510.0f &&
           cfg.sf >= 5 && cfg.sf <= 12 &&
           cfg.cr >= 5 && cfg.cr <= 8 &&
           cfg.txPowerDbm >= -9 && cfg.txPowerDbm <= 22;
}

void loadLoraConfig(const char* keyPrefix, LoraConfigValues& cfg) {
    char keyFreq[16], keyBw[16], keySf[16], keyCr[16], keySync[16], keyTx[16];
    snprintf(keyFreq, sizeof(keyFreq), "%sFreq", keyPrefix);
    snprintf(keyBw,   sizeof(keyBw),   "%sBw",   keyPrefix);
    snprintf(keySf,   sizeof(keySf),   "%sSf",   keyPrefix);
    snprintf(keyCr,   sizeof(keyCr),   "%sCr",   keyPrefix);
    snprintf(keySync, sizeof(keySync), "%sSync", keyPrefix);
    snprintf(keyTx,   sizeof(keyTx),   "%sTx",   keyPrefix);

    Preferences prefs;
    prefs.begin("ch-cfg", true);
    LoraConfigValues stored{
        prefs.getFloat(keyFreq, cfg.freqMHz),
        prefs.getFloat(keyBw, cfg.bwKHz),
        prefs.getUChar(keySf, cfg.sf),
        prefs.getUChar(keyCr, cfg.cr),
        prefs.getUChar(keySync, cfg.syncWord),
        static_cast<int8_t>(prefs.getChar(keyTx, cfg.txPowerDbm)),
    };
    prefs.end();

    // Sanity-check before trusting stored values, guarding against a corrupt
    // or never-written NVS blob.
    if (isValidLoraConfig(stored)) {
        cfg = stored;
        logPrintf("CH_NVS_%s_LORA_LOAD freq=%.3f bw=%.2f sf=%u cr=%u sync=0x%02X tx=%d\n",
                  keyPrefix, cfg.freqMHz, cfg.bwKHz, cfg.sf, cfg.cr, cfg.syncWord, cfg.txPowerDbm);
    } else {
        logPrintf("CH_NVS_%s_LORA_INVALID fallback-to-build-time\n", keyPrefix);
    }
}

bool saveLoraConfig(const char* keyPrefix, const LoraConfigValues& cfg) {
    if (!isValidLoraConfig(cfg)) return false;

    char keyFreq[16], keyBw[16], keySf[16], keyCr[16], keySync[16], keyTx[16];
    snprintf(keyFreq, sizeof(keyFreq), "%sFreq", keyPrefix);
    snprintf(keyBw,   sizeof(keyBw),   "%sBw",   keyPrefix);
    snprintf(keySf,   sizeof(keySf),   "%sSf",   keyPrefix);
    snprintf(keyCr,   sizeof(keyCr),   "%sCr",   keyPrefix);
    snprintf(keySync, sizeof(keySync), "%sSync", keyPrefix);
    snprintf(keyTx,   sizeof(keyTx),   "%sTx",   keyPrefix);

    Preferences prefs;
    if (!prefs.begin("ch-cfg", false)) return false;
    bool ok = true;
    ok = ok && prefs.putFloat(keyFreq, cfg.freqMHz) == sizeof(float);
    ok = ok && prefs.putFloat(keyBw, cfg.bwKHz) == sizeof(float);
    ok = ok && prefs.putUChar(keySf, cfg.sf) == sizeof(uint8_t);
    ok = ok && prefs.putUChar(keyCr, cfg.cr) == sizeof(uint8_t);
    ok = ok && prefs.putUChar(keySync, cfg.syncWord) == sizeof(uint8_t);
    ok = ok && prefs.putChar(keyTx, cfg.txPowerDbm) == sizeof(int8_t);
    prefs.end();
    if (!ok) return false;

    Preferences verify;
    if (!verify.begin("ch-cfg", true)) return false;
    const bool match =
        verify.getFloat(keyFreq, -1.0f) == cfg.freqMHz &&
        verify.getFloat(keyBw, -1.0f) == cfg.bwKHz &&
        verify.getUChar(keySf, 0) == cfg.sf &&
        verify.getUChar(keyCr, 0) == cfg.cr &&
        verify.getUChar(keySync, 0) == cfg.syncWord &&
        verify.getChar(keyTx, 0) == cfg.txPowerDbm;
    verify.end();
    return match;
}

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

void updateRuntimeParent(uint16_t newId, uint8_t newRouteFlags = 0) {
    const uint16_t oldId = parentId;
    const bool changed = (parentId != newId);
    parentId                = newId;
    runtimeConfig.meshDstId = newId;
    meshDepth = (newId == ROOT_GATEWAY_ID) ? 1 : 0xFF;
    if (changed) {
        lastParentChangedMs = millis();
        parentRouteFlags = newRouteFlags;
        helloAckFailureCount = 0;
        parentFailCnt = 0;
        noAckBurst = 0;
        lastParentSeenMs = 0;
        lastParentRssiDbm = -32768;
        lastParentSnrDb = -128;
        bootHelloPending = newId != 0;
        nextHelloDueMs = millis();
        handleMeshAckParentChange(oldId, newId);
    } else {
        parentRouteFlags = newRouteFlags;
        if ((meshAck.kind == MeshAckKind::LocalAlarm || meshAck.kind == MeshAckKind::RelayAlarm) &&
            meshAck.expectedParent == newId) {
            meshAck.expectedParentFlags = newRouteFlags;
        }
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
                           uint8_t routeFlags, bool hasReverseLink = false,
                           int16_t reverseRssiDbm = 0, int8_t reverseSnrDb = 0) {
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
    slot->routeFlags = routeFlags;
    slot->seenAtMs = millis();
    slot->active = true;
    if (id == parentId) {
        parentRouteFlags = routeFlags;
        if (meshAck.kind == MeshAckKind::Hello && meshAck.expectedParent == id &&
            (routeFlags & pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1) == 0) {
            clearMeshAckTransaction("parent-capability-downgrade");
            nextHelloDueMs = millis() + HELLO_INTERVAL_MS;
        }
        if ((meshAck.kind == MeshAckKind::LocalAlarm || meshAck.kind == MeshAckKind::RelayAlarm) &&
            meshAck.expectedParent == id) {
            meshAck.expectedParentFlags = routeFlags;
        }
        lastParentSeenMs = slot->seenAtMs;
        lastParentRssiDbm = rssiDbm;
        lastParentSnrDb = snrDb;
    }
    logPrintf("CH_PARENT_CANDIDATE id=0x%04X parent=0x%04X depth=%u caps=0x%02X rssi=%d snr=%d reverse=%u reverseRssi=%d reverseSnr=%d battMv=%u\n",
              id,
              advertisedParent,
              depth,
              routeFlags,
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

    updateRuntimeParent(best->id, best->routeFlags);
    parentAlt = selectedAlt;
    meshDepth = (best->id == ROOT_GATEWAY_ID) ? 1 : static_cast<uint8_t>(best->depth + 1);
    lastParentSeenMs = millis();
    lastParentRssiDbm = best->rssiDbm;
    lastParentSnrDb = best->snrDb;
    nextHelloDueMs = millis();
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
    if (VBAT_READ_ONLY) return true;
    return batteryMv == 0xFFFF || batteryMv >= BATT_CRITICAL_MV;
}

// ─── Radio pin setup ────────────────────────────────────────────────────────

void setupRadioPinsSafe() {
    pinMode(pgl::ch::board::PIN_RADIO_A_CS,   OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_CS,   HIGH);
    pinMode(pgl::ch::board::PIN_RADIO_B_CS,   OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_CS,   HIGH);
    pinMode(pgl::ch::board::PIN_RADIO_A_RST, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, USE_REFERENCE_RADIO_RESET ? HIGH : LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_RST, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, USE_REFERENCE_RADIO_RESET ? HIGH : LOW);
    if (USE_RF_SWITCH) {
        pinMode(pgl::ch::board::PIN_RADIO_A_RXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_RXEN, LOW);
        pinMode(pgl::ch::board::PIN_RADIO_A_TXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_A_TXEN, LOW);
        pinMode(pgl::ch::board::PIN_RADIO_B_RXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_RXEN, LOW);
        pinMode(pgl::ch::board::PIN_RADIO_B_TXEN, OUTPUT); digitalWrite(pgl::ch::board::PIN_RADIO_B_TXEN, LOW);
    } else {
        logPrintln("CH_RF_SWITCH_SKIP reason=build-disabled");
    }
}

void releaseRadioReset() {
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, LOW);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, LOW);
    serviceDelay(USE_REFERENCE_RADIO_RESET ? 20 : 50);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, HIGH);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, HIGH);
    serviceDelay(USE_REFERENCE_RADIO_RESET ? 50 : 500);
    if (USE_REFERENCE_RADIO_RESET) logPrintln("CH_RADIO_RESET_STYLE reference");
}

bool beginRadio(SX1262*& radio, Module*& module, const RadioPins& pins,
                const char* name, float freq, float bw, uint8_t sf, uint8_t cr, uint8_t sync,
                int8_t txPower) {
    if (module == nullptr) {
        module = new Module(pins.cs, pins.dio1, pins.rst, pins.busy,
                            SPI, SPISettings(RADIO_SPI_HZ, MSBFIRST, SPI_MODE0));
    }
    if (radio == nullptr) {
        radio = new SX1262(module);
    }
    // EBYTE E22-900MM22S uses its own 32 MHz crystal.  Keep the TCXO path
    // only as a diagnostic fallback for a different fitted module.
    int16_t st = radio->begin(freq, bw, sf, cr, sync, txPower,
                               RADIO_PREAMBLE, RADIO_XTAL_TCXO_VOLTAGE, false);
    logPrintf("CH_%s_BEGIN_XTAL_STATE=%d\n", name, st);
    if (st == RADIOLIB_ERR_SPI_CMD_INVALID || st == RADIOLIB_ERR_SPI_CMD_FAILED) {
        st = radio->begin(freq, bw, sf, cr, sync, txPower,
                          RADIO_PREAMBLE, RADIO_TCXO_VOLTAGE, false);
        logPrintf("CH_%s_BEGIN_TCXO16_STATE=%d\n", name, st);
    }
    logPrintf("CH_%s_BEGIN_STATE=%d\n", name, st);
    if (st != RADIOLIB_ERR_NONE) return false;
    if (USE_RF_SWITCH) {
        radio->setRfSwitchPins(pins.rxen, pins.txen);
    } else {
        logPrintf("CH_%s_RF_SWITCH_SKIP reason=build-disabled\n", name);
    }
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
    // DIO1 signals both RxDone and TxDone.  Do not leave the receive callback
    // armed through a blocking transmit, otherwise TxDone is consumed as a
    // phantom zero-length receive.
    radio->clearPacketReceivedAction();
    serviceTick();
    const int16_t st = radio->transmit(frame, frameSize);
    if (USE_RF_SWITCH) {
        digitalWrite(pins.rxen, LOW);
        digitalWrite(pins.txen, LOW);
    }
    if (radio == starRadio) {
        radio->setPacketReceivedAction(onStarPacketReceived);
        startStarReceive("after-tx");
    } else if (radio == meshRadio) {
        radio->setPacketReceivedAction(onMeshPacketReceived);
        startMeshReceive("after-tx");
    }
    serviceTick();
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
    const uint8_t downlinkSeq = static_cast<uint8_t>(dl->commandId & 0x00FF);
    uint8_t downlinkFrame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_NODE_DOWNLINK, CH_ID, targetNodeId, downlinkSeq,
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

bool meshAckBusy() {
    return meshAck.kind != MeshAckKind::None;
}

const char* meshAckKindName(MeshAckKind kind) {
    switch (kind) {
        case MeshAckKind::None:       return "none";
        case MeshAckKind::LocalAlarm: return "local-alarm";
        case MeshAckKind::RelayAlarm: return "relay-alarm";
        case MeshAckKind::Hello:      return "hello";
    }
    return "unknown";
}

void clearMeshAckTransaction(const char* reason) {
    if (meshAckBusy()) {
        logPrintf("CH_MESH_ACK_CLEAR reason=%s kind=%s parent=0x%04X frameSeq=%u retry=%u\n",
                  reason, meshAckKindName(meshAck.kind), meshAck.expectedParent,
                  meshAck.frameSeq, meshAck.retryCount);
    }
    meshAck = MeshAckPending{};
}

bool retargetPendingAlarm(uint16_t newParent) {
    if ((meshAck.kind != MeshAckKind::LocalAlarm && meshAck.kind != MeshAckKind::RelayAlarm) ||
        newParent == 0 || meshAck.frameSize == 0) {
        return false;
    }

    pgl::protocol::FrameView decoded{};
    if (pgl::protocol::decodeAppFrame(meshAck.frame, meshAck.frameSize, decoded,
                                      pgl::protocol::MESH_MAX_PAYLOAD) != pgl::protocol::FrameStatus::Ok) {
        return false;
    }
    uint8_t retargeted[pgl::ch::CH_TX_FRAME_MAX]{};
    const auto enc = pgl::protocol::encodeAppFrame(
        decoded.typeFlags, CH_ID, newParent, decoded.seq,
        decoded.payload, decoded.payloadLen,
        retargeted, sizeof(retargeted), pgl::protocol::MESH_MAX_PAYLOAD);
    if (enc.status != pgl::protocol::FrameStatus::Ok) return false;

    memcpy(meshAck.frame, retargeted, enc.size);
    meshAck.frameSize = enc.size;
    meshAck.expectedParent = newParent;
    meshAck.expectedParentFlags = parentRouteFlags;
    meshAck.retryCount = 0;
    meshAck.sentAtMs = millis() - ALARM_ACK_TMO_MS;
    return true;
}

void handleMeshAckParentChange(uint16_t oldParent, uint16_t newParent) {
    if (meshAck.kind == MeshAckKind::Hello) {
        clearMeshAckTransaction("parent-changed");
        return;
    }
    if (meshAck.kind != MeshAckKind::LocalAlarm && meshAck.kind != MeshAckKind::RelayAlarm) return;

    meshAck.expectedParent = 0;
    meshAck.expectedParentFlags = 0;
    if (newParent != 0 && retargetPendingAlarm(newParent)) {
        logPrintf("CH_ALARM_ACK_RETARGET kind=%s oldParent=0x%04X newParent=0x%04X nodeId=0x%04X frameSeq=%u\n",
                  meshAckKindName(meshAck.kind), oldParent, newParent,
                  meshAck.alarmNodeId, meshAck.frameSeq);
    } else {
        logPrintf("CH_ALARM_ACK_DEFER kind=%s oldParent=0x%04X newParent=0x%04X nodeId=0x%04X frameSeq=%u\n",
                  meshAckKindName(meshAck.kind), oldParent, newParent,
                  meshAck.alarmNodeId, meshAck.frameSeq);
    }
}

void startMeshAckTransaction(MeshAckKind kind, uint16_t expectedParent,
                             uint16_t alarmNodeId, uint8_t gldSeq,
                             uint16_t helloToken, const uint8_t* frame,
                             size_t frameSize) {
    if (frame == nullptr || frameSize == 0 || frameSize > sizeof(meshAck.frame)) return;
    meshAck = MeshAckPending{};
    meshAck.kind = kind;
    meshAck.expectedParent = expectedParent;
    meshAck.expectedParentFlags = parentRouteFlags;
    meshAck.alarmNodeId = alarmNodeId;
    meshAck.helloToken = helloToken;
    meshAck.frameSeq = frame[6];
    meshAck.gldSeq = gldSeq;
    meshAck.sentAtMs = millis();
    meshAck.frameSize = frameSize;
    memcpy(meshAck.frame, frame, frameSize);
    logPrintf("CH_MESH_ACK_START kind=%s parent=0x%04X frameSeq=%u nodeId=0x%04X gldSeq=%u caps=0x%02X\n",
              meshAckKindName(kind), expectedParent, meshAck.frameSeq,
              alarmNodeId, gldSeq, meshAck.expectedParentFlags);
}

bool onAlarmAckFromParent(const pgl::protocol::FrameView& decoded) {
    const bool alarmPending = meshAck.kind == MeshAckKind::LocalAlarm ||
                              meshAck.kind == MeshAckKind::RelayAlarm;
    const bool tupleMatches = alarmPending &&
                              decoded.typeFlags == pgl::protocol::TYPE_ALARM_ACK_COMPACT &&
                              decoded.srcId == meshAck.expectedParent &&
                              decoded.dstId == CH_ID &&
                              decoded.seq == meshAck.frameSeq;
    const bool nodeIdV1 = (meshAck.expectedParentFlags &
                           pgl::protocol::CH_CONFIG_CAP_ALARM_ACK_NODE_ID_V1) != 0;
    const bool payloadMatches = nodeIdV1
        ? decoded.payload != nullptr &&
              decoded.payloadLen == pgl::protocol::MESH_ALARM_ACK_V1_PAYLOAD_SIZE &&
              readU16Be(decoded.payload) == meshAck.alarmNodeId
        : decoded.payloadLen == 0;
    if (!tupleMatches || !payloadMatches) {
        logPrintf("CH_ALARM_ACK_IGNORE src=0x%04X dst=0x%04X seq=%u len=%u pending=%s waitParent=0x%04X waitSeq=%u nodeV1=%u\n",
                  decoded.srcId, decoded.dstId, decoded.seq, decoded.payloadLen,
                  meshAckKindName(meshAck.kind), meshAck.expectedParent,
                  meshAck.frameSeq, nodeIdV1 ? 1 : 0);
        return false;
    }

    const MeshAckKind completedKind = meshAck.kind;
    const uint16_t completedNodeId = meshAck.alarmNodeId;
    const uint8_t completedGldSeq = meshAck.gldSeq;
    const uint8_t completedRetries = meshAck.retryCount;
    if (completedKind == MeshAckKind::LocalAlarm) {
        pgl::ch::markAlarmAcked(completedNodeId, completedGldSeq,
                                alarmQueue, ALARM_QUEUE_CAPACITY);
    }
    logPrintf("CH_ALARM_ACK_RECV kind=%s nodeId=0x%04X frameSeq=%u gldSeq=%u retries=%u\n",
              meshAckKindName(completedKind), completedNodeId, decoded.seq,
              completedGldSeq, completedRetries);
    clearMeshAckTransaction("alarm-ack-recv");
    parentFailCnt = 0;
    noAckBurst = 0;
    return true;
}

void checkFailover() {
    const bool retainedAlarm = meshAck.kind == MeshAckKind::LocalAlarm ||
                               meshAck.kind == MeshAckKind::RelayAlarm;
    if (noAckBurst >= NO_ACK_RECOVERY_TH && !retainedAlarm) {
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
    if (meshAck.kind != MeshAckKind::LocalAlarm && meshAck.kind != MeshAckKind::RelayAlarm) return;
    if (meshAck.expectedParent == 0 && parentId != 0) {
        retargetPendingAlarm(parentId);
    }
    if (meshAck.expectedParent == 0 || millis() - meshAck.sentAtMs < ALARM_ACK_TMO_MS) return;

    if (meshAck.retryCount < ALARM_RETRY_MAX) {
        const uint8_t nextRetry = static_cast<uint8_t>(meshAck.retryCount + 1);
        const bool canRetry = meshReady && meshRadio != nullptr && txAllowed() &&
                              meshAck.frameSize > 0 && meshAck.frameSize <= sizeof(meshAck.frame) &&
                              meshAck.expectedParent == parentId;
        bool txOk = false;
        if (canRetry) {
            txOk = transmitRadio(meshRadio, MESH_PINS, meshAck.frame, meshAck.frameSize, "MESH_ALARM_RETRY");
            startMeshReceive("after-alarm-retry");
        }
        meshAck.retryCount = nextRetry;
        meshAck.sentAtMs = millis();
        logPrintf("CH_ALARM_ACK_RETRY kind=%s nodeId=0x%04X frameSeq=%u gldSeq=%u retry=%u max=%u txOk=%u canRetry=%u\n",
                  meshAckKindName(meshAck.kind), meshAck.alarmNodeId,
                  meshAck.frameSeq, meshAck.gldSeq, nextRetry, ALARM_RETRY_MAX,
                  txOk ? 1 : 0, canRetry ? 1 : 0);
        return;
    }

    logPrintf("CH_ALARM_ACK_GIVEUP kind=%s nodeId=0x%04X frameSeq=%u gldSeq=%u retries=%u max=%u retained=1\n",
              meshAckKindName(meshAck.kind), meshAck.alarmNodeId,
              meshAck.frameSeq, meshAck.gldSeq, meshAck.retryCount, ALARM_RETRY_MAX);
    // Never acknowledge or discard an alarm locally on timeout. The retained
    // frame is retried and retargeted by updateRuntimeParent() after failover.
    meshAck.retryCount = 0;
    meshAck.sentAtMs = millis();
    parentFailCnt++;
    noAckBurst++;
    checkFailover();
}

// ─── Drain TX queue ─────────────────────────────────────────────────────────

void drainTxQueue() {
    if (!meshReady || meshRadio == nullptr) return;
    if (meshAckBusy()) return;

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
        const bool alarmFrame = txSize >= pgl::protocol::APPFRAME_OVERHEAD +
                                             pgl::protocol::GLD_RECORD_HEADER_SIZE &&
                                pgl::protocol::messageType(frameCopy[1]) == pgl::protocol::MSG_SENSOR_DATA &&
                                pgl::protocol::hasAlarmAckFlag(frameCopy[1]) &&
                                frameCopy[7] >= pgl::protocol::GLD_RECORD_HEADER_SIZE;
        const bool relayAlarm = item->kind == pgl::ch::ChTxKind::RelayFrame && alarmFrame;

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

        if (isAlarmPush || relayAlarm) {
            const uint16_t ackNodeId = isAlarmPush
                ? txNodeId
                : readU16Be(&frameCopy[pgl::protocol::APPFRAME_HEADER_SIZE]);
            const uint8_t ackGldSeq = isAlarmPush
                ? txSeq
                : frameCopy[pgl::protocol::APPFRAME_HEADER_SIZE + 2];
            startMeshAckTransaction(
                isAlarmPush ? MeshAckKind::LocalAlarm : MeshAckKind::RelayAlarm,
                readU16Be(&frameCopy[4]), ackNodeId, ackGldSeq, 0,
                frameCopy, txSize);
            break;
        }
    }
    if (txAttempted) startMeshReceive("after-drain");
}

// ─── MESH management messages ───────────────────────────────────────────────

uint32_t helloIntervalMs() {
    const uint32_t jitter = HELLO_JITTER_MS == 0
        ? 0
        : (static_cast<uint32_t>(CH_ID) * 997UL) % HELLO_JITTER_MS;
    return HELLO_INTERVAL_MS + jitter;
}

bool helloRequestsAckFrom(const pgl::protocol::FrameView& decoded, uint16_t receiverId) {
    return decoded.payload != nullptr &&
           decoded.payloadLen >= pgl::protocol::CH_HELLO_V1_PAYLOAD_SIZE &&
           decoded.srcId != receiverId &&
           readU16Be(&decoded.payload[0]) == decoded.srcId &&
           readU16Be(&decoded.payload[2]) == receiverId &&
           (decoded.payload[11] & pgl::protocol::CH_HELLO_FLAG_ACK_REQUEST_V1) != 0;
}

bool recentHelloDuplicate(const pgl::protocol::FrameView& decoded) {
    if (decoded.payload == nullptr || decoded.payloadLen < 8) return false;
    const uint16_t origin = readU16Be(&decoded.payload[0]);
    const uint16_t token = readU16Be(&decoded.payload[6]);
    const uint32_t now = millis();
    for (auto& item : recentHellos) {
        if (item.active && now - item.seenAtMs > RECENT_HELLO_TTL_MS) item.active = false;
        if (item.active && item.origin == origin && item.seq == decoded.seq && item.token == token) {
            item.seenAtMs = now;
            return true;
        }
    }
    return false;
}

void rememberHello(const pgl::protocol::FrameView& decoded) {
    if (decoded.payload == nullptr || decoded.payloadLen < 8) return;
    RecentHello* slot = nullptr;
    for (auto& item : recentHellos) {
        if (!item.active) {
            slot = &item;
            break;
        }
        if (slot == nullptr || item.seenAtMs < slot->seenAtMs) slot = &item;
    }
    if (slot == nullptr) return;
    slot->active = true;
    slot->origin = readU16Be(&decoded.payload[0]);
    slot->token = readU16Be(&decoded.payload[6]);
    slot->seq = decoded.seq;
    slot->seenAtMs = millis();
}

bool sendHelloAck(const pgl::protocol::FrameView& hello, const char* reason) {
    if (!meshReady || meshRadio == nullptr || !helloRequestsAckFrom(hello, CH_ID)) return false;
    uint8_t payload[pgl::protocol::CH_HELLO_ACK_V1_PAYLOAD_SIZE]{};
    payload[0] = hello.payload[0];
    payload[1] = hello.payload[1];
    payload[2] = hello.payload[6];
    payload[3] = hello.payload[7];
    uint8_t ack[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::CH_HELLO_ACK_V1_PAYLOAD_SIZE]{};
    const auto enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_HELLO_ACK, CH_ID, hello.srcId, hello.seq,
        payload, sizeof(payload), ack, sizeof(ack), pgl::protocol::MESH_MAX_PAYLOAD);
    if (enc.status != pgl::protocol::FrameStatus::Ok) return false;
    const bool txOk = transmitRadio(meshRadio, MESH_PINS, ack, enc.size, "MESH_HELLO_ACK");
    startMeshReceive("after-hello-ack-tx");
    logPrintf("CH_HELLO_ACK_TX reason=%s dst=0x%04X seq=%u txOk=%u\n",
              reason, hello.srcId, hello.seq, txOk ? 1 : 0);
    return txOk;
}

bool sendHello() {
    if (!meshReady || meshRadio == nullptr || !txAllowed() || parentId == 0 || meshAckBusy()) return false;
    const uint32_t uptimeSec = millis() / 1000UL;
    const uint8_t seq = helloSeq++;
    const bool ackRequested = (parentRouteFlags & pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1) != 0;
    uint8_t payload[pgl::protocol::CH_HELLO_V1_PAYLOAD_SIZE]{};
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
    payload[11] = ackRequested ? pgl::protocol::CH_HELLO_FLAG_ACK_REQUEST_V1 : 0;
    const uint8_t payloadLen = ackRequested
        ? static_cast<uint8_t>(pgl::protocol::CH_HELLO_V1_PAYLOAD_SIZE)
        : static_cast<uint8_t>(pgl::protocol::CH_HELLO_LEGACY_PAYLOAD_SIZE);
    uint8_t frame[pgl::ch::CH_TX_FRAME_MAX]{};
    const pgl::protocol::FrameEncodeResult enc = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CH_HELLO, CH_ID, parentId, seq,
        payload, payloadLen, frame, sizeof(frame), pgl::protocol::MESH_MAX_PAYLOAD);
    if (enc.status != pgl::protocol::FrameStatus::Ok) return false;
    const bool txOk = transmitRadio(meshRadio, MESH_PINS, frame, enc.size, "MESH_HELLO");
    startMeshReceive("after-hello");
    if (txOk && ackRequested) {
        startMeshAckTransaction(MeshAckKind::Hello, parentId, 0, 0,
                                static_cast<uint16_t>(uptimeSec), frame, enc.size);
    }
    logPrintf("CH_HELLO_TX parentId=0x%04X parentAlt=0x%04X seq=%u battMv=%u uptimeSec=%lu depth=%u caps=0x%02X ackWait=%u txOk=%u\n",
              parentId, parentAlt, seq, batteryMv, static_cast<unsigned long>(uptimeSec), meshDepth,
              parentRouteFlags, ackRequested && txOk ? 1 : 0, txOk ? 1 : 0);
    return txOk;
}

void retryHelloIfNeeded() {
    if (meshAck.kind != MeshAckKind::Hello || millis() - meshAck.sentAtMs < HELLO_ACK_TMO_MS) return;
    if (meshAck.retryCount >= HELLO_RETRY_MAX) {
        const uint16_t failedParent = meshAck.expectedParent;
        const uint8_t failedSeq = meshAck.frameSeq;
        const uint8_t failedRetries = meshAck.retryCount;
        if (helloAckFailureCount < 0xFF) helloAckFailureCount++;
        logPrintf("CH_HELLO_ACK_FAIL parent=0x%04X seq=%u retries=%u timeoutMs=%lu\n",
                  failedParent, failedSeq, failedRetries,
                  static_cast<unsigned long>(HELLO_ACK_TMO_MS));
        clearMeshAckTransaction("hello-retry-exhausted");
        if (helloAckFailureCount >= HELLO_FAILURE_THRESHOLD) {
            setState(ChState::PARENT_FAILOVER, "hello-ACK-failures");
        } else {
            nextHelloDueMs = millis() + HELLO_REPROBE_MS;
            logPrintf("CH_HELLO_ACK_REPROBE failure=%u threshold=%u dueInMs=%lu\n",
                      helloAckFailureCount, HELLO_FAILURE_THRESHOLD,
                      static_cast<unsigned long>(HELLO_REPROBE_MS));
        }
        return;
    }
    meshAck.retryCount++;
    meshAck.sentAtMs = millis();
    const bool txOk = transmitRadio(meshRadio, MESH_PINS, meshAck.frame, meshAck.frameSize, "MESH_HELLO_RETRY");
    startMeshReceive("after-hello-retry");
    logPrintf("CH_HELLO_ACK_RETRY parent=0x%04X seq=%u retry=%u/%u txOk=%u\n",
              meshAck.expectedParent, meshAck.frameSeq, meshAck.retryCount, HELLO_RETRY_MAX, txOk ? 1 : 0);
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
    serviceDelay(20 + ((CH_ID & 0x000F) * 30) + (millis() % 40));
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
    payload[7] = pgl::protocol::CH_CONFIG_FLAG_ROUTE_TO_ROOT |
                 pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1 |
                 pgl::protocol::CH_CONFIG_CAP_ALARM_ACK_NODE_ID_V1 |
                 pgl::protocol::CH_CONFIG_CAP_NODE_COMMAND_ROUTE_V1;

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
    serviceDelay(responseDelayMs);
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
        const uint32_t ttlMs = dl.ttlMs > 0 ? dl.ttlMs : PENDING_TTL_MS;
        if (dl.active && (now - dl.receivedAtMs) >= ttlMs) {
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

    if (status != pgl::ch::ChRuntimeStatus::Ok) {
        const uint16_t srcId = packetLen >= 4
                                   ? (static_cast<uint16_t>(frame[2]) << 8) | frame[3]
                                   : 0;
        const uint16_t dstId = packetLen >= 6
                                   ? (static_cast<uint16_t>(frame[4]) << 8) | frame[5]
                                   : 0;
        logPrintf("CH_STAR_REJECT status=%s src=0x%04X dst=0x%04X local=0x%04X\n",
                  pgl::ch::chRuntimeStatusName(status), srcId, dstId, CH_ID);
        startStarReceive("after-star-reject");
        return;
    }

    reportCache("star-rx");

    if (result.ackBuilt && meshAck.kind == MeshAckKind::Hello) {
        clearMeshAckTransaction("alarm-preempts-hello");
        nextHelloDueMs = millis() + HELLO_REPROBE_MS;
    }

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

    if (msgType == pgl::protocol::MSG_CH_HELLO_ACK) {
        const bool matches = meshAck.kind == MeshAckKind::Hello &&
                             decoded.typeFlags == pgl::protocol::MSG_CH_HELLO_ACK &&
                             decoded.srcId == meshAck.expectedParent &&
                             decoded.dstId == CH_ID &&
                             decoded.seq == meshAck.frameSeq &&
                             decoded.payload != nullptr &&
                             decoded.payloadLen == pgl::protocol::CH_HELLO_ACK_V1_PAYLOAD_SIZE &&
                             readU16Be(&decoded.payload[0]) == CH_ID &&
                             readU16Be(&decoded.payload[2]) == meshAck.helloToken;
        if (matches) {
            lastParentSeenMs = millis();
            lastParentRssiDbm = rxRssiDbm;
            lastParentSnrDb = rxSnrDb;
            logPrintf("CH_HELLO_ACK_RECV parent=0x%04X seq=%u rssi=%d snr=%d retry=%u\n",
                      decoded.srcId, decoded.seq, rxRssiDbm, rxSnrDb, meshAck.retryCount);
            helloAckFailureCount = 0;
            clearMeshAckTransaction("hello-ack-recv");
        } else {
            logPrintf("CH_HELLO_ACK_IGNORE src=0x%04X dst=0x%04X seq=%u len=%u pending=%s waitParent=0x%04X waitSeq=%u\n",
                      decoded.srcId, decoded.dstId, decoded.seq, decoded.payloadLen,
                      meshAckKindName(meshAck.kind), meshAck.expectedParent, meshAck.frameSeq);
        }
        startMeshReceive("after-hello-ack-rx");
        return;
    }

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

    // Compact alarm ACKs are terminal control frames. Return here so their
    // shared SENSOR_DATA type can never fall through into uplink relay logic.
    if (decoded.typeFlags == pgl::protocol::TYPE_ALARM_ACK_COMPACT &&
        decoded.payloadLen < pgl::protocol::GLD_RECORD_HEADER_SIZE) {
        onAlarmAckFromParent(decoded);
        startMeshReceive("after-alarm-ack-rx");
        return;
    }

    // CH_CONFIG_RESPONSE: learn/update parent
    if (msgType == pgl::protocol::MSG_CH_CONFIG_RESPONSE && decoded.dstId == CH_ID) {
        uint16_t advertisedParent = 0;
        uint16_t candidateBatteryMv = 0xFFFF;
        uint8_t candidateDepth = (decoded.srcId == ROOT_GATEWAY_ID) ? 0 : 0xFF;
        uint8_t candidateRouteFlags = 0;
        bool hasReverseLink = false;
        int16_t reverseRssiDbm = 0;
        int8_t reverseSnrDb = 0;
        if (decoded.payloadLen >= 8 && decoded.payload != nullptr) {
            advertisedParent = (static_cast<uint16_t>(decoded.payload[2]) << 8) | decoded.payload[3];
            candidateDepth = decoded.payload[4];
            candidateBatteryMv = (static_cast<uint16_t>(decoded.payload[5]) << 8) | decoded.payload[6];
            candidateRouteFlags = decoded.payload[7];
            if (decoded.srcId == ROOT_GATEWAY_ID && decoded.payloadLen >= 10) {
                hasReverseLink = true;
                reverseRssiDbm = static_cast<int8_t>(decoded.payload[8]);
                reverseSnrDb = static_cast<int8_t>(decoded.payload[9]);
            }
        }
        logPrintf("CH_CONFIG_RESPONSE_RECV srcId=0x%04X parent=0x%04X depth=%u caps=0x%02X rssi=%d snr=%d reverse=%u reverseRssi=%d reverseSnr=%d\n",
                  decoded.srcId,
                  advertisedParent,
                   candidateDepth,
                   candidateRouteFlags,
                  rxRssiDbm,
                  rxSnrDb,
                  hasReverseLink ? 1 : 0,
                  reverseRssiDbm,
                  reverseSnrDb);
        upsertParentCandidate(decoded.srcId, advertisedParent, candidateDepth,
                              candidateBatteryMv, rxRssiDbm, rxSnrDb,
                              candidateRouteFlags,
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
        logPrintf("CH_PULL_PROCESS status=%s onwardQueued=%u pullStatus=%u txStatus=%u requestId=%u dataStatus=%s records=%u responseSize=%u buildStatus=%u\n",
                  pgl::ch::chRuntimeStatusName(status),
                  result.onwardQueued ? 1 : 0,
                  static_cast<unsigned>(result.pullStatus),
                  static_cast<unsigned>(result.txQueueStatus),
                  static_cast<unsigned>(result.pullRequestId),
                  pgl::ch::clusterDataStatusName(result.clusterDataStatus),
                  static_cast<unsigned>(result.clusterRecordCount),
                  static_cast<unsigned>(result.clusterResponseSize),
                  static_cast<unsigned>(result.clusterBuildStatus));
        reportCache("pull");
        if (chState == ChState::JOINED) drainTxQueue();
        return;
    }

    // Uplink relay to parent
    if (decoded.dstId == CH_ID &&
        (msgType == pgl::protocol::MSG_CLUSTER_DATA_RESPONSE ||
         msgType == pgl::protocol::MSG_SENSOR_DATA ||
         msgType == pgl::protocol::MSG_CH_HELLO) &&
        parentId != 0 && parentId != CH_ID) {
        const bool duplicateHello = msgType == pgl::protocol::MSG_CH_HELLO &&
                                    recentHelloDuplicate(decoded);
        if (duplicateHello) {
            sendHelloAck(decoded, "child-hello-duplicate");
            logPrintf("CH_HELLO_DUPLICATE origin=0x%04X via=0x%04X seq=%u relaySkipped=1\n",
                      decoded.payload != nullptr && decoded.payloadLen >= 2
                          ? readU16Be(&decoded.payload[0]) : 0,
                      decoded.srcId, decoded.seq);
            startMeshReceive("after-hello-duplicate");
            return;
        }
        const bool queued = enqueueRelayFrame(decoded, parentId, "uplink-to-parent");
        if (queued && msgType == pgl::protocol::MSG_CH_HELLO) {
            rememberHello(decoded);
            sendHelloAck(decoded, "child-hello-accepted");
        }
        logPrintf("CH_UPLINK_RELAY msgType=0x%02X from=0x%04X parent=0x%04X queued=%u\n",
                  msgType, decoded.srcId, parentId, queued ? 1 : 0);

        // Hop-by-hop alarm ACK: decoded.srcId here is the child CH that pushed
        // this alarm (its own CH_ID is the AppFrame srcId - see
        // buildSingleRecordSensorPushFrame), and that child is waiting for an
        // ACK from its immediate parent, i.e. this CH - not from the far-end
        // gateway. Without this, every alarm relayed through a CH at mesh
        // depth >= 2 times out upstream of here even though it was actually
        // delivered, driving the child through repeated retries and eventual
        // parent failover/restart. Mirrors the gateway's own
        // sendGatewayAckIfNeeded, one hop down; fire-and-forget like that path.
        if (queued && msgType == pgl::protocol::MSG_SENSOR_DATA &&
            pgl::protocol::hasAlarmAckFlag(decoded.typeFlags) &&
            decoded.payload != nullptr &&
            decoded.payloadLen >= pgl::protocol::GLD_RECORD_HEADER_SIZE) {
            uint8_t ackPayload[pgl::protocol::MESH_ALARM_ACK_V1_PAYLOAD_SIZE]{};
            ackPayload[0] = decoded.payload[0];
            ackPayload[1] = decoded.payload[1];
            uint8_t childAck[pgl::protocol::APPFRAME_OVERHEAD +
                             pgl::protocol::MESH_ALARM_ACK_V1_PAYLOAD_SIZE]{};
            const pgl::protocol::FrameEncodeResult childAckEnc = pgl::protocol::encodeAppFrame(
                pgl::protocol::TYPE_ALARM_ACK_COMPACT,
                CH_ID,
                decoded.srcId,
                decoded.seq,
                ackPayload,
                sizeof(ackPayload),
                childAck,
                sizeof(childAck),
                pgl::protocol::MESH_MAX_PAYLOAD);
            if (childAckEnc.status == pgl::protocol::FrameStatus::Ok) {
                transmitRadio(meshRadio, MESH_PINS, childAck, childAckEnc.size, "MESH_CHILD_ACK");
            }
        }

        if (chState == ChState::JOINED) drainTxQueue();
        startMeshReceive("after-uplink-relay");
        return;
    }

    // SERVER_NODE_COMMAND: relay a routed v1 envelope or store the final
    // command as a pending STAR downlink. Direct legacy frames retain their
    // original 7-byte body for rolling-upgrade compatibility.
    if (msgType == pgl::protocol::MSG_SERVER_NODE_COMMAND) {
        pgl::protocol::ServerNodeCommandView command{};
        const pgl::protocol::ServerNodeCommandStatus commandStatus =
            pgl::protocol::decodeServerNodeCommandPayload(
                decoded.payload, decoded.payloadLen, command);
        if (commandStatus != pgl::protocol::ServerNodeCommandStatus::Ok) {
            logPrintf("CH_NODE_COMMAND_REJECT status=%s src=0x%04X seq=%u payloadLen=%u\n",
                      pgl::protocol::serverNodeCommandStatusName(commandStatus),
                      decoded.srcId, decoded.seq, decoded.payloadLen);
            startMeshReceive("after-node-cmd-reject");
            return;
        }

        if (command.routed) {
            const int16_t localHopIndex =
                pgl::protocol::findServerNodeCommandHopIndex(command, CH_ID);
            if (localHopIndex < 0) {
                logPrintf("CH_NODE_COMMAND_ROUTE_REJECT reason=local-hop-missing ch=0x%04X src=0x%04X\n",
                          CH_ID, decoded.srcId);
                startMeshReceive("after-node-cmd-route-reject");
                return;
            }
            const uint16_t expectedSource = localHopIndex == 0
                ? ROOT_GATEWAY_ID
                : pgl::protocol::serverNodeCommandHopAt(
                      command, static_cast<uint8_t>(localHopIndex - 1));
            if (decoded.srcId != expectedSource) {
                logPrintf("CH_NODE_COMMAND_ROUTE_REJECT reason=previous-hop src=0x%04X expected=0x%04X localHop=%d\n",
                          decoded.srcId, expectedSource, static_cast<int>(localHopIndex));
                startMeshReceive("after-node-cmd-route-source-reject");
                return;
            }
            if (static_cast<uint8_t>(localHopIndex) + 1 < command.hopCount) {
                const uint16_t nextHop = pgl::protocol::serverNodeCommandHopAt(
                    command, static_cast<uint8_t>(localHopIndex + 1));
                const bool queued = enqueueRelayFrame(decoded, nextHop, "node-command-downstream");
                logPrintf("CH_NODE_COMMAND_RELAY routeVersion=%u localHop=%d/%u nextHop=0x%04X targetNode=0x%04X commandId=%u queued=%u\n",
                          command.routeVersion, static_cast<int>(localHopIndex),
                          static_cast<unsigned>(command.hopCount), nextHop,
                          command.targetNodeId, command.commandId, queued ? 1 : 0);
                if (chState == ChState::JOINED) drainTxQueue();
                startMeshReceive("after-node-cmd-relay");
                return;
            }
        }

        PendingDownlink* dl = findOrAllocateDownlink(command.targetNodeId);
        if (dl != nullptr) {
            dl->nodeId       = command.targetNodeId;
            dl->commandId    = command.commandId;
            dl->ttlMs        = command.ttlSec > 0
                ? static_cast<uint32_t>(command.ttlSec) * 1000UL
                : PENDING_TTL_MS;
            dl->payloadLen   = command.commandLen;
            dl->receivedAtMs = millis();
            memcpy(dl->payload, command.commandBytes, command.commandLen);
            dl->active = true;
            logPrintf("CH_DOWNLINK_STORED routeVersion=%u nodeId=0x%04X commandId=%u ttlSec=%u payloadLen=%u\n",
                      command.routed ? command.routeVersion : 0,
                      command.targetNodeId, command.commandId, command.ttlSec,
                      static_cast<unsigned>(command.commandLen));
            if (isNodeExtPower(command.targetNodeId) && starReady && starRadio != nullptr) {
                logPrintf("CH_DOWNLINK_EXT_POWER_IMMEDIATE nodeId=0x%04X\n",
                          command.targetNodeId);
                sendNodeDownlink(command.targetNodeId, dl);
            }
        } else {
            logPrintf("CH_DOWNLINK_STORE_FULL nodeId=0x%04X\n", command.targetNodeId);
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
    logPrintf("CH_ACK_PROFILE fieldTest=%u helloIntervalMs=%lu helloJitterMs=%lu healthTimeoutMs=%lu caps=0x%02X\n",
              FIELD_TEST_BUILD ? 1 : 0,
              static_cast<unsigned long>(HELLO_INTERVAL_MS),
              static_cast<unsigned long>(HELLO_JITTER_MS),
              static_cast<unsigned long>(PARENT_HEALTH_TIMEOUT_MS),
              pgl::protocol::CH_CONFIG_FLAG_ROUTE_TO_ROOT |
                  pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1 |
                  pgl::protocol::CH_CONFIG_CAP_ALARM_ACK_NODE_ID_V1 |
                  pgl::protocol::CH_CONFIG_CAP_NODE_COMMAND_ROUTE_V1);
}

// ─── State handlers ──────────────────────────────────────────────────────────

void handleWaitBatt() {
    batteryMv = readBatteryMv();
    if (VBAT_READ_ONLY) {
        runtimeConfig.chBatteryMv = batteryMv;
        logPrintf("CH_BATT_READONLY_MV=%u thresholdIgnored=%u\n", batteryMv, BATT_START_MV);
        setState(ChState::RADIO_INIT, "vbat-read-only");
        serviceDelay(100);
        return;
    }
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
    serviceDelay(1000);
}

void handleRadioInit() {
    releaseRadioReset();
    pgl::ch::clearNodeCache(nodeCache, NODE_CACHE_CAPACITY);
    pgl::ch::clearAlarmQueue(alarmQueue, ALARM_QUEUE_CAPACITY);
    pgl::ch::clearChTxQueue(txQueue, TX_QUEUE_CAPACITY);

    starReady = beginRadio(starRadio, starModule, STAR_PINS, "STAR",
                           STAR_FREQ_MHZ, STAR_BW_KHZ, STAR_SF, STAR_CR, STAR_SYNC_WORD,
                           STAR_TX_POWER_DBM);
    meshReady = beginRadio(meshRadio, meshModule, MESH_PINS, "MESH",
                           MESH_FREQ_MHZ, MESH_BW_KHZ, MESH_SF, MESH_CR, MESH_SYNC_WORD,
                           MESH_TX_POWER_DBM);
    logPrintf("CH_RUNTIME_READY star=%u mesh=%u\n", starReady ? 1 : 0, meshReady ? 1 : 0);

    if (!starReady || !meshReady) {
        if (RADIO_INIT_RETRY_MS > 0) {
            logPrintf("CH_RADIO_INIT_RETRY star=%u mesh=%u retryMs=%lu\n",
                      starReady ? 1 : 0, meshReady ? 1 : 0,
                      static_cast<unsigned long>(RADIO_INIT_RETRY_MS));
            serviceDelay(RADIO_INIT_RETRY_MS);
            return;
        }
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
        nextHelloDueMs = millis();
    }
}

void handleJoined() {
    handleStarPacketReceived();
    handleMeshPacketReceived();
    checkAlarmAckTimeout();
    retryHelloIfNeeded();
    if (chState != ChState::JOINED) return;
    drainTxQueue();

    const uint32_t now = millis();
    if (bootHelloPending && parentId != 0 &&
        (lastBootHelloAttemptMs == 0 || now - lastBootHelloAttemptMs >= 1000)) {
        lastBootHelloAttemptMs = now;
        logPrintf("CH_BOOT_HELLO reason=boot-joined parentId=0x%04X parentAlt=0x%04X\n",
                  parentId, parentAlt);
        if (sendHello()) {
            bootHelloPending = false;
            nextHelloDueMs = now + helloIntervalMs();
        }
    }
    if (nextRouteVerifyDueMs == 0) {
        scheduleNextRouteVerify(now);
    }
    if (!routeVerifyActive && !meshAckBusy() &&
        static_cast<int32_t>(now - nextRouteVerifyDueMs) >= 0) {
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
    if (routeVerifyActive && !meshAckBusy() &&
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
    if (!bootHelloPending && !meshAckBusy() &&
        static_cast<int32_t>(now - nextHelloDueMs) >= 0) {
        if (sendHello()) {
            nextHelloDueMs = now + helloIntervalMs();
        }
    }

    if (parentId != 0 && lastParentSeenMs != 0 &&
        meshAck.kind != MeshAckKind::Hello &&
        now - lastParentSeenMs >= PARENT_HEALTH_TIMEOUT_MS) {
        logPrintf("CH_PARENT_HEALTH_FAIL parent=0x%04X ageMs=%lu timeoutMs=%lu lastRssi=%d lastSnr=%d\n",
                  parentId,
                  static_cast<unsigned long>(now - lastParentSeenMs),
                  static_cast<unsigned long>(PARENT_HEALTH_TIMEOUT_MS),
                  lastParentRssiDbm,
                  lastParentSnrDb);
        setState(ChState::PARENT_FAILOVER, "parent-health-timeout");
        return;
    }

    runHousekeeping();
    reportCachePeriodic();

    batteryMv                 = readBatteryMv();
    runtimeConfig.chBatteryMv = batteryMv;
    if (VBAT_READ_ONLY) {
        // handleJoined() runs every loop() tick for as long as the CH stays
        // JOINED (its normal steady state), so this must be rate-limited the
        // same way reportCachePeriodic() above is - logging on every 20 ms
        // tick printed ~50 unchanging lines/sec over both Serial and Serial0
        // indefinitely, which is pure serial-port and CPU overhead with zero
        // added diagnostic value between reports.
        const uint32_t nowMs = millis();
        if (nowMs - lastBattReadonlyLogMs >= CACHE_REPORT_INTERVAL_MS) {
            lastBattReadonlyLogMs = nowMs;
            logPrintf("CH_BATT_READONLY_MV=%u runMinIgnored=%u criticalIgnored=%u\n",
                      batteryMv, BATT_RUN_MIN_MV, BATT_CRITICAL_MV);
        }
        serviceDelay(20);
        return;
    }
    if (batteryMv < BATT_RUN_MIN_MV) {
        logPrintf("CH_BATT_LOW battMv=%u threshold=%u\n", batteryMv, BATT_RUN_MIN_MV);
        lowPowerEnteredMs = millis();
        setState(ChState::LOW_POWER, "batt-low");
    }

    serviceDelay(20);
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
        nextHelloDueMs = millis();
    }
}

void handleLowPower() {
    handleStarPacketReceived();
    handleMeshPacketReceived();
    if (txAllowed()) drainTxQueue();

    batteryMv = readBatteryMv();
    if (VBAT_READ_ONLY) {
        runtimeConfig.chBatteryMv = batteryMv;
        logPrintf("CH_LOW_POWER_BYPASS battMv=%u runMinIgnored=%u criticalIgnored=%u\n",
                  batteryMv, BATT_RUN_MIN_MV, BATT_CRITICAL_MV);
        setState(ChState::JOINED, "vbat-read-only-low-power-bypass");
        serviceDelay(100);
        return;
    }
    logPrintf("CH_LOW_POWER battMv=%u critical=%u\n", batteryMv, BATT_CRITICAL_MV);

    if (batteryMv >= BATT_RUN_MIN_MV) {
        setState(ChState::JOINED, "batt-recovered");
        return;
    }
    if (batteryMv < BATT_CRITICAL_MV || millis() - lowPowerEnteredMs >= 300000UL) {
        setState(ChState::RECOVERY, "low-power-timeout");
    }
    serviceDelay(1000);
}

// ─── Serial operator console ────────────────────────────────────────────────
//
// The GLD firmware exposes a rich text-command console; the CH historically
// only printed CH_* log lines. This mirrors the GLD pattern so the CH operator
// app can query structured status and drive safe actions over USB serial.

static bool chConsoleDebugVerbose = false;

void emitCmdAck(const char* cmd, const char* status, const char* message) {
    logPrintf("CH_CMD_ACK_JSON {\"cmd\":\"%s\",\"status\":\"%s\",\"message\":\"%s\"}\n",
              cmd, status, message);
}

void emitInfoJson() {
    const uint8_t caps = pgl::protocol::CH_CONFIG_FLAG_ROUTE_TO_ROOT
                       | pgl::protocol::CH_CONFIG_CAP_HELLO_ACK_V1
                       | pgl::protocol::CH_CONFIG_CAP_ALARM_ACK_NODE_ID_V1
                       | pgl::protocol::CH_CONFIG_CAP_NODE_COMMAND_ROUTE_V1;
    logPrintf("CH_INFO_JSON {\"chId\":\"%04X\",\"rootGatewayId\":\"%04X\","
              "\"firmwareName\":\"%s\",\"firmwareVersion\":\"%s\",\"protocolVersion\":\"%s\","
              "\"caps\":\"0x%02X\",",
              CH_ID, ROOT_GATEWAY_ID,
              pgl::firmware::CH_FIRMWARE_NAME, pgl::firmware::CH_FIRMWARE_VERSION,
              pgl::firmware::PROTOCOL_VERSION, caps);
    // Mirrors CH_ACK_PROFILE (a boot-only log line) so a client that connects
    // mid-session - after that one-time line has already scrolled past - can
    // still learn the hello schedule on demand via GET_INFO instead of never
    // being able to compute a next-hello countdown at all.
    logPrintf("\"helloProfile\":{\"intervalMs\":%lu,\"jitterMs\":%lu,\"healthTimeoutMs\":%lu,\"fieldTest\":%u},",
              static_cast<unsigned long>(HELLO_INTERVAL_MS),
              static_cast<unsigned long>(HELLO_JITTER_MS),
              static_cast<unsigned long>(PARENT_HEALTH_TIMEOUT_MS),
              FIELD_TEST_BUILD ? 1 : 0);
    logPrintf("\"starLora\":{\"freqMHz\":%.1f,\"bwKHz\":%.0f,\"sf\":%u,\"cr\":%u,\"syncWord\":%u,\"txPowerDbm\":%d},",
              static_cast<double>(STAR_FREQ_MHZ), static_cast<double>(STAR_BW_KHZ),
              STAR_SF, STAR_CR, STAR_SYNC_WORD, STAR_TX_POWER_DBM);
    logPrintf("\"meshLora\":{\"freqMHz\":%.1f,\"bwKHz\":%.0f,\"sf\":%u,\"cr\":%u,\"syncWord\":%u,\"txPowerDbm\":%d}}\n",
              static_cast<double>(MESH_FREQ_MHZ), static_cast<double>(MESH_BW_KHZ),
              MESH_SF, MESH_CR, MESH_SYNC_WORD, MESH_TX_POWER_DBM);
}

void emitStatusJson() {
    size_t used = 0, downlinkPending = 0;
    for (size_t i = 0; i < NODE_CACHE_CAPACITY; ++i) if (nodeCache[i].used) ++used;
    for (size_t i = 0; i < DOWNLINK_STORE_CAPACITY; ++i) if (downlinkStore[i].active) ++downlinkPending;
    logPrintf("CH_STATUS_JSON {\"state\":\"%s\",\"batteryMv\":%u,\"uptimeSec\":%lu,"
              "\"parentId\":\"%04X\",\"parentRssi\":%d,\"parentSnr\":%d,\"meshDepth\":%u,"
              "\"nodeCount\":%u,\"downlinkPending\":%u,\"unsentNormal\":%u,\"unsentAlarm\":%u}\n",
              chStateName(chState), batteryMv, static_cast<unsigned long>(millis() / 1000UL),
              parentId, lastParentRssiDbm, lastParentSnrDb,
              meshDepth == 0xFF ? 0 : meshDepth,
              static_cast<unsigned>(used), static_cast<unsigned>(downlinkPending),
              static_cast<unsigned>(pgl::ch::countNodeCacheUnsentNormal(nodeCache, NODE_CACHE_CAPACITY)),
              static_cast<unsigned>(pgl::ch::countNodeCacheUnsentAlarm(nodeCache, NODE_CACHE_CAPACITY)));
}

void emitNodesJson() {
    const uint32_t now = millis();
    logPrint("CH_NODES_JSON {\"nodes\":[");
    bool first = true;
    for (size_t i = 0; i < NODE_CACHE_CAPACITY; ++i) {
        const pgl::ch::NodeCacheEntry& e = nodeCache[i];
        if (!e.used) continue;
        logPrintf("%s{\"nodeId\":\"%04X\",\"seq\":%u,\"alarm\":%u,\"extPower\":%u,\"unsent\":%u,\"ageMs\":%lu}",
                  first ? "" : ",", e.nodeId, e.currentSeq,
                  pgl::ch::isNodeCacheEntryAlarm(e) ? 1 : 0,
                  (e.flags & pgl::protocol::NC_FLAG_EXT_POWER) ? 1 : 0,
                  pgl::ch::isNodeCacheEntryUnsent(e) ? 1 : 0,
                  static_cast<unsigned long>(now - e.lastSeenMs));
        first = false;
    }
    logPrintln("]}");
}

void emitParentsJson() {
    logPrintf("CH_PARENTS_JSON {\"active\":\"%04X\",\"candidates\":[", parentId);
    bool first = true;
    for (size_t i = 0; i < PARENT_CANDIDATE_CAPACITY; ++i) {
        const ParentCandidate& c = parentCandidates[i];
        if (c.id == 0) continue;
        logPrintf("%s{\"id\":\"%04X\",\"parent\":\"%04X\",\"depth\":%u,\"rssi\":%d,\"snr\":%d,\"battMv\":%u,\"caps\":\"0x%02X\"}",
                  first ? "" : ",", c.id, c.advertisedParent, c.depth,
                  c.rssiDbm, c.snrDb, c.batteryMv, c.routeFlags);
        first = false;
    }
    logPrintln("]}");
}

void clearParentNvs() {
    Preferences prefs;
    prefs.begin("ch-cfg", false);
    prefs.remove("parentId");
    prefs.remove("parentAlt");
    prefs.end();
    parentId = DEFAULT_PARENT_ID;
    parentAlt = 0;
    savedParentId = DEFAULT_PARENT_ID;
    savedParentAlt = 0;
    runtimeConfig.meshDstId = DEFAULT_PARENT_ID;
    logPrintln("CH_NVS_PARENT_CLEARED reason=operator-console");
}

int8_t hexNibble(char value) {
    if (value >= '0' && value <= '9') return static_cast<int8_t>(value - '0');
    if (value >= 'A' && value <= 'F') return static_cast<int8_t>(value - 'A' + 10);
    if (value >= 'a' && value <= 'f') return static_cast<int8_t>(value - 'a' + 10);
    return -1;
}

bool parseChIdentityJson(const char* json, uint16_t& outId) {
    if (json == nullptr) return false;
    const char* key = strstr(json, "\"chId\"");
    if (key == nullptr) return false;
    const char* value = strchr(key + 6, ':');
    if (value == nullptr) return false;
    ++value;
    while (*value == ' ' || *value == '\t') ++value;
    if (*value++ != '"') return false;

    uint16_t parsed = 0;
    for (uint8_t i = 0; i < 4; ++i) {
        const int8_t nibble = hexNibble(value[i]);
        if (nibble < 0) return false;
        parsed = static_cast<uint16_t>((parsed << 4) | static_cast<uint8_t>(nibble));
    }
    if (value[4] != '"' || !isProvisionableChIdentity(parsed)) return false;
    outId = parsed;
    return true;
}

bool parseGatewayIdJson(const char* json, uint16_t& outId) {
    if (json == nullptr) return false;
    const char* key = strstr(json, "\"gatewayId\"");
    if (key == nullptr) return false;
    const char* value = strchr(key + 11, ':');
    if (value == nullptr) return false;
    ++value;
    while (*value == ' ' || *value == '\t') ++value;
    if (*value++ != '"') return false;

    uint16_t parsed = 0;
    for (uint8_t i = 0; i < 4; ++i) {
        const int8_t nibble = hexNibble(value[i]);
        if (nibble < 0) return false;
        parsed = static_cast<uint16_t>((parsed << 4) | static_cast<uint8_t>(nibble));
    }
    if (value[4] != '"' || !isProvisionableGatewayId(parsed)) return false;
    outId = parsed;
    return true;
}

bool jsonFindNumber(const char* json, const char* key, double& outValue) {
    if (json == nullptr || key == nullptr) return false;
    char pattern[24];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char* found = strstr(json, pattern);
    if (found == nullptr) return false;
    const char* value = strchr(found + strlen(pattern), ':');
    if (value == nullptr) return false;
    ++value;
    char* endPtr = nullptr;
    const double parsed = strtod(value, &endPtr);
    if (endPtr == value) return false;
    outValue = parsed;
    return true;
}

bool parseLoraConfigJson(const char* json, LoraConfigValues& out, const char*& reason) {
    double freqMHz = 0, bwKHz = 0, sf = 0, cr = 0, syncWord = 0, txPowerDbm = 0;
    if (!jsonFindNumber(json, "freqMHz", freqMHz) || !(freqMHz >= 900.0 && freqMHz <= 930.0)) {
        reason = "freqMHz-out-of-range-900-930";
        return false;
    }
    if (!jsonFindNumber(json, "bwKHz", bwKHz) || !(bwKHz >= 1.0 && bwKHz <= 510.0)) {
        reason = "bwKHz-out-of-range";
        return false;
    }
    if (!jsonFindNumber(json, "sf", sf) || !(sf >= 5.0 && sf <= 12.0)) {
        reason = "sf-out-of-range-5-12";
        return false;
    }
    if (!jsonFindNumber(json, "cr", cr) || !(cr >= 5.0 && cr <= 8.0)) {
        reason = "cr-out-of-range-5-8";
        return false;
    }
    if (!jsonFindNumber(json, "syncWord", syncWord) || !(syncWord >= 0.0 && syncWord <= 255.0)) {
        reason = "syncWord-out-of-range-0-255";
        return false;
    }
    if (!jsonFindNumber(json, "txPowerDbm", txPowerDbm) || !(txPowerDbm >= -9.0 && txPowerDbm <= 22.0)) {
        reason = "txPowerDbm-out-of-range-minus9-22";
        return false;
    }
    out.freqMHz = static_cast<float>(freqMHz);
    out.bwKHz = static_cast<float>(bwKHz);
    out.sf = static_cast<uint8_t>(sf);
    out.cr = static_cast<uint8_t>(cr);
    out.syncWord = static_cast<uint8_t>(syncWord);
    out.txPowerDbm = static_cast<int8_t>(txPowerDbm);
    return true;
}

void dispatchSerialCommand(const pgl::ch::ChSerialCommand& cmd) {
    using T = pgl::ch::ChSerialCommandType;
    switch (cmd.type) {
        case T::AppPing:        emitCmdAck("APP_PING", "ok", "pong"); break;
        case T::GetInfo:        emitInfoJson(); break;
        case T::GetStatus:      emitStatusJson(); break;
        case T::GetNodes:       emitNodesJson(); break;
        case T::GetParents:     emitParentsJson(); break;
        case T::SendHello:
            nextHelloDueMs = 0;
            bootHelloPending = true;
            emitCmdAck("SEND_HELLO", "ok", "hello-scheduled");
            break;
        case T::ClearParentNvs:
            clearParentNvs();
            emitCmdAck("CLEAR_PARENT_NVS", "ok", "parent-forgotten");
            if (chState == ChState::JOINED) setState(ChState::PARENT_FAILOVER, "operator-clear-parent");
            break;
        case T::ForceFailover:
            emitCmdAck("FORCE_FAILOVER", "ok", "entering-failover");
            setState(ChState::PARENT_FAILOVER, "operator-console");
            break;
        case T::DebugOn:
            chConsoleDebugVerbose = true;
            emitCmdAck("DEBUG_ON", "ok", "verbose");
            break;
        case T::DebugOff:
            chConsoleDebugVerbose = false;
            emitCmdAck("DEBUG_OFF", "ok", "quiet");
            break;
        case T::Restart:
            emitCmdAck("RESTART", "ok", "restarting");
            serviceDelay(200);
            ESP.restart();
            break;
        case T::SetChAddressJson: {
            uint16_t requestedId = 0;
            if (!parseChIdentityJson(cmd.payload, requestedId)) {
                emitCmdAck("SET_CH_ADDRESS_JSON", "error",
                           "invalid-chId-use-four-hex-node-id-not-root");
                break;
            }
            if (!saveChIdentity(requestedId)) {
                emitCmdAck("SET_CH_ADDRESS_JSON", "error", "nvs-write-or-readback-failed");
                break;
            }
            emitCmdAck("SET_CH_ADDRESS_JSON", "ok", "saved-verified-restarting");
            serviceDelay(250);
            ESP.restart();
            break;
        }
        case T::SetRootGatewayJson: {
            uint16_t requestedGw = 0;
            if (!parseGatewayIdJson(cmd.payload, requestedGw)) {
                emitCmdAck("SET_ROOT_GATEWAY_JSON", "error",
                           "invalid-gatewayId-use-four-hex-node-id-not-chId");
                break;
            }
            if (!saveRootGateway(requestedGw)) {
                emitCmdAck("SET_ROOT_GATEWAY_JSON", "error", "nvs-write-or-readback-failed");
                break;
            }
            emitCmdAck("SET_ROOT_GATEWAY_JSON", "ok", "saved-verified-restarting");
            serviceDelay(250);
            ESP.restart();
            break;
        }
        case T::SetStarLoraJson: {
            LoraConfigValues cfg{};
            const char* reason = "invalid-json-or-missing-fields";
            if (!parseLoraConfigJson(cmd.payload, cfg, reason)) {
                emitCmdAck("SET_STAR_LORA_JSON", "error", reason);
                break;
            }
            if (!saveLoraConfig("star", cfg)) {
                emitCmdAck("SET_STAR_LORA_JSON", "error", "nvs-write-or-readback-failed");
                break;
            }
            emitCmdAck("SET_STAR_LORA_JSON", "ok", "saved-verified-restarting");
            serviceDelay(250);
            ESP.restart();
            break;
        }
        case T::SetMeshLoraJson: {
            LoraConfigValues cfg{};
            const char* reason = "invalid-json-or-missing-fields";
            if (!parseLoraConfigJson(cmd.payload, cfg, reason)) {
                emitCmdAck("SET_MESH_LORA_JSON", "error", reason);
                break;
            }
            if (!saveLoraConfig("mesh", cfg)) {
                emitCmdAck("SET_MESH_LORA_JSON", "error", "nvs-write-or-readback-failed");
                break;
            }
            emitCmdAck("SET_MESH_LORA_JSON", "ok", "saved-verified-restarting");
            serviceDelay(250);
            ESP.restart();
            break;
        }
        case T::Unknown:
            emitCmdAck("UNKNOWN", "error", "unrecognized-command");
            break;
        default:
            break;
    }
}

void pollSerialConsole() {
    pgl::ch::ChSerialCommand cmd;
    if (parseSerialCommand(cmd)) dispatchSerialCommand(cmd);
}

}  // namespace

// ─── Arduino entry points ────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
    setupExternalWdtKeepalivePin();
    pulseExternalWdtKeepaliveNow();
    serviceDelay(1000);
    if (CH_BOOT_SETTLE_MS > 0) {
        logPrintf("CH_BOOT_SETTLE delayMs=%lu\n", static_cast<unsigned long>(CH_BOOT_SETTLE_MS));
        serviceDelay(CH_BOOT_SETTLE_MS);
    }

    esp_task_wdt_init(60, true);
    esp_task_wdt_add(NULL);
    taskWdtReady = true;
    logPrintln("CH_WDT_INIT ok");

    setupRadioPinsSafe();
    SPI.begin(pgl::ch::board::PIN_SPI_SCK,
              pgl::ch::board::PIN_SPI_MISO,
              pgl::ch::board::PIN_SPI_MOSI);

    loadChIdentity();
    loadRootGateway();
    LoraConfigValues starCfg{STAR_FREQ_MHZ, STAR_BW_KHZ, STAR_SF, STAR_CR, STAR_SYNC_WORD, STAR_TX_POWER_DBM};
    loadLoraConfig("star", starCfg);
    STAR_FREQ_MHZ = starCfg.freqMHz; STAR_BW_KHZ = starCfg.bwKHz; STAR_SF = starCfg.sf;
    STAR_CR = starCfg.cr; STAR_SYNC_WORD = starCfg.syncWord; STAR_TX_POWER_DBM = starCfg.txPowerDbm;
    LoraConfigValues meshCfg{MESH_FREQ_MHZ, MESH_BW_KHZ, MESH_SF, MESH_CR, MESH_SYNC_WORD, MESH_TX_POWER_DBM};
    loadLoraConfig("mesh", meshCfg);
    MESH_FREQ_MHZ = meshCfg.freqMHz; MESH_BW_KHZ = meshCfg.bwKHz; MESH_SF = meshCfg.sf;
    MESH_CR = meshCfg.cr; MESH_SYNC_WORD = meshCfg.syncWord; MESH_TX_POWER_DBM = meshCfg.txPowerDbm;
    printBootHeader();
    loadParents();
    updateRuntimeParent(parentId);

    setState(ChState::WAIT_BATT, "boot");
}

void loop() {
    serviceTick();
    pollSerialConsole();

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
            serviceDelay(500);
            ESP.restart();
            break;
    }
}
