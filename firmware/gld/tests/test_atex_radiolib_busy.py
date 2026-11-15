"""Compile real SX126x/Module sources against a fault-injectable fake HAL.

Tests are host-only. They do not prove the deadline on ESP32, RF behavior, or
the timing of a real ATEX module. No source or generated file is installed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "firmware/lib/RadioLib/src"
SX = LIB / "modules/SX126x/SX126x.cpp"
COMPILER = Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe"

HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <new>
#include "Module.h"
#include "modules/SX126x/SX126x.h"

struct FakeHal : RadioLibHal {
    uint32_t now = 0;
    bool busyAlways = false, busyAfterTx = false, busyAfterClearIrq = false;
    bool busyAfterIrqRead = false, busyAfterRxStatus = false;
    bool failStandbyStatus = false, busyAfterStandby = false, sawStandby = false, csHigh = true;
    bool sawTx = false, sawClearIrq = false;
    bool sawIrqRead = false, sawRxStatus = false;
    unsigned packetTypeReads = 0, failPacketTypeRead = 0;
    uint8_t failurePayloadType = RADIOLIB_SX126X_PACKET_TYPE_LORA;
    unsigned afterTxReads = 0, txCount = 0, rxCount = 0, transfers = 0, readBufferCount = 0;
    unsigned csLowWrites = 0, csHighWrites = 0;
    FakeHal() : RadioLibHal(0, 1, 0, 1, 1, 2) {}
    void pinMode(uint32_t, uint32_t) override {}
    void digitalWrite(uint32_t pin, uint32_t value) override {
        if (pin == 1) { csHigh = value == GpioLevelHigh; if (csHigh) ++csHighWrites; else ++csLowWrites; }
    }
    uint32_t digitalRead(uint32_t) override {
        if (busyAlways) return 1;
        if (busyAfterClearIrq && sawClearIrq) return 1;
        if (busyAfterIrqRead && sawIrqRead) return 1;
        if (busyAfterRxStatus && sawRxStatus) return 1;
        if (busyAfterStandby && sawStandby) return 1;
        if (busyAfterTx && sawTx) return afterTxReads++ != 0;
        return 0;
    }
    void attachInterrupt(uint32_t, void (*)(void), uint32_t) override {}
    void detachInterrupt(uint32_t) override {}
    void delay(RadioLibTime_t ms) override { now += ms; }
    void delayMicroseconds(RadioLibTime_t) override {}
    RadioLibTime_t millis() override { return now; }
    RadioLibTime_t micros() override { return now * 1000; }
    long pulseIn(uint32_t, uint32_t, RadioLibTime_t) override { return 0; }
    void spiBegin() override {}
    void spiBeginTransaction() override {}
    void spiTransfer(uint8_t* out, size_t len, uint8_t* in) override {
        ++transfers;
        std::memset(in, 0, len);
        if (len && out[0] == RADIOLIB_SX126X_CMD_SET_STANDBY) sawStandby = true;
        if (len > 1 && out[0] == RADIOLIB_SX126X_CMD_SET_STANDBY && failStandbyStatus) in[1] = 0xEE;
        if (len && out[0] == RADIOLIB_SX126X_CMD_GET_PACKET_TYPE) {
            ++packetTypeReads;
            in[len-1] = packetTypeReads == failPacketTypeRead ? failurePayloadType : RADIOLIB_SX126X_PACKET_TYPE_LORA;
            if (packetTypeReads == failPacketTypeRead && len > 1) in[1] = 0xEE;
        }
        if (len >= 4 && out[0] == RADIOLIB_SX126X_CMD_GET_IRQ_STATUS) {
            in[len-2] = 0x02; in[len-1] = 0x01; sawIrqRead = true;
        }
        if (len >= 4 && out[0] == RADIOLIB_SX126X_CMD_GET_RX_BUFFER_STATUS) {
            in[len-2] = 4; in[len-1] = 7; sawRxStatus = true;
        }
        if (len && out[0] == RADIOLIB_SX126X_CMD_READ_BUFFER) ++readBufferCount;
        if (len && out[0] == RADIOLIB_SX126X_CMD_SET_TX) { sawTx = true; ++txCount; }
        if (len && out[0] == RADIOLIB_SX126X_CMD_SET_RX) ++rxCount;
        if (len && out[0] == RADIOLIB_SX126X_CMD_CLEAR_IRQ_STATUS) sawClearIrq = true;
    }
    void spiEndTransaction() override {}
    void spiEnd() override {}
    void yield() override { ++now; }
};

static int16_t parseInjectedStatus(uint8_t status) {
    return status == 0xEE ? RADIOLIB_ERR_SPI_CMD_FAILED : RADIOLIB_ERR_NONE;
}

static void setup(Module& mod) {
    mod.spiConfig.widths[RADIOLIB_MODULE_SPI_WIDTH_CMD] = Module::BITS_8;
    mod.spiConfig.widths[RADIOLIB_MODULE_SPI_WIDTH_STATUS] = Module::BITS_8;
    mod.spiConfig.stream = true;
    mod.spiConfig.statusPos = 1;
    mod.spiConfig.parseStatusCb = parseInjectedStatus;
    mod.spiConfig.timeout = 1000;
}

static void stuckAtEntry() {
    FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
    alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
    SX126x& radio = *new (storage) SX126x(&mod); hal.busyAlways = true;
    hal.now = UINT32_MAX - 20;
    const uint32_t start = hal.now;
    const int16_t result = radio.startReceive();
    assert(result == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
    assert(hal.now - start == 50 && hal.transfers == 0);
    assert(hal.csHigh && hal.csLowWrites > 0 && hal.csHighWrites > 0);
    assert(mod.spiConfig.timeout == 1000);
}

static void standbyAlwaysReleasesCsOnErrors() {
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.busyAlways = true;
        assert(radio.standby() == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
        assert(hal.csHigh && hal.csLowWrites > 0 && hal.csHighWrites > 0);
        assert(hal.transfers == 0 && mod.spiConfig.timeout == 1000);
    }
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.busyAlways = true; hal.csHigh = false;
        assert(radio.standby(RADIOLIB_SX126X_STANDBY_RC, false) == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
        assert(hal.csHigh && mod.spiConfig.timeout == 1000);
    }
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.failStandbyStatus = true;
        assert(radio.standby() == RADIOLIB_ERR_SPI_CMD_FAILED);
        assert(hal.csHigh && hal.transfers > 0 && mod.spiConfig.timeout == 1000);
    }
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.busyAfterStandby = true;
        assert(radio.standby() == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
        assert(hal.sawStandby && hal.csHigh && hal.now == 50 && mod.spiConfig.timeout == 1000);
    }
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.failStandbyStatus = true;
        assert(radio.startReceive() == RADIOLIB_ERR_SPI_CMD_FAILED);
        assert(hal.csHigh && hal.rxCount == 0 && mod.spiConfig.timeout == 1000);
    }
}

static void stuckAfterTxIsUncertain() {
    FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
    alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
    SX126x& radio = *new (storage) SX126x(&mod); hal.busyAfterTx = true;
    const uint8_t payload[] = {0x11, 0x22};
    const int16_t result = radio.startTransmit(payload, sizeof(payload));
    assert(result == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
    assert(hal.txCount == 1 && hal.now == 50);
    assert(mod.spiConfig.timeout == 1000);
}

static void failedClearIrqNeverStartsRx() {
    FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
    alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
    SX126x& radio = *new (storage) SX126x(&mod); hal.busyAfterClearIrq = true;
    const int16_t result = radio.startReceive();
    assert(result == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
    assert(hal.sawClearIrq && hal.rxCount == 0 && hal.now == 50);
    assert(mod.spiConfig.timeout == 1000);
}

static void healthyRxStarts() {
    FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
    alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
    SX126x& radio = *new (storage) SX126x(&mod);
    assert(radio.startReceive() == RADIOLIB_ERR_NONE);
    assert(hal.rxCount == 1 && mod.spiConfig.timeout == 1000);
}

// Document the remaining vendor API ambiguity, not a success condition:
// both queries discard transport errors and return a zero-shaped value. A
// consumer cannot distinguish that from a legitimate empty result. This test
// intentionally keeps the issue visible until checked APIs are integrated.
static void queryFailureIsNotAValidEmptyRx() {
    FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
    alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
    SX126x& radio = *new (storage) SX126x(&mod); hal.busyAlways = true;
    assert(radio.getIrqFlags() == 0 && hal.now == 50);
    assert(radio.getPacketLength() == 0 && hal.now == 150);
    assert(mod.spiConfig.timeout == 1000);
}

static void checkedQueriesSeparateErrorsAndValues() {
    FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
    alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
    SX126x& radio = *new (storage) SX126x(&mod);
    uint32_t irq = 0xAABBCCDD; size_t length = 123; uint8_t offset = 99;
    assert(radio.getIrqFlagsChecked(irq) == RADIOLIB_ERR_NONE && irq == 0x0201);
    assert(radio.getPacketLengthChecked(length, &offset) == RADIOLIB_ERR_NONE && length == 4 && offset == 7);
    hal.busyAlways = true; irq = 0xAABBCCDD; length = 123; offset = 99;
    assert(radio.getIrqFlagsChecked(irq) == RADIOLIB_ERR_SPI_CMD_TIMEOUT && irq == 0xAABBCCDD);
    assert(radio.getPacketLengthChecked(length, &offset) == RADIOLIB_ERR_SPI_CMD_TIMEOUT && length == 123 && offset == 99);
    assert(mod.spiConfig.timeout == 1000);
}

static void noFalseReceiveOnIrqOrLengthReadFailure() {
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.busyAfterIrqRead = true; uint8_t payload[16] = {};
        assert(radio.readData(payload, sizeof(payload)) == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
        assert(hal.readBufferCount == 0 && mod.spiConfig.timeout == 1000);
    }
    {
        FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
        alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
        SX126x& radio = *new (storage) SX126x(&mod);
        hal.busyAfterRxStatus = true; uint8_t payload[16] = {};
        assert(radio.readData(payload, sizeof(payload)) == RADIOLIB_ERR_SPI_CMD_TIMEOUT);
        assert(hal.readBufferCount == 0 && mod.spiConfig.timeout == 1000);
    }
}

static void packetTypeSpiErrorWithValidPayload() {
    for (uint8_t payloadType : {uint8_t(RADIOLIB_SX126X_PACKET_TYPE_LORA), uint8_t(RADIOLIB_SX126X_PACKET_TYPE_GFSK)}) {
        {
            FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
            alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
            SX126x& radio = *new (storage) SX126x(&mod);
            hal.failPacketTypeRead = 1; hal.failurePayloadType = payloadType;
            const uint8_t payload[] = {0x11, 0x22};
            assert(radio.startTransmit(payload, sizeof(payload)) == RADIOLIB_ERR_SPI_CMD_FAILED);
            assert(hal.packetTypeReads == 1 && hal.txCount == 0 && mod.spiConfig.timeout == 1000);
        }
        {
            FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
            alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
            SX126x& radio = *new (storage) SX126x(&mod);
            hal.failPacketTypeRead = 1; hal.failurePayloadType = payloadType;
            assert(radio.startReceive() == RADIOLIB_ERR_SPI_CMD_FAILED);
            assert(hal.packetTypeReads == 1 && hal.rxCount == 0 && mod.spiConfig.timeout == 1000);
        }
        {
            FakeHal hal; Module mod(&hal, 1, 2, 3, 4); setup(mod);
            alignas(SX126x) unsigned char storage[sizeof(SX126x)] = {};
            SX126x& radio = *new (storage) SX126x(&mod);
            // First modem read succeeds. The second is inside fixSensitivity.
            hal.failPacketTypeRead = 2; hal.failurePayloadType = payloadType;
            const uint8_t payload[] = {0x11, 0x22};
            assert(radio.startTransmit(payload, sizeof(payload)) == RADIOLIB_ERR_SPI_CMD_FAILED);
            assert(hal.packetTypeReads == 2 && hal.txCount == 0 && mod.spiConfig.timeout == 1000);
        }
    }
}

int main() { stuckAtEntry(); standbyAlwaysReleasesCsOnErrors(); stuckAfterTxIsUncertain(); failedClearIrqNeverStartsRx(); healthyRxStarts(); queryFailureIsNotAValidEmptyRx(); checkedQueriesSeparateErrorsAndValues(); noFalseReceiveOnIrqOrLengthReadFailure(); packetTypeSpiErrorWithValidPayload(); }
'''


class AtexRadioBusyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not COMPILER.is_file():
            raise unittest.SkipTest("MinGW toolchain unavailable")
        cls.temp = tempfile.TemporaryDirectory(prefix="atex-radio-busy-")
        cls.directory = Path(cls.temp.name)
        cls.env = dict(os.environ)
        cls.env["PATH"] = str(COMPILER.parent) + os.pathsep + cls.env.get("PATH", "")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compile(self, *args):
        result = subprocess.run([str(COMPILER), *map(str, args)], cwd=ROOT, env=self.env,
                                capture_output=True, text=True)
        if result.returncode:
            self.fail(result.stderr or result.stdout)

    def test_real_driver_fault_injection(self):
        test = self.directory / "test.cpp"
        exe = self.directory / "test.exe"
        test.write_text(HARNESS, encoding="utf-8")
        for paranoid in (0, 1):
            with self.subTest(paranoid=paranoid):
                self.compile("-std=c++1z", "-static", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                             f"-DRADIOLIB_SPI_PARANOID={paranoid}", "-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1", "-DPGL_GLD_DATASET_WORKFLOW=1",
                             "-I" + str(LIB), test, SX, LIB / "Module.cpp", LIB / "Hal.cpp",
                             LIB / "protocols/PhysicalLayer/PhysicalLayer.cpp", LIB / "utils/Utils.cpp",
                             LIB / "utils/CRC.cpp", LIB / "utils/FEC.cpp",
                             LIB / "modules/SX126x/SX126x_LR_FHSS.cpp", "-o", exe)
                subprocess.run([str(exe)], cwd=ROOT, env=self.env, check=True, timeout=5)

    def test_non_atex_preprocessed_driver_matches_git_baseline(self):
        previous = subprocess.run(["git", "show", "HEAD:firmware/lib/RadioLib/src/modules/SX126x/SX126x.cpp"],
                                  cwd=ROOT, check=True, capture_output=True).stdout
        source = self.directory / "SX126x.cpp"
        source.write_bytes(previous)
        for flags in (("-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=0", "-DPGL_GLD_DATASET_WORKFLOW=1"),
                      ("-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1", "-DPGL_GLD_DATASET_WORKFLOW=0")):
            outputs = []
            for i, item in enumerate((source, SX)):
                out = self.directory / (str(i) + ".ii")
                self.compile("-std=c++1z", "-E", "-P", *flags,
                             "-I" + str(LIB / "modules/SX126x"), "-I" + str(LIB), item, "-o", out)
                outputs.append(out.read_bytes())
            self.assertEqual(outputs[0], outputs[1], flags)

    def test_non_atex_header_tokens_preserved(self):
        relative = "firmware/lib/RadioLib/src/modules/SX126x/SX126x.h"
        original = subprocess.run(["git", "show", "HEAD:" + relative], cwd=ROOT, check=True,
                                  capture_output=True, text=True).stdout
        current = (ROOT / relative).read_text(encoding="utf-8")
        result = []
        skipped = False
        for line in current.splitlines(keepends=True):
            if line.startswith("#if defined(PGL_GLD_BOARD_PROFILE_GLD_ATEX)"):
                self.assertFalse(skipped)
                skipped = True
            elif skipped and line.startswith("#endif"):
                skipped = False
            elif not skipped:
                result.append(line)
        self.assertFalse(skipped)
        self.assertEqual([line for line in original.splitlines() if line.strip()],
                         [line for line in "".join(result).splitlines() if line.strip()])


if __name__ == "__main__":
    unittest.main()
