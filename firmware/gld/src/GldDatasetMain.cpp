#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <SPI.h>
#include <WiFi.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldDacMux.h"
#include "GldConfig.h"
#include "GldNullingProfile.h"
#include "GldNullingService.h"
#include "GldPower.h"

namespace {

// Standalone dataset runtime kept as a maintenance mirror. The active
// production GLD env builds GldUnifiedMain.cpp and excludes this file.

// ---- Network config ----
constexpr const char* WIFI_SSID      = GLD_WIFI_SSID;
constexpr const char* WIFI_PASSWORD  = GLD_WIFI_PASSWORD;
constexpr const char* MQTT_HOST      = GLD_MQTT_HOST;
constexpr uint16_t    MQTT_PORT      = GLD_MQTT_PORT;
constexpr const char* MQTT_USER      = GLD_MQTT_USER;
constexpr const char* MQTT_PASS      = GLD_MQTT_PASS;
constexpr const char* MQTT_CLIENT_ID = GLD_MQTT_CLIENT_ID;
constexpr const char* DEVICE_ID_STR  = GLD_DEVICE_ID_STR;
constexpr uint16_t    NODE_ID_INT    = GLD_NODE_ID;

// ---- MQTT topics ----
// Subscribe
constexpr const char* TOPIC_DATASET   = GLD_TOPIC_DATASET;
// Publish
constexpr const char* TOPIC_DATA      = GLD_TOPIC_DATA;
constexpr const char* TOPIC_STATUS    = GLD_TOPIC_STATUS;
constexpr const char* TOPIC_SUMMARY   = GLD_TOPIC_SUMMARY;
constexpr const char* TOPIC_ACK       = GLD_TOPIC_ACK;

constexpr uint32_t DATASET_MIN_SAMPLE_INTERVAL_MS = GLD_DATASET_MIN_SAMPLE_INTERVAL_MS;
constexpr uint8_t  DATASET_QUEUE_CAPACITY = 16;
constexpr size_t   DATASET_PAYLOAD_BYTES = 896;
constexpr uint8_t  DATASET_QUEUE_FLUSH_PER_LOOP = 2;
constexpr uint32_t ADS_RECOVERY_RETRY_MS = 5000;
constexpr uint8_t  ADS_READ_FAIL_RECOVERY_THRESHOLD = 3;

// ---- Timing ----
constexpr uint32_t WIFI_TIMEOUT_MS    = GLD_WIFI_TIMEOUT_MS;
constexpr uint32_t MQTT_RETRY_MS      = GLD_MQTT_RETRY_MS;
constexpr uint32_t STATUS_INTERVAL_MS = GLD_STATUS_INTERVAL_MS;
constexpr uint16_t MQTT_BUFFER_SIZE   = GLD_MQTT_BUFFER_SIZE;
constexpr uint8_t ACTIVE_LOW_OUTPUT_ON = LOW;
constexpr uint8_t ACTIVE_LOW_OUTPUT_OFF = HIGH;

// ---- Hardware ----
SPIClass                   gldSpi;
pgl::gld::GldAds1256Reader ads;
pgl::gld::GldDacMux        dac;
WiFiClient                 wifiClient;
PubSubClient               mqtt(wifiClient);

// ---- Dataset session state ----
enum class DatasetState : uint8_t { Idle, Running };
enum class SampleStep   : uint8_t { None, FanOn, FanSettle, Scan };

DatasetState datasetState      = DatasetState::Idle;
SampleStep   sampleStep        = SampleStep::None;
char         currentLabel[32]{};
uint32_t     datasetSeq        = 0;
uint32_t     sessionStartMs    = 0;
uint32_t     lastScanMs        = 0;
uint32_t     stepStartMs       = 0;
uint32_t     lastStatusMs      = 0;
uint32_t     lastMqttAttemptMs = 0;
uint8_t      nullingProfileId  = 0;
bool         adsReady          = false;
bool         dacReady          = false;

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

// Session params (filled from START_DATASET command)
uint32_t     targetSamples     = 0;     // 0 = unlimited
uint32_t     sampleIntervalMs  = DATASET_MIN_SAMPLE_INTERVAL_MS;
uint32_t     maxDurationMs     = 0;     // 0 = unlimited
bool         useFanIntake      = true;
uint32_t     fanOnMs           = 1000;
uint32_t     postFanSettleMs   = 0;

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

void setRecoveryReason(const char* reason) {
    strncpy(lastRecoveryReason, reason != nullptr ? reason : "unknown", sizeof(lastRecoveryReason) - 1);
    lastRecoveryReason[sizeof(lastRecoveryReason) - 1] = '\0';
    lastRecoveryMs = millis();
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
    const bool ok = mqtt.connected() && mqtt.publish(TOPIC_DATA, payload, false);
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
        logPrintf("ADS_RECOVERY_RESULT=OK count=%lu\n",
                  static_cast<unsigned long>(adsRecoveryCount));
    } else {
        ++adsRecoveryFailCount;
        logPrintf("ADS_RECOVERY_RESULT=FAIL failCount=%lu\n",
                  static_cast<unsigned long>(adsRecoveryFailCount));
    }
}

// ---------------------------------------------------------------------------
// Hardware setup
// ---------------------------------------------------------------------------

void setupPins() {
    pinMode(pgl::gld::board::PIN_LORA_CS,    OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_CS,    HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_RXEN,  LOW);
    pinMode(pgl::gld::board::PIN_LORA_TXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_TXEN,  LOW);
    pinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT); digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, ACTIVE_LOW_OUTPUT_OFF);
    pinMode(pgl::gld::board::PIN_BUZZER,     OUTPUT); digitalWrite(pgl::gld::board::PIN_BUZZER,     ACTIVE_LOW_OUTPUT_OFF);
    pinMode(pgl::gld::board::PIN_DC_FAN,     OUTPUT); digitalWrite(pgl::gld::board::PIN_DC_FAN,     LOW);
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT); digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
}

// ---------------------------------------------------------------------------
// Nulling
// ---------------------------------------------------------------------------

void applyNullingProfile(const pgl::gld::GldNullingProfile& profile) {
    if (!dacReady || !pgl::gld::isNullingProfileValid(profile)) return;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        dac.writeDac(ch, profile.dacCode[ch]);
    }
    logPrintf("DAC_APPLY profileId=%u\n", profile.profileId);
}

bool initNulling(bool runIfMissing) {
    pgl::gld::GldNullingProfile profile{};
    if (pgl::gld::loadNullingProfile(profile)) {
        logPrintf("NULLING_NVS_LOAD=found profileId=%u\n", profile.profileId);
        nullingProfileId = profile.profileId;
        applyNullingProfile(profile);
        return true;
    }
    if (!runIfMissing) {
        nullingProfileId = 0;
        logPrintln("NULLING_NVS_LOAD=empty auto_nulling=skip");
        return false;
    }
    logPrintln("NULLING_NVS_LOAD=empty running_nulling_now");
    const pgl::gld::GldNullingServiceResult result =
        pgl::gld::runNullingService(ads, dac);
    logPrintf("NULLING_RUN status=%s successCount=%u\n",
              pgl::gld::gldNullingStatusName(result.status),
              result.successCount);
    if (result.status == pgl::gld::GldNullingStatus::AllChannelsFailed) {
        return false;
    }
    pgl::gld::GldNullingProfile toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = 1;
    pgl::gld::saveNullingProfile(toSave);
    nullingProfileId = 1;
    applyNullingProfile(toSave);
    return true;
}

// ---------------------------------------------------------------------------
// WiFi
// ---------------------------------------------------------------------------

bool connectWifi() {
    ++wifiReconnectCount;
    setRecoveryReason("wifi_connect");
    logPrintf("WIFI_CONNECT ssid=%s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    const uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) {
        delay(200);
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

// ---------------------------------------------------------------------------
// MQTT publish helpers
// ---------------------------------------------------------------------------

void publishStatus(const char* state, const char* detail) {
    StaticJsonDocument<384> doc;
    doc["device_id"] = DEVICE_ID_STR;
    doc["stage"]     = "DATASET";
    doc["state"]     = state;
    doc["detail"]    = detail;
    doc["queue_pending"] = datasetQueueCount;
    doc["queue_dropped"] = datasetQueueDropped;
    doc["publish_fail_count"] = datasetPublishFailCount;
    doc["mqtt_reconnect_count"] = mqttReconnectCount;
    doc["mqtt_connect_fail_count"] = mqttConnectFailCount;
    doc["ads_recovery_count"] = adsRecoveryCount;
    doc["ads_recovery_fail_count"] = adsRecoveryFailCount;
    doc["last_recovery_reason"] = lastRecoveryReason;
    char buf[384];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(TOPIC_STATUS, buf, false);
}

void publishCmdAck(const char* cmd, const char* result) {
    StaticJsonDocument<128> doc;
    doc["device_id"]    = DEVICE_ID_STR;
    doc["cmd"]          = cmd;
    doc["result"]       = result;
    doc["timestamp_ms"] = static_cast<uint32_t>(millis());
    char buf[128];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(TOPIC_ACK, buf, false);
}

void publishSummary() {
    StaticJsonDocument<384> doc;
    doc["device_id"]          = DEVICE_ID_STR;
    doc["stage"]              = "DATASET";
    doc["label"]              = currentLabel;
    doc["total_samples"]      = datasetSeq;
    doc["duration_ms"]        = static_cast<uint32_t>(millis() - sessionStartMs);
    doc["nulling_profile_id"] = nullingProfileId;
    doc["queue_pending"] = datasetQueueCount;
    doc["queue_dropped"] = datasetQueueDropped;
    doc["publish_fail_count"] = datasetPublishFailCount;
    doc["retry_count"] = datasetQueueRetryCount;
    doc["retry_fail_count"] = datasetQueueRetryFailCount;
    doc["ads_recovery_count"] = adsRecoveryCount;
    doc["ads_recovery_fail_count"] = adsRecoveryFailCount;
    char buf[384];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(TOPIC_SUMMARY, buf, false);
}

bool mqttConnect();  // forward declaration

// ---------------------------------------------------------------------------
// MQTT command handler
// ---------------------------------------------------------------------------

void handleCmd(const char* payload, unsigned int length) {
    StaticJsonDocument<512> doc;
    const DeserializationError err = deserializeJson(doc, payload, length);
    if (err) {
        logPrintf("DATASET_CMD_PARSE_ERROR %s\n", err.c_str());
        publishCmdAck("UNKNOWN", "parse_error");
        return;
    }
    const char* cmd = doc["cmd"] | "";
    logPrintf("DATASET_CMD cmd=%s\n", cmd);

    if (strcmp(cmd, "START_DATASET") == 0) {
        if (!pgl::gld::readGldPower().externalPower) {
            logPrintln("DATASET_START_REJECT battery_mode_not_allowed");
            publishCmdAck("START_DATASET", "reject_battery_mode");
            return;
        }
        if (nullingProfileId == 0) {
            logPrintln("DATASET_START_REJECT no_nulling_profile");
            publishCmdAck("START_DATASET", "reject_no_profile");
            return;
        }
        const char* label = doc["label"] | "unknown";
        strncpy(currentLabel, label, sizeof(currentLabel) - 1);
        currentLabel[sizeof(currentLabel) - 1] = '\0';

        targetSamples    = doc["target_samples"]    | 0u;
        const uint32_t requestedSampleIntervalMs =
            doc["sample_interval_ms"] | DATASET_MIN_SAMPLE_INTERVAL_MS;
        sampleIntervalMs = requestedSampleIntervalMs < DATASET_MIN_SAMPLE_INTERVAL_MS
                               ? DATASET_MIN_SAMPLE_INTERVAL_MS
                               : requestedSampleIntervalMs;
        maxDurationMs    = doc["max_duration_ms"]   | 0u;
        useFanIntake     = doc["use_fan_intake"]    | true;
        fanOnMs          = doc["fan_on_ms"]         | 1000u;
        postFanSettleMs  = doc["post_fan_settle_ms"] | 0u;

        datasetSeq     = 0;
        sessionStartMs = millis();
        lastScanMs     = sessionStartMs;
        sampleStep     = SampleStep::None;
        datasetState   = DatasetState::Running;
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_ON);
        publishCmdAck("START_DATASET", "ok");
        publishStatus("running", currentLabel);
        logPrintf("DATASET_START label=%s target=%lu interval=%lu fan=%u\n",
                  currentLabel,
                  static_cast<unsigned long>(targetSamples),
                  static_cast<unsigned long>(sampleIntervalMs),
                  useFanIntake ? 1 : 0);

    } else if (strcmp(cmd, "STOP_DATASET") == 0) {
        if (datasetState == DatasetState::Running) {
            // Ensure fan is off
            digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
        }
        datasetState = DatasetState::Idle;
        sampleStep   = SampleStep::None;
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
        publishCmdAck("STOP_DATASET", "ok");
        publishSummary();
        publishStatus("idle", "stopped");
        logPrintf("DATASET_STOP totalSeq=%lu\n",
                  static_cast<unsigned long>(datasetSeq));

    } else {
        logPrintf("DATASET_CMD_UNKNOWN cmd=%s\n", cmd);
        publishCmdAck(cmd, "unknown_cmd");
    }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, TOPIC_DATASET) == 0) {
        handleCmd(reinterpret_cast<const char*>(payload), length);
    }
}

bool mqttConnect() {
    if (mqtt.connected()) return true;
    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_MS) return false;
    lastMqttAttemptMs = now;
    ++mqttReconnectCount;
    setRecoveryReason("mqtt_connect");

    logPrintf("MQTT_CONNECT host=%s port=%u\n", MQTT_HOST, MQTT_PORT);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(mqttCallback);
    const bool ok = mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
    lastMqttState = mqtt.state();
    if (!ok) {
        ++mqttConnectFailCount;
        setRecoveryReason("mqtt_connect_failed");
    }
    logPrintf("MQTT_CONNECT_RESULT=%s state=%d attempt=%lu failCount=%lu ip=%s rssi=%ld\n",
              ok ? "OK" : "FAIL",
              lastMqttState,
              static_cast<unsigned long>(mqttReconnectCount),
              static_cast<unsigned long>(mqttConnectFailCount),
              WiFi.localIP().toString().c_str(),
              static_cast<long>(WiFi.RSSI()));
    if (ok) {
        mqtt.subscribe(TOPIC_DATASET);
        logPrintf("MQTT_SUBSCRIBE topic=%s\n", TOPIC_DATASET);
        publishStatus("idle", "ready");
    } else {
        wifiClient.stop();
    }
    return ok;
}

// ---------------------------------------------------------------------------
// Dataset record publish
// ---------------------------------------------------------------------------

void publishDataRecord() {
    // JSON pool: root(10 keys) + 3 arrays(8 each) + string pool for label
    StaticJsonDocument<1024> doc;
    doc["device_id"]          = DEVICE_ID_STR;
    doc["node_id"]            = NODE_ID_INT;
    doc["mode"]               = "DATASET";
    doc["seq"]                = datasetSeq;
    doc["timestamp_ms"]       = static_cast<uint32_t>(millis());
    doc["label"]              = currentLabel;
    doc["nulling_profile_id"] = nullingProfileId;

    JsonArray svArr   = doc.createNestedArray("sensor_voltage");
    JsonArray gainArr = doc.createNestedArray("sensor_gain");
    JsonArray statusArr = doc.createNestedArray("sensor_status");
    JsonArray foArr   = doc.createNestedArray("feature_order");

    bool anyFail = false;
    uint8_t okChannels = 0;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        const bool ok = r.status == pgl::gld::GldAds1256Status::Ok;
        svArr.add(r.voltage);
        gainArr.add(r.gain);
        statusArr.add(static_cast<uint8_t>(r.status));
        foArr.add(pgl::gld::board::SENSOR_NAMES[ch]);
        if (ok) ++okChannels;
        if (!ok) anyFail = true;
    }
    noteAdsReadHealth(okChannels, "dataset");

    char payload[DATASET_PAYLOAD_BYTES];
    const size_t len = serializeJson(doc, payload, sizeof(payload));
    const size_t termIndex = len < (sizeof(payload) - 1U) ? len : (sizeof(payload) - 1U);
    payload[termIndex] = '\0';

    const bool pubOk = publishDatasetPayload(payload, datasetSeq, false);
    if (!pubOk) {
        enqueueDatasetPayload(payload, len, datasetSeq);
    }
    logPrintf("DATASET_RECORD seq=%lu label=%s ok=%u queued=%u pending=%u anyFail=%u len=%u\n",
              static_cast<unsigned long>(datasetSeq),
              currentLabel,
              pubOk ? 1 : 0,
              pubOk ? 0 : 1,
              static_cast<unsigned>(datasetQueueCount),
              anyFail ? 1 : 0,
              static_cast<unsigned>(len));
    ++datasetSeq;
}

// ---------------------------------------------------------------------------
// Check auto-stop conditions
// ---------------------------------------------------------------------------

bool shouldAutoStop() {
    if (targetSamples > 0 && datasetSeq >= targetSamples) {
        logPrintf("DATASET_AUTOSTOP target_reached total=%lu\n",
                  static_cast<unsigned long>(datasetSeq));
        return true;
    }
    if (maxDurationMs > 0 && millis() - sessionStartMs >= maxDurationMs) {
        logPrintf("DATASET_AUTOSTOP max_duration total=%lu\n",
                  static_cast<unsigned long>(datasetSeq));
        return true;
    }
    return false;
}

void stopDataset() {
    digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
    datasetState = DatasetState::Idle;
    sampleStep   = SampleStep::None;
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
    publishSummary();
    publishStatus("idle", "completed");
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

    logPrintln("");
    logPrintln("Pertamina GLD dataset runtime");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("DATASET_CONFIG deviceId=%s nodeId=0x%04X broker=%s:%u\n",
              DEVICE_ID_STR, NODE_ID_INT, MQTT_HOST, MQTT_PORT);

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("GLD_POWER mode=%s externalPower=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0);

    adsReady = ads.begin(gldSpi);
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");

    dacReady = dac.begin(Wire);
    logPrintf("DAC_MUX_BEGIN_RESULT=%s\n", dacReady ? "PASS" : "FAIL");

    if (adsReady && dacReady) {
        initNulling(false);
    }

    logPrintf("DATASET_READY adsReady=%u dacReady=%u nullingProfileId=%u\n",
              adsReady ? 1 : 0, dacReady ? 1 : 0, nullingProfileId);

    connectWifi();

    mqtt.setBufferSize(MQTT_BUFFER_SIZE);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(mqttCallback);
    mqttConnect();

    lastStatusMs = millis();
}

void loop() {
    // Maintain WiFi
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
    }

    // Maintain MQTT
    if (!mqtt.connected()) {
        mqttConnect();
    } else {
        mqtt.loop();
    }
    flushDatasetQueue();
    maintainAdsRecovery("dataset_ads_not_ready");

    const uint32_t now = millis();

    // Periodic status heartbeat
    if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
        lastStatusMs = now;
        if (datasetState == DatasetState::Running) {
            publishStatus("running", currentLabel);
        }
    }

    // Dataset sample state machine
    if (datasetState == DatasetState::Running && adsReady) {
        switch (sampleStep) {
            case SampleStep::None:
                if (now - lastScanMs >= sampleIntervalMs) {
                    if (useFanIntake && fanOnMs > 0) {
                        digitalWrite(pgl::gld::board::PIN_DC_FAN, HIGH);
                        stepStartMs = now;
                        sampleStep  = SampleStep::FanOn;
                    } else {
                        publishDataRecord();
                        lastScanMs = now;
                        if (shouldAutoStop()) stopDataset();
                    }
                }
                break;

            case SampleStep::FanOn:
                if (now - stepStartMs >= fanOnMs) {
                    digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
                    stepStartMs = now;
                    sampleStep  = (postFanSettleMs > 0) ? SampleStep::FanSettle
                                                        : SampleStep::Scan;
                }
                break;

            case SampleStep::FanSettle:
                if (now - stepStartMs >= postFanSettleMs) {
                    sampleStep = SampleStep::Scan;
                }
                break;

            case SampleStep::Scan:
                publishDataRecord();
                lastScanMs = now;
                sampleStep = SampleStep::None;
                if (shouldAutoStop()) stopDataset();
                break;
        }
    }

    delay(10);
}
