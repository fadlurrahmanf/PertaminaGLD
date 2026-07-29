// Pertamina GLD CNN real-time runtime — env `gld_cnn`.
//
// Isolated implementation of the CNN-on-ESP32-S3 integration guide
// (TAHAP 1-20). Does not touch the production `gld` unified runtime or the
// `gld_inference_esp32s3` serial-only demo; this is the guide's "backup
// project" (TAHAP 2) as a dedicated PlatformIO environment instead of a
// duplicated directory tree, sharing this repo's existing single-src-dir
// convention (see firmware/platformio.ini [env:gld_cnn]).
//
// Model note: cnn_gas_datasheet_model_data.h is a dual-input (8 raw ADC +
// 7 evidence features), 3-class (CO2/Clean_Air/LPG) graph, not the
// single-input/4-class shape the generic guide assumes — see
// cnn_inference.h. Sensor read order (TAHAP 9) and inference flow
// (TAHAP 10-14) are otherwise implemented as described.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <SPI.h>
#include <WiFi.h>

#include <cstdarg>
#include <cstdio>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldConfig.h"
#include "GldMovingAverage.h"
#include "GldPower.h"
#include "ProtocolConstants.h"
#include "cnn_inference.h"

namespace {

// ---------------------------------------------------------------------------
// TAHAP 17: alarm confidence threshold (guide example: 85%).
// ---------------------------------------------------------------------------
constexpr uint8_t CNN_ALARM_CONFIDENCE_THRESHOLD_PERCENT = 85;

// TAHAP 19/20: scan cadence. Guide loop delay is 100-200 ms; the ADS1256
// moving-average window needs to fill first (see MIN_PRIMED_COUNT below), so
// this is the per-channel sample interval, not the inference interval.
constexpr uint32_t SCAN_INTERVAL_MS = 150;
constexpr uint32_t MQTT_RETRY_MS = GLD_MQTT_RETRY_MS;
constexpr uint8_t MIN_PRIMED_COUNT = pgl::gld::GLD_SENSOR_MOVING_AVERAGE_WINDOW;

constexpr const char* CNN_TOPIC_RESULT =
    PGL_SERVER_DATASET_TOPIC_ROOT "/" GLD_DEVICE_ID_STR "/cnn/result";

constexpr uint8_t ACTIVE_LOW_OUTPUT_ON = LOW;
constexpr uint8_t ACTIVE_LOW_OUTPUT_OFF = HIGH;

// Hardware
SPIClass gldSpi;
pgl::gld::GldAds1256Reader ads;
pgl::gld::GldMovingAverage movingAvg;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// Runtime state
bool adsReady = false;
bool wifiReady = false;
bool cnnReady = false;
uint32_t scanSeq = 0;
uint32_t lastScanMs = 0;
uint32_t lastMqttAttemptMs = 0;
bool lastAlarm = false;

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
}

void logPrintln(const char* text) { Serial.println(text); }

// ---------------------------------------------------------------------------
// TAHAP 17: alarm outputs (LED + buzzer) and MQTT alarm flag.
// ---------------------------------------------------------------------------

void driveAlarmOutputs(bool alarm) {
    digitalWrite(pgl::gld::board::PIN_ALARM_LAMP,
                 alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    digitalWrite(pgl::gld::board::PIN_BUZZER,
                 alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
    digitalWrite(pgl::gld::board::PIN_STATUS_LED,
                 alarm ? ACTIVE_LOW_OUTPUT_ON : ACTIVE_LOW_OUTPUT_OFF);
}

void updateAlarmOutputs(bool alarm) {
    if (alarm == lastAlarm) return;
    lastAlarm = alarm;
    driveAlarmOutputs(alarm);
    logPrintf("GLD_CNN_ALARM_OUTPUT alarm=%u\n", alarm ? 1 : 0);
}

// ---------------------------------------------------------------------------
// TAHAP 16: MQTT dashboard hookup (gas name, confidence, alarm).
// ---------------------------------------------------------------------------

bool ensureMqttConnected() {
    if (mqtt.connected()) return true;
    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_MS) return false;
    lastMqttAttemptMs = now;

    mqtt.setServer(GLD_MQTT_HOST, GLD_MQTT_PORT);
    const bool ok = mqtt.connect(GLD_MQTT_CLIENT_ID, GLD_MQTT_USER, GLD_MQTT_PASS);
    logPrintf("GLD_CNN_MQTT_CONNECT_RESULT=%s state=%d\n", ok ? "PASS" : "FAIL",
              mqtt.state());
    return ok;
}

void publishCnnResult(const pgl::gld::cnn::CnnPrediction& prediction, bool alarm) {
    if (!ensureMqttConnected()) return;
    mqtt.loop();

    StaticJsonDocument<256> doc;
    doc["device_id"] = GLD_DEVICE_ID_STR;
    doc["seq"] = scanSeq;
    doc["gas"] = prediction.ok ? prediction.className : "unknown";
    doc["confidence"] = prediction.confidencePercent;
    doc["alarm"] = alarm;
    doc["ml_ready"] = cnnReady;

    char payload[256];
    const size_t len = serializeJson(doc, payload, sizeof(payload));
    mqtt.publish(CNN_TOPIC_RESULT, reinterpret_cast<const uint8_t*>(payload), len, false);
}

// ---------------------------------------------------------------------------
// TAHAP 9-15: read sensors, run inference, print result, TAHAP 16/17: MQTT +
// alarm.
// ---------------------------------------------------------------------------

void runScanAndInfer() {
    // TAHAP 9: read all 8 MQ sensors. Order MUST match training order
    // (BoardPins.h SENSOR_NAMES = MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2 —
    // already matches CNN_GAS_ADC_NAMES, no remap needed).
    float mavVoltage[8] = {};
    uint8_t primedChannels = 0;
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        if (r.status == pgl::gld::GldAds1256Status::Ok) {
            mavVoltage[ch] = movingAvg.add(ch, r.voltage);
        } else {
            mavVoltage[ch] = movingAvg.value(ch);
        }
        if (movingAvg.count(ch) >= MIN_PRIMED_COUNT) ++primedChannels;
    }

    const bool primed = primedChannels >= pgl::gld::board::SENSOR_COUNT;
    if (!primed) {
        logPrintf("GLD_CNN_WARMUP seq=%lu primed=%u/%u\n",
                  static_cast<unsigned long>(scanSeq), primedChannels,
                  pgl::gld::board::SENSOR_COUNT);
        ++scanSeq;
        return;
    }

    // TAHAP 10/11/12: normalize, quantize (INT8), Invoke() — all inside
    // CNN_Predict()/NeuralNetwork::predict().
    const pgl::gld::cnn::CnnPrediction prediction = pgl::gld::cnn::CNN_Predict(mavVoltage);

    if (!prediction.ok) {
        logPrintln("GLD_CNN_PREDICT_ERROR");
        ++scanSeq;
        return;
    }

    // TAHAP 13/14: output tensor + argmax already resolved by CNN_Predict().
    // TAHAP 15: print to Serial Monitor.
    logPrintf("Gas         : %s\n", prediction.className);
    logPrintf("Confidence  : %u %%\n", prediction.confidencePercent);

    // TAHAP 17: alarm if a non-clean-air class exceeds the confidence
    // threshold.
    const bool alarm = prediction.gasClass != pgl::protocol::GLD_GAS_CLEAR &&
                        prediction.confidencePercent >= CNN_ALARM_CONFIDENCE_THRESHOLD_PERCENT;
    updateAlarmOutputs(alarm);

    // TAHAP 16: send to dashboard over MQTT.
    publishCnnResult(prediction, alarm);

    logPrintf(
        "GLD_CNN_SCAN seq=%lu ts=%lu classIndex=%d gasClass=%u confidence=%u alarm=%u\n",
        static_cast<unsigned long>(scanSeq), static_cast<unsigned long>(millis()),
        prediction.classIndex, prediction.gasClass, prediction.confidencePercent,
        alarm ? 1 : 0);

    ++scanSeq;
}

}  // namespace

// ---------------------------------------------------------------------------
// Arduino entry points — TAHAP 8/20 setup order: Serial -> Sensor -> WiFi ->
// MQTT -> CNN_Init().
// ---------------------------------------------------------------------------

void setup() {
    // Serial
    Serial.begin(115200);
    delay(1000);
    logPrintln("");
    logPrintln("Pertamina GLD CNN real-time runtime (env: gld_cnn)");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);

    // Sensor
    pinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, ACTIVE_LOW_OUTPUT_OFF);
    pinMode(pgl::gld::board::PIN_BUZZER, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_BUZZER, ACTIVE_LOW_OUTPUT_OFF);
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
    pgl::gld::beginGldPowerPins();
    movingAvg.reset();

    adsReady = ads.begin(gldSpi);
    logPrintf("GLD_CNN_ADS_BEGIN=%s\n", adsReady ? "PASS" : "FAIL");

    // WiFi
    WiFi.mode(WIFI_STA);
    WiFi.begin(PGL_SERVER_DATASET_WIFI_SSID, PGL_SERVER_DATASET_WIFI_PASSWORD);
    const uint32_t wifiStart = millis();
    constexpr uint32_t WIFI_TIMEOUT_MS = 15000;
    while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < WIFI_TIMEOUT_MS) {
        delay(250);
    }
    wifiReady = WiFi.status() == WL_CONNECTED;
    logPrintf("GLD_CNN_WIFI_CONNECT=%s\n", wifiReady ? "PASS" : "FAIL");

    // MQTT
    mqtt.setServer(GLD_MQTT_HOST, GLD_MQTT_PORT);
    if (wifiReady) {
        ensureMqttConnected();
    }

    // CNN_Init() — TAHAP 6/7/8.
    cnnReady = pgl::gld::cnn::CNN_Init();
    logPrintf("GLD_CNN_INIT=%s\n", cnnReady ? "PASS" : "FAIL");

    logPrintf("GLD_CNN_READY adsReady=%u wifiReady=%u cnnReady=%u alarmThreshold=%u%%\n",
              adsReady ? 1 : 0, wifiReady ? 1 : 0, cnnReady ? 1 : 0,
              CNN_ALARM_CONFIDENCE_THRESHOLD_PERCENT);

    lastScanMs = millis();
}

void loop() {
    const uint32_t now = millis();

    if (wifiReady && WiFi.status() == WL_CONNECTED) {
        mqtt.loop();
    }

    if (adsReady && cnnReady && now - lastScanMs >= SCAN_INTERVAL_MS) {
        lastScanMs = now;
        runScanAndInfer();
    }
}
