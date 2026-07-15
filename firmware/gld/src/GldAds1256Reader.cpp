#include "GldAds1256Reader.h"

#include <Arduino.h>
#include <ADS1256.h>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

constexpr uint8_t REG_STATUS = 0x00;
constexpr uint8_t REG_MUX = 0x01;
constexpr uint8_t REG_ADCON = 0x02;
constexpr uint8_t REG_DRATE = 0x03;
constexpr uint8_t ADS1256_CMD_RESET = 0xFE;
constexpr float ADS1256_AGC_SATURATION_RATIO = 0.95f;
constexpr float ADS1256_AGC_GAIN_DOWN_RATIO = 0.85f;
constexpr float ADS1256_AGC_GAIN_UP_RATIO = 0.20f;
constexpr uint8_t ADS1256_AGC_GAIN_DOWN_CONFIRM = 1;
constexpr uint8_t ADS1256_AGC_GAIN_UP_CONFIRM = 5;
constexpr uint32_t ADS1256_READ_DRDY_TIMEOUT_MS = 5;

constexpr uint8_t PGA_VALUE_TABLE[7] = {64, 32, 16, 8, 4, 2, 1};
constexpr uint8_t PGA_LIB_CONST[7] = {PGA_64, PGA_32, PGA_16, PGA_8, PGA_4, PGA_2, PGA_1};

uint8_t muxSingleEnded(uint8_t channel) {
    return static_cast<uint8_t>(0x0F | (channel << 4));
}

uint8_t adsInputForSensor(uint8_t sensorChannel) {
    return pgl::gld::board::SENSOR_TO_ADS_CH[sensorChannel];
}

bool waitDrdyLow(uint32_t timeoutMs) {
    const uint32_t start = millis();
    while (digitalRead(pgl::gld::board::PIN_ADS1256_DRDY) != LOW) {
        if (millis() - start >= timeoutMs) {
            return false;
        }
        delay(1);
    }
    return true;
}

}  // namespace

bool GldAds1256Reader::begin(SPIClass& spi) {
    spi_ = &spi;

    pinMode(pgl::gld::board::PIN_LORA_CS, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_CS, HIGH);

    if (ads_ == nullptr) {
        // Same proven pattern as the legacy firmware: this board has SYNC/PDWN
        // but no dedicated ADS1256 RESET line, so SYNC is reused for both.
        ads_ = new ADS1256(
            pgl::gld::board::PIN_ADS1256_DRDY,
            pgl::gld::board::PIN_ADS1256_SYNC,
            pgl::gld::board::PIN_ADS1256_SYNC,
            pgl::gld::board::PIN_ADS1256_CS,
            GLD_ADS1256_VREF_VOLTS,
            spi_);
    }

    pinMode(pgl::gld::board::PIN_ADS1256_CS, OUTPUT);
    pinMode(pgl::gld::board::PIN_ADS1256_DRDY, INPUT);
    pinMode(pgl::gld::board::PIN_ADS1256_SYNC, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    digitalWrite(pgl::gld::board::PIN_ADS1256_SYNC, HIGH);

    digitalWrite(pgl::gld::board::PIN_ADS1256_SYNC, LOW);
    delay(100);
    digitalWrite(pgl::gld::board::PIN_ADS1256_SYNC, HIGH);
    delay(100);

    spi_->begin(
        pgl::gld::board::PIN_SPI_SCK,
        pgl::gld::board::PIN_SPI_MISO,
        pgl::gld::board::PIN_SPI_MOSI);

    ads_->sendDirectCommand(ADS1256_CMD_RESET);
    delay(20);

    if (!waitDrdyLow(1500)) {
        initialized_ = false;
        return false;
    }

    ads_->InitializeADC();
    ads_->setPGA(PGA_64);
    ads_->setDRATE(DRATE_30000SPS);
    ads_->setMUX(muxSingleEnded(adsInputForSensor(0)));
    (void)ads_->readSingle();

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        pgaIndex_[ch] = 0;
        gainConfirmDown_[ch] = 0;
        gainConfirmUp_[ch] = 0;
    }

    initialized_ = true;
    return true;
}

uint8_t GldAds1256Reader::readStatusRegister() {
    return !initialized_ || ads_ == nullptr ? 0 : static_cast<uint8_t>(ads_->readRegister(REG_STATUS) & 0xFF);
}

uint8_t GldAds1256Reader::readMuxRegister() {
    return !initialized_ || ads_ == nullptr ? 0 : static_cast<uint8_t>(ads_->readRegister(REG_MUX) & 0xFF);
}

uint8_t GldAds1256Reader::readAdconRegister() {
    return !initialized_ || ads_ == nullptr ? 0 : static_cast<uint8_t>(ads_->readRegister(REG_ADCON) & 0xFF);
}

uint8_t GldAds1256Reader::readDrateRegister() {
    return !initialized_ || ads_ == nullptr ? 0 : static_cast<uint8_t>(ads_->readRegister(REG_DRATE) & 0xFF);
}

GldAds1256Reading GldAds1256Reader::readChannel(uint8_t channel) {
    if (!initialized_ || ads_ == nullptr) {
        return {GldAds1256Status::NotReady, 0, 0.0f, GLD_ADS1256_DEFAULT_GAIN, false};
    }
    if (channel >= pgl::gld::board::SENSOR_COUNT) {
        return {GldAds1256Status::InvalidChannel, 0, 0.0f, GLD_ADS1256_DEFAULT_GAIN, false};
    }

    if (!gainCalibrate(channel)) {
        return {GldAds1256Status::DrdyTimeout, 0, 0.0f, getCurrentGain(channel), false};
    }
    long raw = 0;
    if (!readSingleInternal(channel, raw)) {
        return {GldAds1256Status::DrdyTimeout, 0, 0.0f, getCurrentGain(channel), false};
    }
    const uint8_t gain = getCurrentGain(channel);
    const float voltage = convertToVoltage(raw, gain);
    const float maxVoltage = GLD_ADS1256_VREF_VOLTS / static_cast<float>(gain);
    const bool saturated = fabsf(voltage) >= (ADS1256_AGC_SATURATION_RATIO * maxVoltage);
    return {GldAds1256Status::Ok, static_cast<int32_t>(raw), voltage, gain, saturated};
}

bool GldAds1256Reader::gainCalibrate(uint8_t channel) {
    long raw = 0;
    if (!readSingleInternal(channel, raw)) {
        return false;
    }
    const uint8_t gain = getCurrentGain(channel);
    const float voltage = convertToVoltage(raw, gain);
    const float maxVoltage = GLD_ADS1256_VREF_VOLTS / static_cast<float>(gain);
    const float ratio = fabsf(voltage) / maxVoltage;

    const bool needDown = ratio >= ADS1256_AGC_SATURATION_RATIO || ratio >= ADS1256_AGC_GAIN_DOWN_RATIO;
    const bool needUp = ratio < ADS1256_AGC_GAIN_UP_RATIO && pgaIndex_[channel] > 0;

    if (needDown && pgaIndex_[channel] < 6) {
        ++gainConfirmDown_[channel];
        gainConfirmUp_[channel] = 0;
        if (gainConfirmDown_[channel] >= ADS1256_AGC_GAIN_DOWN_CONFIRM) {
            ++pgaIndex_[channel];
            gainConfirmDown_[channel] = 0;
            applyGain(channel);
        }
    } else if (needUp) {
        ++gainConfirmUp_[channel];
        gainConfirmDown_[channel] = 0;
        if (gainConfirmUp_[channel] >= ADS1256_AGC_GAIN_UP_CONFIRM) {
            --pgaIndex_[channel];
            gainConfirmUp_[channel] = 0;
            applyGain(channel);
        }
    } else {
        gainConfirmDown_[channel] = 0;
        gainConfirmUp_[channel] = 0;
    }
    return true;
}

uint8_t GldAds1256Reader::getCurrentGain(uint8_t channel) const {
    return PGA_VALUE_TABLE[pgaIndex_[channel]];
}

void GldAds1256Reader::applyGain(uint8_t channel) {
    ads_->setPGA(PGA_LIB_CONST[pgaIndex_[channel]]);
    delay(20);
    ads_->setMUX(muxSingleEnded(adsInputForSensor(channel)));
    (void)ads_->readSingle();
}

float GldAds1256Reader::convertToVoltage(long raw, uint8_t pgaGain) const {
    return (static_cast<float>(raw) / 8388607.0f) * (GLD_ADS1256_VREF_VOLTS / static_cast<float>(pgaGain));
}

bool GldAds1256Reader::readSingleInternal(uint8_t channel, long& raw) {
    ads_->setMUX(muxSingleEnded(adsInputForSensor(channel)));
    if (!waitDrdyLow(ADS1256_READ_DRDY_TIMEOUT_MS)) {
        return false;
    }
    (void)ads_->readSingle();
    if (!waitDrdyLow(ADS1256_READ_DRDY_TIMEOUT_MS)) {
        return false;
    }
    raw = ads_->readSingle();
    return true;
}

const char* gldAds1256StatusName(GldAds1256Status status) {
    switch (status) {
        case GldAds1256Status::Ok:
            return "Ok";
        case GldAds1256Status::NotReady:
            return "NotReady";
        case GldAds1256Status::DrdyTimeout:
            return "DrdyTimeout";
        case GldAds1256Status::InvalidChannel:
            return "InvalidChannel";
    }
    return "Unknown";
}

}  // namespace pgl::gld
