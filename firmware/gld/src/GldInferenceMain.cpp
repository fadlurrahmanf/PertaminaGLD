#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include <esp_system.h>

#include <cstdarg>
#include <cstdio>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldFrameBuilder.h"
#include "GldMovingAverage.h"
#include "GldPower.h"
#include "GldSelfTestConfig.h"
#include "GldSensorTypes.h"
#include "GldThresholdClassifier.h"
#include "ProtocolConstants.h"

// Machine learning model — placeholder from ApplyGasleak project.
// Replace model_data.cpp + scaler_params.cpp when a Pertamina-trained model is ready.
// IMPORTANT: channel remapping in runInference() must match training feature order.
#include "../model/NeuralNetwork.h"
#include "../model/scaler_params.h"

namespace {

// Hardware
SPIClass gldSpi;
pgl::gld::GldAds1256Reader ads;
pgl::gld::GldMovingAverage movingAvg;
Module* loraModule = nullptr;
SX1262* loraRadio  = nullptr;
NeuralNetwork* network = nullptr;

// Runtime state
bool adsReady   = false;
bool radioReady = false;
bool mlReady    = false;
uint8_t txSeq   = 0;
uint32_t txCounter  = 0;
uint32_t scanSeq    = 0;
uint32_t lastScanMs = 0;
uint32_t lastTxMs   = 0;
bool lastAlarm = false;
pgl::gld::GldClassifyResult lastResult{pgl::protocol::GLD_GAS_CLEAR, 100};

// LoRa config — must match CH STAR radio config
constexpr float    GLD_STAR_TX_FREQ_MHZ    = 920.0f;
constexpr float    GLD_STAR_TX_BW_KHZ      = 125.0f;
constexpr uint8_t  GLD_STAR_TX_SF          = 7;
constexpr uint8_t  GLD_STAR_TX_CR          = 5;
constexpr uint8_t  GLD_STAR_TX_SYNC_WORD   = 0x12;
constexpr int8_t   GLD_STAR_TX_POWER_DBM   = 17;
constexpr uint16_t GLD_STAR_TX_PREAMBLE    = 8;
constexpr float    GLD_LORA_TCXO_VOLTAGE   = 1.6f;
constexpr float    GLD_LORA_XTAL_TCXO_VOLTAGE = 0.0f;

// Timing
constexpr uint32_t SCAN_INTERVAL_MS = 1000;
constexpr uint32_t TX_INTERVAL_MS   = 10000;
constexpr uint8_t  MIN_PRIMED_COUNT = pgl::gld::GLD_SENSOR_MOVING_AVERAGE_WINDOW;

// Channel remapping: hardware channel → model input index.
// Matches ApplyGasleak takeDataMQ() switch-case exactly.
// HW:    ch0=MQ8  ch1=MQ135  ch2=MQ3  ch3=MQ5  ch4=MQ4  ch5=MQ7  ch6=MQ6  ch7=MQ2
// Model: [0]=MQ8  [1]=MQ6    [2]=MQ135 [3]=MQ5  [4]=MQ4  [5]=MQ3  [6]=MQ7  [7]=MQ2
constexpr uint8_t HW_TO_MODEL[8] = {0, 2, 5, 3, 4, 6, 1, 7};

// ML confidence threshold for alarm (0-100 scale matching GLD_LEL_THRESHOLD_PERCENT)
constexpr uint8_t ML_CONFIDENCE_THRESHOLD = pgl::protocol::GLD_LEL_THRESHOLD_PERCENT;

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
// Map model class index → GLD gas class constant
// Placeholder mapping — update when real labeled model is trained.
// ---------------------------------------------------------------------------

uint8_t modelClassToGasClass(int predicted) {
    switch (predicted) {
        case 0:  return pgl::protocol::GLD_GAS_CLEAR;
        case 1:  return pgl::protocol::GLD_GAS_LPG;
        case 2:  return pgl::protocol::GLD_GAS_METHANE;
        case 3:  return pgl::protocol::GLD_GAS_PROPANE;
        case 4:  return pgl::protocol::GLD_GAS_BUTANE;
        default: return pgl::protocol::GLD_GAS_ANOMALY;
    }
}

// ---------------------------------------------------------------------------
// Hardware init
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

bool beginLoraRadio() {
    if (!loraModule) {
        loraModule = new Module(
            pgl::gld::board::PIN_LORA_CS, pgl::gld::board::PIN_LORA_DIO1,
            pgl::gld::board::PIN_LORA_RST, pgl::gld::board::PIN_LORA_BUSY,
            gldSpi);
    }
    if (!loraRadio) loraRadio = new SX1262(loraModule);

    const int16_t tcxoState = loraRadio->begin(
        GLD_STAR_TX_FREQ_MHZ, GLD_STAR_TX_BW_KHZ, GLD_STAR_TX_SF, GLD_STAR_TX_CR,
        GLD_STAR_TX_SYNC_WORD, GLD_STAR_TX_POWER_DBM, GLD_STAR_TX_PREAMBLE,
        GLD_LORA_TCXO_VOLTAGE);
    logPrintf("GLD_STAR_BEGIN_TCXO16_STATE=%d\n", tcxoState);

    int16_t beginState = tcxoState;
    if (beginState == RADIOLIB_ERR_SPI_CMD_FAILED) {
        beginState = loraRadio->begin(
            GLD_STAR_TX_FREQ_MHZ, GLD_STAR_TX_BW_KHZ, GLD_STAR_TX_SF, GLD_STAR_TX_CR,
            GLD_STAR_TX_SYNC_WORD, GLD_STAR_TX_POWER_DBM, GLD_STAR_TX_PREAMBLE,
            GLD_LORA_XTAL_TCXO_VOLTAGE);
        logPrintf("GLD_STAR_BEGIN_XTAL_STATE=%d\n", beginState);
    }
    logPrintf("GLD_STAR_BEGIN_STATE=%d\n", beginState);

    if (beginState != RADIOLIB_ERR_NONE) {
        logPrintln("GLD_STAR_READY=0");
        return false;
    }
    loraRadio->setRfSwitchPins(pgl::gld::board::PIN_LORA_RXEN, pgl::gld::board::PIN_LORA_TXEN);
    logPrintln("GLD_STAR_READY=1");
    return true;
}

// ---------------------------------------------------------------------------
// Alarm outputs
// ---------------------------------------------------------------------------

void updateAlarmOutputs(bool alarm) {
    if (alarm == lastAlarm) return;
    lastAlarm = alarm;
    digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, alarm ? HIGH : LOW);
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, alarm ? HIGH : LOW);
    logPrintf("GLD_ALARM_OUTPUT alarm=%u\n", alarm ? 1 : 0);
}

// ---------------------------------------------------------------------------
// Nonce provider
// ---------------------------------------------------------------------------

struct NonceContext { uint32_t counter; };

bool nonceProvider(uint8_t nonce[pgl::protocol::GLD_AES_GCM_NONCE_SIZE], void* ctx) {
    if (!ctx) return false;
    auto* nc = static_cast<NonceContext*>(ctx);
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

// ---------------------------------------------------------------------------
// ML inference on current moving average voltages
// ---------------------------------------------------------------------------

void runInference(const float mavVoltage[8]) {
    if (!mlReady || !network->isInitialized()) return;

    float* modelInput = network->getInputBuffer();
    if (!modelInput) return;

    // Apply channel remapping + StandardScaler normalization
    for (uint8_t hwCh = 0; hwCh < pgl::gld::board::SENSOR_COUNT; ++hwCh) {
        const uint8_t mIdx = HW_TO_MODEL[hwCh];
        modelInput[mIdx] = (mavVoltage[hwCh] - feature_means[mIdx]) / feature_stds[mIdx];
    }

    float confidenceFloat = 0.0f;
    const int predictedClass = network->predict(confidenceFloat);

    if (predictedClass < 0) {
        logPrintln("GLD_ML_PREDICT_ERROR");
        return;
    }

    const uint8_t gasClass   = modelClassToGasClass(predictedClass);
    const uint8_t confidence = static_cast<uint8_t>(confidenceFloat * 100.0f);

    lastResult = {gasClass, confidence};

    logPrintf("GLD_ML_RESULT predictedClass=%d gasClass=%u(%s) confidence=%u\n",
              predictedClass, gasClass,
              pgl::gld::gldGasClassName(gasClass),
              confidence);
}

// ---------------------------------------------------------------------------
// Sensor scan + ML classify
// ---------------------------------------------------------------------------

void runScan() {
    float mavVoltage[8] = {};
    bool allValid = adsReady;
    uint8_t primedChannels = 0;

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading r = ads.readChannel(ch);
        if (r.status == pgl::gld::GldAds1256Status::Ok) {
            mavVoltage[ch] = movingAvg.add(ch, r.voltage);
        } else {
            mavVoltage[ch] = movingAvg.value(ch);
            allValid = false;
        }
        if (movingAvg.count(ch) >= MIN_PRIMED_COUNT) ++primedChannels;
    }

    const bool primed = primedChannels >= pgl::gld::board::SENSOR_COUNT;

    if (primed) {
        runInference(mavVoltage);
    }

    const bool alarm = lastResult.gasClass != pgl::protocol::GLD_GAS_CLEAR &&
                       lastResult.confidence >= ML_CONFIDENCE_THRESHOLD;

    logPrintf("GLD_SENSOR_SCAN seq=%lu ts=%lu allValid=%u primed=%u gasClass=%u(%s) confidence=%u alarm=%u\n",
              static_cast<unsigned long>(scanSeq),
              static_cast<unsigned long>(millis()),
              allValid ? 1 : 0,
              primed ? 1 : 0,
              lastResult.gasClass, pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence,
              alarm ? 1 : 0);

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        logPrintf("  ch%u %-5s mav=%.5f cnt=%u\n",
                  ch,
                  pgl::gld::board::SENSOR_NAMES[ch],
                  mavVoltage[ch],
                  movingAvg.count(ch));
    }

    updateAlarmOutputs(alarm);
    ++scanSeq;
}

// ---------------------------------------------------------------------------
// LoRa TX
// ---------------------------------------------------------------------------

void transmitOnce() {
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    const bool externalPower = power.externalPower;
    const uint16_t batteryMv = power.batteryValid
                                   ? power.batteryMv
                                   : pgl::protocol::GLD_BATTERY_MV_INVALID;

    pgl::gld::GldFrameBuilderConfig config{
        pgl::gld::selftest::NODE_ID,
        pgl::gld::selftest::CH_ID,
        pgl::gld::selftest::KEY_ID,
        pgl::gld::selftest::AES_KEY,
        externalPower,
        pgl::protocol::GLD_LEL_THRESHOLD_PERCENT,
    };
    pgl::gld::GldFrameBuildInput input{
        lastResult.gasClass,
        lastResult.confidence,
        batteryMv,
        txSeq,
    };
    NonceContext nonceCtx{txCounter};
    pgl::gld::GldBuiltFrame frame{};

    const pgl::gld::GldFrameStatus buildStatus =
        pgl::gld::buildGldUplinkFrame(config, input, nonceProvider, &nonceCtx, frame);
    txCounter = nonceCtx.counter;

    logPrintf("GLD_TX_HEADER status=%s src=0x%04X dst=0x%04X seq=%u typeFlags=0x%02X alarm=%u externalPower=%u gasClass=%u(%s) confidence=%u batteryMv=%u frameSize=%u\n",
              pgl::gld::gldFrameStatusName(buildStatus),
              config.nodeId, config.chId, txSeq,
              frame.typeFlags,
              frame.alarm ? 1 : 0,
              externalPower ? 1 : 0,
              lastResult.gasClass, pgl::gld::gldGasClassName(lastResult.gasClass),
              lastResult.confidence,
              batteryMv,
              static_cast<unsigned>(frame.size));

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

    logPrintln("");
    logPrintln("Pertamina GLD ML inference runtime");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("GLD_INFERENCE_CONFIG nodeId=0x%04X chId=0x%04X scanMs=%lu txMs=%lu alarmThreshold=%u\n",
              static_cast<unsigned>(pgl::gld::selftest::NODE_ID),
              static_cast<unsigned>(pgl::gld::selftest::CH_ID),
              static_cast<unsigned long>(SCAN_INTERVAL_MS),
              static_cast<unsigned long>(TX_INTERVAL_MS),
              static_cast<unsigned>(ML_CONFIDENCE_THRESHOLD));

    // Init ML model
    network = new NeuralNetwork();
    mlReady = network->isInitialized();
    logPrintf("GLD_ML_INIT initialized=%u outputSize=%d\n",
              mlReady ? 1 : 0,
              mlReady ? network->getOutputSize() : -1);

    logPrintf("ADS_DRDY_BEFORE_BEGIN=%u\n", digitalRead(pgl::gld::board::PIN_ADS1256_DRDY));
    adsReady = ads.begin(gldSpi);
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");

    radioReady = beginLoraRadio();

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("GLD_POWER mode=%s externalPower=%u batteryMv=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.externalPower ? 1 : 0,
              power.batteryMv);

    logPrintf("GLD_INFERENCE_READY adsReady=%u radioReady=%u mlReady=%u\n",
              adsReady ? 1 : 0, radioReady ? 1 : 0, mlReady ? 1 : 0);

    lastScanMs = millis();
    lastTxMs   = millis();
}

void loop() {
    const uint32_t now = millis();

    if (adsReady && now - lastScanMs >= SCAN_INTERVAL_MS) {
        lastScanMs = now;
        runScan();
    }

    if (radioReady && now - lastTxMs >= TX_INTERVAL_MS) {
        lastTxMs = now;
        transmitOnce();
    }
}
