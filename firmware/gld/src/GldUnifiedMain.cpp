#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdarg>
#include <cstdio>
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
constexpr const char* WIFI_SSID      = GLD_WIFI_SSID;
constexpr const char* WIFI_PASSWORD  = GLD_WIFI_PASSWORD;
constexpr const char* MQTT_HOST      = GLD_MQTT_HOST;
constexpr uint16_t    MQTT_PORT      = GLD_MQTT_PORT;
constexpr const char* MQTT_USER      = GLD_MQTT_USER;
constexpr const char* MQTT_PASS      = GLD_MQTT_PASS;
constexpr const char* MQTT_CLIENT_ID = GLD_MQTT_CLIENT_ID;
constexpr const char* DEVICE_ID_STR  = GLD_DEVICE_ID_STR;
constexpr uint16_t    NODE_ID        = GLD_NODE_ID;

constexpr const char* TOPIC_CMD         = GLD_TOPIC_CMD;
constexpr const char* TOPIC_DATASET     = GLD_TOPIC_DATASET;
constexpr const char* TOPIC_DATA        = GLD_TOPIC_DATA;
constexpr const char* TOPIC_STATUS      = GLD_TOPIC_STATUS;
constexpr const char* TOPIC_SUMMARY     = GLD_TOPIC_SUMMARY;
constexpr const char* TOPIC_ACK         = GLD_TOPIC_ACK;
constexpr const char* TOPIC_NULLING     = GLD_TOPIC_NULLING;
constexpr const char* TOPIC_NULL_STATUS = GLD_TOPIC_NULL_STATUS;

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

// ---------------------------------------------------------------------------
// Channel remapping: hardware ADS1256 channel → model input index
// ---------------------------------------------------------------------------
constexpr uint8_t HW_TO_MODEL[8] = {0, 2, 5, 3, 4, 6, 1, 7};
constexpr uint8_t ML_CONFIDENCE_THRESHOLD = pgl::protocol::GLD_LEL_THRESHOLD_PERCENT;

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
uint8_t  txSeq           = 0;
uint32_t txCounter       = 0;
uint32_t lastScanMs      = 0;
uint32_t lastTxMs        = 0;
uint32_t lastMqttAttemptMs = 0;
uint32_t lastStatusMs    = 0;
bool     lastAlarm       = false;
uint8_t  nullingProfileId = 0;
pgl::gld::GldClassifyResult lastResult{pgl::protocol::GLD_GAS_CLEAR, 100};

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

void logPrintf(const char* fmt, ...) {
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
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
#endif
}

// ---------------------------------------------------------------------------
// Mode command handler — NVS write + reboot
// ---------------------------------------------------------------------------

void onModeCmd(pgl::gld::GldMode newMode) {
    logPrintf("GLD_MODE_SWITCH current=%s new=%s\n",
              pgl::gld::gldModeName(currentMode),
              pgl::gld::gldModeName(newMode));
    pgl::gld::switchGldMode(newMode);
}

// Check Serial every loop tick for SET_MODE commands
void checkSerial() {
    pgl::gld::GldMode newMode;
    if (pgl::gld::parseSerialModeCommand(newMode)) {
        onModeCmd(newMode);
    }
}

// ---------------------------------------------------------------------------
// Common hardware init (all modes)
// ---------------------------------------------------------------------------

void setupPins() {
    pinMode(pgl::gld::board::PIN_LORA_CS,    OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_CS,    HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RST,   OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_RST,   HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_RXEN,  LOW);
    pinMode(pgl::gld::board::PIN_LORA_TXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_TXEN,  LOW);
    pinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT); digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, LOW);
    pinMode(pgl::gld::board::PIN_BUZZER,     OUTPUT); digitalWrite(pgl::gld::board::PIN_BUZZER,     LOW);
    pinMode(pgl::gld::board::PIN_DC_FAN,     OUTPUT); digitalWrite(pgl::gld::board::PIN_DC_FAN,     LOW);
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT); digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
}

// ---------------------------------------------------------------------------
// WiFi + MQTT helpers (dataset / nulling modes)
// ---------------------------------------------------------------------------

bool connectWifi() {
    logPrintf("WIFI_CONNECT ssid=%s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    const uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) delay(200);
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
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(mqttCallback);
    logPrintf("MQTT_CONNECT host=%s port=%u\n", MQTT_HOST, MQTT_PORT);
    const bool ok = mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
    logPrintf("MQTT_CONNECT_RESULT=%s state=%d\n", ok ? "OK" : "FAIL", mqtt.state());
    if (ok) {
        mqtt.subscribe(TOPIC_CMD);
        if (currentMode == pgl::gld::GldMode::DATASET) {
            mqtt.subscribe(TOPIC_DATASET);
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
    doc["device_id"] = DEVICE_ID_STR;
    doc["cmd"] = cmd;
    doc["result"] = result;
    doc["timestamp_ms"] = static_cast<uint32_t>(millis());
    char buf[128];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(TOPIC_ACK, buf, false);
}

void publishDatasetStatus(const char* state, const char* detail) {
    StaticJsonDocument<128> doc;
    doc["device_id"] = DEVICE_ID_STR;
    doc["stage"] = "DATASET";
    doc["state"] = state;
    doc["detail"] = detail;
    char buf[128];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(TOPIC_STATUS, buf, false);
}

void publishDatasetSummary() {
    StaticJsonDocument<192> doc;
    doc["device_id"] = DEVICE_ID_STR;
    doc["stage"] = "DATASET";
    doc["label"] = currentLabel;
    doc["total_samples"] = datasetSeq;
    doc["duration_ms"] = static_cast<uint32_t>(millis() - sessionStartMs);
    doc["nulling_profile_id"] = nullingProfileId;
    char buf[192];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(TOPIC_SUMMARY, buf, false);
}

void publishNullingProfile(const pgl::gld::GldNullingProfile& profile) {
    StaticJsonDocument<640> doc;
    doc["profileId"] = profile.profileId;
    doc["valid"] = pgl::gld::isNullingProfileValid(profile);
    JsonArray dacArr   = doc.createNestedArray("dacCode");
    JsonArray baseArr  = doc.createNestedArray("baselineV");
    JsonArray afterArr = doc.createNestedArray("afterV");
    JsonArray okArr    = doc.createNestedArray("channelOk");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        dacArr.add(profile.dacCode[ch]);
        baseArr.add(profile.baselineV[ch]);
        afterArr.add(profile.afterV[ch]);
        okArr.add(profile.channelOk[ch]);
    }
    char payload[640];
    serializeJson(doc, payload, sizeof(payload));
    mqtt.publish(TOPIC_NULLING, payload, true);
    logPrintf("MQTT_PUBLISH topic=%s ok=1 len=%u\n",
              TOPIC_NULLING, static_cast<unsigned>(strlen(payload)));
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
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, HIGH);
        publishCmdAck("START_DATASET", "ok");
        publishDatasetStatus("running", currentLabel);
        logPrintf("DATASET_START label=%s target=%lu interval=%lu\n",
                  currentLabel,
                  static_cast<unsigned long>(targetSamples),
                  static_cast<unsigned long>(sampleIntervalMs));
    } else if (strcmp(cmd, "STOP_DATASET") == 0) {
        if (datasetState == DatasetState::Running)
            digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
        datasetState = DatasetState::Idle;
        sampleStep   = SampleStep::None;
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
        publishCmdAck("STOP_DATASET", "ok");
        publishDatasetSummary();
        publishDatasetStatus("idle", "stopped");
        logPrintf("DATASET_STOP totalSeq=%lu\n", static_cast<unsigned long>(datasetSeq));
    } else {
        publishCmdAck(cmd, "unknown_cmd");
    }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, TOPIC_CMD) == 0) {
        handleCmdTopic(reinterpret_cast<const char*>(payload), length);
    } else if (strcmp(topic, TOPIC_DATASET) == 0) {
        handleDatasetTopic(reinterpret_cast<const char*>(payload), length);
    }
}

// ---------------------------------------------------------------------------
// Nulling helpers
// ---------------------------------------------------------------------------

bool initNulling() {
    pgl::gld::GldNullingProfile profile{};
    if (pgl::gld::loadNullingProfile(profile)) {
        logPrintf("NULLING_NVS_LOAD=found profileId=%u\n", profile.profileId);
        nullingProfileId = profile.profileId;
        for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch)
            dac.writeDac(ch, profile.dacCode[ch]);
        return true;
    }
    logPrintln("NULLING_NVS_LOAD=empty running_nulling_now");
    const pgl::gld::GldNullingServiceResult result = pgl::gld::runNullingService(ads, dac);
    logPrintf("NULLING_RUN status=%s successCount=%u\n",
              pgl::gld::gldNullingStatusName(result.status), result.successCount);
    if (result.status == pgl::gld::GldNullingStatus::AllChannelsFailed) return false;
    pgl::gld::GldNullingProfile toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = 1;
    pgl::gld::saveNullingProfile(toSave);
    nullingProfileId = 1;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch)
        dac.writeDac(ch, toSave.dacCode[ch]);
    return true;
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
    digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, alarm ? HIGH : LOW);
    digitalWrite(pgl::gld::board::PIN_BUZZER,     alarm ? HIGH : LOW);
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, alarm ? HIGH : LOW);
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
    for (uint8_t hwCh = 0; hwCh < pgl::gld::board::SENSOR_COUNT; ++hwCh) {
        const uint8_t mIdx = HW_TO_MODEL[hwCh];
        modelInput[mIdx] = (mavVoltage[hwCh] - feature_means[mIdx]) / feature_stds[mIdx];
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
        mavVoltage[ch] = (r.status == pgl::gld::GldAds1256Status::Ok)
                         ? movingAvg.add(ch, r.voltage)
                         : movingAvg.value(ch);
        if (movingAvg.count(ch) >= MIN_PRIMED_COUNT) ++primedChannels;
    }
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
            if (pgl::gld::parseLoRaDownlinkCmd(rxBuf, rxLen, NODE_ID, newMode)) {
                logPrintf("GLD_LORA_DOWNLINK_CMD mode=%s\n", pgl::gld::gldModeName(newMode));
                onModeCmd(newMode);
            }
        }
    }
    loraRadio->standby();
}

void transmitOnce() {
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    const uint16_t batteryMv = power.batteryValid ? power.batteryMv
                                                   : pgl::protocol::GLD_BATTERY_MV_INVALID;
    pgl::gld::GldFrameBuilderConfig config{
        NODE_ID, static_cast<uint16_t>(GLD_CH_ID),
        pgl::gld::selftest::KEY_ID,  pgl::gld::selftest::AES_KEY,
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
        logPrintln("GLD_LORA_TX_RESULT=FAIL");
        return;
    }

    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    const int16_t txState = loraRadio->transmit(frame.bytes, frame.size);
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
    doc["device_id"]          = DEVICE_ID_STR;
    doc["node_id"]            = NODE_ID;
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
        svArr.add(r.voltage);
        gainArr.add(r.gain);
        foArr.add(pgl::gld::board::SENSOR_NAMES[ch]);
    }
    char payload[896];
    const size_t len = serializeJson(doc, payload, sizeof(payload));
    const bool ok = mqtt.publish(TOPIC_DATA, payload, false);
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
    digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
    datasetState = DatasetState::Idle;
    sampleStep   = SampleStep::None;
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
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
                    digitalWrite(pgl::gld::board::PIN_DC_FAN, HIGH);
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
                digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
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

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("GLD_POWER mode=%s externalPower=%u batteryMv=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0, power.batteryMv);

    adsReady = ads.begin(gldSpi);
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        // --- INFERENCE mode init ---
        network = new NeuralNetwork();
        mlReady = network->isInitialized();
        logPrintf("GLD_ML_INIT initialized=%u outputSize=%d\n",
                  mlReady ? 1 : 0, mlReady ? network->getOutputSize() : -1);

        radioReady = beginLoraRadio();
        logPrintf("GLD_INFERENCE_READY adsReady=%u radioReady=%u mlReady=%u\n",
                  adsReady ? 1 : 0, radioReady ? 1 : 0, mlReady ? 1 : 0);

        lastScanMs = millis();
        lastTxMs   = millis();

    } else {
        // --- DATASET / NULLING mode init ---
        dacReady = dac.begin(Wire);
        logPrintf("DAC_MUX_BEGIN_RESULT=%s\n", dacReady ? "PASS" : "FAIL");

        if (currentMode == pgl::gld::GldMode::DATASET) {
            if (adsReady && dacReady) initNulling();
            logPrintf("DATASET_READY adsReady=%u dacReady=%u nullingProfileId=%u\n",
                      adsReady ? 1 : 0, dacReady ? 1 : 0, nullingProfileId);
            connectWifi();
            mqtt.setBufferSize(MQTT_BUFFER_SIZE);
            mqttConnect();
            lastStatusMs = millis();

        } else {
            // NULLING mode: run calibration first (blocking)
            if (!adsReady || !dacReady) {
                logPrintf("NULLING_BLOCKED adsReady=%u dacReady=%u\n",
                          adsReady ? 1 : 0, dacReady ? 1 : 0);
            } else {
                logPrintln("NULLING_RUN=start");
                pgl::gld::GldNullingProfile existing{};
                pgl::gld::loadNullingProfile(existing);

                const pgl::gld::GldNullingServiceResult result =
                    pgl::gld::runNullingService(ads, dac);
                logPrintf("NULLING_RUN_DONE status=%s successCount=%u\n",
                          pgl::gld::gldNullingStatusName(result.status), result.successCount);

                if (result.status != pgl::gld::GldNullingStatus::AllChannelsFailed) {
                    pgl::gld::GldNullingProfile toSave = result.profile;
                    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
                    toSave.profileId  = static_cast<uint8_t>(
                        pgl::gld::isNullingProfileValid(existing)
                            ? static_cast<uint8_t>(existing.profileId + 1u) : 1u);
                    const bool saved = pgl::gld::saveNullingProfile(toSave);
                    logPrintf("NULLING_NVS_SAVE=%s profileId=%u\n",
                              saved ? "OK" : "FAIL", toSave.profileId);
                    logPrintln(result.status == pgl::gld::GldNullingStatus::Ok
                               ? "NULLING_RUNTIME_RESULT=PASS"
                               : "NULLING_RUNTIME_RESULT=PARTIAL");
                    nullDone = true;

                    connectWifi();
                    mqtt.setBufferSize(640);
                    if (mqttConnect()) publishNullingProfile(toSave);
                } else {
                    logPrintln("NULLING_RUNTIME_RESULT=FAIL");
                }
            }
        }
    }
}

void loop() {
    checkSerial();

    if (currentMode == pgl::gld::GldMode::INFERENCE) {
        const uint32_t now = millis();
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
        // NULLING mode — calibration done in setup, maintain MQTT
        if (!nullDone) { delay(1000); return; }
        maintainWifi();
        maintainMqtt();
        delay(500);
    }
}
