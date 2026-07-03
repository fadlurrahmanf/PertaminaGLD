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
#include "GldDacMux.h"
#include "GldConfig.h"
#include "GldModeManager.h"
#include "GldNullingProfile.h"
#include "GldNullingService.h"
#include "GldPower.h"

namespace {

constexpr const char* WIFI_SSID      = GLD_WIFI_SSID;
constexpr const char* WIFI_PASSWORD  = GLD_WIFI_PASSWORD;
constexpr const char* MQTT_HOST      = GLD_MQTT_HOST;
constexpr uint16_t    MQTT_PORT      = GLD_MQTT_PORT;
constexpr const char* MQTT_USER      = GLD_MQTT_USER;
constexpr const char* MQTT_PASS      = GLD_MQTT_PASS;
constexpr const char* MQTT_CLIENT_ID = GLD_MQTT_CLIENT_ID;

// Topic: gas-leak-detector/<nodeId>/nulling/result
constexpr const char* MQTT_TOPIC_NULLING = GLD_TOPIC_NULLING;
constexpr const char* MQTT_TOPIC_STATUS  = GLD_TOPIC_NULL_STATUS;

constexpr uint32_t WIFI_TIMEOUT_MS  = GLD_WIFI_TIMEOUT_MS;
constexpr uint32_t MQTT_RETRY_MS    = GLD_MQTT_RETRY_MS;
constexpr uint8_t ACTIVE_LOW_OUTPUT_OFF = HIGH;

SPIClass              gldSpi;
pgl::gld::GldAds1256Reader ads;
pgl::gld::GldDacMux   dac;
WiFiClient            wifiClient;
PubSubClient          mqtt(wifiClient);

bool adsReady  = false;
bool dacReady  = false;
bool nullDone  = false;
uint32_t lastMqttAttemptMs = 0;

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
    pinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT); digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, ACTIVE_LOW_OUTPUT_OFF);
    pinMode(pgl::gld::board::PIN_BUZZER,     OUTPUT); digitalWrite(pgl::gld::board::PIN_BUZZER,     ACTIVE_LOW_OUTPUT_OFF);
    pinMode(pgl::gld::board::PIN_DC_FAN,     OUTPUT); digitalWrite(pgl::gld::board::PIN_DC_FAN,     LOW);
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT); digitalWrite(pgl::gld::board::PIN_STATUS_LED, ACTIVE_LOW_OUTPUT_OFF);
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
    if (ok) {
        logPrintf("WIFI_CONNECTED ip=%s\n", WiFi.localIP().toString().c_str());
    } else {
        logPrintln("WIFI_CONNECT_FAILED");
    }
    return ok;
}

// ---------------------------------------------------------------------------
// MQTT publish helpers
// ---------------------------------------------------------------------------

bool mqttConnect() {
    if (mqtt.connected()) return true;
    const uint32_t now = millis();
    if (now - lastMqttAttemptMs < MQTT_RETRY_MS) return false;
    lastMqttAttemptMs = now;

    logPrintf("MQTT_CONNECT host=%s port=%u\n", MQTT_HOST, MQTT_PORT);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    const bool ok = mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
    logPrintf("MQTT_CONNECT_RESULT=%s\n", ok ? "OK" : "FAIL");
    return ok;
}

void publishNullingProfile(const pgl::gld::GldNullingProfile& profile) {
    StaticJsonDocument<640> doc;
    doc["profileId"]  = profile.profileId;
    doc["valid"]      = pgl::gld::isNullingProfileValid(profile);

    JsonArray dacArr  = doc.createNestedArray("dacCode");
    JsonArray baseArr = doc.createNestedArray("baselineV");
    JsonArray afterArr= doc.createNestedArray("afterV");
    JsonArray okArr   = doc.createNestedArray("channelOk");

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        dacArr.add(profile.dacCode[ch]);
        baseArr.add(profile.baselineV[ch]);
        afterArr.add(profile.afterV[ch]);
        okArr.add(profile.channelOk[ch]);
    }

    char payload[640];
    serializeJson(doc, payload, sizeof(payload));
    const bool ok = mqtt.publish(MQTT_TOPIC_NULLING, payload, true);  // retain=true
    logPrintf("MQTT_PUBLISH topic=%s ok=%u len=%u\n",
              MQTT_TOPIC_NULLING, ok ? 1 : 0, static_cast<unsigned>(strlen(payload)));
}

void publishStatus(const char* status, const char* detail) {
    StaticJsonDocument<128> doc;
    doc["status"] = status;
    doc["detail"] = detail;
    char payload[128];
    serializeJson(doc, payload, sizeof(payload));
    mqtt.publish(MQTT_TOPIC_STATUS, payload, true);
    logPrintf("MQTT_STATUS status=%s detail=%s\n", status, detail);
}

// ---------------------------------------------------------------------------
// Log loaded/saved profile
// ---------------------------------------------------------------------------

void logProfile(const char* tag, const pgl::gld::GldNullingProfile& p) {
    uint8_t successCount = 0;
    for (uint8_t i = 0; i < pgl::gld::board::SENSOR_COUNT; ++i)
        successCount += p.channelOk[i];
    logPrintf("NULLING_PROFILE tag=%s profileId=%u valid=%u successCount=%u\n",
              tag, p.profileId,
              pgl::gld::isNullingProfileValid(p) ? 1 : 0,
              successCount);
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        logPrintf("  ch%u %-5s dacCode=%-4u baselineV=%.6f afterV=%.6f ok=%u\n",
                  ch,
                  pgl::gld::board::SENSOR_NAMES[ch],
                  p.dacCode[ch],
                  p.baselineV[ch],
                  p.afterV[ch],
                  p.channelOk[ch]);
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

    logPrintln("");
    logPrintln("Pertamina GLD nulling runtime");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("GLD_POWER mode=%s externalPower=%u batteryMv=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0,
              power.batteryMv);

    if (!power.externalPower) {
        logPrintln("NULLING_BLOCKED reason=battery_mode_not_allowed");
        return;
    }
    if (pgl::gld::readGldAlarmLatched()) {
        logPrintln("NULLING_BLOCKED reason=alarm_latched");
        return;
    }

    // ----- Load existing profile from NVS -----
    pgl::gld::GldNullingProfile existing{};
    if (pgl::gld::loadNullingProfile(existing)) {
        logPrintln("NULLING_NVS_LOAD=found");
        logProfile("nvs-prev", existing);
    } else {
        logPrintln("NULLING_NVS_LOAD=empty");
    }

    // ----- Init hardware -----
    adsReady = ads.begin(gldSpi);
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");
    dacReady = dac.begin(Wire);
    logPrintf("DAC_MUX_BEGIN_RESULT=%s\n", dacReady ? "PASS" : "FAIL");

    if (!adsReady || !dacReady) {
        logPrintf("NULLING_BLOCKED adsReady=%u dacReady=%u\n",
                  adsReady ? 1 : 0, dacReady ? 1 : 0);
        return;
    }

    // ----- Run nulling -----
    logPrintln("NULLING_RUN=start");
    const pgl::gld::GldNullingServiceResult result =
        pgl::gld::runNullingService(ads, dac);

    logPrintf("NULLING_RUN_DONE status=%s successCount=%u\n",
              pgl::gld::gldNullingStatusName(result.status),
              result.successCount);

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        logPrintf("NULLING_RESULT ch=%u sensor=%-5s dacCode=%u baselineV=%.6f afterV=%.6f ok=%u\n",
                  ch,
                  pgl::gld::board::SENSOR_NAMES[ch],
                  result.profile.dacCode[ch],
                  result.profile.baselineV[ch],
                  result.profile.afterV[ch],
                  result.profile.channelOk[ch]);
    }

    if (result.status == pgl::gld::GldNullingStatus::AllChannelsFailed) {
        logPrintln("NULLING_RUNTIME_RESULT=FAIL");
        return;
    }

    // ----- Build profile to save -----
    pgl::gld::GldNullingProfile toSave = result.profile;
    toSave.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    toSave.profileId  = static_cast<uint8_t>(
        pgl::gld::isNullingProfileValid(existing)
            ? static_cast<uint8_t>(existing.profileId + 1u)
            : 1u);

    // ----- Save to NVS -----
    const bool saved = pgl::gld::saveNullingProfile(toSave);
    logPrintf("NULLING_NVS_SAVE=%s profileId=%u\n",
              saved ? "OK" : "FAIL", toSave.profileId);

    logPrintln(result.status == pgl::gld::GldNullingStatus::Ok
                   ? "NULLING_RUNTIME_RESULT=PASS"
                   : "NULLING_RUNTIME_RESULT=PARTIAL");

    nullDone = true;

    // ----- Connect WiFi → MQTT -----
    const bool wifiOk = connectWifi();
    if (!wifiOk) {
        logPrintln("NULLING_MQTT_SKIP reason=wifi_failed");
        return;
    }

    mqtt.setBufferSize(640);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    if (mqttConnect()) {
        publishStatus("running", "nulling_done");
        publishNullingProfile(toSave);
    }
}

void loop() {
    if (!nullDone) {
        delay(1000);
        return;
    }

    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
    }

    if (!mqtt.connected()) {
        mqttConnect();
    }
    mqtt.loop();

    delay(500);
}
