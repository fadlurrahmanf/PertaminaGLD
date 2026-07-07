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
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldCommandParser.h"
#include "GldDacMux.h"
#include "GldFrameBuilder.h"
#include "GldModeManager.h"
#include "GldMovingAverage.h"
#include "GldNullingProfile.h"
#include "GldNullingService.h"
#include "GldPower.h"
#include "GldSelfTestConfig.h"
#include "GldThresholdClassifier.h"
#include "GldConfig.h"
#include "ProtocolConstants.h"
#include "../model/NeuralNetwork.h"
#include "../model/scaler_params.h"

namespace {

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
constexpr float    STAR_FREQ_MHZ    = GLD_STAR_FREQ_MHZ;
constexpr float    STAR_BW_KHZ      = GLD_STAR_BW_KHZ;
constexpr uint8_t  STAR_SF          = GLD_STAR_SF;
constexpr uint8_t  STAR_CR          = GLD_STAR_CR;
constexpr uint8_t  STAR_SYNC_WORD   = GLD_STAR_SYNC_WORD;
constexpr int8_t   STAR_TX_POWER    = GLD_STAR_TX_POWER_DBM;
constexpr uint16_t STAR_PREAMBLE    = GLD_STAR_PREAMBLE;
constexpr float    LORA_TCXO_V      = GLD_STAR_TCXO_VOLTAGE;
constexpr float    LORA_XTAL_V      = GLD_STAR_XTAL_VOLTAGE;
constexpr uint32_t LORA_RX_WINDOW_MS = GLD_LORA_RX_WINDOW_MS;

// ---------------------------------------------------------------------------
// Timing from GldConfig.h
// ---------------------------------------------------------------------------
constexpr uint32_t SCAN_INTERVAL_MS   = GLD_SCAN_INTERVAL_MS;
constexpr uint32_t TX_INTERVAL_MS     = GLD_TX_INTERVAL_MS;
constexpr uint32_t WIFI_TIMEOUT_MS    = GLD_WIFI_TIMEOUT_MS;
constexpr uint32_t MQTT_RETRY_MS      = GLD_MQTT_RETRY_MS;
constexpr uint32_t STATUS_INTERVAL_MS = GLD_STATUS_INTERVAL_MS;
constexpr uint16_t MQTT_BUFFER_SIZE   = GLD_MQTT_BUFFER_SIZE;
constexpr uint8_t  MIN_PRIMED_COUNT   = pgl::gld::GLD_SENSOR_MOVING_AVERAGE_WINDOW;
constexpr uint8_t  BOOT_SENSOR_SNAPSHOT_COUNT = 5;
constexpr uint32_t BOOT_DAC_SETTLE_MS = 5;
constexpr uint16_t BOOT_MCP_TEST_CODE_LOW = 1;
constexpr uint16_t BOOT_MCP_TEST_CODE_HIGH = 10;
constexpr uint32_t NULLING_RETRY_DELAY_MS = 5000;
constexpr uint32_t NULLING_AUTO_RESTART_DELAY_MS = 800;

#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8
constexpr const char* BOARD_PROFILE = "WROOM-1U-N16R8";
#else
constexpr const char* BOARD_PROFILE = "4D-ESP32S3";
#endif

constexpr uint8_t ML_CONFIDENCE_THRESHOLD = pgl::protocol::GLD_LEL_THRESHOLD_PERCENT;
constexpr uint8_t ACTIVE_LOW_OUTPUT_ON = LOW;
constexpr uint8_t ACTIVE_LOW_OUTPUT_OFF = HIGH;

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
pgl::gld::GldClassifyResult lastResult{pgl::protocol::GLD_GAS_CLEAR, 100};
bool     debugEnabled    = true;
int16_t  lastLoraBeginState = 0;
int16_t  lastLoraTxState = 0;
bool     lastLoraTxOk = false;
int      lastBootAdsDrdyLevel = -1;
uint8_t  lastBootAdsStatus = 0;
bool     lastBootTcaOk = false;
uint8_t  lastBootMcpOkCount = 0;
bool     lastBootMcpControlTested = false;
uint8_t  lastBootMcpControlOkCount = 0;
bool     batteryPowerMode = false;
bool     batteryCyclePoweredOff = false;
uint32_t lastTpl5010KeepaliveMs = 0;
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
};

RuntimeConfig runtimeConfig{};

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
uint32_t     sampleIntervalMs = 1000;
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

void clearRuntimeAesKey() {
    runtimeConfig.aesKeyId = 0;
    memset(runtimeConfig.aesKey, 0, sizeof(runtimeConfig.aesKey));
    runtimeConfig.aesKeyPresent = false;
}

void applySelfTestAesFallbackIfAllowed() {
#if GLD_ALLOW_SELFTEST_AES_FALLBACK
    runtimeConfig.aesKeyId = pgl::gld::selftest::KEY_ID;
    memcpy(runtimeConfig.aesKey, pgl::gld::selftest::AES_KEY, sizeof(runtimeConfig.aesKey));
    runtimeConfig.aesKeyPresent = true;
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
    copyBounded(runtimeConfig.wifiSsid, sizeof(runtimeConfig.wifiSsid), DEFAULT_WIFI_SSID);
    copyBounded(runtimeConfig.wifiPassword, sizeof(runtimeConfig.wifiPassword), DEFAULT_WIFI_PASSWORD);
    copyBounded(runtimeConfig.mqttHost, sizeof(runtimeConfig.mqttHost), DEFAULT_MQTT_HOST);
    runtimeConfig.mqttPort = DEFAULT_MQTT_PORT;
    copyBounded(runtimeConfig.mqttUser, sizeof(runtimeConfig.mqttUser), DEFAULT_MQTT_USER);
    copyBounded(runtimeConfig.mqttPass, sizeof(runtimeConfig.mqttPass), DEFAULT_MQTT_PASS);
    copyBounded(runtimeConfig.topicRoot, sizeof(runtimeConfig.topicRoot), DEFAULT_TOPIC_ROOT);
    clearRuntimeAesKey();
    runtimeConfig.lastDownlinkCommandId = 0;
    buildRuntimeTopics();
}

void loadRuntimeConfig() {
    resetRuntimeConfigDefaults();
    Preferences prefs;
    if (!prefs.begin("gld_app", true)) {
        logPrintln("GLD_APP_CONFIG_LOAD=DEFAULT reason=nvs_unavailable");
        return;
    }
    String value = prefs.getString("deviceId", runtimeConfig.deviceId);
    copyBounded(runtimeConfig.deviceId, sizeof(runtimeConfig.deviceId), value.c_str());
    runtimeConfig.nodeId = prefs.getUShort("nodeId", nodeIdFromDeviceId(runtimeConfig.deviceId, DEFAULT_NODE_ID));
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
    runtimeConfig.ctrlword = static_cast<uint8_t>(prefs.getUChar("ctrlword", runtimeConfig.ctrlword));
    runtimeConfig.aesKeyId = static_cast<uint8_t>(prefs.getUChar("aesKeyId", 0));
    runtimeConfig.aesKeyPresent = prefs.getBool("aesKeySet", false) &&
                                  runtimeConfig.aesKeyId != 0 &&
                                  prefs.getBytesLength("aesKey") == sizeof(runtimeConfig.aesKey);
    if (runtimeConfig.aesKeyPresent) {
        prefs.getBytes("aesKey", runtimeConfig.aesKey, sizeof(runtimeConfig.aesKey));
    } else {
        clearRuntimeAesKey();
    }
    runtimeConfig.lastDownlinkCommandId = prefs.getUShort("lastCmdId", 0);
    prefs.end();
    if (!runtimeConfig.aesKeyPresent) {
        applySelfTestAesFallbackIfAllowed();
    }
    buildRuntimeTopics();
    logPrintf("GLD_APP_CONFIG_LOAD=%s deviceId=%s nodeId=0x%04X ssid=%s mqttHost=%s mqttPort=%u topicRoot=%s aesKey=%u keyId=%u lastCmdId=%u\n",
              runtimeConfigValid() ? "OK" : "DEFAULT_UNCONFIGURED",
              runtimeConfig.deviceId,
              runtimeConfig.nodeId,
              runtimeConfig.wifiSsid,
              runtimeConfig.mqttHost,
              runtimeConfig.mqttPort,
              runtimeConfig.topicRoot,
              runtimeConfig.aesKeyPresent ? 1 : 0,
              runtimeConfig.aesKeyId,
              runtimeConfig.lastDownlinkCommandId);
}

bool saveRuntimeConfig() {
    Preferences prefs;
    if (!prefs.begin("gld_app", false)) return false;
    runtimeConfig.ctrlword = GLD_CTRL_WORD_VALUE;
    prefs.putUChar("ctrlword", runtimeConfig.ctrlword);
    prefs.putString("deviceId", runtimeConfig.deviceId);
    prefs.putUShort("nodeId", runtimeConfig.nodeId);
    prefs.putString("wifiSsid", runtimeConfig.wifiSsid);
    prefs.putString("wifiPass", runtimeConfig.wifiPassword);
    prefs.putString("mqttHost", runtimeConfig.mqttHost);
    prefs.putUShort("mqttPort", runtimeConfig.mqttPort);
    prefs.putString("mqttUser", runtimeConfig.mqttUser);
    prefs.putString("mqttPass", runtimeConfig.mqttPass);
    prefs.putString("topicRoot", runtimeConfig.topicRoot);
    if (runtimeConfig.aesKeyPresent && runtimeConfig.aesKeyId != 0) {
        prefs.putBool("aesKeySet", true);
        prefs.putUChar("aesKeyId", runtimeConfig.aesKeyId);
        prefs.putBytes("aesKey", runtimeConfig.aesKey, sizeof(runtimeConfig.aesKey));
    } else {
        prefs.putBool("aesKeySet", false);
        prefs.remove("aesKeyId");
        prefs.remove("aesKey");
    }
    prefs.putUShort("lastCmdId", runtimeConfig.lastDownlinkCommandId);
    prefs.end();
    return true;
}

bool saveDownlinkReplayState() {
    Preferences prefs;
    if (!prefs.begin("gld_app", false)) return false;
    prefs.putUShort("lastCmdId", runtimeConfig.lastDownlinkCommandId);
    prefs.end();
    return true;
}

bool validDeviceId(const char* deviceId) {
    if (deviceId == nullptr || strlen(deviceId) != 4) return false;
    for (uint8_t i = 0; i < 4; ++i) {
        const char c = deviceId[i];
        const bool ok = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f');
        if (!ok) return false;
    }
    return nodeIdFromDeviceId(deviceId, 0) != 0;
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

void emitCommandAck(const char* cmd, const char* status,
                    const char* message, bool rebootExpected) {
    StaticJsonDocument<256> doc;
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
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
    caps["nullingConfig"] = "read_only";
    caps["serialAppConfig"] = true;
    caps["serialDeviceId"] = true;
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
    StaticJsonDocument<1024> doc;
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
    doc["targetChId"] = static_cast<uint16_t>(GLD_CH_ID);
    doc["firmwareName"] = pgl::firmware::GLD_FIRMWARE_NAME;
    doc["firmwareVersion"] = pgl::firmware::GLD_FIRMWARE_VERSION;
    doc["protocolVersion"] = pgl::firmware::PROTOCOL_VERSION;
    doc["boardProfile"] = BOARD_PROFILE;
    doc["mode"] = pgl::gld::gldModeName(currentMode);
    doc["baud"] = 115200;
    doc["sensorCount"] = pgl::gld::board::SENSOR_COUNT;
    doc["mqttTopicRoot"] = runtimeConfig.topicRoot;
    JsonObject appConfig = doc.createNestedObject("appConfig");
    appConfig["wifiSsid"] = runtimeConfig.wifiSsid;
    appConfig["mqttHost"] = runtimeConfig.mqttHost;
    appConfig["mqttPort"] = runtimeConfig.mqttPort;
    appConfig["mqttUser"] = runtimeConfig.mqttUser;
    appConfig["topicRoot"] = runtimeConfig.topicRoot;
    appConfig["configValid"] = runtimeConfigValid();
    JsonObject security = doc.createNestedObject("security");
    security["aesKeyProvisioned"] = runtimeConfig.aesKeyPresent;
    security["keyId"] = runtimeConfig.aesKeyId;
    security["selfTestFallbackAllowed"] = GLD_ALLOW_SELFTEST_AES_FALLBACK ? true : false;
    security["lastDownlinkCommandId"] = runtimeConfig.lastDownlinkCommandId;
    JsonObject caps = doc.createNestedObject("capabilities");
    addCapabilities(caps);
    rawJsonLine("GLD_INFO_JSON", doc);
}

void emitStatusJson() {
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    StaticJsonDocument<1536> doc;
    doc["deviceId"] = runtimeConfig.deviceId;
    doc["nodeId"] = runtimeConfig.nodeId;
    doc["mode"] = pgl::gld::gldModeName(currentMode);
    doc["uptimeMs"] = static_cast<uint32_t>(millis());
    doc["debugEnabled"] = debugEnabled;

    JsonObject powerObj = doc.createNestedObject("power");
    powerObj["mode"] = pgl::gld::gldPowerModeName(power.mode);
    powerObj["externalPower"] = power.externalPower;
    powerObj["batteryMv"] = power.batteryMv;
    powerObj["batteryValid"] = power.batteryValid;
    powerObj["batteryLow"] = power.batteryLow;
    powerObj["batteryCritical"] = power.batteryCritical;

    JsonObject boot = doc.createNestedObject("bootHealth");
    boot["adsReady"] = adsReady;
    boot["adsDrdyLevel"] = lastBootAdsDrdyLevel;
    boot["adsStatus"] = lastBootAdsStatus;
    boot["tcaOk"] = lastBootTcaOk;
    boot["mcpOkCount"] = lastBootMcpOkCount;
    boot["mcpControlTested"] = lastBootMcpControlTested;
    boot["mcpControlOkCount"] = lastBootMcpControlOkCount;
    boot["dacReady"] = dacReady;
    boot["radioReady"] = radioReady;
    boot["mlReady"] = mlReady;

    JsonObject lora = doc.createNestedObject("lora");
    lora["beginState"] = lastLoraBeginState;
    lora["lastTxState"] = lastLoraTxState;
    lora["lastTxOk"] = lastLoraTxOk;
    lora["txSeq"] = txSeq;
    lora["txCounter"] = txCounter;
    lora["aesKeyProvisioned"] = runtimeConfig.aesKeyPresent;
    lora["keyId"] = runtimeConfig.aesKeyId;
    lora["lastDownlinkCommandId"] = runtimeConfig.lastDownlinkCommandId;

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

    JsonObject nulling = doc.createNestedObject("nulling");
    nulling["done"] = nullDone;
    nulling["retryArmed"] = nullingRetryArmed;
    nulling["attemptCount"] = nullingAttemptCount;
    nulling["nextRetryMs"] = nextNullingRetryMs;

    JsonObject telemetry = doc.createNestedObject("telemetry");
    addTelemetry(telemetry);

    rawJsonLine("GLD_STATUS_JSON", doc);
}

// ---------------------------------------------------------------------------
// Mode command handler — NVS write + reboot
// ---------------------------------------------------------------------------

void onModeCmd(pgl::gld::GldMode newMode) {
    emitCommandAck("SET_MODE", "ok", "mode switch accepted", true);
    logPrintf("GLD_MODE_SWITCH current=%s new=%s\n",
              pgl::gld::gldModeName(currentMode),
              pgl::gld::gldModeName(newMode));
    pgl::gld::switchGldMode(newMode);
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
    delay(250);
    ESP.restart();
}

void onSetAppConfigJson(const char* payload) {
    StaticJsonDocument<1024> doc;
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
        emitCommandAck("SET_DEVICE_ID", "rejected", "deviceId must be 4 hex chars, for example F001", false);
        return;
    }
    copyBounded(runtimeConfig.deviceId, sizeof(runtimeConfig.deviceId), deviceId);
    runtimeConfig.nodeId = doc["nodeId"] | nodeIdFromDeviceId(runtimeConfig.deviceId, DEFAULT_NODE_ID);
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

void handleSerialCommand(const pgl::gld::GldSerialCommand& command) {
    switch (command.type) {
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
        case pgl::gld::GldSerialCommandType::SetAppConfigJson:
            onSetAppConfigJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::SetDeviceIdJson:
            onSetDeviceIdJson(command.payload);
            break;
        case pgl::gld::GldSerialCommandType::None:
        default:
            break;
    }
}

// Check Serial every loop tick for operator/app commands.
void checkSerial() {
    for (uint8_t i = 0; i < 8; ++i) {
        pgl::gld::GldSerialCommand command{};
        if (!pgl::gld::parseSerialCommand(command)) {
            return;
        }
        handleSerialCommand(command);
    }
}

void maintainBatteryWakeLatch() {
    if (!batteryPowerMode) return;

    const uint32_t now = millis();
    if (now - lastTpl5010KeepaliveMs >= pgl::gld::GLD_TPL5010_KEEPALIVE_INTERVAL_MS) {
        lastTpl5010KeepaliveMs = now;
        pgl::gld::pulseGldTpl5010Keepalive();
    }
}

void pulseBatteryWakeLatchNow() {
    if (!batteryPowerMode) return;
    pgl::gld::pulseGldTpl5010Keepalive();
    lastTpl5010KeepaliveMs = millis();
}

void batteryModeTick() {
    checkSerial();
    maintainBatteryWakeLatch();
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
    int drdyLevel = -1;
    uint8_t status = 0;
};

struct BootI2cReport {
    bool tcaOk = false;
    bool mcpOk[pgl::gld::board::SENSOR_COUNT]{};
    uint8_t mcpOkCount = 0;
};

struct BootMcpControlReport {
    bool tested = false;
    bool dacReady = false;
    bool writeLow[pgl::gld::board::SENSOR_COUNT]{};
    bool writeHigh[pgl::gld::board::SENSOR_COUNT]{};
};

bool i2cAck(uint8_t addr) {
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

bool tcaSelect(uint8_t muxChannel) {
    if (muxChannel > 7) return false;
    Wire.beginTransmission(pgl::gld::board::TCA9548A_ADDR);
    Wire.write(static_cast<uint8_t>(1U << muxChannel));
    return Wire.endTransmission() == 0;
}

void tcaDisableAll() {
    Wire.beginTransmission(pgl::gld::board::TCA9548A_ADDR);
    Wire.write(static_cast<uint8_t>(0));
    Wire.endTransmission();
}

BootAdsReport probeBootAds(bool ok) {
    BootAdsReport report{};
    report.ok = ok;
    report.drdyLevel = digitalRead(pgl::gld::board::PIN_ADS1256_DRDY);
    report.status = ok ? ads.readStatusRegister() : 0;
    return report;
}

BootI2cReport probeBootI2c() {
    BootI2cReport report{};
    Wire.begin(pgl::gld::board::PIN_I2C_SDA, pgl::gld::board::PIN_I2C_SCL);
    report.tcaOk = i2cAck(pgl::gld::board::TCA9548A_ADDR);
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        const uint8_t muxChannel = static_cast<uint8_t>(pgl::gld::board::SENSOR_TO_MUX_CH[sensor]);
        const bool muxOk = report.tcaOk && tcaSelect(muxChannel);
        report.mcpOk[sensor] = muxOk && i2cAck(pgl::gld::board::MCP4725_ADDR);
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
        report.writeLow[sensor] = dac.writeDac(sensor, BOOT_MCP_TEST_CODE_LOW);
        delay(BOOT_DAC_SETTLE_MS);
        report.writeHigh[sensor] = dac.writeDac(sensor, BOOT_MCP_TEST_CODE_HIGH);
        delay(BOOT_DAC_SETTLE_MS);
    }
    return report;
}

void bootTableRow(const char* ic, const char* check, const char* status, const char* detail) {
    logPrintf("| %-15s | %-18s | %-9s | %-40s |\n", ic, check, status, detail);
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
    char detail[128];

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

    snprintf(detail, sizeof(detail), "CS=%d DRDY=%d SYNC=%d drdy=%d status=0x%02X",
             pgl::gld::board::PIN_ADS1256_CS,
             pgl::gld::board::PIN_ADS1256_DRDY,
             pgl::gld::board::PIN_ADS1256_SYNC,
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
            snprintf(detail, sizeof(detail), "mux=%u addr=0x%02X write=1,10",
                     static_cast<unsigned>(pgl::gld::board::SENSOR_TO_MUX_CH[sensor]),
                     pgl::gld::board::MCP4725_ADDR);
        } else {
            snprintf(detail, sizeof(detail), "mux=%u addr=0x%02X ack only",
                     static_cast<unsigned>(pgl::gld::board::SENSOR_TO_MUX_CH[sensor]),
                     pgl::gld::board::MCP4725_ADDR);
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
    logPrintf("WIFI_CONNECT ssid=%s\n", runtimeConfig.wifiSsid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(runtimeConfig.wifiSsid, runtimeConfig.wifiPassword);
    const uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) {
        batteryModeTick();
        delay(50);
    }
    const bool ok = WiFi.status() == WL_CONNECTED;
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
    mqtt.setServer(runtimeConfig.mqttHost, runtimeConfig.mqttPort);
    mqtt.setCallback(mqttCallback);
    logPrintf("MQTT_CONNECT host=%s port=%u\n", runtimeConfig.mqttHost, runtimeConfig.mqttPort);
    const bool ok = mqtt.connect(mqttClientId, runtimeConfig.mqttUser, runtimeConfig.mqttPass);
    logPrintf("MQTT_CONNECT_RESULT=%s state=%d\n", ok ? "OK" : "FAIL", mqtt.state());
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
    StaticJsonDocument<128> doc;
    doc["device_id"] = runtimeConfig.deviceId;
    doc["stage"] = "DATASET";
    doc["state"] = state;
    doc["detail"] = detail;
    char buf[128];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(topicStatus, buf, false);
}

void publishDatasetSummary() {
    StaticJsonDocument<192> doc;
    doc["device_id"] = runtimeConfig.deviceId;
    doc["stage"] = "DATASET";
    doc["label"] = currentLabel;
    doc["total_samples"] = datasetSeq;
    doc["duration_ms"] = static_cast<uint32_t>(millis() - sessionStartMs);
    doc["nulling_profile_id"] = nullingProfileId;
    char buf[192];
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
        if (nullingProfileId == 0) {
            publishCmdAck("START_DATASET", "reject_no_profile");
            return;
        }
        const char* label = doc["label"] | "unknown";
        strncpy(currentLabel, label, sizeof(currentLabel) - 1);
        currentLabel[sizeof(currentLabel) - 1] = '\0';
        targetSamples    = doc["target_samples"]     | 0u;
        sampleIntervalMs = doc["sample_interval_ms"] | 1000u;
        maxDurationMs    = doc["max_duration_ms"]    | 0u;
        useFanIntake     = doc["use_fan_intake"]     | true;
        fanOnMs          = doc["fan_on_ms"]          | 1000u;
        postFanSettleMs  = doc["post_fan_settle_ms"] | 0u;
        datasetSeq     = 0;
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
    pgl::gld::GldNullingProfile profile{};
    if (pgl::gld::loadNullingProfile(profile)) {
        logPrintf("NULLING_NVS_LOAD=found profileId=%u\n", profile.profileId);
        nullingProfileId = profile.profileId;
        for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch)
            dac.writeDac(ch, profile.dacCode[ch]);
        return true;
    }
    if (!runIfMissing) {
        nullingProfileId = 0;
        logPrintln("NULLING_NVS_LOAD=empty auto_nulling=skip");
        return false;
    }
    logPrintln("NULLING_NVS_LOAD=empty running_nulling_now");
    const pgl::gld::GldNullingServiceResult result =
        pgl::gld::runNullingService(ads, dac, nullingLogLine, batteryModeTick);
    logPrintf("NULLING_RUN status=%s successCount=%u\n",
              pgl::gld::gldNullingStatusName(result.status), result.successCount);
    if (result.status != pgl::gld::GldNullingStatus::Ok) return false;
    pgl::gld::GldNullingProfile toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = 1;
    pgl::gld::saveNullingProfile(toSave);
    nullingProfileId = 1;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch)
        dac.writeDac(ch, toSave.dacCode[ch]);
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
    nextNullingRetryMs = millis() + NULLING_RETRY_DELAY_MS;
    logPrintf("NULLING_RETRY_SCHEDULED reason=%s delayMs=%lu\n",
              reason,
              static_cast<unsigned long>(NULLING_RETRY_DELAY_MS));
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
    toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = static_cast<uint8_t>(
        pgl::gld::isNullingProfileValid(existing)
            ? static_cast<uint8_t>(existing.profileId + 1u) : 1u);
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
    pgl::gld::writeGldMode(pgl::gld::GldMode::INFERENCE);
    delay(NULLING_AUTO_RESTART_DELAY_MS);
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
        pgl::gld::runNullingService(ads, dac, nullingLogLine, checkSerial);
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
    pgl::gld::GldNullingProfile profile{};
    if (!pgl::gld::loadNullingProfile(profile)) {
        if (dacReady) {
            const bool resetOk = dac.writeAll(0);
            delay(BOOT_DAC_SETTLE_MS);
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
    delay(BOOT_DAC_SETTLE_MS);
    if (allApplied) {
        nullingProfileId = profile.profileId;
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
    if (!power.externalPower) {
        return;
    }

    logPrintln("[BOOT_SENSOR_SAMPLES]");
    applySavedNullingProfileOnly();

    if (!adsReady) {
        logPrintln("BOOT_SENSOR_SAMPLE_BLOCKED reason=ads_not_ready");
        return;
    }

    for (uint8_t sample = 1; sample <= BOOT_SENSOR_SNAPSHOT_COUNT; ++sample) {
        printBootSensorSnapshotRow(sample);
    }
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
    int16_t state = loraRadio->begin(STAR_FREQ_MHZ, STAR_BW_KHZ, STAR_SF, STAR_CR,
                                     STAR_SYNC_WORD, STAR_TX_POWER, STAR_PREAMBLE, LORA_TCXO_V);
    if (state == RADIOLIB_ERR_SPI_CMD_FAILED) {
        state = loraRadio->begin(STAR_FREQ_MHZ, STAR_BW_KHZ, STAR_SF, STAR_CR,
                                 STAR_SYNC_WORD, STAR_TX_POWER, STAR_PREAMBLE, LORA_XTAL_V);
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
    for (size_t i = 0; i < pgl::protocol::GLD_AES_GCM_NONCE_SIZE; ++i)
        nonce[i] = pgl::gld::selftest::NONCE[i];
    const uint32_t r = esp_random();
    nonce[4]  = static_cast<uint8_t>((r >> 24) & 0xFF);
    nonce[5]  = static_cast<uint8_t>((r >> 16) & 0xFF);
    nonce[6]  = static_cast<uint8_t>((r >>  8) & 0xFF);
    nonce[7]  = static_cast<uint8_t>( r         & 0xFF);
    nonce[8]  = static_cast<uint8_t>((nc->counter >> 24) & 0xFF);
    nonce[9]  = static_cast<uint8_t>((nc->counter >> 16) & 0xFF);
    nonce[10] = static_cast<uint8_t>((nc->counter >>  8) & 0xFF);
    nonce[11] = static_cast<uint8_t>( nc->counter        & 0xFF);
    ++nc->counter;
    return true;
}

void updateAlarmOutputs(bool alarm) {
    if (alarm == lastAlarm) return;
    lastAlarm = alarm;
    pgl::gld::writeGldAlarmLatched(alarm);
    optionalDigitalWrite(pgl::gld::board::PIN_ALARM_LAMP, alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    optionalDigitalWrite(pgl::gld::board::PIN_BUZZER,     alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    optionalDigitalWrite(pgl::gld::board::PIN_STATUS_LED, alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    logPrintf("GLD_ALARM_OUTPUT alarm=%u\n", alarm ? 1 : 0);
}

uint8_t modelClassToGasClass(int predicted) {
    switch (predicted) {
        case 0: return pgl::protocol::GLD_GAS_CLEAR;
        case 1: return pgl::protocol::GLD_GAS_LPG;
        case 2: return pgl::protocol::GLD_GAS_METHANE;
        case 3: return pgl::protocol::GLD_GAS_PROPANE;
        case 4: return pgl::protocol::GLD_GAS_BUTANE;
        default: return pgl::protocol::GLD_GAS_ANOMALY;
    }
}

void runInference(const float mavVoltage[8]) {
    if (!mlReady || !network->isInitialized()) return;
    float* modelInput = network->getInputBuffer();
    if (!modelInput) return;
    // Hardware channels: {MQ8,MQ135,MQ3,MQ5,MQ4,MQ7,MQ6,MQ2}
    // Model feature order (scaler_params): {MQ135,MQ2,MQ3,MQ4,MQ7,MQ5,MQ6,MQ8}
    // MODEL_FROM_HW[modelIdx] = hwChannelIdx that provides that model feature.
    static constexpr uint8_t MODEL_FROM_HW[8] = {1, 7, 2, 4, 5, 3, 6, 0};
    for (uint8_t m = 0; m < pgl::gld::board::SENSOR_COUNT; ++m) {
        modelInput[m] = (mavVoltage[MODEL_FROM_HW[m]] - feature_means[m]) / feature_stds[m];
    }
    float confidenceFloat = 0.0f;
    const int predicted = network->predict(confidenceFloat);
    if (predicted < 0) { logPrintln("GLD_ML_PREDICT_ERROR"); return; }
    lastResult = {modelClassToGasClass(predicted),
                  static_cast<uint8_t>(confidenceFloat * 100.0f)};
    logPrintf("GLD_ML_RESULT predictedClass=%d gasClass=%u(%s) confidence=%u\n",
              predicted, lastResult.gasClass,
              pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence);
}

void runScan() {
    float mavVoltage[8] = {};
    uint8_t primedChannels = 0;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        latestSensorGain[ch] = r.gain;
        latestSensorStatus[ch] = static_cast<uint8_t>(r.status);
        mavVoltage[ch] = (r.status == pgl::gld::GldAds1256Status::Ok)
                          ? movingAvg.add(ch, r.voltage)
                          : movingAvg.value(ch);
        latestSensorVoltage[ch] = mavVoltage[ch];
        if (movingAvg.count(ch) >= MIN_PRIMED_COUNT) ++primedChannels;
    }
    latestTelemetryValid = true;
    const bool primed = primedChannels >= pgl::gld::board::SENSOR_COUNT;
    if (primed) runInference(mavVoltage);
    const bool alarm = lastResult.gasClass != pgl::protocol::GLD_GAS_CLEAR &&
                       lastResult.confidence >= ML_CONFIDENCE_THRESHOLD;
    logPrintf("GLD_SENSOR_SCAN seq=%lu allValid=%u primed=%u gasClass=%u(%s) confidence=%u alarm=%u\n",
              static_cast<unsigned long>(txCounter),
              adsReady ? 1 : 0, primed ? 1 : 0,
              lastResult.gasClass, pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence, alarm ? 1 : 0);
    updateAlarmOutputs(alarm);
}

void openLoRaRxWindow() {
    if (!radioReady || !loraRadio) return;
    loraRxFlag = false;
    loraRadio->setPacketReceivedAction(onLoRaRxDone);
    loraRadio->startReceive();
    const uint32_t t0 = millis();
    while (!loraRxFlag && millis() - t0 < LORA_RX_WINDOW_MS) delay(5);
    if (loraRxFlag) {
        uint8_t rxBuf[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD]{};
        const size_t rxLen = loraRadio->getPacketLength();
        const int16_t rxState = loraRadio->readData(rxBuf, sizeof(rxBuf));
        logPrintf("GLD_LORA_DOWNLINK_RX state=%d len=%u\n", rxState, static_cast<unsigned>(rxLen));
        if (rxState == RADIOLIB_ERR_NONE) {
            pgl::gld::GldMode newMode;
            if (pgl::gld::parseLoRaDownlinkCmd(rxBuf, rxLen,
                                               runtimeConfig.nodeId,
                                               runtimeConfig.aesKey,
                                               runtimeConfig.aesKeyPresent,
                                               runtimeConfig.lastDownlinkCommandId,
                                               newMode)) {
                logPrintf("GLD_LORA_DOWNLINK_CMD mode=%s\n", pgl::gld::gldModeName(newMode));
                saveDownlinkReplayState();
                onModeCmd(newMode);
            }
        }
    }
    loraRadio->standby();
}

void transmitOnce() {
    if (!runtimeConfig.aesKeyPresent || runtimeConfig.aesKeyId == 0) {
        lastLoraTxState = -32767;
        lastLoraTxOk = false;
        logPrintln("GLD_SECURITY_NOT_PROVISIONED aesKey=0 txBlocked=1");
        logPrintln("GLD_LORA_TX_RESULT=FAIL");
        return;
    }

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    const uint16_t batteryMv = power.batteryValid ? power.batteryMv
                                                   : pgl::protocol::GLD_BATTERY_MV_INVALID;
    pgl::gld::GldFrameBuilderConfig config{
        runtimeConfig.nodeId, static_cast<uint16_t>(GLD_CH_ID),
        runtimeConfig.aesKeyId, runtimeConfig.aesKey,
        power.externalPower, pgl::protocol::GLD_LEL_THRESHOLD_PERCENT,
    };
    pgl::gld::GldFrameBuildInput input{
        lastResult.gasClass, lastResult.confidence, batteryMv, txSeq,
    };
    NonceCtx nonceCtx{txCounter};
    pgl::gld::GldBuiltFrame frame{};
    const pgl::gld::GldFrameStatus buildStatus =
        pgl::gld::buildGldUplinkFrame(config, input, nonceProvider, &nonceCtx, frame);
    txCounter = nonceCtx.counter;

    logPrintf("GLD_TX_HEADER status=%s seq=%u typeFlags=0x%02X alarm=%u gasClass=%u(%s) confidence=%u frameSize=%u\n",
              pgl::gld::gldFrameStatusName(buildStatus), txSeq, frame.typeFlags,
              frame.alarm ? 1 : 0, lastResult.gasClass,
              pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence, static_cast<unsigned>(frame.size));

    if (buildStatus != pgl::gld::GldFrameStatus::Ok) {
        lastLoraTxState = -32768;
        lastLoraTxOk = false;
        logPrintln("GLD_LORA_TX_RESULT=FAIL");
        return;
    }

    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    const int16_t txState = loraRadio->transmit(frame.bytes, frame.size);
    lastLoraTxState = txState;
    lastLoraTxOk = txState == RADIOLIB_ERR_NONE;
    digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
    digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);
    logPrintf("GLD_STAR_TX_STATE=%d seq=%u\n", txState, txSeq);
    logPrintln(txState == RADIOLIB_ERR_NONE ? "GLD_LORA_TX_RESULT=PASS" : "GLD_LORA_TX_RESULT=FAIL");
    ++txSeq;

    // Class A RX window for downlink commands
    openLoRaRxWindow();
}

// ---------------------------------------------------------------------------
// Dataset sample publish
// ---------------------------------------------------------------------------

void publishDataRecord() {
    StaticJsonDocument<1024> doc;
    doc["device_id"]          = runtimeConfig.deviceId;
    doc["node_id"]            = runtimeConfig.nodeId;
    doc["mode"]               = "DATASET";
    doc["seq"]                = datasetSeq;
    doc["timestamp_ms"]       = static_cast<uint32_t>(millis());
    doc["label"]              = currentLabel;
    doc["nulling_profile_id"] = nullingProfileId;
    JsonArray svArr  = doc.createNestedArray("sensor_voltage");
    JsonArray gainArr = doc.createNestedArray("sensor_gain");
    JsonArray foArr  = doc.createNestedArray("feature_order");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        latestSensorVoltage[ch] = r.voltage;
        latestSensorGain[ch] = r.gain;
        latestSensorStatus[ch] = static_cast<uint8_t>(r.status);
        svArr.add(r.voltage);
        gainArr.add(r.gain);
        foArr.add(pgl::gld::board::SENSOR_NAMES[ch]);
    }
    latestTelemetryValid = true;
    char payload[896];
    const size_t len = serializeJson(doc, payload, sizeof(payload));
    const bool ok = mqtt.publish(topicData, payload, false);
    logPrintf("DATASET_RECORD seq=%lu ok=%u len=%u\n",
              static_cast<unsigned long>(datasetSeq), ok ? 1 : 0,
              static_cast<unsigned>(len));
    ++datasetSeq;
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
    delay(1000);
    loadRuntimeConfig();
    setupPins();
    pgl::gld::beginGldPowerPins();
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
    logPrintf("GLD_POWER mode=%s externalPower=%u batteryMv=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0, power.batteryMv);
    batteryPowerMode = !power.externalPower;
    lastTpl5010KeepaliveMs = millis();
    pulseBatteryWakeLatchNow();
    emitInfoJson();
    emitStatusJson();

    adsReady = ads.begin(gldSpi);
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");
    const BootAdsReport bootAds = probeBootAds(adsReady);
    const BootI2cReport bootI2c = probeBootI2c();
    const BootMcpControlReport bootMcpControl = testBootMcpControl(power.externalPower);
    lastBootAdsDrdyLevel = bootAds.drdyLevel;
    lastBootAdsStatus = bootAds.status;
    lastBootTcaOk = bootI2c.tcaOk;
    lastBootMcpOkCount = bootI2c.mcpOkCount;
    lastBootMcpControlTested = bootMcpControl.tested;
    lastBootMcpControlOkCount = 0;
    for (uint8_t sensor = 0; sensor < pgl::gld::board::SENSOR_COUNT; ++sensor) {
        if (bootMcpControl.dacReady &&
            bootMcpControl.writeLow[sensor] &&
            bootMcpControl.writeHigh[sensor]) {
            ++lastBootMcpControlOkCount;
        }
    }

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        // --- INFERENCE mode init ---
        disableNetworkForOfflineMode("inference_mode");
        network = new NeuralNetwork();
        mlReady = network->isInitialized();
        const int mlOutputSize = mlReady ? network->getOutputSize() : -1;
        logPrintf("GLD_ML_INIT initialized=%u outputSize=%d\n",
                  mlReady ? 1 : 0, mlOutputSize);

        radioReady = beginLoraRadio();
        logPrintf("GLD_INFERENCE_READY adsReady=%u radioReady=%u mlReady=%u\n",
                  adsReady ? 1 : 0, radioReady ? 1 : 0, mlReady ? 1 : 0);
        char modeDetail[96];
        snprintf(modeDetail, sizeof(modeDetail), "ads=%s mcp=%u/%u lora=%s ml=%s",
                 passFail(adsReady),
                 bootI2c.mcpOkCount,
                 pgl::gld::board::SENSOR_COUNT,
                 passFail(radioReady),
                 passFail(mlReady));
        printBootIcReport(power, bootAds, bootI2c, bootMcpControl,
                          true, radioReady,
                          true, mlReady, mlOutputSize,
                          adsReady && radioReady && mlReady,
                          modeDetail);
        runExternalPowerBootSensorSamples(power);

        lastScanMs = millis();
        lastTxMs   = millis();

    } else if (currentMode == pgl::gld::GldMode::NULLING && pgl::gld::readGldAlarmLatched()) {
        // Nulling must not run while a prior alarm is still latched/unacknowledged
        // (design.md §3.6: "nulling blocked when alarm active"). Clear the alarm
        // (button hold / IO38 CLR) before switching into Nulling mode again.
        logPrintln("MODE_BLOCKED reason=alarm_latched mode=nulling");
        pgl::gld::writeGldMode(pgl::gld::GldMode::INFERENCE);
        delay(NULLING_AUTO_RESTART_DELAY_MS);
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
            pulseBatteryWakeLatchNow();
        }
        dacReady = dac.begin(Wire);
        logPrintf("DAC_MUX_BEGIN_RESULT=%s\n", dacReady ? "PASS" : "FAIL");
        pulseBatteryWakeLatchNow();

        if (currentMode == pgl::gld::GldMode::DATASET) {
            if (adsReady && dacReady) {
                initNulling(false);
                pulseBatteryWakeLatchNow();
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
                              adsReady && dacReady && nullingProfileId > 0,
                              modeDetail);
            runExternalPowerBootSensorSamples(power);
            pulseBatteryWakeLatchNow();
            connectWifi();
            pulseBatteryWakeLatchNow();
            mqtt.setBufferSize(MQTT_BUFFER_SIZE);
            mqttConnect();
            pulseBatteryWakeLatchNow();
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
                armNullingRetry("hardware_not_ready");
            } else {
                logPrintln("NULLING_RUN=start");

                const pgl::gld::GldNullingServiceResult result =
                    pgl::gld::runNullingService(ads, dac, nullingLogLine, batteryModeTick);
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
                    armNullingRetry(fullOk ? "nvs_save_failed" : nullingRetryReason(result.status));
                }
            }
        }
    }
}

void loop() {
    checkSerial();
    maintainBatteryWakeLatch();

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        const uint32_t now = millis();

        if (batteryPowerMode) {
            // One-shot wake cycle: scan + inference + LoRa TX + RX window, then
            // clear the power latch to shut the node down. If an alarm is active,
            // stay powered (the alarm lamp/buzzer are driven directly by ESP32
            // GPIO, so cutting power would silence them) and retry each
            // SCAN_INTERVAL_MS until the alarm clears.
            if (!batteryCyclePoweredOff && now - lastScanMs >= SCAN_INTERVAL_MS) {
                lastScanMs = now;
                if (adsReady) runScan();
                if (radioReady) transmitOnce();
                if (!lastAlarm) {
                    logPrintln("GLD_BATTERY_CYCLE_DONE power_off");
                    pgl::gld::pulseGldPowerLatchClear();
                    batteryCyclePoweredOff = true;
                } else {
                    logPrintln("GLD_BATTERY_CYCLE_ALARM_ACTIVE staying_awake");
                }
            }
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
        const uint32_t now = millis();
        if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
            lastStatusMs = now;
            if (datasetState == DatasetState::Running)
                publishDatasetStatus("running", currentLabel);
        }
        runDatasetStateMachine();
        delay(10);

    } else {
        // NULLING mode: offline calibration; Serial commands are checked at loop start.
        if (nullingRetryArmed &&
            static_cast<int32_t>(millis() - nextNullingRetryMs) >= 0) {
            runNullingRetryAttempt();
        }
        delay(100);
    }
}
