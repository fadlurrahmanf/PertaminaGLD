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

// ---- Timing ----
constexpr uint32_t WIFI_TIMEOUT_MS    = GLD_WIFI_TIMEOUT_MS;
constexpr uint32_t MQTT_RETRY_MS      = GLD_MQTT_RETRY_MS;
constexpr uint32_t STATUS_INTERVAL_MS = GLD_STATUS_INTERVAL_MS;
constexpr uint16_t MQTT_BUFFER_SIZE   = GLD_MQTT_BUFFER_SIZE;

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

// Session params (filled from START_DATASET command)
uint32_t     targetSamples     = 0;     // 0 = unlimited
uint32_t     sampleIntervalMs  = 1000;
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

// ---------------------------------------------------------------------------
// Hardware setup
// ---------------------------------------------------------------------------

void setupPins() {
    pinMode(pgl::gld::board::PIN_LORA_CS,    OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_CS,    HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_RXEN,  LOW);
    pinMode(pgl::gld::board::PIN_LORA_TXEN,  OUTPUT); digitalWrite(pgl::gld::board::PIN_LORA_TXEN,  LOW);
    pinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT); digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, LOW);
    pinMode(pgl::gld::board::PIN_BUZZER,     OUTPUT); digitalWrite(pgl::gld::board::PIN_BUZZER,     LOW);
    pinMode(pgl::gld::board::PIN_DC_FAN,     OUTPUT); digitalWrite(pgl::gld::board::PIN_DC_FAN,     LOW);
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT); digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
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

bool initNulling() {
    pgl::gld::GldNullingProfile profile{};
    if (pgl::gld::loadNullingProfile(profile)) {
        logPrintf("NULLING_NVS_LOAD=found profileId=%u\n", profile.profileId);
        nullingProfileId = profile.profileId;
        applyNullingProfile(profile);
        return true;
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
    logPrintf("WIFI_CONNECT ssid=%s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    const uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) {
        delay(200);
    }
    const bool ok = WiFi.status() == WL_CONNECTED;
    logPrintf(ok ? "WIFI_CONNECTED ip=%s\n" : "WIFI_CONNECT_FAILED\n",
              ok ? WiFi.localIP().toString().c_str() : "");
    return ok;
}

// ---------------------------------------------------------------------------
// MQTT publish helpers
// ---------------------------------------------------------------------------

void publishStatus(const char* state, const char* detail) {
    StaticJsonDocument<128> doc;
    doc["device_id"] = DEVICE_ID_STR;
    doc["stage"]     = "DATASET";
    doc["state"]     = state;
    doc["detail"]    = detail;
    char buf[128];
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
    StaticJsonDocument<192> doc;
    doc["device_id"]          = DEVICE_ID_STR;
    doc["stage"]              = "DATASET";
    doc["label"]              = currentLabel;
    doc["total_samples"]      = datasetSeq;
    doc["duration_ms"]        = static_cast<uint32_t>(millis() - sessionStartMs);
    doc["nulling_profile_id"] = nullingProfileId;
    char buf[192];
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
        if (nullingProfileId == 0) {
            logPrintln("DATASET_START_REJECT no_nulling_profile");
            publishCmdAck("START_DATASET", "reject_no_profile");
            return;
        }
        const char* label = doc["label"] | "unknown";
        strncpy(currentLabel, label, sizeof(currentLabel) - 1);
        currentLabel[sizeof(currentLabel) - 1] = '\0';

        targetSamples    = doc["target_samples"]    | 0u;
        sampleIntervalMs = doc["sample_interval_ms"] | 1000u;
        maxDurationMs    = doc["max_duration_ms"]   | 0u;
        useFanIntake     = doc["use_fan_intake"]    | true;
        fanOnMs          = doc["fan_on_ms"]         | 1000u;
        postFanSettleMs  = doc["post_fan_settle_ms"] | 0u;

        datasetSeq     = 0;
        sessionStartMs = millis();
        lastScanMs     = sessionStartMs;
        sampleStep     = SampleStep::None;
        datasetState   = DatasetState::Running;
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, HIGH);
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
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
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

    logPrintf("MQTT_CONNECT host=%s port=%u\n", MQTT_HOST, MQTT_PORT);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(mqttCallback);
    const bool ok = mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
    logPrintf("MQTT_CONNECT_RESULT=%s state=%d ip=%s rssi=%ld\n",
              ok ? "OK" : "FAIL",
              mqtt.state(),
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
    JsonArray foArr   = doc.createNestedArray("feature_order");

    bool anyFail = false;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        const bool ok = r.status == pgl::gld::GldAds1256Status::Ok;
        svArr.add(r.voltage);
        gainArr.add(r.gain);
        foArr.add(pgl::gld::board::SENSOR_NAMES[ch]);
        if (!ok) anyFail = true;
    }

    char payload[896];
    const size_t len = serializeJson(doc, payload, sizeof(payload));

    const bool pubOk = mqtt.publish(TOPIC_DATA, payload, false);
    logPrintf("DATASET_RECORD seq=%lu label=%s ok=%u anyFail=%u len=%u\n",
              static_cast<unsigned long>(datasetSeq),
              currentLabel,
              pubOk ? 1 : 0,
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
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
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
        initNulling();
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
