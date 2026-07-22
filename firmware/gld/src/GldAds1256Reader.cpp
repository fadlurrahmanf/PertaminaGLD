#include "GldAds1256Reader.h"

#include <Arduino.h>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

constexpr uint8_t REG_STATUS = 0x00;
constexpr uint8_t REG_MUX = 0x01;
constexpr uint8_t REG_ADCON = 0x02;
constexpr uint8_t REG_DRATE = 0x03;
constexpr uint8_t ADS1256_CMD_RDATA = 0x01;
constexpr uint8_t ADS1256_CMD_RREG = 0x10;
constexpr uint8_t ADS1256_CMD_WREG = 0x50;
constexpr uint8_t ADS1256_CMD_SELFCAL = 0xF0;
constexpr uint8_t ADS1256_CMD_RESET = 0xFE;
constexpr uint8_t ADS1256_STATUS_DEFAULT = 0b00110110;
constexpr uint8_t ADS1256_DRATE_30000SPS = 0b11110000;
constexpr uint32_t ADS1256_SPI_CLOCK_HZ = 1920000;
constexpr float ADS1256_AGC_SATURATION_RATIO = 0.95f;
constexpr float ADS1256_AGC_GAIN_DOWN_RATIO = 0.85f;
constexpr float ADS1256_AGC_GAIN_UP_RATIO = 0.20f;
constexpr uint8_t ADS1256_AGC_GAIN_DOWN_CONFIRM = 1;
constexpr uint8_t ADS1256_AGC_GAIN_UP_CONFIRM = 5;
constexpr uint32_t ADS1256_READ_DRDY_TIMEOUT_MS = 5;
constexpr uint32_t ADS1256_CONFIG_DRDY_TIMEOUT_MS = 25;
constexpr uint32_t ADS1256_STARTUP_DRDY_TIMEOUT_MS = 1500;

constexpr uint8_t PGA_VALUE_TABLE[7] = {64, 32, 16, 8, 4, 2, 1};
// ADS1256 ADCON.PGA encodings, ordered to match PGA_VALUE_TABLE.
constexpr uint8_t PGA_REGISTER_TABLE[7] = {6, 5, 4, 3, 2, 1, 0};

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

bool waitDrdyHigh(uint32_t timeoutMs) {
    const uint32_t start = millis();
    while (digitalRead(pgl::gld::board::PIN_ADS1256_DRDY) != HIGH) {
        if (millis() - start >= timeoutMs) {
            return false;
        }
        delay(1);
    }
    return true;
}

void sendDirectCommand(SPIClass& spi, uint8_t command) {
    spi.beginTransaction(SPISettings(ADS1256_SPI_CLOCK_HZ, MSBFIRST, SPI_MODE1));
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, LOW);
    delayMicroseconds(5);
    spi.transfer(command);
    delayMicroseconds(5);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    spi.endTransaction();
}

bool writeRegisterBounded(
    SPIClass& spi,
    uint8_t registerAddress,
    uint8_t value,
    uint32_t timeoutMs) {
    if (!waitDrdyLow(timeoutMs)) {
        return false;
    }

    spi.beginTransaction(SPISettings(ADS1256_SPI_CLOCK_HZ, MSBFIRST, SPI_MODE1));
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, LOW);
    delayMicroseconds(5);
    spi.transfer(static_cast<uint8_t>(ADS1256_CMD_WREG | registerAddress));
    spi.transfer(0x00);
    spi.transfer(value);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    spi.endTransaction();
    delay(10);
    return true;
}

bool readRegisterBounded(
    SPIClass& spi,
    uint8_t registerAddress,
    uint8_t& value,
    uint32_t timeoutMs) {
    if (!waitDrdyLow(timeoutMs)) {
        return false;
    }

    spi.beginTransaction(SPISettings(ADS1256_SPI_CLOCK_HZ, MSBFIRST, SPI_MODE1));
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, LOW);
    spi.transfer(static_cast<uint8_t>(ADS1256_CMD_RREG | registerAddress));
    spi.transfer(0x00);
    delayMicroseconds(7);
    value = spi.transfer(0xFF);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    spi.endTransaction();
    return true;
}

bool readRawBounded(SPIClass& spi, long& raw, uint32_t timeoutMs) {
    if (!waitDrdyLow(timeoutMs)) {
        return false;
    }

    spi.beginTransaction(SPISettings(ADS1256_SPI_CLOCK_HZ, MSBFIRST, SPI_MODE1));
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, LOW);
    spi.transfer(ADS1256_CMD_RDATA);
    delayMicroseconds(7);
    const uint8_t msb = spi.transfer(0x00);
    const uint8_t mid = spi.transfer(0x00);
    const uint8_t lsb = spi.transfer(0x00);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    spi.endTransaction();

    int32_t signedRaw =
        (static_cast<int32_t>(msb) << 16) |
        (static_cast<int32_t>(mid) << 8) |
        static_cast<int32_t>(lsb);
    if ((signedRaw & 0x00800000L) != 0) {
        signedRaw |= static_cast<int32_t>(0xFF000000UL);
    }
    raw = static_cast<long>(signedRaw);
    return true;
}

}  // namespace

bool GldAds1256Reader::begin(SPIClass& spi) {
    spi_ = &spi;
    initialized_ = false;
    activePgaIndex_ = 0xFF;

    pinMode(pgl::gld::board::PIN_LORA_CS, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_CS, HIGH);

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

    sendDirectCommand(*spi_, ADS1256_CMD_RESET);
    delay(20);

    if (!waitDrdyLow(ADS1256_STARTUP_DRDY_TIMEOUT_MS)) {
        return false;
    }

    if (!writeRegisterBounded(
            *spi_, REG_STATUS, ADS1256_STATUS_DEFAULT, ADS1256_STARTUP_DRDY_TIMEOUT_MS) ||
        !writeRegisterBounded(
            *spi_, REG_MUX, muxSingleEnded(adsInputForSensor(0)), ADS1256_STARTUP_DRDY_TIMEOUT_MS) ||
        !writeRegisterBounded(
            *spi_, REG_ADCON, PGA_REGISTER_TABLE[0], ADS1256_STARTUP_DRDY_TIMEOUT_MS) ||
        !writeRegisterBounded(
            *spi_, REG_DRATE, ADS1256_DRATE_30000SPS, ADS1256_STARTUP_DRDY_TIMEOUT_MS)) {
        return false;
    }

    if (!waitDrdyLow(ADS1256_STARTUP_DRDY_TIMEOUT_MS)) {
        return false;
    }
    sendDirectCommand(*spi_, ADS1256_CMD_SELFCAL);
    // SELFCAL raises DRDY while calibration is running and lowers it when the
    // result is ready. Waiting for both edges avoids accepting the pre-command
    // LOW level as a completed calibration.
    if (!waitDrdyHigh(ADS1256_STARTUP_DRDY_TIMEOUT_MS) ||
        !waitDrdyLow(ADS1256_STARTUP_DRDY_TIMEOUT_MS)) {
        return false;
    }

    long discardedRaw = 0;
    if (!readRawBounded(*spi_, discardedRaw, ADS1256_STARTUP_DRDY_TIMEOUT_MS)) {
        return false;
    }

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        pgaIndex_[ch] = 0;
        gainConfirmDown_[ch] = 0;
        gainConfirmUp_[ch] = 0;
    }

    activePgaIndex_ = 0;
    initialized_ = true;
    return true;
}

uint8_t GldAds1256Reader::readStatusRegister() {
    uint8_t value = 0;
    return initialized_ && spi_ != nullptr &&
                   readRegisterBounded(*spi_, REG_STATUS, value, ADS1256_CONFIG_DRDY_TIMEOUT_MS)
               ? value
               : 0;
}

uint8_t GldAds1256Reader::readMuxRegister() {
    uint8_t value = 0;
    return initialized_ && spi_ != nullptr &&
                   readRegisterBounded(*spi_, REG_MUX, value, ADS1256_CONFIG_DRDY_TIMEOUT_MS)
               ? value
               : 0;
}

uint8_t GldAds1256Reader::readAdconRegister() {
    uint8_t value = 0;
    return initialized_ && spi_ != nullptr &&
                   readRegisterBounded(*spi_, REG_ADCON, value, ADS1256_CONFIG_DRDY_TIMEOUT_MS)
               ? value
               : 0;
}

uint8_t GldAds1256Reader::readDrateRegister() {
    uint8_t value = 0;
    return initialized_ && spi_ != nullptr &&
                   readRegisterBounded(*spi_, REG_DRATE, value, ADS1256_CONFIG_DRDY_TIMEOUT_MS)
               ? value
               : 0;
}

GldAds1256Reading GldAds1256Reader::readChannel(uint8_t channel) {
    if (!initialized_ || spi_ == nullptr) {
        return {GldAds1256Status::NotReady, 0, 0.0f, GLD_ADS1256_DEFAULT_GAIN, false};
    }
    if (channel >= pgl::gld::board::SENSOR_COUNT) {
        return {GldAds1256Status::InvalidChannel, 0, 0.0f, GLD_ADS1256_DEFAULT_GAIN, false};
    }

    // ADS1256 has one global PGA. Restore the selected channel's remembered
    // gain before its first conversion so channel switching cannot leak gain.
    if (!applyGain(channel)) {
        return {GldAds1256Status::DrdyTimeout, 0, 0.0f, getCurrentGain(channel), false};
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
    const float maxVoltage = (2.0f * GLD_ADS1256_VREF_VOLTS) / static_cast<float>(gain);
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
    const float maxVoltage = (2.0f * GLD_ADS1256_VREF_VOLTS) / static_cast<float>(gain);
    const float ratio = fabsf(voltage) / maxVoltage;

    const bool needDown = ratio >= ADS1256_AGC_SATURATION_RATIO || ratio >= ADS1256_AGC_GAIN_DOWN_RATIO;
    const bool needUp = ratio < ADS1256_AGC_GAIN_UP_RATIO && pgaIndex_[channel] > 0;

    if (needDown && pgaIndex_[channel] < 6) {
        ++gainConfirmDown_[channel];
        gainConfirmUp_[channel] = 0;
        if (gainConfirmDown_[channel] >= ADS1256_AGC_GAIN_DOWN_CONFIRM) {
            const uint8_t previousIndex = pgaIndex_[channel];
            ++pgaIndex_[channel];
            gainConfirmDown_[channel] = 0;
            if (!applyGain(channel)) {
                pgaIndex_[channel] = previousIndex;
                return false;
            }
        }
    } else if (needUp) {
        ++gainConfirmUp_[channel];
        gainConfirmDown_[channel] = 0;
        if (gainConfirmUp_[channel] >= ADS1256_AGC_GAIN_UP_CONFIRM) {
            const uint8_t previousIndex = pgaIndex_[channel];
            --pgaIndex_[channel];
            gainConfirmUp_[channel] = 0;
            if (!applyGain(channel)) {
                pgaIndex_[channel] = previousIndex;
                return false;
            }
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

bool GldAds1256Reader::applyGain(uint8_t channel) {
    const uint8_t targetIndex = pgaIndex_[channel];
    if (activePgaIndex_ == targetIndex) {
        return true;
    }
    if (spi_ == nullptr ||
        !writeRegisterBounded(
            *spi_, REG_ADCON, PGA_REGISTER_TABLE[targetIndex], ADS1256_CONFIG_DRDY_TIMEOUT_MS)) {
        return false;
    }
    activePgaIndex_ = targetIndex;
    return true;
}

float GldAds1256Reader::convertToVoltage(long raw, uint8_t pgaGain) const {
    const float bipolarFullScale =
        (2.0f * GLD_ADS1256_VREF_VOLTS) / static_cast<float>(pgaGain);
    return (static_cast<float>(raw) / 8388608.0f) * bipolarFullScale;
}

bool GldAds1256Reader::readSingleInternal(uint8_t channel, long& raw) {
    if (spi_ == nullptr ||
        !writeRegisterBounded(
            *spi_,
            REG_MUX,
            muxSingleEnded(adsInputForSensor(channel)),
            ADS1256_CONFIG_DRDY_TIMEOUT_MS)) {
        return false;
    }

    long discardedRaw = 0;
    if (!readRawBounded(*spi_, discardedRaw, ADS1256_READ_DRDY_TIMEOUT_MS)) {
        return false;
    }
    return readRawBounded(*spi_, raw, ADS1256_READ_DRDY_TIMEOUT_MS);
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
