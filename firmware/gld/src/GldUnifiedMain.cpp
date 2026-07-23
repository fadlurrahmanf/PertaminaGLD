#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdarg>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldCommandParser.h"
#include "GldDacMux.h"
#include "GldDatasetValidator.h"
#include "GldFrameBuilder.h"
#include "GldModeManager.h"
#include "GldMovingAverage.h"
#include "GldNullingProfile.h"
#include "GldNullingService.h"
#include "GldQcProfile.h"
#include "GldQcService.h"
#include "GldPower.h"
#include "GldThresholdClassifier.h"
#include "GldConfig.h"
#include "FirmwareConfig.h"
#if GLD_ALLOW_SELFTEST_AES_FALLBACK
#if !defined(PGL_GLD_FIELDTEST_SELFTEST_BUILD)
#error "Public AES self-test fallback is allowed only in an explicit nonproduction field-test build"
#endif
#include "GldSelfTestConfig.h"
#endif
#include "ProtocolConstants.h"
#include "../model/ModelMetadata.h"
#include "../model/NeuralNetwork.h"

namespace {

static_assert(static_cast<uint8_t>(pgl::gld::GldAds1256Status::Ok) ==
                  pgl::gld::GLD_DATASET_STATUS_OK,
              "Dataset validator status contract must track ADS1256 Ok");

// ---------------------------------------------------------------------------
// Resolved from GldConfig.h
// ---------------------------------------------------------------------------
constexpr const char* DEFAULT_WIFI_SSID      = GLD_WIFI_SSID;
constexpr const char* DEFAULT_WIFI_PASSWORD  = GLD_WIFI_PASSWORD;
constexpr const char* DEFAULT_MQTT_HOST      = GLD_MQTT_HOST;
constexpr uint16_t    DEFAULT_MQTT_PORT      = GLD_MQTT_PORT;
constexpr const char* DEFAULT_MQTT_USER      = GLD_MQTT_USER;
constexpr const char* DEFAULT_MQTT_PASS      = GLD_MQTT_PASS;
constexpr const char* DEFAULT_DEVICE_ID_STR  = GLD_DEVICE_ID_STR;
constexpr uint16_t    DEFAULT_NODE_ID        = GLD_NODE_ID;
constexpr const char* DEFAULT_TOPIC_ROOT     = PGL_SERVER_DATASET_TOPIC_ROOT;

// ---------------------------------------------------------------------------
// LoRa config (STAR) — harus cocok dengan CH, tidak diubah per-node
// ---------------------------------------------------------------------------
constexpr float    DEFAULT_STAR_FREQ_MHZ    = GLD_STAR_FREQ_MHZ;
constexpr float    DEFAULT_STAR_BW_KHZ      = GLD_STAR_BW_KHZ;
constexpr uint8_t  DEFAULT_STAR_SF          = GLD_STAR_SF;
constexpr uint8_t  DEFAULT_STAR_CR          = GLD_STAR_CR;
constexpr uint8_t  DEFAULT_STAR_SYNC_WORD   = GLD_STAR_SYNC_WORD;
constexpr int8_t   DEFAULT_STAR_TX_POWER    = GLD_STAR_TX_POWER_DBM;
constexpr uint16_t DEFAULT_STAR_PREAMBLE    = GLD_STAR_PREAMBLE;
constexpr float    DEFAULT_LORA_TCXO_V      = GLD_STAR_TCXO_VOLTAGE;
constexpr float    DEFAULT_LORA_XTAL_V      = GLD_STAR_XTAL_VOLTAGE;
constexpr uint32_t LORA_RX_WINDOW_MS = GLD_LORA_RX_WINDOW_MS;
constexpr float    STAR_RUNTIME_MIN_FREQ_MHZ = 920.0f;
constexpr float    STAR_RUNTIME_MAX_FREQ_MHZ = 923.0f;

// ---------------------------------------------------------------------------
// Timing from GldConfig.h
// ---------------------------------------------------------------------------
constexpr uint32_t SCAN_INTERVAL_MS   = GLD_SCAN_INTERVAL_MS;
constexpr uint32_t DATASET_MIN_SAMPLE_INTERVAL_MS = GLD_DATASET_MIN_SAMPLE_INTERVAL_MS;
constexpr uint32_t TX_INTERVAL_MS     = GLD_TX_INTERVAL_MS;
constexpr uint32_t WIFI_TIMEOUT_MS    = GLD_WIFI_TIMEOUT_MS;
constexpr uint32_t MQTT_RETRY_MS      = GLD_MQTT_RETRY_MS;
constexpr uint32_t STATUS_INTERVAL_MS = GLD_STATUS_INTERVAL_MS;
constexpr uint16_t MQTT_BUFFER_SIZE   = GLD_MQTT_BUFFER_SIZE;
constexpr uint8_t  MIN_PRIMED_COUNT   = pgl::gld::GLD_SENSOR_MOVING_AVERAGE_WINDOW;
constexpr uint8_t  BOOT_SENSOR_SNAPSHOT_COUNT = 5;
constexpr uint32_t BOOT_DAC_SETTLE_MS = 5;
constexpr uint16_t BOOT_I2C_TIMEOUT_MS = 50;
constexpr uint8_t  BOOT_MCP_TEST_EDGE_COUNT = 10;
constexpr uint16_t BOOT_MCP_TEST_LOW_START = pgl::gld::board::GLD_DAC_CODE_MIN;
constexpr uint16_t BOOT_MCP_TEST_LOW_END =
    BOOT_MCP_TEST_LOW_START + BOOT_MCP_TEST_EDGE_COUNT - 1U;
constexpr uint16_t BOOT_MCP_TEST_HIGH_END = pgl::gld::board::GLD_DAC_CODE_MAX;
constexpr uint16_t BOOT_MCP_TEST_HIGH_START =
    BOOT_MCP_TEST_HIGH_END - BOOT_MCP_TEST_EDGE_COUNT + 1U;
constexpr uint16_t DIAG_SWEEP_DAC_CODE_LOW = pgl::gld::board::GLD_DAC_CODE_MIN;
constexpr uint16_t DIAG_SWEEP_DAC_CODE_HIGH = 4000;
constexpr uint8_t  DIAG_SWEEP_SAMPLE_COUNT = 5;
constexpr uint32_t DIAG_SWEEP_SETTLE_MS = 250;
constexpr uint8_t  DATASET_QUEUE_CAPACITY = 16;
constexpr size_t   DATASET_PAYLOAD_BYTES = 896;
constexpr uint8_t  DATASET_QUEUE_FLUSH_PER_LOOP = 2;
constexpr uint32_t ADS_RECOVERY_RETRY_MS = 5000;
constexpr uint8_t  ADS_READ_FAIL_RECOVERY_THRESHOLD = 3;
constexpr uint32_t BOOT_RECOVERY_DELAY_MS = 60000;
constexpr uint8_t  BOOT_RECOVERY_MAX_RESTARTS = 1;
constexpr uint32_t ADS1256_SPI_HZ = 1920000;
constexpr uint8_t ADS1256_RREG_CMD = 0x10;
constexpr uint8_t ADS1256_REG_STATUS = 0x00;
constexpr uint8_t ADS1256_REG_MUX = 0x01;
constexpr uint8_t ADS1256_REG_ADCON = 0x02;
constexpr uint8_t ADS1256_REG_DRATE = 0x03;
constexpr uint32_t NULLING_RETRY_DELAY_MS = 5000;
constexpr uint32_t NULLING_AUTO_RESTART_DELAY_MS = 800;
constexpr uint32_t BATTERY_FAULT_SERIAL_HOLD_MS = 10000;
constexpr uint32_t BATTERY_SENSOR_WARMUP_MS = GLD_BATTERY_SENSOR_WARMUP_MS;
constexpr uint8_t BATTERY_VALID_SAMPLE_BATCHES = GLD_BATTERY_VALID_SAMPLE_BATCHES;
constexpr uint8_t BATTERY_ALARM_TX_ATTEMPTS = GLD_BATTERY_ALARM_TX_ATTEMPTS;
constexpr uint32_t BATTERY_ALARM_RETRY_DELAY_MS = GLD_BATTERY_ALARM_RETRY_DELAY_MS;
constexpr uint32_t BATTERY_SESSION_DEADLINE_MS = GLD_BATTERY_SESSION_DEADLINE_MS;
constexpr uint32_t CFG_BUTTON_DEBOUNCE_MS = GLD_CFG_BUTTON_DEBOUNCE_MS;
constexpr uint32_t POWER_RECONCILE_INTERVAL_MS = 1000;
constexpr uint8_t POWER_RECONCILE_STABLE_SAMPLES = 3;

#if defined(PGL_GLD_TFBG_CONTINUOUS_BATTERY)
constexpr bool TFBG_CONTINUOUS_BATTERY = true;
#else
constexpr bool TFBG_CONTINUOUS_BATTERY = false;
#endif

#if defined(PGL_GLD_FIELDTEST_4CLASS)
// This is a non-production transport/coverage test.  It deliberately bypasses
// the ML model and emits a fixed safe telemetry result, while still requiring
// healthy ADS and LoRa hardware.  Alarm persistence, outputs, and alarm radio
// frames stay disabled.
constexpr bool FIELDTEST_MODEL_UNVERIFIED = true;
#else
constexpr bool FIELDTEST_MODEL_UNVERIFIED = false;
#endif

#if defined(PGL_GLD_ALLOW_UNAUTHENTICATED_ALARM_ACK)
constexpr bool ALLOW_UNAUTHENTICATED_ALARM_ACK = true;
#else
// Existing compact ACKs contain only CRC-protected public fields. They are
// accepted only in an explicitly non-production compatibility build; default
// firmware never clears a persisted alarm based on a forgeable RF packet.
constexpr bool ALLOW_UNAUTHENTICATED_ALARM_ACK = false;
#endif

#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8
constexpr const char* BOARD_PROFILE = "WROOM-1U-N16R8";
#else
constexpr const char* BOARD_PROFILE = "4D-ESP32S3";
#endif

constexpr uint8_t ACTIVE_LOW_OUTPUT_ON = LOW;
constexpr uint8_t ACTIVE_LOW_OUTPUT_OFF = HIGH;

static_assert(BATTERY_VALID_SAMPLE_BATCHES >= pgl::gld::GLD_SENSOR_MOVING_AVERAGE_WINDOW,
              "Battery inference requires a fully primed moving-average window");
static_assert(BATTERY_ALARM_TX_ATTEMPTS > 0,
              "Battery alarm transmission must have at least one attempt");
#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8
static_assert(pgl::gld::board::PIN_USER_BUTTON == 16, "Unexpected GLD CFG pin");
static_assert(pgl::gld::board::PIN_STATUS_LED == 39, "Unexpected GLD status LED pin");
#endif

// ---------------------------------------------------------------------------
// Runtime objects
// ---------------------------------------------------------------------------
pgl::gld::GldMode    currentMode = pgl::gld::GldMode::INFERENCE;
SPIClass             gldSpi;
pgl::gld::GldAds1256Reader ads;
pgl::gld::GldMovingAverage movingAvg;
pgl::gld::GldDacMux  dac;
WiFiClient           wifiClient;
PubSubClient         mqtt(wifiClient);
Module*              loraModule = nullptr;
SX1262*              loraRadio  = nullptr;
NeuralNetwork*       network    = nullptr;

// Runtime state
bool adsReady   = false;
bool dacReady   = false;
bool radioReady = false;
bool mlReady    = false;
bool nullDone   = false;
bool nullingRetryArmed = false;
bool nullingProfileApplied = false;
bool lastInferenceValid = false;
bool sensorFaultActive = false;
bool modelProfileReady = false;
uint8_t  txSeq           = 0;
uint32_t txCounter       = 0;
uint32_t lastScanMs      = 0;
uint32_t lastTxMs        = 0;
uint32_t lastMqttAttemptMs = 0;
uint32_t lastStatusMs    = 0;
uint32_t nextNullingRetryMs = 0;
bool     lastAlarm       = false;
uint8_t  nullingProfileId = 0;
uint8_t  nullingAttemptCount = 0;
pgl::gld::GldNullingConfig nullingConfig{};

struct DatasetQueuedPayload {
    char payload[DATASET_PAYLOAD_BYTES]{};
    size_t len = 0;
    uint32_t seq = 0;
};

DatasetQueuedPayload datasetQueue[DATASET_QUEUE_CAPACITY];
uint8_t datasetQueueHead = 0;
uint8_t datasetQueueCount = 0;
uint32_t datasetQueueEnqueued = 0;
uint32_t datasetQueueDropped = 0;
uint32_t datasetPublishFailCount = 0;
uint32_t datasetQueueRetryCount = 0;
uint32_t datasetQueueRetryFailCount = 0;
uint32_t datasetRejectedSamples = 0;
pgl::gld::GldDatasetRejectReason lastDatasetRejectReason =
    pgl::gld::GldDatasetRejectReason::None;
int8_t lastDatasetRejectChannel = -1;
uint8_t lastDatasetRejectOkFiniteCount = 0;
uint8_t lastDatasetRejectStatus = 0xFF;
uint8_t lastDatasetRejectGain = 0;
bool lastDatasetRejectSaturated = false;

uint32_t wifiReconnectCount = 0;
uint32_t wifiReconnectFailCount = 0;
uint32_t mqttReconnectCount = 0;
uint32_t mqttConnectFailCount = 0;
int lastMqttState = 0;
uint32_t adsRecoveryCount = 0;
uint32_t adsRecoveryFailCount = 0;
uint32_t lastAdsRecoveryAttemptMs = 0;
uint8_t adsReadFailStreak = 0;
char lastRecoveryReason[48] = "none";
uint32_t lastRecoveryMs = 0;
bool bootRecoveryArmed = false;
bool bootRecoveryRestartAllowed = false;
bool bootRecoveryNonAdsFailure = false;
uint32_t bootRecoveryDueMs = 0;
char bootRecoveryReason[64] = "none";
RTC_DATA_ATTR uint8_t bootRecoveryRestartCount = 0;

// GLD_GAS_ANOMALY + confidence 0 is the "not classifying" sentinel (no ML
// result available yet / ML unavailable), so a dead classifier never looks
// like a genuine "clear air, 100%" reading. See runScan().
pgl::gld::GldClassifyResult lastResult{pgl::protocol::GLD_GAS_ANOMALY, 0};
bool     debugEnabled    = true;
int16_t  lastLoraBeginState = 0;
int16_t  lastLoraTxState = 0;
bool     lastLoraTxOk = false;
int      lastBootAdsDrdyLevel = -1;
int      lastBootAdsDrdyPulldownLevel = -1;
int      lastBootAdsDrdyPullupLevel = -1;
int      lastBootAdsMisoPulldownLevel = -1;
int      lastBootAdsMisoPullupLevel = -1;
int      lastBootAdsCsLevel = -1;
int      lastBootAdsSyncLevel = -1;
uint8_t  lastBootAdsStatus = 0;
uint8_t  lastBootAdsMux = 0;
uint8_t  lastBootAdsAdcon = 0;
uint8_t  lastBootAdsDrate = 0;
const char* lastBootAdsReason = "not_checked";
bool     lastBootTcaOk = false;
uint8_t  lastBootMcpOkCount = 0;
bool     lastBootMcpOk[pgl::gld::board::SENSOR_COUNT]{};
uint8_t  lastBootMcpAddrMask[pgl::gld::board::SENSOR_COUNT]{};
bool     lastBootMcpControlTested = false;
uint8_t  lastBootMcpControlOkCount = 0;
bool     lastBootMcpControlOk[pgl::gld::board::SENSOR_COUNT]{};
bool     batteryPowerMode = false;
bool     batteryCyclePoweredOff = false;
bool     batteryFaultPowerOffArmed = false;
bool     powerTransitionShutdownPending = false;
bool     batteryPersistenceFaultHold = false;
bool     batteryPendingSaveRequired = false;
uint32_t batteryPersistenceRetryDueMs = 0;
uint32_t batteryFaultPowerOffDueMs = 0;
uint32_t lastWdtKeepaliveMs = 0;
uint32_t lastPowerReconcileMs = 0;
bool powerModeCandidateBattery = false;
uint8_t powerModeCandidateCount = 0;

enum class BatterySessionState : uint8_t {
    Inactive = 0,
    Warmup,
    Sampling,
    Transmit,
    CompleteHeld,
    PowerOffIssued,
};

BatterySessionState batterySessionState = BatterySessionState::Inactive;
uint32_t batterySessionStartedMs = 0;
uint32_t batteryStateStartedMs = 0;
uint32_t batteryLastSampleAttemptMs = 0;
uint32_t batteryLastWarmupPrimeMs = 0;
uint32_t batteryNextTxAttemptMs = 0;
uint8_t batteryValidSampleBatches = 0;
uint8_t batteryAlarmTxAttempts = 0;
bool batteryAlarmAckReceived = false;
char batteryCompletionReason[48] = "session_done";
pgl::gld::GldPendingAlarm batteryPendingAlarm{};

struct GldTxSnapshot {
    bool valid = false;
    bool alarm = false;
    uint8_t sequence = 0;
    uint8_t frameLen = 0;
    uint8_t frame[pgl::gld::GLD_PENDING_ALARM_FRAME_CAPACITY]{};
};

GldTxSnapshot batteryTxSnapshot{};
pgl::gld::GldClassifyResult batteryFreshResult{pgl::protocol::GLD_GAS_ANOMALY, 0};
bool batteryFreshInferenceValid = false;
bool batteryFreshAlarm = false;
bool batterySendingPersistedAlarm = false;
bool batteryFreshAlarmQueued = false;

bool serviceHoldActive = false;
bool cfgButtonRawHigh = true;
bool cfgButtonStableHigh = true;
bool cfgButtonPressArmed = false;
uint32_t cfgButtonRawChangedMs = 0;

const char* batterySessionStateName(BatterySessionState state) {
    switch (state) {
        case BatterySessionState::Inactive: return "inactive";
        case BatterySessionState::Warmup: return "warmup";
        case BatterySessionState::Sampling: return "sampling";
        case BatterySessionState::Transmit: return "transmit";
        case BatterySessionState::CompleteHeld: return "complete_held";
        case BatterySessionState::PowerOffIssued: return "power_off_issued";
    }
    return "unknown";
}
float    latestSensorVoltage[pgl::gld::board::SENSOR_COUNT]{};
uint8_t  latestSensorGain[pgl::gld::board::SENSOR_COUNT]{};
uint8_t  latestSensorStatus[pgl::gld::board::SENSOR_COUNT]{};
bool     latestTelemetryValid = false;

// Marks the NVS-stored board deployment config as deliberately set via
// SET_APP_CONFIG_JSON, matching design.md's BoardDeploymentConfig ctrlword gate.
// 0x00 (default) means "never configured; running on compiled-in defaults".
constexpr uint8_t GLD_CTRL_WORD_VALUE = 0xA3;

struct RuntimeConfig {
    uint8_t ctrlword = 0x00;
    char deviceId[17]{};
    uint16_t nodeId = DEFAULT_NODE_ID;
    uint16_t chId = static_cast<uint16_t>(GLD_CH_ID);
    char wifiSsid[33]{};
    char wifiPassword[65]{};
    char mqttHost[65]{};
    uint16_t mqttPort = DEFAULT_MQTT_PORT;
    char mqttUser[33]{};
    char mqttPass[65]{};
    char topicRoot[65]{};
    uint8_t aesKeyId = 0;
    uint8_t aesKey[16]{};
    bool aesKeyPresent = false;
    uint16_t lastDownlinkCommandId = 0;
    float loraFreqMHz = DEFAULT_STAR_FREQ_MHZ;
    float loraBwKHz = DEFAULT_STAR_BW_KHZ;
    uint8_t loraSf = DEFAULT_STAR_SF;
    uint8_t loraCr = DEFAULT_STAR_CR;
    uint8_t loraSyncWord = DEFAULT_STAR_SYNC_WORD;
    int8_t loraTxPowerDbm = DEFAULT_STAR_TX_POWER;
    uint16_t loraPreamble = DEFAULT_STAR_PREAMBLE;
    float loraTcxoVoltage = DEFAULT_LORA_TCXO_V;
    float loraXtalVoltage = DEFAULT_LORA_XTAL_V;
};

RuntimeConfig runtimeConfig{};

enum class RuntimeAesKeySource : uint8_t {
    None = 0,
    Nvs,
    SelfTest,
};

RuntimeAesKeySource runtimeAesKeySource = RuntimeAesKeySource::None;

const char* runtimeAesKeySourceName() {
    switch (runtimeAesKeySource) {
        case RuntimeAesKeySource::None: return "none";
        case RuntimeAesKeySource::Nvs: return "nvs";
        case RuntimeAesKeySource::SelfTest: return "selftest";
    }
    return "unknown";
}

bool beginLoraRadio();

bool runtimeConfigValid() {
    return runtimeConfig.ctrlword == GLD_CTRL_WORD_VALUE &&
           strlen(runtimeConfig.wifiSsid) > 0 &&
           strlen(runtimeConfig.mqttHost) > 0;
}
char mqttClientId[40]{};
char topicCmd[128]{};
char topicDataset[128]{};
char topicData[128]{};
char topicStatus[128]{};
char topicSummary[128]{};
char topicAck[128]{};

// Dataset session state
enum class DatasetState : uint8_t { Idle, Running };
enum class SampleStep   : uint8_t { None, FanOn, FanSettle, Scan };
DatasetState datasetState   = DatasetState::Idle;
SampleStep   sampleStep     = SampleStep::None;
char         currentLabel[32]{};
uint32_t     datasetSeq     = 0;
uint32_t     sessionStartMs = 0;
uint32_t     stepStartMs    = 0;
uint32_t     targetSamples  = 0;
uint32_t     sampleIntervalMs = DATASET_MIN_SAMPLE_INTERVAL_MS;
uint32_t     maxDurationMs  = 0;
bool         useFanIntake   = true;
uint32_t     fanOnMs        = 1000;
uint32_t     postFanSettleMs = 0;

// LoRa Class A RX flag
volatile bool loraRxFlag = false;

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

void rawPrintln(const char* text) {
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
#endif
}

void rawPrint(const char* text) {
    Serial.print(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(text);
#endif
}

template <typename TDoc>
void rawJsonLine(const char* prefix, const TDoc& doc) {
    Serial.print(prefix);
    Serial.print(' ');
    serializeJson(doc, Serial);
    Serial.println();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(prefix);
    Serial0.print(' ');
    serializeJson(doc, Serial0);
    Serial0.println();
#endif
}

void logPrintf(const char* fmt, ...) {
    if (!debugEnabled) return;
    char buf[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    Serial.print(buf);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(buf);
#endif
}

void logPrintln(const char* text) {
    if (!debugEnabled) return;
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
#endif
}

void copyBounded(char* target, size_t targetSize, const char* source) {
    if (targetSize == 0) return;
    if (source == nullptr) source = "";
    strncpy(target, source, targetSize - 1);
    target[targetSize - 1] = '\0';
}

uint16_t nodeIdFromDeviceId(const char* deviceId, uint16_t fallback) {
    if (deviceId == nullptr || strlen(deviceId) != 4) return fallback;
    char* end = nullptr;
    const unsigned long parsed = strtoul(deviceId, &end, 16);
    if (end == deviceId || *end != '\0' || parsed == 0 || parsed > 0xFFFFUL) return fallback;
    return static_cast<uint16_t>(parsed);
}

int hexNibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

bool parseAesKeyHex(const char* text, uint8_t out[16]) {
    if (text == nullptr || out == nullptr) return false;
    size_t outLen = 0;
    int highNibble = -1;
    for (const char* p = text; *p != '\0'; ++p) {
        if ((*p == '0') && (p[1] == 'x' || p[1] == 'X') && highNibble < 0 && outLen == 0) {
            ++p;
            continue;
        }
        const int nibble = hexNibble(*p);
        if (nibble < 0) {
            if (*p == ':' || *p == '-' || *p == '_' || isspace(static_cast<unsigned char>(*p))) {
                continue;
            }
            return false;
        }
        if (highNibble < 0) {
            highNibble = nibble;
        } else {
            if (outLen >= 16) return false;
            out[outLen++] = static_cast<uint8_t>((highNibble << 4) | nibble);
            highNibble = -1;
        }
    }
    return highNibble < 0 && outLen == 16;
}

void setRejectReason(char* target, size_t targetSize, const char* reason) {
    if (target == nullptr || targetSize == 0) return;
    snprintf(target, targetSize, "%s", reason != nullptr ? reason : "invalid config");
}

bool approxEqual(float a, float b, float tolerance = 0.02f) {
    return fabsf(a - b) <= tolerance;
}

bool normalizeLoraBandwidth(float& bwKHz) {
    constexpr float allowed[] = {7.8f, 10.4f, 15.6f, 20.8f, 31.25f,
                                 41.7f, 62.5f, 125.0f, 250.0f, 500.0f};
    for (float allowedBw : allowed) {
        if (approxEqual(bwKHz, allowedBw, 0.08f)) {
            bwKHz = allowedBw;
            return true;
        }
    }
    return false;
}

bool isAllowedTcxoVoltage(float voltage) {
    constexpr float allowed[] = {0.0f, 1.6f, 1.7f, 1.8f, 2.2f, 2.4f, 2.7f, 3.0f, 3.3f};
    for (float allowedVoltage : allowed) {
        if (approxEqual(voltage, allowedVoltage, 0.01f)) return true;
    }
    return false;
}

bool validateRuntimeLoraConfig(RuntimeConfig& config, char* reason = nullptr, size_t reasonSize = 0) {
    if (!std::isfinite(config.loraFreqMHz) ||
        config.loraFreqMHz < STAR_RUNTIME_MIN_FREQ_MHZ ||
        config.loraFreqMHz > STAR_RUNTIME_MAX_FREQ_MHZ) {
        setRejectReason(reason, reasonSize, "freqMHz must be 920.0..923.0 for STAR");
        return false;
    }
    if (!std::isfinite(config.loraBwKHz) || !normalizeLoraBandwidth(config.loraBwKHz)) {
        setRejectReason(reason, reasonSize, "bwKHz must be 7.8,10.4,15.6,20.8,31.25,41.7,62.5,125,250,500");
        return false;
    }
    if (config.loraSf < 5 || config.loraSf > 12) {
        setRejectReason(reason, reasonSize, "sf must be 5..12");
        return false;
    }
    if (config.loraCr < 5 || config.loraCr > 8) {
        setRejectReason(reason, reasonSize, "cr must be 5..8");
        return false;
    }
    if (config.loraTxPowerDbm < -9 || config.loraTxPowerDbm > 22) {
        setRejectReason(reason, reasonSize, "txPowerDbm must be -9..22");
        return false;
    }
    if (config.loraPreamble < 6) {
        setRejectReason(reason, reasonSize, "preamble must be >= 6");
        return false;
    }
    if (!std::isfinite(config.loraTcxoVoltage) || !isAllowedTcxoVoltage(config.loraTcxoVoltage)) {
        setRejectReason(reason, reasonSize, "tcxoVoltage must be 0,1.6,1.7,1.8,2.2,2.4,2.7,3.0,3.3");
        return false;
    }
    if (!std::isfinite(config.loraXtalVoltage) || !isAllowedTcxoVoltage(config.loraXtalVoltage)) {
        setRejectReason(reason, reasonSize, "xtalVoltage must be 0,1.6,1.7,1.8,2.2,2.4,2.7,3.0,3.3");
        return false;
    }
    return true;
}

void resetRuntimeLoraDefaults() {
    runtimeConfig.loraFreqMHz = DEFAULT_STAR_FREQ_MHZ;
    runtimeConfig.loraBwKHz = DEFAULT_STAR_BW_KHZ;
    runtimeConfig.loraSf = DEFAULT_STAR_SF;
    runtimeConfig.loraCr = DEFAULT_STAR_CR;
    runtimeConfig.loraSyncWord = DEFAULT_STAR_SYNC_WORD;
    runtimeConfig.loraTxPowerDbm = DEFAULT_STAR_TX_POWER;
    runtimeConfig.loraPreamble = DEFAULT_STAR_PREAMBLE;
    runtimeConfig.loraTcxoVoltage = DEFAULT_LORA_TCXO_V;
    runtimeConfig.loraXtalVoltage = DEFAULT_LORA_XTAL_V;
}

void clearRuntimeAesKey() {
    runtimeConfig.aesKeyId = 0;
    memset(runtimeConfig.aesKey, 0, sizeof(runtimeConfig.aesKey));
    runtimeConfig.aesKeyPresent = false;
    runtimeAesKeySource = RuntimeAesKeySource::None;
}

void applySelfTestAesFallbackIfAllowed() {
#if GLD_ALLOW_SELFTEST_AES_FALLBACK
    runtimeConfig.aesKeyId = pgl::gld::selftest::KEY_ID;
    memcpy(runtimeConfig.aesKey, pgl::gld::selftest::AES_KEY, sizeof(runtimeConfig.aesKey));
    runtimeConfig.aesKeyPresent = true;
    runtimeAesKeySource = RuntimeAesKeySource::SelfTest;
    logPrintln("GLD_SECURITY_LOAD=SELFTEST_FALLBACK");
#else
    logPrintln("GLD_SECURITY_LOAD=UNPROVISIONED");
#endif
}

void buildRuntimeTopics() {
    snprintf(mqttClientId, sizeof(mqttClientId), "gld-unified-%s", runtimeConfig.deviceId);
    snprintf(topicCmd, sizeof(topicCmd), "%s/%s/cmd", runtimeConfig.topicRoot, runtimeConfig.deviceId);
    snprintf(topicDataset, sizeof(topicDataset), "%s/%s/dataset", runtimeConfig.topicRoot, runtimeConfig.deviceId);
    snprintf(topicData, sizeof(topicData), "%s/%s/dataset/data", runtimeConfig.topicRoot, runtimeConfig.deviceId);
    snprintf(topicStatus, sizeof(topicStatus), "%s/%s/dataset/status", runtimeConfig.topicRoot, runtimeConfig.deviceId);
    snprintf(topicSummary, sizeof(topicSummary), "%s/%s/dataset/summary", runtimeConfig.topicRoot, runtimeConfig.deviceId);
    snprintf(topicAck, sizeof(topicAck), "%s/%s/cmd/ack", runtimeConfig.topicRoot, runtimeConfig.deviceId);
}

void resetRuntimeConfigDefaults() {
    copyBounded(runtimeConfig.deviceId, sizeof(runtimeConfig.deviceId), DEFAULT_DEVICE_ID_STR);
    runtimeConfig.nodeId = DEFAULT_NODE_ID;
    runtimeConfig.chId = static_cast<uint16_t>(GLD_CH_ID);
    copyBounded(runtimeConfig.wifiSsid, sizeof(runtimeConfig.wifiSsid), DEFAULT_WIFI_SSID);
    copyBounded(runtimeConfig.wifiPassword, sizeof(runtimeConfig.wifiPassword), DEFAULT_WIFI_PASSWORD);
    copyBounded(runtimeConfig.mqttHost, sizeof(runtimeConfig.mqttHost), DEFAULT_MQTT_HOST);
    runtimeConfig.mqttPort = DEFAULT_MQTT_PORT;
    copyBounded(runtimeConfig.mqttUser, sizeof(runtimeConfig.mqttUser), DEFAULT_MQTT_USER);
    copyBounded(runtimeConfig.mqttPass, sizeof(runtimeConfig.mqttPass), DEFAULT_MQTT_PASS);
    copyBounded(runtimeConfig.topicRoot, sizeof(runtimeConfig.topicRoot), DEFAULT_TOPIC_ROOT);
    clearRuntimeAesKey();
    runtimeConfig.lastDownlinkCommandId = 0;
    resetRuntimeLoraDefaults();
    buildRuntimeTopics();
}

void loadRuntimeConfig() {
    resetRuntimeConfigDefaults();
    Preferences prefs;
    if (!prefs.begin("gld_app", true)) {
        logPrintln("GLD_APP_CONFIG_LOAD=DEFAULT reason=nvs_unavailable");
        applySelfTestAesFallbackIfAllowed();
        return;
    }
    String value = prefs.getString("deviceId", runtimeConfig.deviceId);
    copyBounded(runtimeConfig.deviceId, sizeof(runtimeConfig.deviceId), value.c_str());
    runtimeConfig.nodeId = nodeIdFromDeviceId(runtimeConfig.deviceId, DEFAULT_NODE_ID);
    runtimeConfig.chId = prefs.getUShort("chId", runtimeConfig.chId);
    value = prefs.getString("wifiSsid", runtimeConfig.wifiSsid);
    copyBounded(runtimeConfig.wifiSsid, sizeof(runtimeConfig.wifiSsid), value.c_str());
    value = prefs.getString("wifiPass", runtimeConfig.wifiPassword);
    copyBounded(runtimeConfig.wifiPassword, sizeof(runtimeConfig.wifiPassword), value.c_str());
    value = prefs.getString("mqttHost", runtimeConfig.mqttHost);
    copyBounded(runtimeConfig.mqttHost, sizeof(runtimeConfig.mqttHost), value.c_str());
    runtimeConfig.mqttPort = prefs.getUShort("mqttPort", runtimeConfig.mqttPort);
    value = prefs.getString("mqttUser", runtimeConfig.mqttUser);
    copyBounded(runtimeConfig.mqttUser, sizeof(runtimeConfig.mqttUser), value.c_str());
    value = prefs.getString("mqttPass", runtimeConfig.mqttPass);
    copyBounded(runtimeConfig.mqttPass, sizeof(runtimeConfig.mqttPass), value.c_str());
    value = prefs.getString("topicRoot", runtimeConfig.topicRoot);
    copyBounded(runtimeConfig.topicRoot, sizeof(runtimeConfig.topicRoot), value.c_str());
    runtimeConfig.loraFreqMHz = prefs.getFloat("loraFreq", runtimeConfig.loraFreqMHz);
    runtimeConfig.loraBwKHz = prefs.getFloat("loraBw", runtimeConfig.loraBwKHz);
    runtimeConfig.loraSf = static_cast<uint8_t>(prefs.getUChar("loraSf", runtimeConfig.loraSf));
    runtimeConfig.loraCr = static_cast<uint8_t>(prefs.getUChar("loraCr", runtimeConfig.loraCr));
    runtimeConfig.loraSyncWord = static_cast<uint8_t>(prefs.getUChar("loraSync", runtimeConfig.loraSyncWord));
    runtimeConfig.loraTxPowerDbm = static_cast<int8_t>(prefs.getShort("loraPwr", runtimeConfig.loraTxPowerDbm));
    runtimeConfig.loraPreamble = prefs.getUShort("loraPre", runtimeConfig.loraPreamble);
    runtimeConfig.loraTcxoVoltage = prefs.getFloat("loraTcxo", runtimeConfig.loraTcxoVoltage);
    runtimeConfig.loraXtalVoltage = prefs.getFloat("loraXtal", runtimeConfig.loraXtalVoltage);
    runtimeConfig.ctrlword = static_cast<uint8_t>(prefs.getUChar("ctrlword", runtimeConfig.ctrlword));
    const String storedSchema = prefs.getString("schema", "");
    if (storedSchema.length() > 0 &&
        storedSchema != pgl::firmware::CONFIG_SCHEMA_VERSION) {
        runtimeConfig.ctrlword = 0;
        logPrintf("GLD_APP_CONFIG_SCHEMA_MISMATCH stored=%s expected=%s\n",
                  storedSchema.c_str(), pgl::firmware::CONFIG_SCHEMA_VERSION);
    }
    runtimeConfig.aesKeyId = static_cast<uint8_t>(prefs.getUChar("aesKeyId", 0));
    runtimeConfig.aesKeyPresent = prefs.getBool("aesKeySet", false) &&
                                  runtimeConfig.aesKeyId != 0 &&
                                  prefs.getBytesLength("aesKey") == sizeof(runtimeConfig.aesKey);
    if (runtimeConfig.aesKeyPresent) {
        if (prefs.getBytes("aesKey", runtimeConfig.aesKey, sizeof(runtimeConfig.aesKey)) !=
            sizeof(runtimeConfig.aesKey)) {
            clearRuntimeAesKey();
        } else {
            runtimeAesKeySource = RuntimeAesKeySource::Nvs;
        }
    } else {
        clearRuntimeAesKey();
    }
    runtimeConfig.lastDownlinkCommandId = prefs.getUShort("lastCmdId", 0);
    prefs.end();
    if (runtimeConfig.ctrlword != GLD_CTRL_WORD_VALUE) {
        clearRuntimeAesKey();
        runtimeConfig.lastDownlinkCommandId = 0;
    }
    if (!runtimeConfig.aesKeyPresent) {
        applySelfTestAesFallbackIfAllowed();
    }
    char loraReason[120]{};
    if (!validateRuntimeLoraConfig(runtimeConfig, loraReason, sizeof(loraReason))) {
        resetRuntimeLoraDefaults();
        logPrintf("GLD_LORA_CONFIG_LOAD=DEFAULT reason=%s\n", loraReason);
    }
    buildRuntimeTopics();
    logPrintf("GLD_APP_CONFIG_LOAD=%s deviceId=%s nodeId=0x%04X chId=0x%04X ssid=%s mqttHost=%s mqttPort=%u topicRoot=%s aesKey=%u aesKeySource=%s keyId=%u lastCmdId=%u lora=%.3f/%.2f/SF%u/CR%u sync=0x%02X power=%d preamble=%u\n",
              runtimeConfigValid() ? "OK" : "DEFAULT_UNCONFIGURED",
              runtimeConfig.deviceId,
              runtimeConfig.nodeId,
              runtimeConfig.chId,
              runtimeConfig.wifiSsid,
              runtimeConfig.mqttHost,
              runtimeConfig.mqttPort,
              runtimeConfig.topicRoot,
              runtimeConfig.aesKeyPresent ? 1 : 0,
              runtimeAesKeySourceName(),
              runtimeConfig.aesKeyId,
              runtimeConfig.lastDownlinkCommandId,
              runtimeConfig.loraFreqMHz,
              runtimeConfig.loraBwKHz,
              runtimeConfig.loraSf,
              runtimeConfig.loraCr,
              runtimeConfig.loraSyncWord,
              runtimeConfig.loraTxPowerDbm,
              runtimeConfig.loraPreamble);
}

bool saveRuntimeConfig() {
    Preferences prefs;
    if (!prefs.begin("gld_app", false)) return false;
    auto putStringChecked = [&prefs](const char* key, const char* value) {
        prefs.putString(key, value != nullptr ? value : "");
        return prefs.getString(key, "__pgl_missing__") == String(value != nullptr ? value : "");
    };
    auto removeIfPresent = [&prefs](const char* key) {
        return !prefs.isKey(key) || prefs.remove(key);
    };

    // Invalidate first and publish the commit marker last. A brownout or any
    // failed write therefore leaves the config visibly invalid instead of
    // exposing a mixed old/new record behind a valid ctrlword.
    bool ok = prefs.putUChar("ctrlword", 0) == sizeof(uint8_t);
    runtimeConfig.ctrlword = 0;
    ok = putStringChecked("schema", pgl::firmware::CONFIG_SCHEMA_VERSION) && ok;
    ok = putStringChecked("deviceId", runtimeConfig.deviceId) && ok;
    ok = prefs.putUShort("nodeId", runtimeConfig.nodeId) == sizeof(uint16_t) && ok;
    ok = prefs.putUShort("chId", runtimeConfig.chId) == sizeof(uint16_t) && ok;
    ok = putStringChecked("wifiSsid", runtimeConfig.wifiSsid) && ok;
    ok = putStringChecked("wifiPass", runtimeConfig.wifiPassword) && ok;
    ok = putStringChecked("mqttHost", runtimeConfig.mqttHost) && ok;
    ok = prefs.putUShort("mqttPort", runtimeConfig.mqttPort) == sizeof(uint16_t) && ok;
    ok = putStringChecked("mqttUser", runtimeConfig.mqttUser) && ok;
    ok = putStringChecked("mqttPass", runtimeConfig.mqttPass) && ok;
    ok = putStringChecked("topicRoot", runtimeConfig.topicRoot) && ok;
    ok = prefs.putFloat("loraFreq", runtimeConfig.loraFreqMHz) == sizeof(float) && ok;
    ok = prefs.putFloat("loraBw", runtimeConfig.loraBwKHz) == sizeof(float) && ok;
    ok = prefs.putUChar("loraSf", runtimeConfig.loraSf) == sizeof(uint8_t) && ok;
    ok = prefs.putUChar("loraCr", runtimeConfig.loraCr) == sizeof(uint8_t) && ok;
    ok = prefs.putUChar("loraSync", runtimeConfig.loraSyncWord) == sizeof(uint8_t) && ok;
    ok = prefs.putShort("loraPwr", runtimeConfig.loraTxPowerDbm) == sizeof(int16_t) && ok;
    ok = prefs.putUShort("loraPre", runtimeConfig.loraPreamble) == sizeof(uint16_t) && ok;
    ok = prefs.putFloat("loraTcxo", runtimeConfig.loraTcxoVoltage) == sizeof(float) && ok;
    ok = prefs.putFloat("loraXtal", runtimeConfig.loraXtalVoltage) == sizeof(float) && ok;
    if (runtimeConfig.aesKeyPresent && runtimeConfig.aesKeyId != 0) {
        ok = prefs.putBool("aesKeySet", true) == sizeof(uint8_t) && ok;
        ok = prefs.putUChar("aesKeyId", runtimeConfig.aesKeyId) == sizeof(uint8_t) && ok;
        ok = prefs.putBytes("aesKey", runtimeConfig.aesKey, sizeof(runtimeConfig.aesKey)) ==
                 sizeof(runtimeConfig.aesKey) && ok;
    } else {
        ok = prefs.putBool("aesKeySet", false) == sizeof(uint8_t) && ok;
        ok = removeIfPresent("aesKeyId") && ok;
        ok = removeIfPresent("aesKey") && ok;
    }
    ok = prefs.putUShort("lastCmdId", runtimeConfig.lastDownlinkCommandId) == sizeof(uint16_t) && ok;
    if (ok) {
        ok = prefs.putUChar("ctrlword", GLD_CTRL_WORD_VALUE) == sizeof(uint8_t);
    }
    prefs.end();
    runtimeConfig.ctrlword = ok ? GLD_CTRL_WORD_VALUE : 0;
    return ok;
}

bool saveDownlinkReplayState() {
    Preferences prefs;
    if (!prefs.begin("gld_app", false)) return false;
    const bool stored = prefs.putUShort("lastCmdId", runtimeConfig.lastDownlinkCommandId) ==
                        sizeof(uint16_t);
    prefs.end();
    return stored;
}

bool validDeviceId(const char* deviceId) {
    if (deviceId == nullptr || strlen(deviceId) != 4) return false;
    for (uint8_t i = 0; i < 4; ++i) {
        const char c = deviceId[i];
        const bool ok = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f');
        if (!ok) return false;
    }
    return pgl::config::isProvisionableGldId(nodeIdFromDeviceId(deviceId, 0));
}

// New CH provisioning uses the dedicated 0010-0FFF range.  Existing NVS
// values are deliberately not rewritten on boot; this guard applies only to
// an explicit SET_CH_ADDRESS_JSON command.
bool validChId(uint16_t chId) {
    if (!pgl::config::isProvisionableChId(chId)) return false;
    if (chId == runtimeConfig.nodeId) return false;
    return true;
}

template <typename TDoc>
JsonVariant findConfigField(TDoc& doc, const char* key1,
                            const char* key2 = nullptr,
                            const char* key3 = nullptr) {
    JsonVariant value = doc[key1];
    if (!value.isNull()) return value;
    if (key2 != nullptr) {
        value = doc[key2];
        if (!value.isNull()) return value;
    }
    if (key3 != nullptr) {
        value = doc[key3];
        if (!value.isNull()) return value;
    }
    JsonVariant lora = doc["lora"];
    if (lora.isNull()) return JsonVariant();
    value = lora[key1];
    if (!value.isNull()) return value;
    if (key2 != nullptr) {
        value = lora[key2];
        if (!value.isNull()) return value;
    }
    if (key3 != nullptr) {
        value = lora[key3];
        if (!value.isNull()) return value;
    }
    return JsonVariant();
}

bool parseFloatJson(JsonVariant value, float& out) {
    if (value.isNull()) return false;
    const char* text = value.as<const char*>();
    if (text != nullptr) {
        char* end = nullptr;
        const float parsed = strtof(text, &end);
        while (end != nullptr && isspace(static_cast<unsigned char>(*end))) ++end;
        if (end == text || (end != nullptr && *end != '\0') || !std::isfinite(parsed)) return false;
        out = parsed;
        return true;
    }
    const float parsed = value.as<float>();
    if (!std::isfinite(parsed)) return false;
    out = parsed;
    return true;
}

bool parseLongJson(JsonVariant value, long& out) {
    if (value.isNull()) return false;
    const char* text = value.as<const char*>();
    if (text != nullptr) {
        char* end = nullptr;
        const long parsed = strtol(text, &end, 0);
        while (end != nullptr && isspace(static_cast<unsigned char>(*end))) ++end;
        if (end == text || (end != nullptr && *end != '\0')) return false;
        out = parsed;
        return true;
    }
    out = value.as<long>();
    return true;
}

bool readFloatConfigField(JsonDocument& doc, const char* key1, const char* key2,
                          const char* key3, float& target, bool& sawField,
                          char* reason, size_t reasonSize) {
    JsonVariant value = findConfigField(doc, key1, key2, key3);
    if (value.isNull()) return true;
    sawField = true;
    float parsed = target;
    if (!parseFloatJson(value, parsed)) {
        char msg[96];
        snprintf(msg, sizeof(msg), "%s must be numeric", key1);
        setRejectReason(reason, reasonSize, msg);
        return false;
    }
    target = parsed;
    return true;
}

bool readLongConfigField(JsonDocument& doc, const char* key1, const char* key2,
                         const char* key3, long& target, bool& sawField,
                         char* reason, size_t reasonSize) {
    JsonVariant value = findConfigField(doc, key1, key2, key3);
    if (value.isNull()) return true;
    sawField = true;
    long parsed = target;
    if (!parseLongJson(value, parsed)) {
        char msg[96];
        snprintf(msg, sizeof(msg), "%s must be an integer", key1);
        setRejectReason(reason, reasonSize, msg);
        return false;
    }
    target = parsed;
    return true;
}

bool hasRuntimeLoraPatch(JsonDocument& doc) {
    if (!doc["lora"].isNull()) return true;
    return !findConfigField(doc, "freqMHz", "loraFreqMHz", "frequencyMHz").isNull() ||
           !findConfigField(doc, "bwKHz", "loraBwKHz", "bandwidthKHz").isNull() ||
           !findConfigField(doc, "sf", "loraSf", "spreadingFactor").isNull() ||
           !findConfigField(doc, "cr", "loraCr", "codingRate").isNull() ||
           !findConfigField(doc, "syncWord", "loraSyncWord", nullptr).isNull() ||
           !findConfigField(doc, "txPowerDbm", "txPower", "powerDbm").isNull() ||
           !findConfigField(doc, "preamble", "preambleLength", "loraPreamble").isNull() ||
           !findConfigField(doc, "tcxoVoltage", "tcxoV", "loraTcxoVoltage").isNull() ||
           !findConfigField(doc, "xtalVoltage", "xtalTcxoVoltage", "loraXtalVoltage").isNull();
}

bool applyRuntimeLoraPatch(JsonDocument& doc, char* reason, size_t reasonSize) {
    RuntimeConfig updated = runtimeConfig;
    bool sawField = false;
    if (!readFloatConfigField(doc, "freqMHz", "loraFreqMHz", "frequencyMHz",
                              updated.loraFreqMHz, sawField, reason, reasonSize)) return false;
    if (!readFloatConfigField(doc, "bwKHz", "loraBwKHz", "bandwidthKHz",
                              updated.loraBwKHz, sawField, reason, reasonSize)) return false;
    if (!readFloatConfigField(doc, "tcxoVoltage", "tcxoV", "loraTcxoVoltage",
                              updated.loraTcxoVoltage, sawField, reason, reasonSize)) return false;
    if (!readFloatConfigField(doc, "xtalVoltage", "xtalTcxoVoltage", "loraXtalVoltage",
                              updated.loraXtalVoltage, sawField, reason, reasonSize)) return false;

    long sf = updated.loraSf;
    long cr = updated.loraCr;
    long syncWord = updated.loraSyncWord;
    long txPower = updated.loraTxPowerDbm;
    long preamble = updated.loraPreamble;
    if (!readLongConfigField(doc, "sf", "loraSf", "spreadingFactor",
                             sf, sawField, reason, reasonSize)) return false;
    if (!readLongConfigField(doc, "cr", "loraCr", "codingRate",
                             cr, sawField, reason, reasonSize)) return false;
    if (!readLongConfigField(doc, "syncWord", "loraSyncWord", nullptr,
                             syncWord, sawField, reason, reasonSize)) return false;
    if (!readLongConfigField(doc, "txPowerDbm", "txPower", "powerDbm",
                             txPower, sawField, reason, reasonSize)) return false;
    if (!readLongConfigField(doc, "preamble", "preambleLength", "loraPreamble",
                             preamble, sawField, reason, reasonSize)) return false;
    if (!sawField) {
        setRejectReason(reason, reasonSize, "no LoRa fields provided");
        return false;
    }
    if (sf < 0 || sf > 255 || cr < 0 || cr > 255 || syncWord < 0 || syncWord > 255 ||
        txPower < -128 || txPower > 127 || preamble < 0 || preamble > 65535) {
        setRejectReason(reason, reasonSize, "LoRa integer field is out of storage range");
        return false;
    }
    updated.loraSf = static_cast<uint8_t>(sf);
    updated.loraCr = static_cast<uint8_t>(cr);
    updated.loraSyncWord = static_cast<uint8_t>(syncWord);
    updated.loraTxPowerDbm = static_cast<int8_t>(txPower);
    updated.loraPreamble = static_cast<uint16_t>(preamble);
    if (!validateRuntimeLoraConfig(updated, reason, reasonSize)) return false;
    runtimeConfig.loraFreqMHz = updated.loraFreqMHz;
    runtimeConfig.loraBwKHz = updated.loraBwKHz;
    runtimeConfig.loraSf = updated.loraSf;
    runtimeConfig.loraCr = updated.loraCr;
    runtimeConfig.loraSyncWord = updated.loraSyncWord;
    runtimeConfig.loraTxPowerDbm = updated.loraTxPowerDbm;
    runtimeConfig.loraPreamble = updated.loraPreamble;
    runtimeConfig.loraTcxoVoltage = updated.loraTcxoVoltage;
    runtimeConfig.loraXtalVoltage = updated.loraXtalVoltage;
    return true;
}

void formatHex4(uint16_t value, char* out, size_t outSize) {
    snprintf(out, outSize, "%04X", value);
}

void nullingLogLine(const char* text) {
    logPrintln(text);
}

const char* datasetStateName() {
    return datasetState == DatasetState::Running ? "running" : "idle";
}

const char* sampleStepName() {
    switch (sampleStep) {
        case SampleStep::FanOn: return "fan_on";
        case SampleStep::FanSettle: return "fan_settle";
        case SampleStep::Scan: return "scan";
        case SampleStep::None:
        default:
            return "idle";
    }
}

void setRecoveryReason(const char* reason) {
    copyBounded(lastRecoveryReason, sizeof(lastRecoveryReason), reason != nullptr ? reason : "unknown");
    lastRecoveryMs = millis();
}

bool bootRecoveryDelayActive() {
    return bootRecoveryArmed &&
           static_cast<int32_t>(millis() - bootRecoveryDueMs) < 0;
}

uint8_t datasetQueueTail() {
    return static_cast<uint8_t>((datasetQueueHead + datasetQueueCount) % DATASET_QUEUE_CAPACITY);
}

void enqueueDatasetPayload(const char* payload, size_t len, uint32_t seq) {
    if (payload == nullptr || len == 0) return;
    if (datasetQueueCount >= DATASET_QUEUE_CAPACITY) {
        logPrintf("DATASET_QUEUE_DROP seq=%lu reason=full\n",
                  static_cast<unsigned long>(datasetQueue[datasetQueueHead].seq));
        datasetQueueHead = static_cast<uint8_t>((datasetQueueHead + 1U) % DATASET_QUEUE_CAPACITY);
        --datasetQueueCount;
        ++datasetQueueDropped;
    }

    DatasetQueuedPayload& slot = datasetQueue[datasetQueueTail()];
    const size_t maxCopy = sizeof(slot.payload) - 1U;
    const size_t copyLen = len < maxCopy ? len : maxCopy;
    memcpy(slot.payload, payload, copyLen);
    slot.payload[copyLen] = '\0';
    slot.len = copyLen;
    slot.seq = seq;
    ++datasetQueueCount;
    ++datasetQueueEnqueued;
    logPrintf("DATASET_QUEUE_ENQUEUE seq=%lu pending=%u len=%u\n",
              static_cast<unsigned long>(seq),
              static_cast<unsigned>(datasetQueueCount),
              static_cast<unsigned>(copyLen));
}

bool publishDatasetPayload(const char* payload, uint32_t seq, bool retry) {
    const bool ok = mqtt.connected() && mqtt.publish(topicData, payload, false);
    if (retry) {
        if (ok) {
            ++datasetQueueRetryCount;
            logPrintf("DATASET_QUEUE_RETRY seq=%lu ok=1 pending=%u\n",
                      static_cast<unsigned long>(seq),
                      static_cast<unsigned>(datasetQueueCount > 0 ? datasetQueueCount - 1U : 0U));
        } else {
            ++datasetQueueRetryFailCount;
            logPrintf("DATASET_QUEUE_RETRY seq=%lu ok=0 pending=%u\n",
                      static_cast<unsigned long>(seq),
                      static_cast<unsigned>(datasetQueueCount));
        }
    } else if (!ok) {
        ++datasetPublishFailCount;
    }
    return ok;
}

void flushDatasetQueue() {
    if (datasetQueueCount == 0 || !mqtt.connected()) return;
    for (uint8_t i = 0; i < DATASET_QUEUE_FLUSH_PER_LOOP && datasetQueueCount > 0; ++i) {
        DatasetQueuedPayload& slot = datasetQueue[datasetQueueHead];
        if (!publishDatasetPayload(slot.payload, slot.seq, true)) {
            break;
        }
        datasetQueueHead = static_cast<uint8_t>((datasetQueueHead + 1U) % DATASET_QUEUE_CAPACITY);
        --datasetQueueCount;
    }
}

void noteAdsReadHealth(uint8_t okCount, const char* context) {
    if (okCount > 0) {
        adsReadFailStreak = 0;
        return;
    }
    if (adsReadFailStreak < 255) ++adsReadFailStreak;
    logPrintf("ADS_READ_HEALTH context=%s okCount=0 streak=%u\n",
              context != nullptr ? context : "unknown",
              static_cast<unsigned>(adsReadFailStreak));
    if (adsReadFailStreak >= ADS_READ_FAIL_RECOVERY_THRESHOLD) {
        adsReady = false;
        setRecoveryReason("ads_all_channels_failed");
        logPrintf("ADS_RECOVERY_ARM reason=all_channels_failed context=%s\n",
                  context != nullptr ? context : "unknown");
    }
}

void maintainAdsRecovery(const char* reason) {
    if (adsReady) return;
    if (bootRecoveryDelayActive()) return;
    const uint32_t now = millis();
    if (lastAdsRecoveryAttemptMs != 0 && now - lastAdsRecoveryAttemptMs < ADS_RECOVERY_RETRY_MS) {
        return;
    }
    lastAdsRecoveryAttemptMs = now;
    setRecoveryReason(reason != nullptr ? reason : "ads_not_ready");
    logPrintf("ADS_RECOVERY_ATTEMPT reason=%s\n", lastRecoveryReason);
    const bool ok = ads.begin(gldSpi);
    adsReady = ok;
    if (ok) {
        ++adsRecoveryCount;
        adsReadFailStreak = 0;
        movingAvg.reset();
        logPrintf("ADS_RECOVERY_RESULT=OK count=%lu\n",
                  static_cast<unsigned long>(adsRecoveryCount));
    } else {
        ++adsRecoveryFailCount;
        logPrintf("ADS_RECOVERY_RESULT=FAIL failCount=%lu\n",
                  static_cast<unsigned long>(adsRecoveryFailCount));
    }
}

void emitCommandAck(const char* cmd, const char* status,
                    const char* message, bool rebootExpected) {
    StaticJsonDocument<256> doc;
    char chIdHex[5];
    formatHex4(runtimeConfig.chId, chIdHex, sizeof(chIdHex));
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
    doc["chId"] = chIdHex;
    doc["cmd"] = cmd;
    doc["status"] = status;
    doc["message"] = message;
    doc["rebootExpected"] = rebootExpected;
    doc["mode"] = pgl::gld::gldModeName(currentMode);
    doc["uptimeMs"] = static_cast<uint32_t>(millis());
    rawJsonLine("GLD_CMD_ACK_JSON", doc);
}

void addCapabilities(JsonObject caps) {
    caps["appPing"] = true;
    caps["getInfo"] = true;
    caps["getStatus"] = true;
    caps["serialAckJson"] = true;
    caps["runningTelemetry"] = true;
    caps["modeSwitchReboots"] = true;
    caps["datasetControlPath"] = "mqtt";
    caps["nullingConfig"] = "SET_NULLING_CONFIG_JSON thresholdV,minFinalV";
    caps["qcTracking"] = "SET_QC_RESULT_JSON channel,pass,timestamp / GET_QC_STATUS";
    caps["nullingSingleChannel"] = "RUN_NULLING_SINGLE_JSON channel";
    caps["fullScaleSweep"] = "RUN_FULLSCALE_SWEEP_JSON channel";
    caps["qcReset"] = "RESET_QC_RESULT_JSON channel / RESET_QC_ALL";
    caps["serialAppConfig"] = true;
    caps["serialDeviceId"] = true;
    caps["serialChAddress"] = "SET_CH_ADDRESS_JSON chId";
    caps["serialLoraConfig"] = "SET_LORA_CONFIG_JSON freqMHz,bwKHz,sf,cr,syncWord,txPowerDbm,preamble,tcxoVoltage,xtalVoltage";
    caps["liveLoraReinit"] = true;
    caps["runBootCheck"] = true;
    caps["adsMcpSweep"] = "RUN_ADS_MCP_SWEEP";
    caps["sleepNow"] = "SLEEP_NOW";
    caps["batteryServiceHold"] = "CFG press-release toggle / SERVICE_HOLD_OFF";
    caps["securityProvisioning"] = "SET_APP_CONFIG_JSON aesKeyHex";
    caps["authenticatedDownlink"] = true;
}

void addTelemetry(JsonObject telemetry) {
    telemetry["valid"] = latestTelemetryValid;
    telemetry["sampleMs"] = lastScanMs;
    telemetry["gasClass"] = lastResult.gasClass;
    telemetry["gasName"] = pgl::gld::gldGasClassName(lastResult.gasClass);
    telemetry["confidence"] = lastResult.confidence;
    telemetry["alarm"] = lastAlarm;

    JsonArray voltage = telemetry.createNestedArray("sensorVoltage");
    JsonArray gain = telemetry.createNestedArray("sensorGain");
    JsonArray status = telemetry.createNestedArray("sensorStatus");
    JsonArray order = telemetry.createNestedArray("featureOrder");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        voltage.add(latestSensorVoltage[ch]);
        gain.add(latestSensorGain[ch]);
        status.add(latestSensorStatus[ch]);
        order.add(pgl::gld::board::SENSOR_NAMES[ch]);
    }
}

void emitInfoJson() {
    static StaticJsonDocument<1536> doc;
    doc.clear();
    char chIdHex[5];
    formatHex4(runtimeConfig.chId, chIdHex, sizeof(chIdHex));
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
    doc["targetChId"] = chIdHex;
    doc["firmwareName"] = pgl::firmware::GLD_FIRMWARE_NAME;
    doc["firmwareVersion"] = pgl::firmware::GLD_FIRMWARE_VERSION;
    doc["protocolVersion"] = pgl::firmware::PROTOCOL_VERSION;
    doc["boardProfile"] = BOARD_PROFILE;
    doc["mode"] = pgl::gld::gldModeName(currentMode);
    doc["batteryServiceHold"] = serviceHoldActive;
    doc["baud"] = 115200;
    doc["sensorCount"] = pgl::gld::board::SENSOR_COUNT;
    doc["mqttTopicRoot"] = runtimeConfig.topicRoot;
    JsonObject starLora = doc.createNestedObject("starLora");
    starLora["freqMHz"] = runtimeConfig.loraFreqMHz;
    starLora["bwKHz"] = runtimeConfig.loraBwKHz;
    starLora["sf"] = runtimeConfig.loraSf;
    starLora["cr"] = runtimeConfig.loraCr;
    starLora["syncWord"] = runtimeConfig.loraSyncWord;
    starLora["txPowerDbm"] = runtimeConfig.loraTxPowerDbm;
    starLora["preamble"] = runtimeConfig.loraPreamble;
    starLora["tcxoVoltage"] = runtimeConfig.loraTcxoVoltage;
    starLora["xtalVoltage"] = runtimeConfig.loraXtalVoltage;
    starLora["runtime"] = true;
    JsonObject appConfig = doc.createNestedObject("appConfig");
    appConfig["wifiSsid"] = runtimeConfig.wifiSsid;
    appConfig["mqttHost"] = runtimeConfig.mqttHost;
    appConfig["mqttPort"] = runtimeConfig.mqttPort;
    appConfig["mqttUser"] = runtimeConfig.mqttUser;
    appConfig["topicRoot"] = runtimeConfig.topicRoot;
    appConfig["configValid"] = runtimeConfigValid();
    JsonObject security = doc.createNestedObject("security");
    security["aesKeyProvisioned"] =
        runtimeAesKeySource == RuntimeAesKeySource::Nvs;
    security["aesKeyPresent"] = runtimeConfig.aesKeyPresent;
    security["aesKeySource"] = runtimeAesKeySourceName();
    security["keyId"] = runtimeConfig.aesKeyId;
    security["selfTestFallbackAllowed"] = GLD_ALLOW_SELFTEST_AES_FALLBACK ? true : false;
    security["lastDownlinkCommandId"] = runtimeConfig.lastDownlinkCommandId;
    JsonObject caps = doc.createNestedObject("capabilities");
    addCapabilities(caps);
    rawJsonLine("GLD_INFO_JSON", doc);
}

void emitStatusJson() {
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    static StaticJsonDocument<4096> doc;
    doc.clear();
    char chIdHex[5];
    formatHex4(runtimeConfig.chId, chIdHex, sizeof(chIdHex));
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
    doc["targetChId"] = chIdHex;
    doc["mode"] = pgl::gld::gldModeName(currentMode);
    doc["uptimeMs"] = static_cast<uint32_t>(millis());
    doc["debugEnabled"] = debugEnabled;

    JsonObject powerObj = doc.createNestedObject("power");
    powerObj["mode"] = pgl::gld::gldPowerModeName(power.mode);
    powerObj["externalPower"] = power.externalPower;
    powerObj["batteryMv"] = power.batteryMv;
    powerObj["batteryValid"] = power.batteryValid;
    powerObj["batteryDetected"] = power.batteryDetected;
    powerObj["batterySenseStatus"] = pgl::gld::gldBatterySenseStatusName(power.batterySenseStatus);
    powerObj["batteryLow"] = power.batteryLow;
    powerObj["batteryCritical"] = power.batteryCritical;
    powerObj["sourceAmbiguous"] = power.powerSourceAmbiguous;
    powerObj["serviceHoldActive"] = serviceHoldActive;
    powerObj["serviceHoldEffective"] = batteryPowerMode &&
        (serviceHoldActive || batteryPersistenceFaultHold ||
         digitalRead(pgl::gld::board::PIN_USER_BUTTON) == LOW ||
         !cfgButtonRawHigh || cfgButtonPressArmed);

    JsonObject batterySession = doc.createNestedObject("batterySession");
    batterySession["state"] = batterySessionStateName(batterySessionState);
    batterySession["startedMs"] = batterySessionStartedMs;
    batterySession["stateStartedMs"] = batteryStateStartedMs;
    batterySession["validSampleBatches"] = batteryValidSampleBatches;
    batterySession["requiredSampleBatches"] = BATTERY_VALID_SAMPLE_BATCHES;
    batterySession["alarmTxAttempts"] = batteryAlarmTxAttempts;
    batterySession["alarmTxAttemptLimit"] = BATTERY_ALARM_TX_ATTEMPTS;
    batterySession["alarmAckReceived"] = batteryAlarmAckReceived;
    batterySession["pendingAlarm"] = batteryPendingAlarm.active;
    batterySession["pendingSaveRequired"] = batteryPendingSaveRequired;
    batterySession["persistenceFaultHold"] = batteryPersistenceFaultHold;
    batterySession["completionReason"] = batteryCompletionReason;

    JsonObject boot = doc.createNestedObject("bootHealth");
    boot["adsReady"] = adsReady;
    boot["adsDrdyLevel"] = lastBootAdsDrdyLevel;
    boot["adsDrdyPulldownLevel"] = lastBootAdsDrdyPulldownLevel;
    boot["adsDrdyPullupLevel"] = lastBootAdsDrdyPullupLevel;
    boot["adsMisoPulldownLevel"] = lastBootAdsMisoPulldownLevel;
    boot["adsMisoPullupLevel"] = lastBootAdsMisoPullupLevel;
    boot["adsCsLevel"] = lastBootAdsCsLevel;
    boot["adsSyncLevel"] = lastBootAdsSyncLevel;
    boot["adsStatus"] = lastBootAdsStatus;
    boot["adsMux"] = lastBootAdsMux;
    boot["adsAdcon"] = lastBootAdsAdcon;
    boot["adsDrate"] = lastBootAdsDrate;
    boot["adsReason"] = lastBootAdsReason;
    boot["tcaOk"] = lastBootTcaOk;
    boot["mcpOkCount"] = lastBootMcpOkCount;
    JsonArray mcpOk = boot.createNestedArray("mcpOk");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        mcpOk.add(lastBootMcpOk[ch]);
    }
    JsonArray mcpAddrMask = boot.createNestedArray("mcpAddrMask");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        mcpAddrMask.add(lastBootMcpAddrMask[ch]);
    }
    boot["mcpControlTested"] = lastBootMcpControlTested;
    boot["mcpControlOkCount"] = lastBootMcpControlOkCount;
    JsonArray mcpControlOk = boot.createNestedArray("mcpControlOk");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        mcpControlOk.add(lastBootMcpControlOk[ch]);
    }
    boot["dacReady"] = dacReady;
    boot["radioReady"] = radioReady;
    boot["mlReady"] = mlReady;
    boot["nullingProfileApplied"] = nullingProfileApplied;
    boot["modelProfileReady"] = modelProfileReady;

    JsonObject modelStatus = doc.createNestedObject("model");
    modelStatus["profileId"] = pgl::gld::model::PROFILE_ID;
    modelStatus["scalerProfileId"] = pgl::gld::model::SCALER_PROFILE_ID;
    modelStatus["productionApproved"] = pgl::gld::model::PRODUCTION_APPROVED;
    modelStatus["boundNullingProfileId"] = pgl::gld::model::BOUND_NULLING_PROFILE_ID;
    modelStatus["activeNullingProfileId"] = nullingProfileId;
    modelStatus["profileReady"] = modelProfileReady;
    modelStatus["inferenceValid"] = lastInferenceValid;
    modelStatus["sensorFault"] = sensorFaultActive;

    JsonObject lora = doc.createNestedObject("lora");
    lora["beginState"] = lastLoraBeginState;
    lora["lastTxState"] = lastLoraTxState;
    lora["lastTxOk"] = lastLoraTxOk;
    lora["txSeq"] = txSeq;
    lora["txCounter"] = txCounter;
    lora["aesKeyProvisioned"] =
        runtimeAesKeySource == RuntimeAesKeySource::Nvs;
    lora["aesKeyPresent"] = runtimeConfig.aesKeyPresent;
    lora["aesKeySource"] = runtimeAesKeySourceName();
    lora["keyId"] = runtimeConfig.aesKeyId;
    lora["lastDownlinkCommandId"] = runtimeConfig.lastDownlinkCommandId;
    lora["freqMHz"] = runtimeConfig.loraFreqMHz;
    lora["bwKHz"] = runtimeConfig.loraBwKHz;
    lora["sf"] = runtimeConfig.loraSf;
    lora["cr"] = runtimeConfig.loraCr;
    lora["syncWord"] = runtimeConfig.loraSyncWord;
    lora["txPowerDbm"] = runtimeConfig.loraTxPowerDbm;
    lora["preamble"] = runtimeConfig.loraPreamble;
    lora["tcxoVoltage"] = runtimeConfig.loraTcxoVoltage;
    lora["xtalVoltage"] = runtimeConfig.loraXtalVoltage;

    JsonObject dataset = doc.createNestedObject("dataset");
    dataset["state"] = datasetStateName();
    dataset["step"] = sampleStepName();
    dataset["label"] = currentLabel;
    dataset["seq"] = datasetSeq;
    dataset["targetSamples"] = targetSamples;
    dataset["sampleIntervalMs"] = sampleIntervalMs;
    dataset["maxDurationMs"] = maxDurationMs;
    dataset["useFanIntake"] = useFanIntake;
    dataset["fanOnMs"] = fanOnMs;
    dataset["postFanSettleMs"] = postFanSettleMs;
    dataset["nullingProfileId"] = nullingProfileId;
    dataset["queuePending"] = datasetQueueCount;
    dataset["queueCapacity"] = DATASET_QUEUE_CAPACITY;
    dataset["queueEnqueued"] = datasetQueueEnqueued;
    dataset["queueDropped"] = datasetQueueDropped;
    dataset["publishFailCount"] = datasetPublishFailCount;
    dataset["retryCount"] = datasetQueueRetryCount;
    dataset["retryFailCount"] = datasetQueueRetryFailCount;
    dataset["rejectedSamples"] = datasetRejectedSamples;
    dataset["lastRejectReason"] =
        pgl::gld::gldDatasetRejectReasonName(lastDatasetRejectReason);
    dataset["lastRejectChannel"] = static_cast<int>(lastDatasetRejectChannel);
    dataset["lastRejectOkFiniteCount"] = lastDatasetRejectOkFiniteCount;
    dataset["lastRejectStatus"] = lastDatasetRejectStatus;
    dataset["lastRejectGain"] = lastDatasetRejectGain;
    dataset["lastRejectSaturated"] = lastDatasetRejectSaturated;

    JsonObject recovery = doc.createNestedObject("recovery");
    recovery["wifiReconnectCount"] = wifiReconnectCount;
    recovery["wifiReconnectFailCount"] = wifiReconnectFailCount;
    recovery["mqttReconnectCount"] = mqttReconnectCount;
    recovery["mqttConnectFailCount"] = mqttConnectFailCount;
    recovery["lastMqttState"] = lastMqttState;
    recovery["adsRecoveryCount"] = adsRecoveryCount;
    recovery["adsRecoveryFailCount"] = adsRecoveryFailCount;
    recovery["adsReadFailStreak"] = adsReadFailStreak;
    recovery["lastReason"] = lastRecoveryReason;
    recovery["lastRecoveryMs"] = lastRecoveryMs;
    recovery["bootRecoveryArmed"] = bootRecoveryArmed;
    recovery["bootRecoveryDueMs"] = bootRecoveryDueMs;
    recovery["bootRecoveryReason"] = bootRecoveryReason;
    recovery["bootRecoveryNonAdsFailure"] = bootRecoveryNonAdsFailure;
    recovery["bootRecoveryRestartCount"] = bootRecoveryRestartCount;

    JsonObject nulling = doc.createNestedObject("nulling");
    nulling["done"] = nullDone;
    nulling["retryArmed"] = nullingRetryArmed;
    nulling["attemptCount"] = nullingAttemptCount;
    nulling["nextRetryMs"] = nextNullingRetryMs;
    nulling["thresholdV"] = nullingConfig.thresholdV;
    nulling["minFinalV"] = nullingConfig.minFinalV;

    JsonObject telemetry = doc.createNestedObject("telemetry");
    addTelemetry(telemetry);

    rawJsonLine("GLD_STATUS_JSON", doc);
}

// ---------------------------------------------------------------------------
// Mode command handler — NVS write + reboot
// ---------------------------------------------------------------------------

void serviceDelay(uint32_t durationMs);
void runBootCheckFromSerialCommand();
void runAdsMcpSweepFromSerialCommand();
void sleepNowFromSerialCommand();
bool serviceHoldBlocksClr();
void setServiceHoldActive(bool active, const char* source);

void onModeCmd(pgl::gld::GldMode newMode) {
    if (!pgl::gld::writeGldMode(newMode)) {
        emitCommandAck("SET_MODE", "error", "mode persistence failed; restart cancelled", false);
        logPrintf("GLD_MODE_SWITCH current=%s new=%s persisted=0 restart=0\n",
                  pgl::gld::gldModeName(currentMode),
                  pgl::gld::gldModeName(newMode));
        return;
    }
    emitCommandAck("SET_MODE", "ok", "mode switch accepted", true);
    logPrintf("GLD_MODE_SWITCH current=%s new=%s\n",
              pgl::gld::gldModeName(currentMode),
              pgl::gld::gldModeName(newMode));
    ESP.restart();
}

void onDebugCmd(bool enabled) {
    debugEnabled = enabled;
    emitCommandAck(enabled ? "DEBUG_ON" : "DEBUG_OFF", "ok",
                   enabled ? "serial debug enabled" : "serial debug disabled",
                   false);
    rawPrintln(enabled
        ? "DEBUG_ON accepted, serial debug enabled"
        : "DEBUG_OFF accepted, serial debug disabled");
}

void rebootAfterAckIfRequested(bool reboot) {
    if (!reboot) return;
    serviceDelay(250);
    ESP.restart();
}

void restartFromSerialCommand() {
    emitCommandAck("RESTART", "ok", "restarting", true);
    // Deliberately a plain delay(), not serviceDelay(): RESTART is checked
    // unconditionally in checkSerial(), even reentrant from deep inside a
    // blocking nulling/full-scale-sweep tick loop, and serviceDelay() calls
    // firmwareServiceTick() -> checkSerial() again - one more reentrant frame
    // on top of an already-deep call stack is enough to trip the loopTask
    // stack canary and panic instead of restarting cleanly. Serial.flush()
    // below already blocks until the ack bytes are fully transmitted, so no
    // service ticking is needed here anyway.
    delay(50);
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    ESP.restart();
}

void sleepNowFromSerialCommand() {
    if (serviceHoldBlocksClr()) {
        emitCommandAck("SLEEP_NOW", "blocked", "battery service hold is active", false);
        logPrintln("GLD_SERVICE_HOLD_BLOCK_CLR reason=serial_sleep_now");
        return;
    }
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    emitCommandAck("SLEEP_NOW", "ok", "clearing power latch via CLR", false);
    logPrintf("GLD_SERIAL_SLEEP_NOW power_off mode=%s externalPower=%u batteryMv=%u clr=HIGH_LOW_HIGH\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0,
              power.batteryMv);
    serviceDelay(100);
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    if (serviceHoldBlocksClr()) {
        emitCommandAck("SLEEP_NOW", "blocked", "CFG went low before CLR", false);
        logPrintln("GLD_SERVICE_HOLD_BLOCK_CLR reason=serial_sleep_now_final_guard");
        Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
        Serial0.flush();
#endif
        return;
    }
    pgl::gld::pulseGldPowerLatchClear();
}

// QC bench pin injection - lets the operator app manually exercise the
// TPL5010 DONE/CLR nets from the QC tab, independent of the automatic
// keepalive/sleep cycle. See docs/firmware/gld-tpl5010-wake-sleep-com10-report.md.
void injectTplDoneFromSerialCommand() {
    emitCommandAck("INJECT_TPL_DONE", "ok", "pulsing TPL5010 DONE pin once", false);
    logPrintf("GLD_SERIAL_INJECT_TPL_DONE pulse=HIGH_LOW\n");
    pgl::gld::pulseGldTpl5010Keepalive();
}

// CLR pulses the same active-low power-latch reset as SLEEP_NOW, so this
// injection can cut board power and drop the serial connection - flush the
// ack before pulsing, exactly like sleepNowFromSerialCommand().
void injectTplClrFromSerialCommand() {
    if (serviceHoldBlocksClr()) {
        emitCommandAck("INJECT_TPL_CLR", "blocked", "battery service hold is active", false);
        logPrintln("GLD_SERVICE_HOLD_BLOCK_CLR reason=serial_inject_tpl_clr");
        return;
    }
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    emitCommandAck("INJECT_TPL_CLR", "ok", "pulsing power latch CLR once", false);
    logPrintf("GLD_SERIAL_INJECT_TPL_CLR mode=%s externalPower=%u batteryMv=%u clr=HIGH_LOW_HIGH\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0,
              power.batteryMv);
    serviceDelay(100);
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    if (serviceHoldBlocksClr()) {
        emitCommandAck("INJECT_TPL_CLR", "blocked", "CFG went low before CLR", false);
        logPrintln("GLD_SERVICE_HOLD_BLOCK_CLR reason=serial_inject_tpl_clr_final_guard");
        Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
        Serial0.flush();
#endif
        return;
    }
    pgl::gld::pulseGldPowerLatchClear();
}

void serviceHoldOffFromSerialCommand() {
    setServiceHoldActive(false, "serial");
    emitCommandAck("SERVICE_HOLD_OFF", "ok", "battery service hold disabled", false);
}

void onUnknownSerialCommand(const char* commandText) {
    rawPrint(commandText);
    rawPrintln(" command is unknown");
}

void logRuntimeLoraConfig(const char* marker, bool reboot, bool liveApplied) {
    logPrintf("%s freqMHz=%.3f bwKHz=%.2f sf=%u cr=%u sync=0x%02X power=%d preamble=%u tcxo=%.1f xtal=%.1f reboot=%u liveApplied=%u beginState=%d\n",
              marker,
              runtimeConfig.loraFreqMHz,
              runtimeConfig.loraBwKHz,
              runtimeConfig.loraSf,
              runtimeConfig.loraCr,
              runtimeConfig.loraSyncWord,
              runtimeConfig.loraTxPowerDbm,
              runtimeConfig.loraPreamble,
              runtimeConfig.loraTcxoVoltage,
              runtimeConfig.loraXtalVoltage,
              reboot ? 1 : 0,
              liveApplied ? 1 : 0,
              static_cast<int>(lastLoraBeginState));
}

bool applyLoraRuntimeNowIfNeeded(bool reboot, bool& liveApplied) {
    liveApplied = false;
    if (reboot || currentMode != pgl::gld::GldMode::INFERENCE) return true;
    liveApplied = true;
    radioReady = beginLoraRadio();
    return radioReady;
}

void onSetLoraConfigJson(const char* payload) {
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("SET_LORA_CONFIG", "error", "invalid json", false);
        return;
    }
    const bool reboot = doc["reboot"] | false;
    char reason[160]{};
    if (!applyRuntimeLoraPatch(doc, reason, sizeof(reason))) {
        emitCommandAck("SET_LORA_CONFIG", "rejected", reason, false);
        return;
    }
    if (!saveRuntimeConfig()) {
        emitCommandAck("SET_LORA_CONFIG", "error", "failed to save lora config", false);
        return;
    }
    bool liveApplied = false;
    const bool liveOk = applyLoraRuntimeNowIfNeeded(reboot, liveApplied);
    logRuntimeLoraConfig("GLD_LORA_CONFIG_SAVE=OK", reboot, liveApplied);
    if (!liveOk) {
        emitCommandAck("SET_LORA_CONFIG", "error", "lora config saved but radio reinit failed", false);
        return;
    }
    const char* message = reboot
        ? "lora config saved; rebooting"
        : liveApplied ? "lora config saved; radio reapplied" : "lora config saved; applies on next running init";
    emitCommandAck("SET_LORA_CONFIG", "ok", message, reboot);
    rebootAfterAckIfRequested(reboot);
}

void onSetAppConfigJson(const char* payload) {
    StaticJsonDocument<1536> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("SET_APP_CONFIG", "error", "invalid json", false);
        return;
    }
    const char* ssid = doc["ssid"].as<const char*>();
    if (ssid == nullptr) ssid = doc["wifiSsid"].as<const char*>();
    if (ssid == nullptr) ssid = runtimeConfig.wifiSsid;
    const char* password = doc["password"].as<const char*>();
    if (password == nullptr) password = doc["wifiPassword"].as<const char*>();
    if (password == nullptr) password = runtimeConfig.wifiPassword;
    const char* mqttHost = doc["mqttHost"].as<const char*>();
    if (mqttHost == nullptr) mqttHost = doc["brokerHost"].as<const char*>();
    if (mqttHost == nullptr) mqttHost = runtimeConfig.mqttHost;
    const uint16_t mqttPort = doc["mqttPort"] | runtimeConfig.mqttPort;
    const char* mqttUser = doc["mqttUser"].as<const char*>();
    if (mqttUser == nullptr) mqttUser = runtimeConfig.mqttUser;
    const char* mqttPass = doc["mqttPass"].as<const char*>();
    if (mqttPass == nullptr) mqttPass = runtimeConfig.mqttPass;
    const char* topicRoot = doc["topicRoot"].as<const char*>();
    if (topicRoot == nullptr) topicRoot = runtimeConfig.topicRoot;
    const bool reboot = doc["reboot"] | true;
    const bool clearAesKey = doc["clearAesKey"] | false;
    const char* aesKeyHex = doc["aesKeyHex"].as<const char*>();
    if (aesKeyHex == nullptr) aesKeyHex = doc["gldAes128KeyHex"].as<const char*>();
    if (aesKeyHex == nullptr) aesKeyHex = doc["GLD_AES128_KEY_HEX"].as<const char*>();
    const bool aesKeyProvided = aesKeyHex != nullptr && strlen(aesKeyHex) > 0;
    uint8_t parsedAesKey[16]{};
    const uint8_t requestedKeyId = static_cast<uint8_t>(doc["keyId"] | runtimeConfig.aesKeyId);
    const bool loraPatch = hasRuntimeLoraPatch(doc);

    if (strlen(ssid) == 0 || strlen(mqttHost) == 0 || strlen(topicRoot) == 0 || mqttPort == 0) {
        emitCommandAck("SET_APP_CONFIG", "rejected", "ssid, mqttHost, mqttPort, and topicRoot are required", false);
        return;
    }
    if (aesKeyProvided) {
        if (requestedKeyId == 0) {
            emitCommandAck("SET_APP_CONFIG", "rejected", "keyId must be 1..255 when aesKeyHex is provided", false);
            return;
        }
        if (!parseAesKeyHex(aesKeyHex, parsedAesKey)) {
            emitCommandAck("SET_APP_CONFIG", "rejected", "aesKeyHex must contain exactly 16 bytes / 32 hex chars", false);
            return;
        }
    }
    if (loraPatch) {
        char reason[160]{};
        if (!applyRuntimeLoraPatch(doc, reason, sizeof(reason))) {
            emitCommandAck("SET_APP_CONFIG", "rejected", reason, false);
            return;
        }
    }

    copyBounded(runtimeConfig.wifiSsid, sizeof(runtimeConfig.wifiSsid), ssid);
    copyBounded(runtimeConfig.wifiPassword, sizeof(runtimeConfig.wifiPassword), password);
    copyBounded(runtimeConfig.mqttHost, sizeof(runtimeConfig.mqttHost), mqttHost);
    runtimeConfig.mqttPort = mqttPort;
    copyBounded(runtimeConfig.mqttUser, sizeof(runtimeConfig.mqttUser), mqttUser);
    copyBounded(runtimeConfig.mqttPass, sizeof(runtimeConfig.mqttPass), mqttPass);
    copyBounded(runtimeConfig.topicRoot, sizeof(runtimeConfig.topicRoot), topicRoot);
    if (clearAesKey) {
        clearRuntimeAesKey();
        runtimeConfig.lastDownlinkCommandId = 0;
    }
    if (aesKeyProvided) {
        runtimeConfig.aesKeyId = requestedKeyId;
        memcpy(runtimeConfig.aesKey, parsedAesKey, sizeof(runtimeConfig.aesKey));
        runtimeConfig.aesKeyPresent = true;
        runtimeAesKeySource = RuntimeAesKeySource::Nvs;
        runtimeConfig.lastDownlinkCommandId = 0;
    }
    buildRuntimeTopics();

    if (!saveRuntimeConfig()) {
        emitCommandAck("SET_APP_CONFIG", "error", "failed to save app config", false);
        return;
    }

    logPrintf("GLD_APP_CONFIG_SAVE=OK ssid=%s mqttHost=%s mqttPort=%u topicRoot=%s aesKey=%u keyId=%u reboot=%u\n",
              runtimeConfig.wifiSsid,
              runtimeConfig.mqttHost,
              runtimeConfig.mqttPort,
              runtimeConfig.topicRoot,
              runtimeConfig.aesKeyPresent ? 1 : 0,
              runtimeConfig.aesKeyId,
              reboot ? 1 : 0);
    if (loraPatch) {
        bool liveApplied = false;
        const bool liveOk = applyLoraRuntimeNowIfNeeded(reboot, liveApplied);
        logRuntimeLoraConfig("GLD_LORA_CONFIG_SAVE=OK", reboot, liveApplied);
        if (!liveOk) {
            emitCommandAck("SET_APP_CONFIG", "error", "app config saved but lora reinit failed", false);
            return;
        }
    }
    emitCommandAck("SET_APP_CONFIG", "ok", reboot ? "app config saved; rebooting" : "app config saved", reboot);
    if (!reboot) {
        mqtt.disconnect();
        WiFi.disconnect(false);
    }
    rebootAfterAckIfRequested(reboot);
}

void onSetDeviceIdJson(const char* payload) {
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("SET_DEVICE_ID", "error", "invalid json", false);
        return;
    }
    const char* deviceId = doc["deviceId"].as<const char*>();
    if (deviceId == nullptr) deviceId = doc["id"].as<const char*>();
    if (deviceId == nullptr) deviceId = "";
    const bool reboot = doc["reboot"] | true;
    if (!validDeviceId(deviceId)) {
        emitCommandAck("SET_DEVICE_ID", "rejected", "deviceId must be a GLD ID in 1001-FEFF", false);
        return;
    }
    const uint16_t derivedNodeId = nodeIdFromDeviceId(deviceId, DEFAULT_NODE_ID);
    if (!doc["nodeId"].isNull()) {
        uint16_t explicitNodeId = 0;
        const char* nodeIdText = doc["nodeId"].as<const char*>();
        if (nodeIdText != nullptr && nodeIdText[0] != '\0') {
            explicitNodeId = nodeIdFromDeviceId(nodeIdText, 0);
        } else {
            const uint32_t nodeIdNumber = doc["nodeId"] | 0u;
            if (nodeIdNumber <= 0xFFFFU) {
                explicitNodeId = static_cast<uint16_t>(nodeIdNumber);
            }
        }
        if (explicitNodeId != derivedNodeId) {
            emitCommandAck("SET_DEVICE_ID", "rejected", "nodeId must match deviceId; omit nodeId unless it is identical", false);
            return;
        }
    }
    copyBounded(runtimeConfig.deviceId, sizeof(runtimeConfig.deviceId), deviceId);
    runtimeConfig.nodeId = derivedNodeId;
    buildRuntimeTopics();
    if (!saveRuntimeConfig()) {
        emitCommandAck("SET_DEVICE_ID", "error", "failed to save device id", false);
        return;
    }
    logPrintf("GLD_DEVICE_ID_SAVE=OK deviceId=%s nodeId=0x%04X reboot=%u\n",
              runtimeConfig.deviceId, runtimeConfig.nodeId, reboot ? 1 : 0);
    emitCommandAck("SET_DEVICE_ID", "ok", reboot ? "device id saved; rebooting" : "device id saved", reboot);
    rebootAfterAckIfRequested(reboot);
}

void onSetChAddressJson(const char* payload) {
    StaticJsonDocument<128> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("SET_CH_ADDRESS", "error", "invalid json", false);
        return;
    }
    const char* chIdStr = doc["chId"].as<const char*>();
    if (chIdStr == nullptr) chIdStr = doc["chAddress"].as<const char*>();
    if (chIdStr == nullptr) chIdStr = "";
    const bool reboot = doc["reboot"] | true;
    const uint16_t parsedChId = nodeIdFromDeviceId(chIdStr, 0);
    if (parsedChId == 0 || !validChId(parsedChId)) {
        emitCommandAck("SET_CH_ADDRESS", "rejected",
            "chId must be a CH ID in 0010-0FFF and not the GLD's own ID", false);
        return;
    }
    runtimeConfig.chId = parsedChId;
    if (!saveRuntimeConfig()) {
        emitCommandAck("SET_CH_ADDRESS", "error", "failed to save CH address", false);
        return;
    }
    logPrintf("GLD_CH_ADDRESS_SAVE=OK chId=0x%04X reboot=%u\n", runtimeConfig.chId, reboot ? 1 : 0);
    emitCommandAck("SET_CH_ADDRESS", "ok", reboot ? "CH address saved; rebooting" : "CH address saved", reboot);
    rebootAfterAckIfRequested(reboot);
}

void onSetNullingConfigJson(const char* payload) {
    StaticJsonDocument<128> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("SET_NULLING_CONFIG", "error", "invalid json", false);
        return;
    }
    const float thresholdV = doc["thresholdV"] | nullingConfig.thresholdV;
    const float minFinalV  = doc["minFinalV"] | nullingConfig.minFinalV;

    if (!(thresholdV > 0.0f) || thresholdV > pgl::gld::GLD_ADS1256_VREF_VOLTS) {
        emitCommandAck("SET_NULLING_CONFIG", "rejected", "thresholdV must be > 0 and <= VREF", false);
        return;
    }
    if (minFinalV < -pgl::gld::GLD_ADS1256_VREF_VOLTS || minFinalV > pgl::gld::GLD_ADS1256_VREF_VOLTS) {
        emitCommandAck("SET_NULLING_CONFIG", "rejected", "minFinalV out of ADS1256 VREF range", false);
        return;
    }

    pgl::gld::GldNullingConfig updated{};
    updated.thresholdV = thresholdV;
    updated.minFinalV  = minFinalV;
    if (!pgl::gld::saveNullingConfig(updated)) {
        emitCommandAck("SET_NULLING_CONFIG", "error", "failed to save nulling config", false);
        return;
    }
    nullingConfig = updated;
    logPrintf("GLD_NULLING_CONFIG_SAVE=OK thresholdV=%.6f minFinalV=%.6f\n",
              nullingConfig.thresholdV, nullingConfig.minFinalV);
    emitCommandAck("SET_NULLING_CONFIG", "ok", "nulling config saved; applies on next nulling run", false);
}

void onSetQcResultJson(const char* payload) {
    StaticJsonDocument<192> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("SET_QC_RESULT", "error", "invalid json", false);
        return;
    }
    if (!doc.containsKey("channel") || !doc.containsKey("pass")) {
        emitCommandAck("SET_QC_RESULT", "rejected", "channel and pass are required", false);
        return;
    }
    const int channel = doc["channel"].as<int>();
    if (channel < 0 || channel >= pgl::gld::board::SENSOR_COUNT) {
        emitCommandAck("SET_QC_RESULT", "rejected", "channel must be 0..7", false);
        return;
    }
    const bool pass = doc["pass"].as<bool>();
    const char* timestamp = doc["timestamp"].as<const char*>();
    if (timestamp == nullptr) timestamp = "";

    pgl::gld::GldQcProfile profile{};
    if (!pgl::gld::loadQcProfile(profile)) {
        profile = pgl::gld::GldQcProfile{};
    }
    profile.validMagic = pgl::gld::QC_PROFILE_VALID_MAGIC;
    profile.tested[channel] = 1;
    profile.passed[channel] = pass ? 1u : 0u;
    strncpy(profile.timestamp[channel], timestamp, pgl::gld::QC_TIMESTAMP_LEN - 1);
    profile.timestamp[channel][pgl::gld::QC_TIMESTAMP_LEN - 1] = '\0';

    if (!pgl::gld::saveQcProfile(profile)) {
        emitCommandAck("SET_QC_RESULT", "error", "failed to save qc result", false);
        return;
    }
    logPrintf("GLD_QC_RESULT_SAVE=OK channel=%d pass=%u\n", channel, pass ? 1u : 0u);
    emitCommandAck("SET_QC_RESULT", "ok", "qc result saved", false);
}

void onResetQcResultJson(const char* payload) {
    StaticJsonDocument<64> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("RESET_QC_RESULT", "error", "invalid json", false);
        return;
    }
    if (!doc.containsKey("channel")) {
        emitCommandAck("RESET_QC_RESULT", "rejected", "channel is required", false);
        return;
    }
    const int channel = doc["channel"].as<int>();
    if (channel < 0 || channel >= pgl::gld::board::SENSOR_COUNT) {
        emitCommandAck("RESET_QC_RESULT", "rejected", "channel must be 0..7", false);
        return;
    }

    pgl::gld::GldQcProfile profile{};
    if (!pgl::gld::loadQcProfile(profile)) {
        profile = pgl::gld::GldQcProfile{};
    }
    profile.validMagic = pgl::gld::QC_PROFILE_VALID_MAGIC;
    profile.tested[channel] = 0;
    profile.passed[channel] = 0;
    profile.timestamp[channel][0] = '\0';

    if (!pgl::gld::saveQcProfile(profile)) {
        emitCommandAck("RESET_QC_RESULT", "error", "failed to save qc reset", false);
        return;
    }
    logPrintf("GLD_QC_RESULT_RESET=OK channel=%d\n", channel);
    emitCommandAck("RESET_QC_RESULT", "ok", "qc result reset", false);
}

void onResetQcAll() {
    pgl::gld::GldQcProfile profile{};
    profile.validMagic = pgl::gld::QC_PROFILE_VALID_MAGIC;
    if (!pgl::gld::saveQcProfile(profile)) {
        emitCommandAck("RESET_QC_ALL", "error", "failed to save qc reset", false);
        return;
    }
    logPrintln("GLD_QC_RESULT_RESET_ALL=OK");
    emitCommandAck("RESET_QC_ALL", "ok", "all qc results reset", false);
}

void emitQcStatusJson() {
    pgl::gld::GldQcProfile qcProfile{};
    const bool qcValid = pgl::gld::loadQcProfile(qcProfile);
    if (!qcValid) qcProfile = pgl::gld::GldQcProfile{};

    pgl::gld::GldNullingProfile nullingProfile{};
    const bool nullingValid = pgl::gld::loadNullingProfile(nullingProfile);

    StaticJsonDocument<1024> doc;
    char chIdHex[5];
    formatHex4(runtimeConfig.chId, chIdHex, sizeof(chIdHex));
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
    doc["chId"] = chIdHex;

    JsonArray channels = doc.createNestedArray("channels");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        JsonObject c = channels.createNestedObject();
        c["channel"] = ch;
        c["sensor"] = pgl::gld::board::SENSOR_NAMES[ch];
        c["nullingOk"] = nullingValid && nullingProfile.channelOk[ch] != 0;
        c["tested"] = qcProfile.tested[ch] != 0;
        c["pass"] = qcProfile.passed[ch] != 0;
        c["timestamp"] = qcProfile.timestamp[ch];
    }
    rawJsonLine("GLD_QC_STATUS_JSON", doc);
}

// Forward declaration - defined further down near the nulling retry state
// machine, but the QC tab's single-channel nulling command needs it here.
bool ensureNullingHardwareReady();
void checkSerial();
void firmwareServiceTick();

void onRunNullingSingleJson(const char* payload) {
    StaticJsonDocument<96> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("RUN_NULLING_SINGLE", "error", "invalid json", false);
        return;
    }
    if (!doc.containsKey("channel")) {
        emitCommandAck("RUN_NULLING_SINGLE", "rejected", "channel is required", false);
        return;
    }
    const int channel = doc["channel"].as<int>();
    if (channel < 0 || channel >= pgl::gld::board::SENSOR_COUNT) {
        emitCommandAck("RUN_NULLING_SINGLE", "rejected", "channel must be 0..7", false);
        return;
    }
    if (!ensureNullingHardwareReady()) {
        emitCommandAck("RUN_NULLING_SINGLE", "error", "ADS/DAC not ready", false);
        return;
    }

    const pgl::gld::GldNullingSingleResult result = pgl::gld::runNullingServiceSingleChannel(
        ads, dac, static_cast<uint8_t>(channel), nullingLogLine, firmwareServiceTick, nullingConfig);

    // A single-channel service may update only an already-complete production
    // profile. Never promote a partial/failing result into a valid profile.
    pgl::gld::GldNullingProfile existing{};
    const bool hadExisting = pgl::gld::loadNullingProfile(existing);
    if (!hadExisting) {
        emitCommandAck("RUN_NULLING_SINGLE", "rejected",
                       "complete nulling profile required before single-channel update", false);
        return;
    }
    if (!result.success) {
        emitCommandAck("RUN_NULLING_SINGLE", "failed",
                       "channel nulling failed; active profile unchanged", false);
        return;
    }
    if (existing.profileId == UINT8_MAX) {
        emitCommandAck("RUN_NULLING_SINGLE", "rejected",
                       "nulling profile id exhausted; maintenance reset required", false);
        return;
    }

    pgl::gld::GldNullingProfile toSave = existing;
    toSave.profileId = static_cast<uint8_t>(existing.profileId + 1u);
    toSave.dacCode[channel]   = result.dacCode;
    toSave.baselineV[channel] = result.baselineV;
    toSave.afterV[channel]    = result.afterV;
    toSave.channelOk[channel] = 1u;

    if (!pgl::gld::isNullingProfileValid(toSave)) {
        emitCommandAck("RUN_NULLING_SINGLE", "error", "updated profile validation failed", false);
        return;
    }
    if (!dac.writeDac(static_cast<uint8_t>(channel), result.dacCode)) {
        emitCommandAck("RUN_NULLING_SINGLE", "error", "DAC apply failed; active profile unchanged", false);
        return;
    }
    if (!pgl::gld::saveNullingProfile(toSave)) {
        (void)dac.writeDac(static_cast<uint8_t>(channel), existing.dacCode[channel]);
        emitCommandAck("RUN_NULLING_SINGLE", "error", "nulling result computed but failed to save profile", false);
        return;
    }
    nullingProfileId = toSave.profileId;
    nullingProfileApplied = true;
    logPrintf("GLD_NULLING_SINGLE_SAVE=OK channel=%d success=%u profileId=%u\n",
              channel, 1u, toSave.profileId);
    emitCommandAck("RUN_NULLING_SINGLE", "ok", "channel nulled", false);
}

// Diagnostic voltage-vs-DAC-code sweep for one channel, used by the QC tab's
// "Full Scale Nulling" popup to show the operator the sensor's full response
// curve. Does not alter the persisted nulling profile - the DAC is restored
// to that channel's currently-nulled code (or 0 if never nulled) once the
// sweep finishes.
void onRunFullScaleSweepJson(const char* payload) {
    StaticJsonDocument<96> doc;
    if (deserializeJson(doc, payload)) {
        emitCommandAck("RUN_FULLSCALE_SWEEP", "error", "invalid json", false);
        return;
    }
    if (!doc.containsKey("channel")) {
        emitCommandAck("RUN_FULLSCALE_SWEEP", "rejected", "channel is required", false);
        return;
    }
    const int channel = doc["channel"].as<int>();
    if (channel < 0 || channel >= pgl::gld::board::SENSOR_COUNT) {
        emitCommandAck("RUN_FULLSCALE_SWEEP", "rejected", "channel must be 0..7", false);
        return;
    }
    if (!ensureNullingHardwareReady()) {
        emitCommandAck("RUN_FULLSCALE_SWEEP", "error", "ADS/DAC not ready", false);
        return;
    }

    pgl::gld::GldNullingProfile existing{};
    const bool hadExisting = pgl::gld::loadNullingProfile(existing);
    const uint16_t restoreCode = (hadExisting && existing.channelOk[channel]) ? existing.dacCode[channel] : 0;

    emitCommandAck("RUN_FULLSCALE_SWEEP", "ok", "running full scale sweep", false);
    // firmwareServiceTick (not bare checkSerial) - a full 4096-code sweep runs
    // well past the external TPL5010 watchdog's keepalive window, so the tick
    // function must also pulse the watchdog (see maintainWdtKeepalive) or the
    // board hard-resets mid-sweep.
    const pgl::gld::GldFullScaleSweepResult result = pgl::gld::runFullScaleSweep(
        ads, dac, static_cast<uint8_t>(channel), restoreCode, 1, nullingLogLine, firmwareServiceTick);
    if (!result.success) {
        dacReady = false;
        nullingProfileApplied = false;
        nullingProfileId = 0;
        logPrintf("GLD_FULLSCALE_SWEEP_RESULT=FAIL channel=%d status=%s restoreCode=%u runtimeInvalidated=1\n",
                  channel,
                  pgl::gld::gldNullingStatusName(result.status),
                  result.restoredCode);
    } else {
        logPrintf("GLD_FULLSCALE_SWEEP_RESULT=PASS channel=%d restoreCode=%u\n",
                  channel, result.restoredCode);
    }
}

void handleSerialCommand(const pgl::gld::GldSerialCommand& command) {
    switch (command.type) {
        case pgl::gld::GldSerialCommandType::Unknown:
            onUnknownSerialCommand(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetMode:
            onModeCmd(command.mode);
            break;
        case pgl::gld::GldSerialCommandType::DebugOn:
            onDebugCmd(true);
            break;
        case pgl::gld::GldSerialCommandType::DebugOff:
            onDebugCmd(false);
            break;
        case pgl::gld::GldSerialCommandType::AppPing:
            emitCommandAck("APP_PING", "ok", "pong", false);
            break;
        case pgl::gld::GldSerialCommandType::GetInfo:
            emitInfoJson();
            break;
        case pgl::gld::GldSerialCommandType::GetStatus:
            emitStatusJson();
            break;
        case pgl::gld::GldSerialCommandType::Restart:
            restartFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::RunBootCheck:
            runBootCheckFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::RunAdsMcpSweep:
            runAdsMcpSweepFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::SleepNow:
            sleepNowFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::ServiceHoldOff:
            serviceHoldOffFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::SetAppConfigJson:
            onSetAppConfigJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetDeviceIdJson:
            onSetDeviceIdJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetChAddressJson:
            onSetChAddressJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetLoraConfigJson:
            onSetLoraConfigJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetNullingConfigJson:
            onSetNullingConfigJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetQcResultJson:
            onSetQcResultJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::GetQcStatus:
            emitQcStatusJson();
            break;
        case pgl::gld::GldSerialCommandType::RunNullingSingleJson:
            onRunNullingSingleJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::ResetQcResultJson:
            onResetQcResultJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::ResetQcAll:
            onResetQcAll();
            break;
        case pgl::gld::GldSerialCommandType::RunFullScaleSweepJson:
            onRunFullScaleSweepJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::InjectTplDone:
            injectTplDoneFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::InjectTplClr:
            injectTplClrFromSerialCommand();
            break;
        case pgl::gld::GldSerialCommandType::None:
        default:
            break;
    }
}

// Check Serial every loop tick for operator/app commands.
// Guarded against re-entrancy: long-running command handlers (e.g. RUN_BOOT_CHECK)
// call firmwareServiceTick() internally to keep the WDT fed and stay responsive,
// which would otherwise let a newly arrived command dispatch itself from deep
// inside an already-executing handler and blow the loopTask stack. While a
// command is being handled, any serial bytes that arrive stay queued in the
// UART buffer and are picked up on the next non-reentrant call.
//
// RESTART is the one exception: it is checked and actioned unconditionally,
// even from a reentrant call deep inside a multi-minute nulling or full-scale
// sweep tick loop, so a stuck or very long-running sweep can never leave the
// board unrecoverable from software until it finishes or is power-cycled -
// ESP.restart() never returns, so there is no stack to unwind. Any other
// command parsed while already nested is stashed in a single slot and
// drained once nesting unwinds, so it is only delayed, never lost.
void checkSerial() {
    static bool inProgress = false;
    static pgl::gld::GldSerialCommand pendingCommand{};
    static bool hasPending = false;

    if (!hasPending) {
        pgl::gld::GldSerialCommand parsed{};
        if (pgl::gld::parseSerialCommand(parsed)) {
            if (parsed.type == pgl::gld::GldSerialCommandType::Restart) {
                restartFromSerialCommand();
                return;  // unreachable in practice - ESP.restart() reboots immediately
            }
            pendingCommand = parsed;
            hasPending = true;
        }
    }

    if (inProgress) {
        return;
    }
    inProgress = true;
    for (uint8_t i = 0; i < 8; ++i) {
        pgl::gld::GldSerialCommand command{};
        if (hasPending) {
            command = pendingCommand;
            hasPending = false;
        } else if (!pgl::gld::parseSerialCommand(command)) {
            break;
        }
        if (command.type == pgl::gld::GldSerialCommandType::Restart) {
            restartFromSerialCommand();
            return;
        }
        handleSerialCommand(command);
    }
    inProgress = false;
}

void pulseWdtKeepaliveNow() {
    const bool serviceHoldRequested = serviceHoldActive ||
        batteryPersistenceFaultHold ||
        digitalRead(pgl::gld::board::PIN_USER_BUTTON) == LOW ||
        !cfgButtonRawHigh || cfgButtonPressArmed;
    if (batteryPowerMode && !TFBG_CONTINUOUS_BATTERY && !serviceHoldRequested) {
        lastWdtKeepaliveMs = millis();
        return;
    }
    pgl::gld::pulseGldTpl5010Keepalive();
    lastWdtKeepaliveMs = millis();
}

void maintainWdtKeepalive() {
    const bool serviceHoldRequested = serviceHoldActive ||
        batteryPersistenceFaultHold ||
        digitalRead(pgl::gld::board::PIN_USER_BUTTON) == LOW ||
        !cfgButtonRawHigh || cfgButtonPressArmed;
    if (batteryPowerMode && !TFBG_CONTINUOUS_BATTERY && !serviceHoldRequested) return;
    const uint32_t now = millis();
    if (now - lastWdtKeepaliveMs >= pgl::gld::GLD_WDT_KEEPALIVE_INTERVAL_MS) {
        pulseWdtKeepaliveNow();
    }
}

bool serviceHoldBlocksClr() {
    // LOW immediately inhibits CLR, even before the release edge has completed
    // the persistent toggle. This prevents the board powering off while the
    // operator is still holding CFG and waiting to release it.
    const bool cfgLowNow = digitalRead(pgl::gld::board::PIN_USER_BUTTON) == LOW;
    return batteryPowerMode &&
           (serviceHoldActive || batteryPersistenceFaultHold ||
            cfgLowNow || !cfgButtonRawHigh || cfgButtonPressArmed);
}

void blinkServiceHoldEnabled() {
#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8
    // IO39 is the active-low status LED on this production profile. On the
    // legacy profile GPIO39 is LoRa RST, so this indication is compiled out.
    for (uint8_t i = 0; i < 2; ++i) {
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_ON);
        delay(120);
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
        delay(120);
    }
    digitalWrite(pgl::gld::board::PIN_STATUS_LED,
                 lastAlarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
#endif
}

void setServiceHoldActive(bool active, const char* source) {
    if (serviceHoldActive == active) {
        logPrintf("GLD_SERVICE_HOLD state=%s source=%s unchanged=1\n",
                  active ? "ON" : "OFF", source != nullptr ? source : "unknown");
        return;
    }

    serviceHoldActive = active;
    const bool persisted = pgl::gld::writeGldServiceHold(active);
    logPrintf("GLD_SERVICE_HOLD state=%s source=%s persisted=%u batteryMode=%u session=%s\n",
              active ? "ON" : "OFF",
              source != nullptr ? source : "unknown",
              persisted ? 1u : 0u,
              batteryPowerMode ? 1 : 0,
              batterySessionStateName(batterySessionState));

    if (active) {
        blinkServiceHoldEnabled();
        if (batteryPowerMode) {
            // Feed TPL5010 immediately, then maintainWdtKeepalive() continues
            // every 10 seconds while CLR is inhibited for service/upload.
            pulseWdtKeepaliveNow();
        }
    }
}

void beginServiceHoldButton() {
    pinMode(pgl::gld::board::PIN_USER_BUTTON, INPUT_PULLUP);
    const bool initialHigh = digitalRead(pgl::gld::board::PIN_USER_BUTTON) == HIGH;
    cfgButtonRawHigh = initialHigh;
    cfgButtonStableHigh = initialHigh;
    // If the operator deliberately holds CFG through boot, releasing it is the
    // first valid RISING event. Pin setup runs after the 1-second rail settle,
    // so the VCC ramp itself cannot arm this path.
    cfgButtonPressArmed = !initialHigh;
    cfgButtonRawChangedMs = millis();
    logPrintf("GLD_CFG_BUTTON_INIT level=%s pressArmed=%u serviceHold=%u\n",
              initialHigh ? "HIGH" : "LOW",
              cfgButtonPressArmed ? 1 : 0,
              serviceHoldActive ? 1 : 0);
}

void maintainServiceHoldButton() {
    if (!batteryPowerMode) return;

    const uint32_t now = millis();
    const bool rawHigh = digitalRead(pgl::gld::board::PIN_USER_BUTTON) == HIGH;
    if (rawHigh != cfgButtonRawHigh) {
        cfgButtonRawHigh = rawHigh;
        cfgButtonRawChangedMs = now;
        return;
    }
    if (rawHigh == cfgButtonStableHigh || now - cfgButtonRawChangedMs < CFG_BUTTON_DEBOUNCE_MS) {
        return;
    }

    cfgButtonStableHigh = rawHigh;
    if (!cfgButtonStableHigh) {
        cfgButtonPressArmed = true;
        logPrintln("GLD_CFG_BUTTON event=PRESS level=LOW");
        return;
    }

    if (cfgButtonPressArmed) {
        cfgButtonPressArmed = false;
        logPrintln("GLD_CFG_BUTTON event=RELEASE level=HIGH rising=1");
        setServiceHoldActive(!serviceHoldActive, "cfg_release");
    }
}

bool batteryRuntimeReady() {
    if (FIELDTEST_MODEL_UNVERIFIED) {
        return adsReady && radioReady;
    }
    return adsReady && radioReady && mlReady && nullingProfileApplied && modelProfileReady;
}

void startBatteryInferenceSession() {
    const uint32_t now = millis();
    batterySessionState = BatterySessionState::Warmup;
    batterySessionStartedMs = now;
    batteryStateStartedMs = now;
    batteryLastSampleAttemptMs = now;
    batteryLastWarmupPrimeMs = 0;
    batteryNextTxAttemptMs = 0;
    batteryValidSampleBatches = 0;
    batteryAlarmTxAttempts = 0;
    batteryAlarmAckReceived = false;
    batteryCyclePoweredOff = false;
    snprintf(batteryCompletionReason, sizeof(batteryCompletionReason), "session_running");
    logPrintf("GLD_BATTERY_SESSION_START warmupMs=%lu validBatches=%u sampleIntervalMs=%lu alarmTxAttempts=%u rxWindowMs=%lu deadlineMs=%lu pendingAlarm=%u serviceHold=%u\n",
              static_cast<unsigned long>(BATTERY_SENSOR_WARMUP_MS),
              static_cast<unsigned>(BATTERY_VALID_SAMPLE_BATCHES),
              static_cast<unsigned long>(SCAN_INTERVAL_MS),
              static_cast<unsigned>(BATTERY_ALARM_TX_ATTEMPTS),
              static_cast<unsigned long>(LORA_RX_WINDOW_MS),
              static_cast<unsigned long>(BATTERY_SESSION_DEADLINE_MS),
              batteryPendingAlarm.active ? 1 : 0,
              serviceHoldActive ? 1 : 0);
}

const char* batteryRuntimeBlockReason() {
    if (!adsReady) return "ads_not_ready";
    if (!radioReady) return "radio_not_ready";
    if (FIELDTEST_MODEL_UNVERIFIED) return "none";
    if (!mlReady) return "ml_not_ready";
    if (!nullingProfileApplied) return "nulling_profile_not_applied";
    if (!modelProfileReady) return "model_profile_unapproved_or_mismatch";
    return "none";
}

void armBatteryFaultPowerOff(const char* reason) {
    if (batteryFaultPowerOffArmed) return;
    batteryFaultPowerOffArmed = true;
    batteryFaultPowerOffDueMs = millis() + BATTERY_FAULT_SERIAL_HOLD_MS;
    logPrintf("GLD_BATTERY_SESSION_WAIT reason=%s delayMs=%lu adsReady=%u radioReady=%u mlReady=%u\n",
              reason != nullptr ? reason : "hardware_not_ready",
              static_cast<unsigned long>(BATTERY_FAULT_SERIAL_HOLD_MS),
              adsReady ? 1 : 0,
              radioReady ? 1 : 0,
              mlReady ? 1 : 0);
}

void enterBatteryPersistenceFaultHold(const char* reason) {
    batteryPersistenceFaultHold = true;
    batteryPersistenceRetryDueMs = millis() + BATTERY_ALARM_RETRY_DELAY_MS;
    batterySessionState = BatterySessionState::CompleteHeld;
    batteryStateStartedMs = millis();
    snprintf(batteryCompletionReason, sizeof(batteryCompletionReason), "%s",
             reason != nullptr ? reason : "persistence_fault");
    logPrintf("GLD_BATTERY_PERSISTENCE_HOLD reason=%s retryMs=%lu clrBlocked=1\n",
              batteryCompletionReason,
              static_cast<unsigned long>(BATTERY_ALARM_RETRY_DELAY_MS));
    pulseWdtKeepaliveNow();
}

void completeBatterySessionAndPowerOff(const char* reason) {
    if (batteryCyclePoweredOff || batterySessionState == BatterySessionState::PowerOffIssued) return;

    if (FIELDTEST_MODEL_UNVERIFIED) {
        logPrintf("GLD_FIELDTEST_POWER_OFF_SUPPRESSED reason=%s action=continuous_keepalive\n",
                  reason != nullptr ? reason : "session_done");
        pulseWdtKeepaliveNow();
        return;
    }

    snprintf(batteryCompletionReason, sizeof(batteryCompletionReason), "%s",
             reason != nullptr ? reason : "session_done");
    if (serviceHoldBlocksClr()) {
        if (batterySessionState != BatterySessionState::CompleteHeld) {
            batterySessionState = BatterySessionState::CompleteHeld;
            batteryStateStartedMs = millis();
            logPrintf("GLD_BATTERY_SESSION_HELD reason=%s clrBlocked=1 holdEffective=1 serviceHold=%u cfgLow=%u\n",
                      batteryCompletionReason,
                      serviceHoldActive ? 1 : 0,
                      cfgButtonRawHigh ? 0 : 1);
            pulseWdtKeepaliveNow();
        }
        return;
    }

    logPrintf("GLD_BATTERY_SESSION_DONE power_off reason=%s done=LOW_HIGH_LOW donePulseUs=%lu doneToClrDelayUs=%lu clr=HIGH_LOW_HIGH clrPulseUs=%lu\n",
              batteryCompletionReason,
              static_cast<unsigned long>(pgl::gld::GLD_TPL5010_DONE_PULSE_US),
              static_cast<unsigned long>(pgl::gld::GLD_DONE_TO_CLR_DELAY_US),
              static_cast<unsigned long>(pgl::gld::GLD_POWER_LATCH_CLEAR_PULSE_US));
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    if (serviceHoldBlocksClr()) {
        batterySessionState = BatterySessionState::CompleteHeld;
        batteryStateStartedMs = millis();
        logPrintf("GLD_BATTERY_SESSION_POWER_OFF_ABORT reason=%s cfgLowOrHold=1 action=complete_held\n",
                  batteryCompletionReason);
        pulseWdtKeepaliveNow();
        return;
    }
    batteryCyclePoweredOff = true;
    batterySessionState = BatterySessionState::PowerOffIssued;
    batteryStateStartedMs = millis();
    pgl::gld::pulseGldTpl5010DoneThenPowerLatchClear();
}

void applyRuntimePowerReading(const pgl::gld::GldPowerReading& power,
                              const char* source,
                              bool immediate = false) {
    const bool requestedBatteryMode = TFBG_CONTINUOUS_BATTERY || !power.externalPower;
    if (requestedBatteryMode == batteryPowerMode) {
        powerModeCandidateCount = 0;
        powerModeCandidateBattery = requestedBatteryMode;
        return;
    }

    if (!immediate) {
        if (powerModeCandidateCount == 0 ||
            powerModeCandidateBattery != requestedBatteryMode) {
            powerModeCandidateBattery = requestedBatteryMode;
            powerModeCandidateCount = 1;
            return;
        }
        if (powerModeCandidateCount < POWER_RECONCILE_STABLE_SAMPLES) {
            ++powerModeCandidateCount;
        }
        if (powerModeCandidateCount < POWER_RECONCILE_STABLE_SAMPLES) {
            return;
        }
    }

    const bool previousBatteryMode = batteryPowerMode;
    batteryPowerMode = requestedBatteryMode;
    powerModeCandidateCount = 0;
    logPrintf("GLD_POWER_TRANSITION source=%s fromBattery=%u toBattery=%u mode=%s batterySense=%s ambiguous=%u batteryMv=%u\n",
              source != nullptr ? source : "runtime",
              previousBatteryMode ? 1u : 0u,
              batteryPowerMode ? 1u : 0u,
              pgl::gld::gldPowerModeName(power.mode),
              pgl::gld::gldBatterySenseStatusName(power.batterySenseStatus),
              power.powerSourceAmbiguous ? 1u : 0u,
              power.batteryMv);

    if (batteryPowerMode) {
        if (currentMode != pgl::gld::GldMode::INFERENCE) {
            const bool persisted = pgl::gld::writeGldMode(pgl::gld::GldMode::INFERENCE);
            powerTransitionShutdownPending = true;
            logPrintf("MODE_POWER_TRANSITION_BLOCK mode=%s nextMode=inference persisted=%u action=power_off\n",
                      pgl::gld::gldModeName(currentMode), persisted ? 1u : 0u);
            completeBatterySessionAndPowerOff("unsupported_mode_power_transition");
            return;
        }
        if (!TFBG_CONTINUOUS_BATTERY) {
            startBatteryInferenceSession();
        }
        return;
    }

    // External power returned before CLR: cancel the one-shot state so an
    // in-flight battery session cannot cut a newly restored external rail.
    powerTransitionShutdownPending = false;
    batteryPersistenceFaultHold = false;
    batterySessionState = BatterySessionState::Inactive;
    batteryFaultPowerOffArmed = false;
    batteryCyclePoweredOff = false;
    logPrintln("GLD_BATTERY_SESSION_CANCEL reason=external_power_restored clrInhibited=1");
}

void reconcileRuntimePowerMode() {
    const uint32_t now = millis();
    if (now - lastPowerReconcileMs < POWER_RECONCILE_INTERVAL_MS) {
        return;
    }
    lastPowerReconcileMs = now;
    applyRuntimePowerReading(pgl::gld::readGldPower(), "periodic", false);
}

void firmwareServiceTick() {
    maintainServiceHoldButton();
    checkSerial();
    maintainWdtKeepalive();
}

void serviceDelay(uint32_t durationMs) {
    const uint32_t startedMs = millis();
    while (millis() - startedMs < durationMs) {
        firmwareServiceTick();
        const uint32_t elapsedMs = millis() - startedMs;
        const uint32_t remainingMs = durationMs > elapsedMs ? durationMs - elapsedMs : 0;
        delay(remainingMs > 50 ? 50 : remainingMs);
    }
    firmwareServiceTick();
}

// ---------------------------------------------------------------------------
// Common hardware init (all modes)
// ---------------------------------------------------------------------------

bool isValidBoardPin(int pin) {
    return pin >= 0;
}

void optionalPinMode(int pin, uint8_t mode) {
    if (isValidBoardPin(pin)) {
        pinMode(static_cast<uint8_t>(pin), mode);
    }
}

void optionalDigitalWrite(int pin, uint8_t value) {
    if (isValidBoardPin(pin)) {
        digitalWrite(static_cast<uint8_t>(pin), value);
    }
}

void setupPins() {
    pinMode(pgl::gld::board::PIN_LORA_CS,    OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_CS,    HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RST,   OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_RST,   HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_RXEN,  LOW);
    pinMode(pgl::gld::board::PIN_LORA_TXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_TXEN,  LOW);
    optionalPinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT); optionalDigitalWrite(pgl::gld::board::PIN_ALARM_LAMP, ACTIVE_LOW_OUTPUT_OFF);
    optionalPinMode(pgl::gld::board::PIN_BUZZER,     OUTPUT); optionalDigitalWrite(pgl::gld::board::PIN_BUZZER,     ACTIVE_LOW_OUTPUT_OFF);
    optionalPinMode(pgl::gld::board::PIN_DC_FAN,     OUTPUT); optionalDigitalWrite(pgl::gld::board::PIN_DC_FAN,     LOW);
    optionalPinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT); optionalDigitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
}

const char* passFail(bool ok) {
    return ok ? "PASS" : "FAIL";
}

const char* okNotOk(bool ok) {
    return ok ? "OK" : "NOT_OK";
}

const char* checkedOkNotOk(bool checked, bool ok) {
    return checked ? okNotOk(ok) : "SKIP";
}

struct BootAdsReport {
    bool ok = false;
    const char* reason = "not_checked";
    int drdyLevel = -1;
    int drdyPulldownLevel = -1;
    int drdyPullupLevel = -1;
    int misoPulldownLevel = -1;
    int misoPullupLevel = -1;
    int csLevel = -1;
    int syncLevel = -1;
    uint8_t status = 0;
    uint8_t mux = 0;
    uint8_t adcon = 0;
    uint8_t drate = 0;
};

struct BootI2cReport {
    bool tcaOk = false;
    bool mcpOk[pgl::gld::board::SENSOR_COUNT]{};
    uint8_t mcpAddrMask[pgl::gld::board::SENSOR_COUNT]{};
    uint8_t mcpOkCount = 0;
};

struct BootMcpControlReport {
    bool tested = false;
    bool dacReady = false;
    bool writeLow[pgl::gld::board::SENSOR_COUNT]{};
    bool writeHigh[pgl::gld::board::SENSOR_COUNT]{};
};

struct BootDiagnosticsResult {
    BootAdsReport ads;
    BootI2cReport i2c;
    BootMcpControlReport mcpControl;
};

uint8_t bootBoolMask(const bool values[pgl::gld::board::SENSOR_COUNT]);

const char* bootReportFailureReason(const BootAdsReport& adsReport,
                                    const BootI2cReport& i2cReport,
                                    const BootMcpControlReport& mcpControl,
                                    bool radioChecked,
                                    bool radioOk,
                                    bool mlChecked,
                                    bool mlOk) {
    if (!adsReport.ok) return "ads_boot_fail";
    if (!i2cReport.tcaOk) return "tca_boot_fail";
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        const bool mcpOk = mcpControl.tested
                               ? i2cReport.mcpOk[sensor] &&
                                     mcpControl.dacReady &&
                                     mcpControl.writeLow[sensor] &&
                                     mcpControl.writeHigh[sensor]
                               : i2cReport.mcpOk[sensor];
        if (!mcpOk) return "mcp_boot_fail";
    }
    if (radioChecked && !radioOk) return "lora_boot_fail";
    if (mlChecked && !mlOk) return "ml_boot_fail";
    return nullptr;
}

bool bootReportHasNonAdsFailure(const BootI2cReport& i2cReport,
                                const BootMcpControlReport& mcpControl,
                                bool radioChecked,
                                bool radioOk,
                                bool mlChecked,
                                bool mlOk) {
    if (!i2cReport.tcaOk) return true;
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        const bool mcpOk = mcpControl.tested
                               ? i2cReport.mcpOk[sensor] &&
                                     mcpControl.dacReady &&
                                     mcpControl.writeLow[sensor] &&
                                     mcpControl.writeHigh[sensor]
                               : i2cReport.mcpOk[sensor];
        if (!mcpOk) return true;
    }
    if (radioChecked && !radioOk) return true;
    if (mlChecked && !mlOk) return true;
    return false;
}

void armBootReportRecoveryIfNeeded(const BootAdsReport& adsReport,
                                   const BootI2cReport& i2cReport,
                                   const BootMcpControlReport& mcpControl,
                                   bool radioChecked,
                                   bool radioOk,
                                   bool mlChecked,
                                   bool mlOk) {
    const char* reason = bootReportFailureReason(adsReport, i2cReport, mcpControl,
                                                 radioChecked, radioOk, mlChecked, mlOk);
    if (reason == nullptr) {
        bootRecoveryArmed = false;
        bootRecoveryRestartAllowed = false;
        bootRecoveryNonAdsFailure = false;
        bootRecoveryRestartCount = 0;
        copyBounded(bootRecoveryReason, sizeof(bootRecoveryReason), "none");
        return;
    }

    bootRecoveryArmed = true;
    bootRecoveryNonAdsFailure = bootReportHasNonAdsFailure(i2cReport, mcpControl,
                                                           radioChecked, radioOk,
                                                           mlChecked, mlOk);
    bootRecoveryRestartAllowed = bootRecoveryNonAdsFailure || !adsReport.ok;
    bootRecoveryDueMs = millis() + BOOT_RECOVERY_DELAY_MS;
    copyBounded(bootRecoveryReason, sizeof(bootRecoveryReason), reason);
    setRecoveryReason(reason);
    logPrintf("BOOT_RECOVERY_ARM reason=%s delayMs=%lu restartCount=%u maxRestart=%u\n",
              bootRecoveryReason,
              static_cast<unsigned long>(BOOT_RECOVERY_DELAY_MS),
              static_cast<unsigned>(bootRecoveryRestartCount),
              static_cast<unsigned>(BOOT_RECOVERY_MAX_RESTARTS));
}

void maintainBootReportRecovery() {
    if (!bootRecoveryArmed) return;
    if (static_cast<int32_t>(millis() - bootRecoveryDueMs) < 0) return;

    bootRecoveryArmed = false;
    logPrintf("BOOT_RECOVERY_DUE reason=%s adsReady=%u restartCount=%u\n",
              bootRecoveryReason,
              adsReady ? 1 : 0,
              static_cast<unsigned>(bootRecoveryRestartCount));

    if (!adsReady) {
        setRecoveryReason("boot_report_ads_retry");
        logPrintln("BOOT_RECOVERY_RETRY target=ADS1256");
        const bool ok = ads.begin(gldSpi);
        adsReady = ok;
        if (ok) {
            ++adsRecoveryCount;
            adsReadFailStreak = 0;
            logPrintf("BOOT_RECOVERY_RETRY_RESULT target=ADS1256 result=OK count=%lu\n",
                      static_cast<unsigned long>(adsRecoveryCount));
            if (!bootRecoveryNonAdsFailure) {
                bootRecoveryRestartAllowed = false;
                copyBounded(bootRecoveryReason, sizeof(bootRecoveryReason), "none");
                logPrintln("BOOT_RECOVERY_CLEAR reason=ads_retry_ok");
                return;
            }
        } else {
            ++adsRecoveryFailCount;
            logPrintf("BOOT_RECOVERY_RETRY_RESULT target=ADS1256 result=FAIL failCount=%lu\n",
                      static_cast<unsigned long>(adsRecoveryFailCount));
        }
    }

    if (!bootRecoveryRestartAllowed) return;
    if (!bootRecoveryNonAdsFailure && adsReady) return;
    if (bootRecoveryRestartCount >= BOOT_RECOVERY_MAX_RESTARTS) {
        logPrintf("BOOT_RECOVERY_RESTART_SUPPRESSED reason=%s restartCount=%u maxRestart=%u\n",
                  bootRecoveryReason,
                  static_cast<unsigned>(bootRecoveryRestartCount),
                  static_cast<unsigned>(BOOT_RECOVERY_MAX_RESTARTS));
        return;
    }

    ++bootRecoveryRestartCount;
    logPrintf("BOOT_RECOVERY_RESTART reason=%s restartCount=%u delayMs=%lu\n",
              bootRecoveryReason,
              static_cast<unsigned>(bootRecoveryRestartCount),
              static_cast<unsigned long>(BOOT_RECOVERY_DELAY_MS));
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    ESP.restart();
}

bool i2cAck(uint8_t addr) {
    firmwareServiceTick();
    Wire.beginTransmission(addr);
    const bool ok = Wire.endTransmission() == 0;
    firmwareServiceTick();
    return ok;
}

bool tcaSelect(uint8_t muxChannel) {
    if (muxChannel > 7) return false;
    firmwareServiceTick();
    Wire.beginTransmission(pgl::gld::board::TCA9548A_ADDR);
    Wire.write(static_cast<uint8_t>(1U << muxChannel));
    const bool ok = Wire.endTransmission() == 0;
    firmwareServiceTick();
    return ok;
}

void tcaDisableAll() {
    firmwareServiceTick();
    Wire.beginTransmission(pgl::gld::board::TCA9548A_ADDR);
    Wire.write(static_cast<uint8_t>(0));
    Wire.endTransmission();
    firmwareServiceTick();
}

void probeInputPullLevels(int pin, int& pulldownLevel, int& pullupLevel) {
    pinMode(static_cast<uint8_t>(pin), INPUT_PULLDOWN);
    delay(2);
    pulldownLevel = digitalRead(pin);
    pinMode(static_cast<uint8_t>(pin), INPUT_PULLUP);
    delay(2);
    pullupLevel = digitalRead(pin);
    pinMode(static_cast<uint8_t>(pin), INPUT);
}

uint8_t readAdsRegisterRawNoWait(uint8_t reg) {
    firmwareServiceTick();
    gldSpi.beginTransaction(SPISettings(ADS1256_SPI_HZ, MSBFIRST, SPI_MODE1));
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, LOW);
    delayMicroseconds(5);
    gldSpi.transfer(static_cast<uint8_t>(ADS1256_RREG_CMD | (reg & 0x0F)));
    gldSpi.transfer(0x00);
    delayMicroseconds(5);
    const uint8_t value = gldSpi.transfer(0xFF);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    gldSpi.endTransaction();
    firmwareServiceTick();
    return value;
}

BootAdsReport probeBootAds(bool ok) {
    BootAdsReport report{};
    report.ok = ok;
    report.drdyLevel = digitalRead(pgl::gld::board::PIN_ADS1256_DRDY);
    report.csLevel = digitalRead(pgl::gld::board::PIN_ADS1256_CS);
    report.syncLevel = digitalRead(pgl::gld::board::PIN_ADS1256_SYNC);
    report.reason = ok ? "ok" : (report.drdyLevel == HIGH ? "drdy_timeout" : "init_failed");
    report.status = readAdsRegisterRawNoWait(ADS1256_REG_STATUS);
    report.mux = readAdsRegisterRawNoWait(ADS1256_REG_MUX);
    report.adcon = readAdsRegisterRawNoWait(ADS1256_REG_ADCON);
    report.drate = readAdsRegisterRawNoWait(ADS1256_REG_DRATE);
    probeInputPullLevels(
        pgl::gld::board::PIN_ADS1256_DRDY,
        report.drdyPulldownLevel,
        report.drdyPullupLevel);
    probeInputPullLevels(
        pgl::gld::board::PIN_SPI_MISO,
        report.misoPulldownLevel,
        report.misoPullupLevel);
    return report;
}

uint8_t scanMcpAddressMaskOnSelectedMux() {
    uint8_t mask = 0;
    for (uint8_t offset = 0; offset < 8; ++offset) {
        const uint8_t addr = static_cast<uint8_t>(pgl::gld::board::MCP4725_ADDR + offset);
        if (i2cAck(addr)) {
            mask |= static_cast<uint8_t>(1U << offset);
        }
    }
    return mask;
}

BootI2cReport probeBootI2c() {
    BootI2cReport report{};
    Wire.begin(pgl::gld::board::PIN_I2C_SDA, pgl::gld::board::PIN_I2C_SCL);
#if defined(ARDUINO_ARCH_ESP32)
    Wire.setTimeOut(BOOT_I2C_TIMEOUT_MS);
#endif
    firmwareServiceTick();
    report.tcaOk = i2cAck(pgl::gld::board::TCA9548A_ADDR);
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        firmwareServiceTick();
        const uint8_t muxChannel = static_cast<uint8_t>(pgl::gld::board::SENSOR_TO_MUX_CH[sensor]);
        const bool muxOk = report.tcaOk && tcaSelect(muxChannel);
        report.mcpAddrMask[sensor] = muxOk ? scanMcpAddressMaskOnSelectedMux() : 0;
        report.mcpOk[sensor] = (report.mcpAddrMask[sensor] & 0x01) != 0;
        if (report.mcpOk[sensor]) ++report.mcpOkCount;
    }
    tcaDisableAll();
    return report;
}

BootMcpControlReport testBootMcpControl(bool externalPower) {
    BootMcpControlReport report{};
    if (!externalPower) {
        return report;
    }

    report.tested = true;
    if (!dacReady) {
        (void)dac.begin(Wire);
        dacReady = dac.ready();
    }
    report.dacReady = dacReady;
    if (!dacReady) {
        return report;
    }

    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        bool lowOk = true;
        bool highOk = true;
        for (uint8_t offset = 0; offset < BOOT_MCP_TEST_EDGE_COUNT; ++offset) {
            const uint16_t lowCode = static_cast<uint16_t>(BOOT_MCP_TEST_LOW_START + offset);
            lowOk = dac.writeDac(sensor, lowCode) && lowOk;
            serviceDelay(BOOT_DAC_SETTLE_MS);
        }
        for (uint8_t offset = 0; offset < BOOT_MCP_TEST_EDGE_COUNT; ++offset) {
            const uint16_t highCode = static_cast<uint16_t>(BOOT_MCP_TEST_HIGH_START + offset);
            highOk = dac.writeDac(sensor, highCode) && highOk;
            serviceDelay(BOOT_DAC_SETTLE_MS);
        }
        report.writeLow[sensor] = lowOk;
        report.writeHigh[sensor] = highOk;
    }
    return report;
}

BootDiagnosticsResult runBootHardwareDiagnostics(bool externalPower) {
    BootDiagnosticsResult result{};

    logPrintln("BOOT_PROBE_ADS=start");
    adsReady = ads.begin(gldSpi);
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");
    result.ads = probeBootAds(adsReady);
    logPrintf("BOOT_PROBE_ADS=done adsReady=%u reason=%s drdy=%d pd=%d pu=%d misoPD=%d misoPU=%d cs=%d sync=%d status=0x%02X mux=0x%02X adcon=0x%02X drate=0x%02X\n",
              adsReady ? 1 : 0,
              result.ads.reason,
              result.ads.drdyLevel,
              result.ads.drdyPulldownLevel,
              result.ads.drdyPullupLevel,
              result.ads.misoPulldownLevel,
              result.ads.misoPullupLevel,
              result.ads.csLevel,
              result.ads.syncLevel,
              result.ads.status,
              result.ads.mux,
              result.ads.adcon,
              result.ads.drate);

    logPrintln("BOOT_PROBE_I2C=start");
    result.i2c = probeBootI2c();
    logPrintf("BOOT_PROBE_I2C=done tcaOk=%u mcpOkCount=%u/%u mcpMask=0x%02X\n",
              result.i2c.tcaOk ? 1 : 0,
              result.i2c.mcpOkCount,
              pgl::gld::board::SENSOR_COUNT,
              bootBoolMask(result.i2c.mcpOk));

    logPrintln("BOOT_PROBE_MCP_CONTROL=start");
    result.mcpControl = testBootMcpControl(externalPower);

    lastBootAdsDrdyLevel = result.ads.drdyLevel;
    lastBootAdsDrdyPulldownLevel = result.ads.drdyPulldownLevel;
    lastBootAdsDrdyPullupLevel = result.ads.drdyPullupLevel;
    lastBootAdsMisoPulldownLevel = result.ads.misoPulldownLevel;
    lastBootAdsMisoPullupLevel = result.ads.misoPullupLevel;
    lastBootAdsCsLevel = result.ads.csLevel;
    lastBootAdsSyncLevel = result.ads.syncLevel;
    lastBootAdsStatus = result.ads.status;
    lastBootAdsMux = result.ads.mux;
    lastBootAdsAdcon = result.ads.adcon;
    lastBootAdsDrate = result.ads.drate;
    lastBootAdsReason = result.ads.reason;
    lastBootTcaOk = result.i2c.tcaOk;
    lastBootMcpOkCount = result.i2c.mcpOkCount;
    lastBootMcpControlTested = result.mcpControl.tested;
    lastBootMcpControlOkCount = 0;
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        lastBootMcpOk[sensor] = result.i2c.mcpOk[sensor];
        lastBootMcpAddrMask[sensor] = result.i2c.mcpAddrMask[sensor];
        lastBootMcpControlOk[sensor] = result.mcpControl.dacReady &&
                                       result.mcpControl.writeLow[sensor] &&
                                       result.mcpControl.writeHigh[sensor];
        if (lastBootMcpControlOk[sensor]) {
            ++lastBootMcpControlOkCount;
        }
    }
    logPrintf("BOOT_PROBE_MCP_CONTROL=done tested=%u dacReady=%u writeOkCount=%u/%u writeMask=0x%02X\n",
              result.mcpControl.tested ? 1 : 0,
              result.mcpControl.dacReady ? 1 : 0,
              lastBootMcpControlOkCount,
              pgl::gld::board::SENSOR_COUNT,
              bootBoolMask(lastBootMcpControlOk));

    return result;
}

void bootTableRow(const char* ic, const char* check, const char* status, const char* detail) {
    logPrintf("| %-15s | %-18s | %-9s | %-40s |\n", ic, check, status, detail);
}

uint8_t bootBoolMask(const bool values[pgl::gld::board::SENSOR_COUNT]) {
    uint8_t mask = 0;
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        if (values[sensor]) {
            mask |= static_cast<uint8_t>(1U << sensor);
        }
    }
    return mask;
}

void printBootIcReport(const pgl::gld::GldPowerReading& power,
                       const BootAdsReport& adsReport,
                       const BootI2cReport& i2cReport,
                       const BootMcpControlReport& mcpControl,
                       bool radioChecked,
                       bool radioOk,
                       bool mlChecked,
                       bool mlOk,
                       int mlOutputSize,
                       bool modeReady,
                       const char* modeDetail) {
    char detail[256];

    logPrintln("[BOOT_IC_REPORT]");
    logPrintln("+-----------------+--------------------+-----------+------------------------------------------+");
    logPrintln("| IC/Fungsi       | Check              | Status    | Detail                                   |");
    logPrintln("+-----------------+--------------------+-----------+------------------------------------------+");

    snprintf(detail, sizeof(detail), "mode=%s external=%u batteryMv=%u",
             pgl::gld::gldPowerModeName(power.mode),
             power.externalPower ? 1 : 0,
             power.batteryMv);
    bootTableRow("POWER", "sense", "OK", detail);

    snprintf(detail, sizeof(detail), "SCK=%d MOSI=%d MISO=%d",
             pgl::gld::board::PIN_SPI_SCK,
             pgl::gld::board::PIN_SPI_MOSI,
             pgl::gld::board::PIN_SPI_MISO);
    bootTableRow("SPI_BUS", "pins", "OK", detail);

    snprintf(detail, sizeof(detail), "reason=%s DRDY=%d ST=0x%02X",
             adsReport.reason,
             adsReport.drdyLevel,
             adsReport.status);
    bootTableRow("ADS1256", "SPI begin", okNotOk(adsReport.ok), detail);

    snprintf(detail, sizeof(detail), "SDA=%d SCL=%d",
             pgl::gld::board::PIN_I2C_SDA,
             pgl::gld::board::PIN_I2C_SCL);
    bootTableRow("I2C_BUS", "pins", "OK", detail);

    snprintf(detail, sizeof(detail), "addr=0x%02X",
             pgl::gld::board::TCA9548A_ADDR);
    bootTableRow("TCA9548A", "I2C ACK", okNotOk(i2cReport.tcaOk), detail);

    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        char icName[24];
        snprintf(icName, sizeof(icName), "MCP4725-%s", pgl::gld::board::SENSOR_NAMES[sensor]);
        const bool testedOk = i2cReport.mcpOk[sensor] &&
                              mcpControl.dacReady &&
                              mcpControl.writeLow[sensor] &&
                              mcpControl.writeHigh[sensor];
        const char* status = mcpControl.tested
                                 ? (testedOk ? "OK_TESTED" : "NOT_OK")
                                 : okNotOk(i2cReport.mcpOk[sensor]);
        if (mcpControl.tested) {
            snprintf(detail, sizeof(detail), "mux=%u addr=0x%02X addrMask=0x%02X write=%u-%u,%u-%u",
                     static_cast<unsigned>(pgl::gld::board::SENSOR_TO_MUX_CH[sensor]),
                     pgl::gld::board::MCP4725_ADDR,
                     i2cReport.mcpAddrMask[sensor],
                     static_cast<unsigned>(BOOT_MCP_TEST_LOW_START),
                     static_cast<unsigned>(BOOT_MCP_TEST_LOW_END),
                     static_cast<unsigned>(BOOT_MCP_TEST_HIGH_START),
                     static_cast<unsigned>(BOOT_MCP_TEST_HIGH_END));
        } else {
            snprintf(detail, sizeof(detail), "mux=%u addr=0x%02X addrMask=0x%02X ack only",
                     static_cast<unsigned>(pgl::gld::board::SENSOR_TO_MUX_CH[sensor]),
                     pgl::gld::board::MCP4725_ADDR,
                     i2cReport.mcpAddrMask[sensor]);
        }
        bootTableRow(icName, mcpControl.tested ? "I2C+DAC write" : "I2C ACK", status, detail);
    }

    snprintf(detail, sizeof(detail), "NSS=%d DIO1=%d RST=%d BUSY=%d state=%d",
             pgl::gld::board::PIN_LORA_CS,
             pgl::gld::board::PIN_LORA_DIO1,
             pgl::gld::board::PIN_LORA_RST,
             pgl::gld::board::PIN_LORA_BUSY,
             static_cast<int>(lastLoraBeginState));
    bootTableRow("SX1262", "LoRa begin", checkedOkNotOk(radioChecked, radioOk), detail);

    snprintf(detail, sizeof(detail), "classes=%d model outputs", mlOutputSize);
    bootTableRow("ML_MODEL", "init/classes", checkedOkNotOk(mlChecked, mlOk), detail);

    bootTableRow("MODE_READY", pgl::gld::gldModeName(currentMode), okNotOk(modeReady), modeDetail);
    logPrintln("+-----------------+--------------------+-----------+------------------------------------------+");
}

// ---------------------------------------------------------------------------
// WiFi + MQTT helpers (dataset mode only)
// ---------------------------------------------------------------------------

void disableNetworkForOfflineMode(const char* reason) {
    if (mqtt.connected()) mqtt.disconnect();
    wifiClient.stop();
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    logPrintf("WIFI_OFF mode=%s reason=%s\n",
              pgl::gld::gldModeName(currentMode),
              reason != nullptr ? reason : "offline_mode");
}

bool connectWifi() {
    ++wifiReconnectCount;
    setRecoveryReason("wifi_connect");
    logPrintf("WIFI_CONNECT ssid=%s\n", runtimeConfig.wifiSsid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(runtimeConfig.wifiSsid, runtimeConfig.wifiPassword);
    const uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) {
        serviceDelay(50);
    }
    const bool ok = WiFi.status() == WL_CONNECTED;
    if (!ok) {
        ++wifiReconnectFailCount;
        setRecoveryReason("wifi_connect_failed");
    }
    logPrintf(ok ? "WIFI_CONNECTED ip=%s\n" : "WIFI_CONNECT_FAILED\n",
              ok ? WiFi.localIP().toString().c_str() : "");
    return ok;
}

void maintainWifi() {
    if (WiFi.status() != WL_CONNECTED) connectWifi();
}

// Forward declarations
bool mqttConnect();
void mqttCallback(char* topic, byte* payload, unsigned int length);

bool mqttConnect() {
    if (mqtt.connected()) return true;
    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_MS) return false;
    lastMqttAttemptMs = now;
    ++mqttReconnectCount;
    setRecoveryReason("mqtt_connect");
    mqtt.setServer(runtimeConfig.mqttHost, runtimeConfig.mqttPort);
    mqtt.setCallback(mqttCallback);
    logPrintf("MQTT_CONNECT host=%s port=%u\n", runtimeConfig.mqttHost, runtimeConfig.mqttPort);
    const bool ok = mqtt.connect(mqttClientId, runtimeConfig.mqttUser, runtimeConfig.mqttPass);
    lastMqttState = mqtt.state();
    if (!ok) {
        ++mqttConnectFailCount;
        setRecoveryReason("mqtt_connect_failed");
    }
    logPrintf("MQTT_CONNECT_RESULT=%s state=%d attempt=%lu failCount=%lu\n",
              ok ? "OK" : "FAIL",
              lastMqttState,
              static_cast<unsigned long>(mqttReconnectCount),
              static_cast<unsigned long>(mqttConnectFailCount));
    if (ok) {
        mqtt.subscribe(topicCmd);
        if (currentMode == pgl::gld::GldMode::DATASET) {
            mqtt.subscribe(topicDataset);
        }
    } else {
        wifiClient.stop();
    }
    return ok;
}

void maintainMqtt() {
    if (!mqtt.connected()) mqttConnect();
    else mqtt.loop();
}

// ---------------------------------------------------------------------------
// MQTT publish helpers
// ---------------------------------------------------------------------------

void publishCmdAck(const char* cmd, const char* result) {
    StaticJsonDocument<128> doc;
    doc["device_id"] = runtimeConfig.deviceId;
    doc["cmd"] = cmd;
    doc["result"] = result;
    doc["timestamp_ms"] = static_cast<uint32_t>(millis());
    char buf[128];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(topicAck, buf, false);
}

void publishDatasetStatus(const char* state, const char* detail) {
    StaticJsonDocument<384> doc;
    doc["device_id"] = runtimeConfig.deviceId;
    doc["stage"] = "DATASET";
    doc["state"] = state;
    doc["detail"] = detail;
    doc["queue_pending"] = datasetQueueCount;
    doc["queue_dropped"] = datasetQueueDropped;
    doc["publish_fail_count"] = datasetPublishFailCount;
    doc["rejected_samples"] = datasetRejectedSamples;
    doc["last_reject_reason"] =
        pgl::gld::gldDatasetRejectReasonName(lastDatasetRejectReason);
    doc["last_reject_channel"] = static_cast<int>(lastDatasetRejectChannel);
    doc["last_reject_ok_finite_count"] = lastDatasetRejectOkFiniteCount;
    doc["last_reject_status"] = lastDatasetRejectStatus;
    doc["last_reject_gain"] = lastDatasetRejectGain;
    doc["last_reject_saturated"] = lastDatasetRejectSaturated;
    char buf[384];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(topicStatus, buf, false);
}

void publishDatasetRejectedStatus(
    const pgl::gld::GldDatasetValidationResult& validation,
    const pgl::gld::GldDatasetChannelSample* samples,
    size_t count) {
    StaticJsonDocument<512> doc;
    doc["device_id"] = runtimeConfig.deviceId;
    doc["stage"] = "DATASET";
    doc["state"] = "sample_rejected";
    doc["detail"] = pgl::gld::gldDatasetRejectReasonName(validation.reason);
    doc["attempted_seq"] = datasetSeq;
    doc["rejected_samples"] = datasetRejectedSamples;
    doc["expected_channel_count"] = pgl::gld::GLD_DATASET_FEATURE_COUNT;
    doc["actual_channel_count"] = count;
    doc["ok_finite_count"] = validation.okFiniteCount;
    doc["channel"] = static_cast<int>(validation.channel);
    if (validation.channel >= 0 &&
        static_cast<size_t>(validation.channel) < count && samples != nullptr) {
        const size_t channel = static_cast<size_t>(validation.channel);
        const pgl::gld::GldDatasetChannelSample& sample = samples[channel];
        doc["expected_feature"] = pgl::gld::GLD_DATASET_CANONICAL_FEATURE_ORDER[channel];
        doc["actual_feature"] = sample.feature != nullptr ? sample.feature : "null";
        doc["sensor_status"] = sample.status;
        doc["gain"] = sample.gain;
        doc["saturated"] = sample.saturated;
        doc["finite"] = std::isfinite(sample.voltage);
    }
    char buf[512];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(topicStatus, buf, false);
}

void publishDatasetSummary() {
    StaticJsonDocument<384> doc;
    doc["device_id"] = runtimeConfig.deviceId;
    doc["stage"] = "DATASET";
    doc["label"] = currentLabel;
    doc["total_samples"] = datasetSeq;
    doc["duration_ms"] = static_cast<uint32_t>(millis() - sessionStartMs);
    doc["nulling_profile_id"] = nullingProfileId;
    doc["queue_pending"] = datasetQueueCount;
    doc["queue_dropped"] = datasetQueueDropped;
    doc["publish_fail_count"] = datasetPublishFailCount;
    doc["rejected_samples"] = datasetRejectedSamples;
    doc["last_reject_reason"] =
        pgl::gld::gldDatasetRejectReasonName(lastDatasetRejectReason);
    doc["last_reject_channel"] = static_cast<int>(lastDatasetRejectChannel);
    char buf[384];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(topicSummary, buf, false);
}

// ---------------------------------------------------------------------------
// MQTT callback — handles SET_MODE (all), dataset commands (dataset mode)
// ---------------------------------------------------------------------------

void handleCmdTopic(const char* payload, unsigned int length) {
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, payload, length)) return;
    const char* cmd = doc["cmd"] | "";
    if (strcmp(cmd, "SET_MODE") == 0) {
        const char* modeStr = doc["mode"] | "";
        publishCmdAck("SET_MODE", "ok");
        onModeCmd(pgl::gld::gldModeFromString(modeStr));
    }
}

void handleDatasetTopic(const char* payload, unsigned int length) {
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload, length)) {
        publishCmdAck("UNKNOWN", "parse_error");
        return;
    }
    const char* cmd = doc["cmd"] | "";
    if (strcmp(cmd, "SET_MODE") == 0) {
        const char* modeStr = doc["mode"] | "";
        publishCmdAck("SET_MODE", "ok");
        onModeCmd(pgl::gld::gldModeFromString(modeStr));
        return;
    }
    if (strcmp(cmd, "START_DATASET") == 0) {
        if (nullingProfileId == 0 || !nullingProfileApplied) {
            publishCmdAck("START_DATASET", "reject_no_profile");
            return;
        }
        const char* label = doc["label"] | "unknown";
        strncpy(currentLabel, label, sizeof(currentLabel) - 1);
        currentLabel[sizeof(currentLabel) - 1] = '\0';
        targetSamples    = doc["target_samples"]     | 0u;
        const uint32_t requestedSampleIntervalMs =
            doc["sample_interval_ms"] | DATASET_MIN_SAMPLE_INTERVAL_MS;
        sampleIntervalMs = requestedSampleIntervalMs < DATASET_MIN_SAMPLE_INTERVAL_MS
                               ? DATASET_MIN_SAMPLE_INTERVAL_MS
                               : requestedSampleIntervalMs;
        maxDurationMs    = doc["max_duration_ms"]    | 0u;
        useFanIntake     = doc["use_fan_intake"]     | true;
        fanOnMs          = doc["fan_on_ms"]          | 1000u;
        postFanSettleMs  = doc["post_fan_settle_ms"] | 0u;
        datasetSeq     = 0;
        datasetRejectedSamples = 0;
        lastDatasetRejectReason = pgl::gld::GldDatasetRejectReason::None;
        lastDatasetRejectChannel = -1;
        lastDatasetRejectOkFiniteCount = 0;
        lastDatasetRejectStatus = 0xFF;
        lastDatasetRejectGain = 0;
        lastDatasetRejectSaturated = false;
        sessionStartMs = millis();
        lastScanMs     = sessionStartMs;
        sampleStep     = SampleStep::None;
        datasetState   = DatasetState::Running;
        optionalDigitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_ON);
        publishCmdAck("START_DATASET", "ok");
        publishDatasetStatus("running", currentLabel);
        logPrintf("DATASET_START label=%s target=%lu interval=%lu\n",
                  currentLabel,
                  static_cast<unsigned long>(targetSamples),
                  static_cast<unsigned long>(sampleIntervalMs));
    } else if (strcmp(cmd, "STOP_DATASET") == 0) {
        if (datasetState == DatasetState::Running)
            optionalDigitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
        datasetState = DatasetState::Idle;
        sampleStep   = SampleStep::None;
        optionalDigitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
        publishCmdAck("STOP_DATASET", "ok");
        publishDatasetSummary();
        publishDatasetStatus("idle", "stopped");
        logPrintf("DATASET_STOP totalSeq=%lu\n", static_cast<unsigned long>(datasetSeq));
    } else {
        publishCmdAck(cmd, "unknown_cmd");
    }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, topicCmd) == 0) {
        handleCmdTopic(reinterpret_cast<const char*>(payload), length);
    } else if (strcmp(topic, topicDataset) == 0) {
        handleDatasetTopic(reinterpret_cast<const char*>(payload), length);
    }
}

// ---------------------------------------------------------------------------
// Nulling helpers
// ---------------------------------------------------------------------------

bool initNulling(bool runIfMissing) {
    nullingProfileApplied = false;
    pgl::gld::GldNullingProfile profile{};
    if (pgl::gld::loadNullingProfile(profile)) {
        logPrintf("NULLING_NVS_LOAD=found profileId=%u\n", profile.profileId);
        bool allApplied = true;
        for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
            allApplied = dac.writeDac(ch, profile.dacCode[ch]) && allApplied;
        }
        if (!allApplied) {
            nullingProfileId = 0;
            (void)dac.writeAll(0);
            logPrintln("NULLING_NVS_APPLY=FAIL safeReset=1");
            return false;
        }
        nullingProfileId = profile.profileId;
        nullingProfileApplied = true;
        return true;
    }
    if (!runIfMissing) {
        nullingProfileId = 0;
        logPrintln("NULLING_NVS_LOAD=empty auto_nulling=skip");
        return false;
    }
    logPrintln("NULLING_NVS_LOAD=empty running_nulling_now");
    const pgl::gld::GldNullingServiceResult result =
        pgl::gld::runNullingService(ads, dac, nullingLogLine, firmwareServiceTick, nullingConfig);
    logPrintf("NULLING_RUN status=%s successCount=%u\n",
              pgl::gld::gldNullingStatusName(result.status), result.successCount);
    if (result.status != pgl::gld::GldNullingStatus::Ok ||
        result.successCount != pgl::gld::board::SENSOR_COUNT) {
        return false;
    }
    pgl::gld::GldNullingProfile toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = 1;
    if (!pgl::gld::isNullingProfileValid(toSave)) {
        return false;
    }
    if (!pgl::gld::saveNullingProfile(toSave)) {
        return false;
    }
    bool allApplied = true;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        allApplied = dac.writeDac(ch, toSave.dacCode[ch]) && allApplied;
    }
    if (!allApplied) {
        nullingProfileId = 0;
        (void)dac.writeAll(0);
        return false;
    }
    nullingProfileId = toSave.profileId;
    nullingProfileApplied = true;
    return true;
}

const char* nullingRetryReason(pgl::gld::GldNullingStatus status) {
    switch (status) {
        case pgl::gld::GldNullingStatus::AdsNotReady:       return "ads_not_ready";
        case pgl::gld::GldNullingStatus::DacNotReady:       return "dac_not_ready";
        case pgl::gld::GldNullingStatus::AllChannelsFailed: return "all_channels_failed";
        case pgl::gld::GldNullingStatus::PartialSuccess:    return "partial_success";
        case pgl::gld::GldNullingStatus::Ok:                return "none";
    }
    return "unknown";
}

void armNullingRetry(const char* reason) {
    nullDone = false;
    nullingRetryArmed = true;
    const uint32_t now = millis();
    const uint32_t delayMs = bootRecoveryDelayActive()
                                 ? static_cast<uint32_t>(bootRecoveryDueMs - now)
                                 : NULLING_RETRY_DELAY_MS;
    nextNullingRetryMs = now + delayMs;
    logPrintf("NULLING_RETRY_SCHEDULED reason=%s delayMs=%lu\n",
              reason,
              static_cast<unsigned long>(delayMs));
}

bool ensureNullingHardwareReady() {
    if (!adsReady) {
        adsReady = ads.begin(gldSpi);
        logPrintf("NULLING_ADS_REBEGIN=%s\n", passFail(adsReady));
    }
    if (!dacReady) {
        dacReady = dac.begin(Wire);
        logPrintf("NULLING_DAC_REBEGIN=%s\n", passFail(dacReady));
    }
    return adsReady && dacReady;
}

bool saveCompleteNullingProfile(const pgl::gld::GldNullingServiceResult& result,
                                pgl::gld::GldNullingProfile& toSave) {
    if (result.status != pgl::gld::GldNullingStatus::Ok ||
        result.successCount != pgl::gld::board::SENSOR_COUNT) {
        return false;
    }

    pgl::gld::GldNullingProfile existing{};
    pgl::gld::loadNullingProfile(existing);
    if (pgl::gld::isNullingProfileValid(existing) && existing.profileId == UINT8_MAX) {
        logPrintln("NULLING_NVS_SAVE=FAIL reason=profile_id_exhausted");
        return false;
    }
    toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = static_cast<uint8_t>(
        pgl::gld::isNullingProfileValid(existing)
            ? static_cast<uint8_t>(existing.profileId + 1u) : 1u);
    if (!pgl::gld::isNullingProfileValid(toSave)) {
        logPrintln("NULLING_NVS_SAVE=FAIL reason=profile_validation");
        return false;
    }
    const bool saved = pgl::gld::saveNullingProfile(toSave);
    logPrintf("NULLING_NVS_SAVE=%s profileId=%u\n",
              saved ? "OK" : "FAIL", toSave.profileId);
    if (saved) {
        nullingProfileId = toSave.profileId;
    }
    return saved;
}

void returnToRunningAfterNulling(const pgl::gld::GldNullingProfile& profile) {
    logPrintf("NULLING_AUTO_MODE_SWITCH target=running mode=inference profileId=%u delayMs=%lu\n",
              profile.profileId,
              static_cast<unsigned long>(NULLING_AUTO_RESTART_DELAY_MS));
    if (!pgl::gld::writeGldMode(pgl::gld::GldMode::INFERENCE)) {
        logPrintln("NULLING_AUTO_MODE_SWITCH=FAIL reason=nvs_write");
        armNullingRetry("mode_persist_failed");
        return;
    }
    serviceDelay(NULLING_AUTO_RESTART_DELAY_MS);
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.flush();
#endif
    ESP.restart();
}

void runNullingRetryAttempt() {
    nullingRetryArmed = false;
    ++nullingAttemptCount;
    logPrintf("NULLING_RETRY_START attempt=%u\n",
              static_cast<unsigned>(nullingAttemptCount));

    if (!ensureNullingHardwareReady()) {
        logPrintf("NULLING_RETRY_BLOCKED adsReady=%u dacReady=%u\n",
                  adsReady ? 1 : 0, dacReady ? 1 : 0);
        armNullingRetry("hardware_not_ready");
        return;
    }

    const pgl::gld::GldNullingServiceResult result =
        pgl::gld::runNullingService(ads, dac, nullingLogLine, firmwareServiceTick, nullingConfig);
    logPrintf("NULLING_RETRY_DONE status=%s successCount=%u\n",
              pgl::gld::gldNullingStatusName(result.status), result.successCount);

    pgl::gld::GldNullingProfile toSave{};
    if (saveCompleteNullingProfile(result, toSave)) {
        logPrintln("NULLING_RUNTIME_RESULT=PASS");
        nullDone = true;
        returnToRunningAfterNulling(toSave);
        return;
    }

    const bool fullOk = result.status == pgl::gld::GldNullingStatus::Ok &&
                        result.successCount == pgl::gld::board::SENSOR_COUNT;
    logPrintln(result.status == pgl::gld::GldNullingStatus::PartialSuccess
               ? "NULLING_RUNTIME_RESULT=PARTIAL_RETRY"
               : "NULLING_RUNTIME_RESULT=FAIL_RETRY");
    armNullingRetry(fullOk ? "nvs_save_failed" : nullingRetryReason(result.status));
}

bool applySavedNullingProfileOnly() {
    nullingProfileApplied = false;
    nullingProfileId = 0;
    pgl::gld::GldNullingProfile profile{};
    if (!pgl::gld::loadNullingProfile(profile)) {
        if (dacReady) {
            const bool resetOk = dac.writeAll(0);
            serviceDelay(BOOT_DAC_SETTLE_MS);
            logPrintf("BOOT_NULLING_PROFILE_APPLY=SKIP reason=no_profile dacReset=%s\n",
                      resetOk ? "OK" : "FAIL");
        } else {
            logPrintln("BOOT_NULLING_PROFILE_APPLY=SKIP reason=no_profile");
        }
        return false;
    }

    if (!dacReady) {
        dacReady = dac.begin(Wire);
        logPrintf("BOOT_NULLING_DAC_BEGIN=%s\n", passFail(dacReady));
    }
    if (!dacReady) {
        logPrintf("BOOT_NULLING_PROFILE_APPLY=SKIP profileId=%u reason=dac_not_ready\n",
                  profile.profileId);
        return false;
    }

    bool allApplied = true;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        allApplied = dac.writeDac(ch, profile.dacCode[ch]) && allApplied;
    }
    serviceDelay(BOOT_DAC_SETTLE_MS);
    if (allApplied) {
        nullingProfileId = profile.profileId;
        nullingProfileApplied = true;
    } else {
        const bool resetOk = dac.writeAll(0);
        logPrintf("BOOT_NULLING_PROFILE_SAFE_RESET=%s\n", resetOk ? "OK" : "FAIL");
    }
    logPrintf("BOOT_NULLING_PROFILE_APPLY=%s profileId=%u\n",
              allApplied ? "OK" : "FAIL",
              profile.profileId);
    return allApplied;
}

void printBootSensorSnapshotRow(uint8_t rowNumber) {
    char line[256];
    size_t used = static_cast<size_t>(
        snprintf(line, sizeof(line), "%u. ", static_cast<unsigned>(rowNumber)));

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT && used < sizeof(line); ++ch) {
        firmwareServiceTick();
        const pgl::gld::GldAds1256Reading reading = ads.readChannel(ch);
        const char* sep = (ch + 1U < pgl::gld::board::SENSOR_COUNT) ? " | " : "";
        int written = 0;
        if (reading.status == pgl::gld::GldAds1256Status::Ok) {
            written = snprintf(line + used, sizeof(line) - used,
                               "%s : %.5fV%s",
                               pgl::gld::board::SENSOR_NAMES[ch],
                               reading.voltage,
                               sep);
        } else {
            written = snprintf(line + used, sizeof(line) - used,
                               "%s : ERR(%s)%s",
                               pgl::gld::board::SENSOR_NAMES[ch],
                               pgl::gld::gldAds1256StatusName(reading.status),
                               sep);
        }
        if (written < 0) break;
        used += static_cast<size_t>(written);
    }

    logPrintln(line);
}

void runExternalPowerBootSensorSamples(const pgl::gld::GldPowerReading& power) {
    // The DAC loses its volatile register state whenever the main rail is cut.
    // Apply and verify the complete profile on every boot, including a TPL5010
    // battery wake, before any inference path can become ready.
    (void)applySavedNullingProfileOnly();
    if (!power.externalPower) {
        return;
    }

    logPrintln("[BOOT_SENSOR_SAMPLES]");
    if (!adsReady) {
        logPrintln("BOOT_SENSOR_SAMPLE_BLOCKED reason=ads_not_ready");
        return;
    }

    for (uint8_t sample = 1; sample <= BOOT_SENSOR_SNAPSHOT_COUNT; ++sample) {
        firmwareServiceTick();
        printBootSensorSnapshotRow(sample);
    }
}

void runBootCheckFromSerialCommand() {
    emitCommandAck("RUN_BOOT_CHECK", "ok", "running boot diagnostics", false);

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    applyRuntimePowerReading(power, "run_boot_check", true);
    logPrintf("RUN_BOOT_CHECK_START mode=%s power=%s externalPower=%u\n",
              pgl::gld::gldModeName(currentMode),
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0);

    const BootDiagnosticsResult bootDiagnostics = runBootHardwareDiagnostics(power.externalPower);

    char modeDetail[128];
    bool modeReady = false;
    bool radioChecked = false;
    bool mlChecked = false;
    bool radioOk = false;
    bool mlOk = false;
    int mlOutputSize = -1;

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        radioChecked = true;
        mlChecked = true;
        radioOk = radioReady;
        mlOk = mlReady;
        mlOutputSize = network != nullptr ? network->getOutputSize() : -1;
        modeReady = adsReady && radioReady && mlReady;
        snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u lora=%s ml=%s rerun=1",
                 passFail(adsReady),
                 bootDiagnostics.i2c.mcpOkCount,
                 pgl::gld::board::SENSOR_COUNT,
                 passFail(radioReady),
                 passFail(mlReady));
    } else if (currentMode == pgl::gld::GldMode::DATASET) {
        modeReady = adsReady && dacReady && nullingProfileApplied && nullingProfileId > 0;
        snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u dac=%s nullingProfileId=%u rerun=1",
                 passFail(adsReady),
                 bootDiagnostics.i2c.mcpOkCount,
                 pgl::gld::board::SENSOR_COUNT,
                 passFail(dacReady),
                 nullingProfileId);
    } else {
        modeReady = adsReady && dacReady;
        snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u dac=%s nullingRetry=%u rerun=1",
                 passFail(adsReady),
                 bootDiagnostics.i2c.mcpOkCount,
                 pgl::gld::board::SENSOR_COUNT,
                 passFail(dacReady),
                 nullingRetryArmed ? 1 : 0);
    }

    printBootIcReport(power, bootDiagnostics.ads, bootDiagnostics.i2c, bootDiagnostics.mcpControl,
                      radioChecked, radioOk,
                      mlChecked, mlOk, mlOutputSize,
                      modeReady,
                      modeDetail);
    runExternalPowerBootSensorSamples(power);
    emitStatusJson();
    logPrintln("RUN_BOOT_CHECK_DONE");
}

struct DiagnosticAdsAverage {
    pgl::gld::GldAds1256Status status = pgl::gld::GldAds1256Status::NotReady;
    int32_t raw = 0;
    float voltage = 0.0f;
    uint8_t gain = 0;
};

DiagnosticAdsAverage readDiagnosticAverage(uint8_t ch) {
    DiagnosticAdsAverage out{};
    float voltageSum = 0.0f;
    int64_t rawSum = 0;
    bool ok = true;
    pgl::gld::GldAds1256Status lastStatus = pgl::gld::GldAds1256Status::Ok;
    uint8_t lastGain = 0;

    for (uint8_t sample = 0; sample < DIAG_SWEEP_SAMPLE_COUNT; ++sample) {
        firmwareServiceTick();
        const pgl::gld::GldAds1256Reading reading = ads.readChannel(ch);
        lastStatus = reading.status;
        lastGain = reading.gain;
        if (reading.status != pgl::gld::GldAds1256Status::Ok) {
            ok = false;
        }
        voltageSum += reading.voltage;
        rawSum += reading.raw;
    }
    firmwareServiceTick();

    out.status = ok ? pgl::gld::GldAds1256Status::Ok : lastStatus;
    out.voltage = voltageSum / static_cast<float>(DIAG_SWEEP_SAMPLE_COUNT);
    out.raw = static_cast<int32_t>(rawSum / static_cast<int64_t>(DIAG_SWEEP_SAMPLE_COUNT));
    out.gain = lastGain;
    return out;
}

void runAdsMcpSweepFromSerialCommand() {
    emitCommandAck("RUN_ADS_MCP_SWEEP", "ok", "running ADS/MCP sweep", false);

    if (!adsReady) {
        adsReady = ads.begin(gldSpi);
        logPrintf("ADS_MCP_SWEEP_ADS_BEGIN=%s\n", passFail(adsReady));
    }
    if (!dacReady) {
        dacReady = dac.begin(Wire);
        logPrintf("ADS_MCP_SWEEP_DAC_BEGIN=%s\n", passFail(dacReady));
    }

    if (!adsReady || !dacReady) {
        logPrintf("ADS_MCP_SWEEP_BLOCKED adsReady=%u dacReady=%u\n",
                  adsReady ? 1 : 0, dacReady ? 1 : 0);
        logPrintln("ADS_MCP_SWEEP_DONE status=blocked");
        return;
    }

    pgl::gld::GldNullingProfile profile{};
    const bool profileLoaded = pgl::gld::loadNullingProfile(profile);
    logPrintf("ADS_MCP_SWEEP_START codeLow=%u codeHigh=%u samples=%u settleMs=%lu restore=%s\n",
              static_cast<unsigned>(DIAG_SWEEP_DAC_CODE_LOW),
              static_cast<unsigned>(DIAG_SWEEP_DAC_CODE_HIGH),
              static_cast<unsigned>(DIAG_SWEEP_SAMPLE_COUNT),
              static_cast<unsigned long>(DIAG_SWEEP_SETTLE_MS),
              profileLoaded ? "profile" : "zero");

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        firmwareServiceTick();
        const uint8_t adsInput = pgl::gld::board::SENSOR_TO_ADS_CH[ch];
        const uint8_t muxChannel = pgl::gld::board::SENSOR_TO_MUX_CH[ch];

        const bool writeLow = dac.writeDac(ch, DIAG_SWEEP_DAC_CODE_LOW);
        serviceDelay(DIAG_SWEEP_SETTLE_MS);
        const DiagnosticAdsAverage low = readDiagnosticAverage(ch);

        const bool writeHigh = dac.writeDac(ch, DIAG_SWEEP_DAC_CODE_HIGH);
        serviceDelay(DIAG_SWEEP_SETTLE_MS);
        const DiagnosticAdsAverage high = readDiagnosticAverage(ch);

        const uint16_t restoreCode = profileLoaded
                                         ? profile.dacCode[ch]
                                         : DIAG_SWEEP_DAC_CODE_LOW;
        const bool restoreOk = dac.writeDac(ch, restoreCode);
        serviceDelay(BOOT_DAC_SETTLE_MS);

        const bool ok = writeLow &&
                        writeHigh &&
                        restoreOk &&
                        low.status == pgl::gld::GldAds1256Status::Ok &&
                        high.status == pgl::gld::GldAds1256Status::Ok;
        const float delta = high.voltage - low.voltage;

        logPrintf("ADS_MCP_SWEEP_RESULT ch=%u sensor=%s ads=%u mux=%u "
                  "v0=%.9f v4000=%.9f delta=%.9f st0=%s st4000=%s ok=%u\n",
                  static_cast<unsigned>(ch),
                  pgl::gld::board::SENSOR_NAMES[ch],
                  static_cast<unsigned>(adsInput),
                  static_cast<unsigned>(muxChannel),
                  low.voltage,
                  high.voltage,
                  delta,
                  pgl::gld::gldAds1256StatusName(low.status),
                  pgl::gld::gldAds1256StatusName(high.status),
                  ok ? 1 : 0);
        logPrintf("ADS_MCP_SWEEP_DETAIL ch=%u code0=%u code4000=%u write0=%u write4000=%u "
                  "raw0=%ld raw4000=%ld gain0=%u gain4000=%u restoreCode=%u restoreOk=%u\n",
                  static_cast<unsigned>(ch),
                  static_cast<unsigned>(DIAG_SWEEP_DAC_CODE_LOW),
                  static_cast<unsigned>(DIAG_SWEEP_DAC_CODE_HIGH),
                  writeLow ? 1 : 0,
                  writeHigh ? 1 : 0,
                  static_cast<long>(low.raw),
                  static_cast<long>(high.raw),
                  static_cast<unsigned>(low.gain),
                  static_cast<unsigned>(high.gain),
                  static_cast<unsigned>(restoreCode),
                  restoreOk ? 1 : 0);
    }

    logPrintln("ADS_MCP_SWEEP_DONE status=ok");
}

// ---------------------------------------------------------------------------
// LoRa (inference mode)
// ---------------------------------------------------------------------------

void onLoRaRxDone() { loraRxFlag = true; }

bool beginLoraRadio() {
    if (!loraModule) {
        loraModule = new Module(
            pgl::gld::board::PIN_LORA_CS, pgl::gld::board::PIN_LORA_DIO1,
            pgl::gld::board::PIN_LORA_RST, pgl::gld::board::PIN_LORA_BUSY,
            gldSpi);
    }
    if (!loraRadio) loraRadio = new SX1262(loraModule);
    if (radioReady) {
        loraRadio->standby();
    }
    logPrintf("GLD_STAR_CONFIG freqMHz=%.3f bwKHz=%.2f sf=%u cr=%u sync=0x%02X power=%d preamble=%u tcxo=%.1f xtal=%.1f\n",
              runtimeConfig.loraFreqMHz,
              runtimeConfig.loraBwKHz,
              runtimeConfig.loraSf,
              runtimeConfig.loraCr,
              runtimeConfig.loraSyncWord,
              runtimeConfig.loraTxPowerDbm,
              runtimeConfig.loraPreamble,
              runtimeConfig.loraTcxoVoltage,
              runtimeConfig.loraXtalVoltage);
    int16_t state = loraRadio->begin(runtimeConfig.loraFreqMHz,
                                     runtimeConfig.loraBwKHz,
                                     runtimeConfig.loraSf,
                                     runtimeConfig.loraCr,
                                     runtimeConfig.loraSyncWord,
                                     runtimeConfig.loraTxPowerDbm,
                                     runtimeConfig.loraPreamble,
                                     runtimeConfig.loraTcxoVoltage);
    if (state == RADIOLIB_ERR_SPI_CMD_FAILED) {
        state = loraRadio->begin(runtimeConfig.loraFreqMHz,
                                 runtimeConfig.loraBwKHz,
                                 runtimeConfig.loraSf,
                                 runtimeConfig.loraCr,
                                 runtimeConfig.loraSyncWord,
                                 runtimeConfig.loraTxPowerDbm,
                                 runtimeConfig.loraPreamble,
                                 runtimeConfig.loraXtalVoltage);
    }
    lastLoraBeginState = state;
    logPrintf("GLD_STAR_BEGIN_STATE=%d\n", state);
    if (state != RADIOLIB_ERR_NONE) { logPrintln("GLD_STAR_READY=0"); return false; }
    loraRadio->setRfSwitchPins(pgl::gld::board::PIN_LORA_RXEN, pgl::gld::board::PIN_LORA_TXEN);
    logPrintln("GLD_STAR_READY=1");
    return true;
}

struct NonceCtx { uint32_t counter; };

bool nonceProvider(uint8_t nonce[pgl::protocol::GLD_AES_GCM_NONCE_SIZE], void* ctx) {
    if (!ctx) return false;
    auto* nc = static_cast<NonceCtx*>(ctx);
    // Full 96-bit random nonce (esp_random() is a HW TRNG on ESP32), plus a
    // per-boot counter mixed into the last 4 bytes as defense in depth against
    // a short random collision. The leading bytes must not be a fixed
    // constant: a fixed prefix collapses effective nonce entropy and weakens
    // the AES-GCM uniqueness guarantee for every device sharing the fleet key.
    for (size_t i = 0; i < pgl::protocol::GLD_AES_GCM_NONCE_SIZE; i += 4) {
        const uint32_t r = esp_random();
        nonce[i]     = static_cast<uint8_t>((r >> 24) & 0xFF);
        nonce[i + 1] = static_cast<uint8_t>((r >> 16) & 0xFF);
        nonce[i + 2] = static_cast<uint8_t>((r >>  8) & 0xFF);
        nonce[i + 3] = static_cast<uint8_t>( r         & 0xFF);
    }
    nonce[8]  ^= static_cast<uint8_t>((nc->counter >> 24) & 0xFF);
    nonce[9]  ^= static_cast<uint8_t>((nc->counter >> 16) & 0xFF);
    nonce[10] ^= static_cast<uint8_t>((nc->counter >>  8) & 0xFF);
    nonce[11] ^= static_cast<uint8_t>( nc->counter        & 0xFF);
    ++nc->counter;
    return true;
}

void driveAlarmOutputs(bool alarm) {
    if (FIELDTEST_MODEL_UNVERIFIED) {
        alarm = false;
    }
    optionalDigitalWrite(pgl::gld::board::PIN_ALARM_LAMP, alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    optionalDigitalWrite(pgl::gld::board::PIN_BUZZER,     alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    optionalDigitalWrite(pgl::gld::board::PIN_STATUS_LED, alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
}

bool updateAlarmOutputs(bool alarm) {
    if (FIELDTEST_MODEL_UNVERIFIED) {
        driveAlarmOutputs(false);
        logPrintf("GLD_MODEL_BENCH_ALARM_SUPPRESSED requested=%u\n", alarm ? 1 : 0);
        return true;
    }
    if (alarm == lastAlarm) {
        driveAlarmOutputs(alarm);
        return true;
    }

    const bool persisted = pgl::gld::writeGldAlarmLatched(alarm);
    if (!persisted && !alarm) {
        // Clearing must survive the imminent TPL5010 power cut. If NVS cannot
        // commit the clear state, keep the physical alarm fail-safe and retry
        // on a later valid scan instead of reviving a stale latch next boot.
        logPrintln("GLD_ALARM_PERSIST=FAIL requested=clear failSafe=latched");
        driveAlarmOutputs(true);
        return false;
    }

    lastAlarm = alarm;
    driveAlarmOutputs(alarm);
    if (!persisted) {
        logPrintln("GLD_ALARM_PERSIST=FAIL requested=set physicalAlarm=on");
    }
    logPrintf("GLD_ALARM_OUTPUT alarm=%u\n", alarm ? 1 : 0);
    return persisted;
}

uint8_t modelClassToGasClass(int predicted) {
    if (predicted < 0 || predicted >= pgl::gld::model::EXPECTED_OUTPUT_ELEMENTS) {
        return pgl::protocol::GLD_GAS_ANOMALY;
    }
    const uint8_t gasClass = pgl::gld::model::CLASS_MAP[predicted];
    return pgl::protocol::isValidGasClass(gasClass)
        ? gasClass
        : pgl::protocol::GLD_GAS_ANOMALY;
}

bool modelProfileMatchesActiveNulling() {
    if (FIELDTEST_MODEL_UNVERIFIED) {
        return true;
    }
    if (!mlReady || !nullingProfileApplied || nullingProfileId == 0) {
        return false;
    }
    if (TFBG_CONTINUOUS_BATTERY) {
        // tfbg is an explicitly non-production field exercise environment.
        return true;
    }
    return pgl::gld::model::PRODUCTION_APPROVED &&
           pgl::gld::model::BOUND_NULLING_PROFILE_ID != 0 &&
           pgl::gld::model::BOUND_NULLING_PROFILE_ID == nullingProfileId;
}

bool runInference(const float mavVoltage[8]) {
    if (!mlReady || !network->isInitialized()) {
        return false;
    }
    // Channel n is fed directly as feature n (no remap - hardware channel order
    // already matches CNN_GAS_ADC_NAMES order: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7,
    // MQ6, MQ2). Normalization, evidence-feature computation, and INT8
    // quantization happen inside NeuralNetwork::predict().
    float confidenceFloat = 0.0f;
    const int predicted = network->predict(mavVoltage, confidenceFloat);
    if (predicted < 0 || !std::isfinite(confidenceFloat) ||
        confidenceFloat < 0.0f || confidenceFloat > 1.0f) {
        logPrintln("GLD_ML_PREDICT_ERROR");
        return false;
    }
    lastResult = {modelClassToGasClass(predicted),
                  static_cast<uint8_t>(confidenceFloat * 100.0f)};
    logPrintf("GLD_ML_RESULT predictedClass=%d gasClass=%u(%s) confidence=%u\n",
              predicted, lastResult.gasClass,
              pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence);
    return true;
}

bool runScan(bool requireCompleteBatch = false) {
    (void)requireCompleteBatch;
    pgl::gld::GldAds1256Reading readings[pgl::gld::board::SENSOR_COUNT]{};
    float mavVoltage[8] = {};
    uint8_t okChannels = 0;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        readings[ch] = r;
        latestSensorGain[ch] = r.gain;
        latestSensorStatus[ch] = static_cast<uint8_t>(r.status);
        if (r.status == pgl::gld::GldAds1256Status::Ok && !r.saturated) ++okChannels;
    }
    noteAdsReadHealth(okChannels, "runScan");
    const bool allValid = okChannels == pgl::gld::board::SENSOR_COUNT;
    latestTelemetryValid = allValid;

    uint8_t primedChannels = 0;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const bool mayCommit = allValid &&
                               readings[ch].status == pgl::gld::GldAds1256Status::Ok &&
                               !readings[ch].saturated;
        mavVoltage[ch] = mayCommit ? movingAvg.add(ch, readings[ch].voltage)
                                   : movingAvg.value(ch);
        latestSensorVoltage[ch] = mavVoltage[ch];
        if (movingAvg.count(ch) >= MIN_PRIMED_COUNT) ++primedChannels;
    }

    const bool primed = primedChannels >= pgl::gld::board::SENSOR_COUNT;
    modelProfileReady = modelProfileMatchesActiveNulling();
    if (FIELDTEST_MODEL_UNVERIFIED) {
        // Payload is intentionally dummy/safe: it proves the authenticated
        // GLD -> CH telemetry path, not gas classification correctness. LoRa
        // cadence is the primary field-test objective, so ADS warm-up/read
        // failures remain visible in diagnostics but never block dummy TX.
        lastResult = {pgl::protocol::GLD_GAS_CLEAR, 0};
        lastInferenceValid = true;
        logPrintf("GLD_FIELDTEST_DUMMY_RESULT allValid=%u primed=%u gasClass=%u confidence=%u\n",
                  allValid ? 1u : 0u, primed ? 1u : 0u,
                  lastResult.gasClass, lastResult.confidence);
    } else {
        lastInferenceValid = allValid && primed && mlReady && nullingProfileApplied &&
                             modelProfileReady &&
                             runInference(mavVoltage);
    }
    sensorFaultActive = FIELDTEST_MODEL_UNVERIFIED ? !(allValid && primed)
                                                   : !lastInferenceValid;
    // The model output is classification confidence, not a calibrated %LEL
    // value. A valid non-clear classification therefore uses a conservative
    // fail-safe alarm policy instead of comparing softmax confidence to 30%.
    const bool classifierAlarm = lastInferenceValid &&
                                 lastResult.gasClass != pgl::protocol::GLD_GAS_CLEAR;
    const bool alarm = FIELDTEST_MODEL_UNVERIFIED ? false : classifierAlarm;
    logPrintf("GLD_SENSOR_SCAN seq=%lu allValid=%u primed=%u inferenceValid=%u sensorFault=%u gasClass=%u(%s) confidence=%u alarm=%u\n",
              static_cast<unsigned long>(txCounter),
              allValid ? 1 : 0, primed ? 1 : 0,
              lastInferenceValid ? 1 : 0, sensorFaultActive ? 1 : 0,
              lastResult.gasClass, pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence, alarm ? 1 : 0);
    if (lastInferenceValid) {
        (void)updateAlarmOutputs(alarm);
    } else {
        logPrintf("GLD_ALARM_OUTPUT held=%u reason=sensor_or_inference_fault\n",
                  lastAlarm ? 1 : 0);
    }
    return allValid;
}

bool openLoRaRxWindow(bool expectAlarmAck, uint8_t expectedSeq) {
    if (!radioReady || !loraRadio) return false;
    bool alarmAckMatched = false;
    loraRxFlag = false;
    loraRadio->setPacketReceivedAction(onLoRaRxDone);
    loraRadio->startReceive();
    const uint32_t t0 = millis();
    while (!loraRxFlag && millis() - t0 < LORA_RX_WINDOW_MS) {
        serviceDelay(5);
    }
    if (loraRxFlag) {
        uint8_t rxBuf[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD]{};
        const size_t rxLen = loraRadio->getPacketLength();
        const int16_t rxState = loraRadio->readData(rxBuf, sizeof(rxBuf));
        logPrintf("GLD_LORA_DOWNLINK_RX state=%d len=%u\n", rxState, static_cast<unsigned>(rxLen));
        if (rxState == RADIOLIB_ERR_NONE) {
            if (expectAlarmAck && ALLOW_UNAUTHENTICATED_ALARM_ACK &&
                pgl::gld::parseCompactAlarmAck(rxBuf, rxLen,
                                               runtimeConfig.chId,
                                               runtimeConfig.nodeId,
                                               expectedSeq)) {
                alarmAckMatched = true;
                logPrintf("GLD_LORA_ALARM_ACK matched=1 chId=0x%04X nodeId=0x%04X seq=%u\n",
                          runtimeConfig.chId, runtimeConfig.nodeId, expectedSeq);
            } else {
                if (expectAlarmAck && !ALLOW_UNAUTHENTICATED_ALARM_ACK) {
                    logPrintln("GLD_LORA_ALARM_ACK rejected=1 reason=unauthenticated_ack_disabled");
                }
                pgl::gld::GldMode newMode;
                const uint16_t previousCommandId = runtimeConfig.lastDownlinkCommandId;
                if (pgl::gld::parseLoRaDownlinkCmd(rxBuf, rxLen,
                                                   runtimeConfig.nodeId,
                                                   runtimeConfig.aesKey,
                                                   runtimeConfig.aesKeyPresent,
                                                   runtimeConfig.lastDownlinkCommandId,
                                                   newMode)) {
                    if (!saveDownlinkReplayState()) {
                        runtimeConfig.lastDownlinkCommandId = previousCommandId;
                        logPrintln("GLD_LORA_DOWNLINK_CMD rejected=1 reason=replay_state_persist_failed");
                    } else {
                        logPrintf("GLD_LORA_DOWNLINK_CMD mode=%s commandId=%u persisted=1\n",
                                  pgl::gld::gldModeName(newMode),
                                  runtimeConfig.lastDownlinkCommandId);
                        onModeCmd(newMode);
                    }
                }
            }
        }
    }
    loraRadio->standby();
    if (expectAlarmAck && !alarmAckMatched) {
        logPrintf("GLD_LORA_ALARM_ACK matched=0 expectedSeq=%u windowMs=%lu\n",
                  expectedSeq, static_cast<unsigned long>(LORA_RX_WINDOW_MS));
    }
    return alarmAckMatched;
}

bool buildTxSnapshot(const pgl::gld::GldClassifyResult& result,
                     GldTxSnapshot& snapshot) {
    snapshot = {};
    if (!runtimeConfig.aesKeyPresent || runtimeConfig.aesKeyId == 0) {
        lastLoraTxState = -32767;
        lastLoraTxOk = false;
        logPrintln("GLD_SECURITY_NOT_PROVISIONED aesKey=0 txBlocked=1");
        logPrintln("GLD_LORA_TX_RESULT=FAIL");
        return false;
    }

    uint8_t sequence = 0;
    if (!pgl::gld::reserveGldTxSequence(sequence)) {
        lastLoraTxState = -32766;
        lastLoraTxOk = false;
        logPrintln("GLD_TX_SEQUENCE_RESERVE=FAIL txBlocked=1");
        return false;
    }
    txSeq = sequence;

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    const uint16_t batteryMv = power.batteryValid ? power.batteryMv
                                                   : pgl::protocol::GLD_BATTERY_MV_INVALID;
    pgl::gld::GldFrameBuilderConfig config{
        runtimeConfig.nodeId, runtimeConfig.chId,
        runtimeConfig.aesKeyId, runtimeConfig.aesKey,
        TFBG_CONTINUOUS_BATTERY ? false : power.externalPower,
        1,
    };
    pgl::gld::GldFrameBuildInput input{
        result.gasClass, result.confidence, batteryMv, sequence,
    };
    NonceCtx nonceCtx{txCounter};
    pgl::gld::GldBuiltFrame frame{};
    const pgl::gld::GldFrameStatus buildStatus =
        pgl::gld::buildGldUplinkFrame(config, input, nonceProvider, &nonceCtx, frame);
    txCounter = nonceCtx.counter;

    logPrintf("GLD_TX_HEADER status=%s seq=%u typeFlags=0x%02X alarm=%u gasClass=%u(%s) confidence=%u frameSize=%u\n",
              pgl::gld::gldFrameStatusName(buildStatus), sequence, frame.typeFlags,
              frame.alarm ? 1 : 0, result.gasClass,
              pgl::gld::gldGasClassName(result.gasClass),
              result.confidence, static_cast<unsigned>(frame.size));

    if (buildStatus != pgl::gld::GldFrameStatus::Ok) {
        lastLoraTxState = -32768;
        lastLoraTxOk = false;
        logPrintln("GLD_LORA_TX_RESULT=FAIL");
        return false;
    }

    if (frame.size > sizeof(snapshot.frame)) {
        lastLoraTxState = -32765;
        lastLoraTxOk = false;
        logPrintln("GLD_TX_SNAPSHOT=FAIL reason=frame_too_large");
        return false;
    }
    snapshot.valid = true;
    snapshot.alarm = frame.alarm;
    snapshot.sequence = sequence;
    snapshot.frameLen = static_cast<uint8_t>(frame.size);
    memcpy(snapshot.frame, frame.bytes, frame.size);
    return true;
}

bool loadFrozenPendingSnapshot(const pgl::gld::GldPendingAlarm& pending,
                               GldTxSnapshot& snapshot) {
    snapshot = {};
    if (!pgl::gld::gldPendingAlarmHasFrozenFrame(pending)) {
        return false;
    }
    snapshot.valid = true;
    snapshot.alarm = true;
    snapshot.sequence = pending.sequence;
    snapshot.frameLen = pending.frameLen;
    memcpy(snapshot.frame, pending.frame, pending.frameLen);
    txSeq = pending.sequence;
    return true;
}

bool persistAlarmSnapshot(const pgl::gld::GldClassifyResult& result,
                          const GldTxSnapshot& snapshot) {
    if (!snapshot.valid || !snapshot.alarm || snapshot.frameLen == 0) {
        return false;
    }
    pgl::gld::GldPendingAlarm pending{};
    pending.active = true;
    pending.gasClass = result.gasClass;
    pending.confidence = result.confidence;
    pending.sequence = snapshot.sequence;
    pending.frameLen = snapshot.frameLen;
    memcpy(pending.frame, snapshot.frame, snapshot.frameLen);
    batteryPendingAlarm = pending;
    if (!pgl::gld::writeGldPendingAlarm(pending)) {
        batteryPendingSaveRequired = true;
        logPrintf("GLD_BATTERY_ALARM_PENDING_SAVE=FAIL seq=%u txBlocked=1\n",
                  snapshot.sequence);
        return false;
    }
    batteryPendingSaveRequired = false;
    logPrintf("GLD_BATTERY_ALARM_PENDING_SAVE=OK seq=%u frameLen=%u frozen=1\n",
              pending.sequence, pending.frameLen);
    return true;
}

bool transmitSnapshot(const GldTxSnapshot& snapshot,
                      bool expectAlarmAck = false) {
    if (FIELDTEST_MODEL_UNVERIFIED && (snapshot.alarm || expectAlarmAck)) {
        lastLoraTxState = -32763;
        lastLoraTxOk = false;
        logPrintf("GLD_FIELDTEST_ALARM_TX_SUPPRESSED frameLen=%u alarm=%u alarmAck=%u\n",
                  static_cast<unsigned>(snapshot.frameLen), snapshot.alarm ? 1 : 0,
                  expectAlarmAck ? 1 : 0);
        return false;
    }
    if (FIELDTEST_MODEL_UNVERIFIED) {
        logPrintf("GLD_FIELDTEST_TELEMETRY_TX frameLen=%u\n",
                  static_cast<unsigned>(snapshot.frameLen));
    }
    if (!snapshot.valid || snapshot.frameLen == 0 || !radioReady || loraRadio == nullptr) {
        lastLoraTxState = -32764;
        lastLoraTxOk = false;
        logPrintln("GLD_LORA_TX_RESULT=FAIL reason=invalid_snapshot_or_radio");
        return false;
    }

    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    const int16_t txState = loraRadio->transmit(snapshot.frame, snapshot.frameLen);
    lastLoraTxState = txState;
    lastLoraTxOk = txState == RADIOLIB_ERR_NONE;
    digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
    digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);
    logPrintf("GLD_STAR_TX_STATE=%d seq=%u frameLen=%u frozen=%u\n",
              txState, snapshot.sequence, snapshot.frameLen,
              snapshot.alarm ? 1u : 0u);
    logPrintln(txState == RADIOLIB_ERR_NONE ? "GLD_LORA_TX_RESULT=PASS" : "GLD_LORA_TX_RESULT=FAIL");

    // Class A RX window for downlink commands
    return openLoRaRxWindow(expectAlarmAck, snapshot.sequence);
}

bool transmitOnce(bool expectAlarmAck = false) {
    if (!lastInferenceValid) {
        lastLoraTxOk = false;
        logPrintln("GLD_LORA_TX_RESULT=BLOCKED reason=inference_invalid");
        return false;
    }
    GldTxSnapshot snapshot{};
    if (!buildTxSnapshot(lastResult, snapshot)) {
        return false;
    }
    return transmitSnapshot(snapshot, expectAlarmAck);
}

bool prepareAndPersistAlarmDelivery(const pgl::gld::GldClassifyResult& result) {
    GldTxSnapshot snapshot{};
    if (!buildTxSnapshot(result, snapshot) || !snapshot.alarm) {
        logPrintln("GLD_BATTERY_ALARM_PREPARE=FAIL reason=frame_build");
        return false;
    }
    batteryTxSnapshot = snapshot;
    batterySendingPersistedAlarm = true;
    if (!persistAlarmSnapshot(result, snapshot)) {
        return false;
    }
    return true;
}

bool activateQueuedFreshAlarm(const char* reason) {
    if (!batteryFreshAlarmQueued || !batteryFreshInferenceValid || !batteryFreshAlarm) {
        return false;
    }
    if (!prepareAndPersistAlarmDelivery(batteryFreshResult)) {
        return false;
    }
    batteryFreshAlarmQueued = false;
    batteryAlarmTxAttempts = 0;
    batteryAlarmAckReceived = false;
    batteryNextTxAttemptMs = millis();
    (void)updateAlarmOutputs(true);
    logPrintf("GLD_BATTERY_FRESH_ALARM_ACTIVATED reason=%s gasClass=%u confidence=%u seq=%u\n",
              reason != nullptr ? reason : "queued",
              batteryFreshResult.gasClass,
              batteryFreshResult.confidence,
              batteryTxSnapshot.sequence);
    return true;
}

void runBatteryInferenceSession() {
    const uint32_t now = millis();

    if (batterySessionState == BatterySessionState::Inactive ||
        batterySessionState == BatterySessionState::PowerOffIssued) {
        return;
    }

    if (batterySessionState == BatterySessionState::CompleteHeld) {
        if (batteryPersistenceFaultHold) {
            if (static_cast<int32_t>(now - batteryPersistenceRetryDueMs) >= 0) {
                batteryPersistenceFaultHold = false;
                batterySessionState = BatterySessionState::Transmit;
                batteryStateStartedMs = now;
                batteryNextTxAttemptMs = now;
                logPrintln("GLD_BATTERY_PERSISTENCE_HOLD retry=1 state=transmit clrBlocked=0");
            }
            return;
        }
        if (!serviceHoldBlocksClr()) {
            logPrintln("GLD_BATTERY_SESSION_RELEASED serviceHold=0 action=power_off");
            completeBatterySessionAndPowerOff(batteryCompletionReason);
        }
        return;
    }

    if (now - batterySessionStartedMs >= BATTERY_SESSION_DEADLINE_MS) {
        logPrintf("GLD_BATTERY_SESSION_DEADLINE elapsedMs=%lu state=%s validBatches=%u txAttempts=%u\n",
                  static_cast<unsigned long>(now - batterySessionStartedMs),
                  batterySessionStateName(batterySessionState),
                  static_cast<unsigned>(batteryValidSampleBatches),
                  static_cast<unsigned>(batteryAlarmTxAttempts));
        completeBatterySessionAndPowerOff("hard_deadline");
        return;
    }

    switch (batterySessionState) {
        case BatterySessionState::Warmup:
            if (batteryLastWarmupPrimeMs == 0 ||
                now - batteryLastWarmupPrimeMs >= SCAN_INTERVAL_MS) {
                batteryLastWarmupPrimeMs = now;
                uint8_t stableChannels = 0;
                for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
                    const pgl::gld::GldAds1256Reading reading = ads.readChannel(ch);
                    if (reading.status == pgl::gld::GldAds1256Status::Ok &&
                        !reading.saturated) {
                        ++stableChannels;
                    }
                }
                logPrintf("GLD_BATTERY_WARMUP_AGC stableChannels=%u/%u\n",
                          static_cast<unsigned>(stableChannels),
                          static_cast<unsigned>(pgl::gld::board::SENSOR_COUNT));
            }
            if (now - batteryStateStartedMs < BATTERY_SENSOR_WARMUP_MS) return;
            movingAvg.reset();
            batteryValidSampleBatches = 0;
            batteryLastSampleAttemptMs = 0;
            batterySessionState = BatterySessionState::Sampling;
            batteryStateStartedMs = now;
            logPrintf("GLD_BATTERY_WARMUP_DONE elapsedMs=%lu movingAverageReset=1\n",
                      static_cast<unsigned long>(now - batterySessionStartedMs));
            return;

        case BatterySessionState::Sampling: {
            if (batteryLastSampleAttemptMs != 0 &&
                now - batteryLastSampleAttemptMs < SCAN_INTERVAL_MS) {
                return;
            }
            batteryLastSampleAttemptMs = now;
            lastScanMs = now;
            const bool completeValidBatch = runScan(true);
            if (completeValidBatch) {
                uint8_t primedBatchCount = UINT8_MAX;
                for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
                    const uint8_t count = movingAvg.count(ch);
                    if (count < primedBatchCount) primedBatchCount = count;
                }
                batteryValidSampleBatches = primedBatchCount;
            }
            logPrintf("GLD_BATTERY_SAMPLE valid=%u count=%u required=%u\n",
                      completeValidBatch ? 1 : 0,
                      static_cast<unsigned>(batteryValidSampleBatches),
                      static_cast<unsigned>(BATTERY_VALID_SAMPLE_BATCHES));
            if (batteryValidSampleBatches < BATTERY_VALID_SAMPLE_BATCHES) return;

            batteryFreshInferenceValid = lastInferenceValid;
            batteryFreshResult = lastResult;
            batteryFreshAlarm = lastInferenceValid &&
                                lastResult.gasClass != pgl::protocol::GLD_GAS_CLEAR;
            batteryFreshAlarmQueued = false;
            batterySendingPersistedAlarm = false;
            batteryTxSnapshot = {};

            if (!batteryFreshInferenceValid && !batteryPendingAlarm.active) {
                armBatteryFaultPowerOff("inference_invalid");
                if (static_cast<int32_t>(now - batteryFaultPowerOffDueMs) >= 0) {
                    completeBatterySessionAndPowerOff("inference_invalid");
                }
                return;
            }

            if (batteryPendingAlarm.active) {
                logPrintf("GLD_BATTERY_PENDING_ALARM_LOAD gasClass=%u confidence=%u freshValid=%u freshGasClass=%u freshConfidence=%u frozen=%u\n",
                          batteryPendingAlarm.gasClass,
                          batteryPendingAlarm.confidence,
                          batteryFreshInferenceValid ? 1u : 0u,
                          batteryFreshResult.gasClass,
                          batteryFreshResult.confidence,
                          pgl::gld::gldPendingAlarmHasFrozenFrame(batteryPendingAlarm) ? 1u : 0u);
                if (!loadFrozenPendingSnapshot(batteryPendingAlarm, batteryTxSnapshot)) {
                    const pgl::gld::GldClassifyResult legacyResult{
                        batteryPendingAlarm.gasClass,
                        batteryPendingAlarm.confidence,
                    };
                    if (!prepareAndPersistAlarmDelivery(legacyResult)) {
                        enterBatteryPersistenceFaultHold("pending_alarm_persist_failed");
                        return;
                    }
                } else {
                    batterySendingPersistedAlarm = true;
                }
                batteryFreshAlarmQueued = batteryFreshAlarm &&
                    (batteryFreshResult.gasClass != batteryPendingAlarm.gasClass ||
                     batteryFreshResult.confidence != batteryPendingAlarm.confidence);
                (void)updateAlarmOutputs(true);
            } else if (batteryFreshAlarm) {
                if (!prepareAndPersistAlarmDelivery(batteryFreshResult)) {
                    enterBatteryPersistenceFaultHold("alarm_persist_failed");
                    return;
                }
                (void)updateAlarmOutputs(true);
            } else if (!buildTxSnapshot(batteryFreshResult, batteryTxSnapshot)) {
                completeBatterySessionAndPowerOff("normal_frame_build_failed");
                return;
            }
            batteryAlarmTxAttempts = 0;
            batteryAlarmAckReceived = false;
            batteryNextTxAttemptMs = now;
            batterySessionState = BatterySessionState::Transmit;
            batteryStateStartedMs = now;
            logPrintf("GLD_BATTERY_INFERENCE_READY alarm=%u freshValid=%u freshQueued=%u gasClass=%u confidence=%u seq=%u frozen=%u\n",
                      batteryTxSnapshot.alarm ? 1u : 0u,
                      batteryFreshInferenceValid ? 1u : 0u,
                      batteryFreshAlarmQueued ? 1u : 0u,
                      batteryFreshResult.gasClass,
                      batteryFreshResult.confidence,
                      batteryTxSnapshot.sequence,
                      batterySendingPersistedAlarm ? 1u : 0u);
            return;
        }

        case BatterySessionState::Transmit: {
            if (static_cast<int32_t>(now - batteryNextTxAttemptMs) < 0) return;

            if (batteryPendingSaveRequired) {
                if (!pgl::gld::writeGldPendingAlarm(batteryPendingAlarm)) {
                    enterBatteryPersistenceFaultHold("pending_alarm_persist_retry_failed");
                    return;
                }
                batteryPendingSaveRequired = false;
                logPrintf("GLD_BATTERY_ALARM_PENDING_SAVE=OK seq=%u retry=1\n",
                          batteryPendingAlarm.sequence);
            }

            if (batteryAlarmAckReceived) {
                const pgl::gld::GldPendingAlarm cleared{};
                if (!pgl::gld::writeGldPendingAlarm(cleared)) {
                    batteryNextTxAttemptMs = millis() + BATTERY_ALARM_RETRY_DELAY_MS;
                    logPrintln("GLD_BATTERY_ALARM_PENDING_CLEAR=FAIL powerOffBlocked=1");
                    enterBatteryPersistenceFaultHold("pending_alarm_clear_failed");
                    return;
                }
                batteryPendingAlarm = {};
                batteryAlarmAckReceived = false;
                if (activateQueuedFreshAlarm("prior_alarm_acknowledged")) {
                    return;
                }
                if (batteryFreshInferenceValid && !batteryFreshAlarm &&
                    !updateAlarmOutputs(false)) {
                    batteryAlarmAckReceived = true;
                    batteryNextTxAttemptMs = millis() + BATTERY_ALARM_RETRY_DELAY_MS;
                    logPrintln("GLD_BATTERY_ALARM_LATCH_CLEAR=FAIL powerOffBlocked=1");
                    enterBatteryPersistenceFaultHold("alarm_latch_clear_failed");
                    return;
                }
                completeBatterySessionAndPowerOff("alarm_ack_received");
                return;
            }

            const bool alarm = batteryTxSnapshot.alarm;
            const bool alarmAck = transmitSnapshot(batteryTxSnapshot, alarm);
            if (alarm) {
                ++batteryAlarmTxAttempts;
            }
            if (!alarm) {
                completeBatterySessionAndPowerOff(lastLoraTxOk
                    ? "normal_tx_rx_done"
                    : "normal_tx_failed");
                return;
            }

            if (alarmAck) {
                batteryAlarmAckReceived = true;
                logPrintf("GLD_BATTERY_ALARM_ACK_SUCCESS attempts=%u\n",
                          static_cast<unsigned>(batteryAlarmTxAttempts));
                batteryNextTxAttemptMs = millis();
                return;
            }

            if (batteryAlarmTxAttempts < BATTERY_ALARM_TX_ATTEMPTS) {
                batteryNextTxAttemptMs = millis() + BATTERY_ALARM_RETRY_DELAY_MS;
                logPrintf("GLD_BATTERY_ALARM_TX_RETRY reason=%s attempt=%u nextAttempt=%u max=%u delayMs=%lu\n",
                          lastLoraTxOk ? "ack_timeout" : "tx_failed",
                          static_cast<unsigned>(batteryAlarmTxAttempts),
                          static_cast<unsigned>(batteryAlarmTxAttempts + 1U),
                          static_cast<unsigned>(BATTERY_ALARM_TX_ATTEMPTS),
                          static_cast<unsigned long>(BATTERY_ALARM_RETRY_DELAY_MS));
                return;
            }

            if (batteryFreshAlarmQueued) {
                if (activateQueuedFreshAlarm("prior_alarm_retry_exhausted")) {
                    return;
                }
                batteryNextTxAttemptMs = millis() + BATTERY_ALARM_RETRY_DELAY_MS;
                logPrintln("GLD_BATTERY_FRESH_ALARM_ACTIVATE=FAIL powerOffBlocked=1");
                enterBatteryPersistenceFaultHold("fresh_alarm_persist_failed");
                return;
            }
            logPrintf("GLD_BATTERY_ALARM_PENDING_RETAIN attempts=%u gasClass=%u confidence=%u seq=%u sleepNext=1\n",
                      static_cast<unsigned>(batteryAlarmTxAttempts),
                      batteryPendingAlarm.gasClass,
                      batteryPendingAlarm.confidence,
                      batteryPendingAlarm.sequence);
            completeBatterySessionAndPowerOff("alarm_ack_timeout_pending");
            return;
        }

        case BatterySessionState::CompleteHeld:
        case BatterySessionState::PowerOffIssued:
        case BatterySessionState::Inactive:
            return;
    }
}

// ---------------------------------------------------------------------------
// Dataset sample publish
// ---------------------------------------------------------------------------

void rejectDatasetRecord(
    const pgl::gld::GldDatasetValidationResult& validation,
    const pgl::gld::GldDatasetChannelSample* samples,
    size_t count) {
    ++datasetRejectedSamples;
    lastDatasetRejectReason = validation.reason;
    lastDatasetRejectChannel = validation.channel;
    lastDatasetRejectOkFiniteCount = validation.okFiniteCount;
    lastDatasetRejectStatus = 0xFF;
    lastDatasetRejectGain = 0;
    lastDatasetRejectSaturated = false;

    if (validation.channel >= 0 &&
        static_cast<size_t>(validation.channel) < count && samples != nullptr) {
        const pgl::gld::GldDatasetChannelSample& sample =
            samples[static_cast<size_t>(validation.channel)];
        lastDatasetRejectStatus = sample.status;
        lastDatasetRejectGain = sample.gain;
        lastDatasetRejectSaturated = sample.saturated;
    }

    logPrintf(
        "DATASET_RECORD_REJECT attemptedSeq=%lu reason=%s channel=%d "
        "okFiniteCount=%u status=%u gain=%u saturated=%u rejectedTotal=%lu\n",
        static_cast<unsigned long>(datasetSeq),
        pgl::gld::gldDatasetRejectReasonName(validation.reason),
        static_cast<int>(validation.channel),
        static_cast<unsigned>(validation.okFiniteCount),
        static_cast<unsigned>(lastDatasetRejectStatus),
        static_cast<unsigned>(lastDatasetRejectGain),
        lastDatasetRejectSaturated ? 1u : 0u,
        static_cast<unsigned long>(datasetRejectedSamples));
    publishDatasetRejectedStatus(validation, samples, count);
}

bool publishDataRecord() {
    pgl::gld::GldAds1256Reading readings[pgl::gld::GLD_DATASET_FEATURE_COUNT]{};
    pgl::gld::GldDatasetChannelSample samples[pgl::gld::GLD_DATASET_FEATURE_COUNT]{};
    uint8_t statusOkChannels = 0;

    static_assert(pgl::gld::board::SENSOR_COUNT == pgl::gld::GLD_DATASET_FEATURE_COUNT,
                  "Dataset contract requires exactly eight board channels");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        readings[ch] = ads.readChannel(ch);
        const pgl::gld::GldAds1256Reading& reading = readings[ch];
        latestSensorVoltage[ch] = reading.voltage;
        latestSensorGain[ch] = reading.gain;
        latestSensorStatus[ch] = static_cast<uint8_t>(reading.status);
        if (reading.status == pgl::gld::GldAds1256Status::Ok) ++statusOkChannels;
        samples[ch] = pgl::gld::GldDatasetChannelSample{
            pgl::gld::board::SENSOR_NAMES[ch],
            static_cast<uint8_t>(reading.status),
            reading.voltage,
            reading.gain,
            reading.saturated,
        };
    }
    noteAdsReadHealth(statusOkChannels, "dataset");

    pgl::gld::GldDatasetValidationResult validation =
        pgl::gld::validateGldDatasetSample(
            samples,
            pgl::gld::board::SENSOR_COUNT,
            nullingProfileApplied,
            nullingProfileId);
    latestTelemetryValid = validation.accepted;
    if (!validation.accepted) {
        rejectDatasetRecord(validation, samples, pgl::gld::board::SENSOR_COUNT);
        return false;
    }

    // Build the wire record only after all eight readings satisfy the schema.
    StaticJsonDocument<1024> doc;
    doc["device_id"]          = runtimeConfig.deviceId;
    doc["node_id"]            = runtimeConfig.nodeId;
    doc["mode"]               = "DATASET";
    doc["seq"]                = datasetSeq;
    doc["timestamp_ms"]       = static_cast<uint32_t>(millis());
    doc["label"]              = currentLabel;
    doc["nulling_profile_id"] = nullingProfileId;
    JsonArray svArr = doc.createNestedArray("sensor_voltage");
    JsonArray gainArr = doc.createNestedArray("sensor_gain");
    JsonArray statusArr = doc.createNestedArray("sensor_status");
    JsonArray foArr = doc.createNestedArray("feature_order");
    for (size_t ch = 0; ch < pgl::gld::GLD_DATASET_FEATURE_COUNT; ++ch) {
        svArr.add(readings[ch].voltage);
        gainArr.add(readings[ch].gain);
        statusArr.add(static_cast<uint8_t>(readings[ch].status));
        foArr.add(pgl::gld::GLD_DATASET_CANONICAL_FEATURE_ORDER[ch]);
    }

    char payload[DATASET_PAYLOAD_BYTES];
    const size_t requiredLen = measureJson(doc);
    if (doc.overflowed() || requiredLen == 0 || requiredLen >= sizeof(payload)) {
        validation.accepted = false;
        validation.reason = pgl::gld::GldDatasetRejectReason::PayloadEncoding;
        validation.channel = -1;
        rejectDatasetRecord(validation, samples, pgl::gld::board::SENSOR_COUNT);
        return false;
    }
    const size_t len = serializeJson(doc, payload, sizeof(payload));
    if (len != requiredLen) {
        validation.accepted = false;
        validation.reason = pgl::gld::GldDatasetRejectReason::PayloadEncoding;
        validation.channel = -1;
        rejectDatasetRecord(validation, samples, pgl::gld::board::SENSOR_COUNT);
        return false;
    }
    payload[len] = '\0';

    const bool published = publishDatasetPayload(payload, datasetSeq, false);
    if (!published) {
        enqueueDatasetPayload(payload, len, datasetSeq);
    }
    logPrintf("DATASET_RECORD seq=%lu ok=%u queued=%u pending=%u len=%u\n",
              static_cast<unsigned long>(datasetSeq), published ? 1 : 0,
              published ? 0 : 1,
              static_cast<unsigned>(datasetQueueCount),
              static_cast<unsigned>(len));
    ++datasetSeq;
    return true;
}

bool shouldAutoStop() {
    if (targetSamples > 0 && datasetSeq >= targetSamples) {
        logPrintf("DATASET_AUTOSTOP target_reached total=%lu\n", static_cast<unsigned long>(datasetSeq));
        return true;
    }
    if (maxDurationMs > 0 && millis() - sessionStartMs >= maxDurationMs) {
        logPrintf("DATASET_AUTOSTOP max_duration total=%lu\n", static_cast<unsigned long>(datasetSeq));
        return true;
    }
    return false;
}

void stopDataset() {
    optionalDigitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
    datasetState = DatasetState::Idle;
    sampleStep   = SampleStep::None;
    optionalDigitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
    publishDatasetSummary();
    publishDatasetStatus("idle", "completed");
}

void runDatasetStateMachine() {
    if (datasetState != DatasetState::Running || !adsReady) return;
    const uint32_t now = millis();
    switch (sampleStep) {
        case SampleStep::None:
            if (now - lastScanMs >= sampleIntervalMs) {
                if (useFanIntake && fanOnMs > 0) {
                    optionalDigitalWrite(pgl::gld::board::PIN_DC_FAN, HIGH);
                    stepStartMs = now;
                    sampleStep  = SampleStep::FanOn;
                } else {
                    publishDataRecord(); lastScanMs = now;
                    if (shouldAutoStop()) stopDataset();
                }
            }
            break;
        case SampleStep::FanOn:
            if (now - stepStartMs >= fanOnMs) {
                optionalDigitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
                stepStartMs = now;
                sampleStep  = (postFanSettleMs > 0) ? SampleStep::FanSettle : SampleStep::Scan;
            }
            break;
        case SampleStep::FanSettle:
            if (now - stepStartMs >= postFanSettleMs) sampleStep = SampleStep::Scan;
            break;
        case SampleStep::Scan:
            publishDataRecord(); lastScanMs = now; sampleStep = SampleStep::None;
            if (shouldAutoStop()) stopDataset();
            break;
    }
}

}  // namespace

// ---------------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
    pgl::gld::beginGldPowerPins();
    // Give USB serial time to settle, but do not dispatch queued operator
    // commands before the boot banner is visible. A queued SLEEP_NOW must not
    // clear the power latch before the operator can see firmware startup.
    delay(1000);
    loadRuntimeConfig();
    if (!pgl::gld::loadNullingConfig(nullingConfig)) {
        nullingConfig = pgl::gld::GldNullingConfig{};
    }
    serviceHoldActive = pgl::gld::readGldServiceHold();
    batteryPendingAlarm = pgl::gld::readGldPendingAlarm();
    setupPins();
    const bool persistedAlarmLatched = pgl::gld::readGldAlarmLatched();
    if (persistedAlarmLatched || batteryPendingAlarm.active) {
        (void)updateAlarmOutputs(true);
    }
    beginServiceHoldButton();
    movingAvg.reset();

    currentMode = pgl::gld::readGldMode();

    logPrintln("");
    logPrintln("Pertamina GLD unified firmware");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("GLD_MODE=%s\n", pgl::gld::gldModeName(currentMode));
    logPrintln("GLD_DEBUG=ON command=DEBUG_OFF|DEBUG_ON");
    logPrintf("[BOOT] GLD mulai boot. firmware=%s mode=%s profile=%s\n",
              pgl::firmware::GLD_FIRMWARE_VERSION,
              pgl::gld::gldModeName(currentMode),
              BOARD_PROFILE);

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("GLD_POWER mode=%s externalPower=%u batteryMv=%u batterySense=%s ambiguous=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0, power.batteryMv,
              pgl::gld::gldBatterySenseStatusName(power.batterySenseStatus),
              power.powerSourceAmbiguous ? 1u : 0u);
    batteryPowerMode = TFBG_CONTINUOUS_BATTERY || !power.externalPower;
    powerModeCandidateBattery = batteryPowerMode;
    powerModeCandidateCount = 0;
    lastPowerReconcileMs = millis();
    if (batteryPowerMode && !TFBG_CONTINUOUS_BATTERY &&
        currentMode != pgl::gld::GldMode::INFERENCE) {
        const pgl::gld::GldMode rejectedMode = currentMode;
        currentMode = pgl::gld::GldMode::INFERENCE;
        const bool persisted = pgl::gld::writeGldMode(currentMode);
        logPrintf("MODE_BATTERY_REJECTED requested=%s fallback=inference persisted=%u\n",
                  pgl::gld::gldModeName(rejectedMode), persisted ? 1u : 0u);
    }
    if (batteryPowerMode && serviceHoldActive) {
        logPrintln("GLD_SERVICE_HOLD state=ON source=nvs persisted=1");
        blinkServiceHoldEnabled();
    }
    pulseWdtKeepaliveNow();
    emitInfoJson();
    emitStatusJson();

    const BootDiagnosticsResult bootDiagnostics = runBootHardwareDiagnostics(power.externalPower);
    const BootAdsReport& bootAds = bootDiagnostics.ads;
    const BootI2cReport& bootI2c = bootDiagnostics.i2c;
    const BootMcpControlReport& bootMcpControl = bootDiagnostics.mcpControl;

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        // --- INFERENCE mode init ---
        disableNetworkForOfflineMode("inference_mode");
        network = new NeuralNetwork();
        mlReady = network->isInitialized();
        const int mlInputSize = mlReady ? network->getInputSize() : -1;
        const int mlOutputSize = mlReady ? network->getOutputSize() : -1;
        logPrintf("GLD_ML_INIT initialized=%u inputSize=%d outputSize=%d\n",
                  mlReady ? 1 : 0, mlInputSize, mlOutputSize);

        radioReady = beginLoraRadio();
        runExternalPowerBootSensorSamples(power);
        modelProfileReady = modelProfileMatchesActiveNulling();
        logPrintf("GLD_MODEL_PROFILE id=%s scaler=%s approved=%u boundNullingProfileId=%u activeNullingProfileId=%u tfbgOverride=%u ready=%u\n",
                  pgl::gld::model::PROFILE_ID,
                  pgl::gld::model::SCALER_PROFILE_ID,
                  pgl::gld::model::PRODUCTION_APPROVED ? 1u : 0u,
                  pgl::gld::model::BOUND_NULLING_PROFILE_ID,
                  nullingProfileId,
                  TFBG_CONTINUOUS_BATTERY ? 1u : 0u,
                  modelProfileReady ? 1u : 0u);
        logPrintf("GLD_INFERENCE_READY adsReady=%u radioReady=%u mlReady=%u nullingApplied=%u modelProfileReady=%u profileId=%u\n",
                  adsReady ? 1 : 0, radioReady ? 1 : 0, mlReady ? 1 : 0,
                  nullingProfileApplied ? 1 : 0, modelProfileReady ? 1 : 0,
                  nullingProfileId);
        char modeDetail[128];
        snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u lora=%s ml=%s nulling=%s modelProfile=%s profileId=%u",
                 passFail(adsReady),
                 bootI2c.mcpOkCount,
                 pgl::gld::board::SENSOR_COUNT,
                 passFail(radioReady),
                 FIELDTEST_MODEL_UNVERIFIED ? "IGNORED" : passFail(mlReady),
                 FIELDTEST_MODEL_UNVERIFIED ? "IGNORED" : passFail(nullingProfileApplied),
                 passFail(modelProfileReady),
                 nullingProfileId);
        printBootIcReport(power, bootAds, bootI2c, bootMcpControl,
                          true, radioReady,
                          !FIELDTEST_MODEL_UNVERIFIED, FIELDTEST_MODEL_UNVERIFIED || mlReady, mlOutputSize,
                          FIELDTEST_MODEL_UNVERIFIED ? (adsReady && radioReady)
                                                   : (adsReady && radioReady && mlReady && nullingProfileApplied && modelProfileReady),
                          modeDetail);
        armBootReportRecoveryIfNeeded(bootAds, bootI2c, bootMcpControl,
                                      true, radioReady,
                                      !FIELDTEST_MODEL_UNVERIFIED,
                                      FIELDTEST_MODEL_UNVERIFIED || mlReady);

        lastScanMs = millis();
        lastTxMs   = millis();
        if (batteryPowerMode && !TFBG_CONTINUOUS_BATTERY) {
            startBatteryInferenceSession();
        }

    } else if (currentMode == pgl::gld::GldMode::NULLING && pgl::gld::readGldAlarmLatched()) {
        // Nulling must not run while a prior alarm is still latched/unacknowledged
        // (design.md §3.6: "nulling blocked when alarm active"). Clear the alarm
        // (button hold / IO38 CLR) before switching into Nulling mode again.
        logPrintln("MODE_BLOCKED reason=alarm_latched mode=nulling");
        pgl::gld::writeGldMode(pgl::gld::GldMode::INFERENCE);
        serviceDelay(NULLING_AUTO_RESTART_DELAY_MS);
        Serial.flush();
#if defined(ARDUINO_ARCH_ESP32)
        Serial0.flush();
#endif
        ESP.restart();

    } else {
        // --- DATASET / NULLING mode init ---
        if (batteryPowerMode) {
            logPrintf("MODE_BATTERY_ALLOWED_TEMP mode=%s\n",
                      pgl::gld::gldModeName(currentMode));
            pulseWdtKeepaliveNow();
        }
        dacReady = dac.begin(Wire);
        logPrintf("DAC_MUX_BEGIN_RESULT=%s\n", dacReady ? "PASS" : "FAIL");
        pulseWdtKeepaliveNow();

        if (currentMode == pgl::gld::GldMode::DATASET) {
            if (adsReady && dacReady) {
                initNulling(false);
                pulseWdtKeepaliveNow();
            }
            logPrintf("DATASET_READY adsReady=%u dacReady=%u nullingProfileId=%u\n",
                      adsReady ? 1 : 0, dacReady ? 1 : 0, nullingProfileId);
            char modeDetail[96];
            snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u dac=%s nullingProfileId=%u",
                     passFail(adsReady),
                     bootI2c.mcpOkCount,
                     pgl::gld::board::SENSOR_COUNT,
                     passFail(dacReady),
                     nullingProfileId);
            printBootIcReport(power, bootAds, bootI2c, bootMcpControl,
                              false, false,
                              false, false, -1,
                              adsReady && dacReady && nullingProfileApplied && nullingProfileId > 0,
                              modeDetail);
            runExternalPowerBootSensorSamples(power);
            armBootReportRecoveryIfNeeded(bootAds, bootI2c, bootMcpControl,
                                          false, false,
                                          false, false);
            pulseWdtKeepaliveNow();
            connectWifi();
            pulseWdtKeepaliveNow();
            mqtt.setBufferSize(MQTT_BUFFER_SIZE);
            mqttConnect();
            pulseWdtKeepaliveNow();
            lastStatusMs = millis();

        } else {
            // NULLING mode: run calibration first (blocking)
            disableNetworkForOfflineMode("nulling_mode");
            if (!adsReady || !dacReady) {
                logPrintf("NULLING_BLOCKED adsReady=%u dacReady=%u\n",
                          adsReady ? 1 : 0, dacReady ? 1 : 0);
                char modeDetail[96];
                snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u dac=%s nulling=BLOCKED_RETRY",
                         passFail(adsReady),
                         bootI2c.mcpOkCount,
                         pgl::gld::board::SENSOR_COUNT,
                         passFail(dacReady));
                printBootIcReport(power, bootAds, bootI2c, bootMcpControl,
                                  false, false,
                                  false, false, -1,
                                  false,
                                  modeDetail);
                runExternalPowerBootSensorSamples(power);
                armBootReportRecoveryIfNeeded(bootAds, bootI2c, bootMcpControl,
                                              false, false,
                                              false, false);
                armNullingRetry("hardware_not_ready");
            } else {
                logPrintln("NULLING_RUN=start");

                const pgl::gld::GldNullingServiceResult result =
                    pgl::gld::runNullingService(ads, dac, nullingLogLine, firmwareServiceTick, nullingConfig);
                logPrintf("NULLING_RUN_DONE status=%s successCount=%u\n",
                          pgl::gld::gldNullingStatusName(result.status), result.successCount);

                pgl::gld::GldNullingProfile toSave{};
                const bool saved = saveCompleteNullingProfile(result, toSave);
                if (saved) {
                    logPrintln("NULLING_RUNTIME_RESULT=PASS");
                    nullDone = true;
                    char modeDetail[96];
                    snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u dac=%s nulling=PASS auto=running profileId=%u",
                             passFail(adsReady),
                             bootI2c.mcpOkCount,
                             pgl::gld::board::SENSOR_COUNT,
                             passFail(dacReady),
                             toSave.profileId);
                    printBootIcReport(power, bootAds, bootI2c, bootMcpControl,
                                      false, false,
                                      false, false, -1,
                                      true,
                                      modeDetail);
                    runExternalPowerBootSensorSamples(power);
                    armBootReportRecoveryIfNeeded(bootAds, bootI2c, bootMcpControl,
                                                  false, false,
                                                  false, false);
                    returnToRunningAfterNulling(toSave);
                } else {
                    const bool partial = result.status == pgl::gld::GldNullingStatus::PartialSuccess;
                    const bool fullOk = result.status == pgl::gld::GldNullingStatus::Ok &&
                                        result.successCount == pgl::gld::board::SENSOR_COUNT;
                    logPrintln(partial
                               ? "NULLING_RUNTIME_RESULT=PARTIAL_RETRY"
                               : "NULLING_RUNTIME_RESULT=FAIL_RETRY");
                    char modeDetail[96];
                    snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u dac=%s nulling=%s",
                             passFail(adsReady),
                             bootI2c.mcpOkCount,
                             pgl::gld::board::SENSOR_COUNT,
                             passFail(dacReady),
                             partial ? "PARTIAL_RETRY" : "FAIL_RETRY");
                    printBootIcReport(power, bootAds, bootI2c, bootMcpControl,
                                      false, false,
                                      false, false, -1,
                                      false,
                                      modeDetail);
                    runExternalPowerBootSensorSamples(power);
                    armBootReportRecoveryIfNeeded(bootAds, bootI2c, bootMcpControl,
                                                  false, false,
                                                  false, false);
                    armNullingRetry(fullOk ? "nvs_save_failed" : nullingRetryReason(result.status));
                }
            }
        }
    }
}

void loop() {
    firmwareServiceTick();
    reconcileRuntimePowerMode();
    if (powerTransitionShutdownPending) {
        completeBatterySessionAndPowerOff("unsupported_mode_power_transition");
        return;
    }
    maintainBootReportRecovery();

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        const uint32_t now = millis();
        maintainAdsRecovery("inference_ads_not_ready");

        if (batteryPowerMode && !TFBG_CONTINUOUS_BATTERY) {
            // One-shot wake cycle: warm-up, 10 complete valid sample batches,
            // inference, bounded LoRa TX/RX, then final DONE followed by CLR.
            // While service hold is active, CLR is inhibited and DONE becomes
            // periodic so the board stays available for firmware upload.
            if (batterySessionState == BatterySessionState::CompleteHeld) {
                runBatteryInferenceSession();
                return;
            }
            if (!batteryRuntimeReady()) {
                const char* reason = batteryRuntimeBlockReason();
                armBatteryFaultPowerOff(reason);
                if (static_cast<int32_t>(now - batteryFaultPowerOffDueMs) >= 0) {
                    completeBatterySessionAndPowerOff(reason);
                }
                return;
            }
            batteryFaultPowerOffArmed = false;
            runBatteryInferenceSession();
            return;
        }

        if (adsReady && now - lastScanMs >= SCAN_INTERVAL_MS) {
            lastScanMs = now;
            runScan();
        }
        if (radioReady && now - lastTxMs >= TX_INTERVAL_MS) {
            lastTxMs = now;
            transmitOnce();
        }

    } else if (currentMode == pgl::gld::GldMode::DATASET) {
        maintainWifi();
        maintainMqtt();
        flushDatasetQueue();
        maintainAdsRecovery("dataset_ads_not_ready");
        const uint32_t now = millis();
        if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
            lastStatusMs = now;
            if (datasetState == DatasetState::Running)
                publishDatasetStatus("running", currentLabel);
        }
        runDatasetStateMachine();
        serviceDelay(10);

    } else {
        // NULLING mode: offline calibration; Serial commands are checked at loop start.
        if (nullingRetryArmed &&
            static_cast<int32_t>(millis() - nextNullingRetryMs) >= 0) {
            runNullingRetryAttempt();
        }
        serviceDelay(100);
    }
}
