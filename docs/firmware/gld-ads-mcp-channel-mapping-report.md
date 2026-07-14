# GLD ADS1256 To TCA/MCP Channel Mapping Report

Tanggal: 2026-07-14
Scope: current firmware source evidence in `D:\PertaminaGLD`, live COM9
firmware-command sweep, and EasyEDA board artifact audit from
`docs/wiring/gld-project-ver2-2026-07-01`.

## Kesimpulan

Update setelah perbaikan firmware: board GLD di
`C:\Users\asus\Downloads\GLD_Project.zip`, schematic Ver3 repo, dan firmware
aktif sudah memakai mapping yang sama. `AIN0/ADS0` dikendalikan oleh
`TCA/MCP7`, `AIN1/ADS1` oleh `TCA/MCP6`, dan seterusnya mengikuti tabel board.

Report ini tetap membedakan dua lapisan:

- Firmware/source mapping: apa yang saat ini dilakukan firmware.
- Board/schematic mapping: apa yang ditunjukkan artefak hardware EasyEDA.

Keduanya sudah selaras untuk mapping ADS/TCA/MCP.

Dalam firmware aktif, korelasi nulling tidak boleh dibaca sebagai "ADS channel
selalu sama dengan MCP channel". Jalur firmware yang benar adalah:

```text
program/sensor channel -> ADS1256 input channel
program/sensor channel -> TCA9548A mux channel -> MCP4725 at address 0x60
```

Jadi angka yang menyatukan ADS dan MCP adalah `program/sensor channel`, bukan
nomor fisik ADS mentah.

Catatan istilah: MCP4725 adalah DAC 1-output. Yang disebut "TCA/MCP channel"
di report ini berarti channel TCA9548A yang dipilih untuk mengakses MCP4725
di cabang tersebut, semuanya memakai alamat MCP4725 `0x60`.

## Jawaban langsung menurut firmware aktif

| ADS1256 input | Program channel | Sensor | TCA/MCP mux channel yang mengendalikan nulling | ADS == TCA/MCP? |
|---:|---:|---|---:|---|
| 0 | 0 | MQ8 | 7 | Tidak, ADS0 dikendalikan lewat TCA/MCP7 |
| 1 | 1 | MQ135 | 6 | Tidak, ADS1 dikendalikan lewat TCA/MCP6 |
| 2 | 2 | MQ3 | 5 | Tidak, ADS2 dikendalikan lewat TCA/MCP5 |
| 3 | 3 | MQ5 | 0 | Tidak, ADS3 dikendalikan lewat TCA/MCP0 |
| 4 | 4 | MQ4 | 1 | Tidak, ADS4 dikendalikan lewat TCA/MCP1 |
| 5 | 5 | MQ7 | 2 | Tidak, ADS5 dikendalikan lewat TCA/MCP2 |
| 6 | 6 | MQ6 | 3 | Tidak, ADS6 dikendalikan lewat TCA/MCP3 |
| 7 | 7 | MQ2 | 4 | Tidak, ADS7 dikendalikan lewat TCA/MCP4 |

Ringkasnya menurut firmware aktif yang sudah diperbaiki: tidak ada ADS channel
yang angka fisiknya sama dengan TCA/MCP mux channel. Pengikatnya adalah
program channel/sensor.

## Jawaban langsung menurut board schematic

Audit schematic `GasLeakIntegratedVer2` dari ZIP baru dan
`SCH_GasLeakIntegratedVer3_2026-06-25.json` yang sudah ada di repo menunjukkan
mapping local analog-block yang sama:

| ADS1256 input label | Firmware mux saat ini | Board schematic mux | Status |
|---:|---:|---:|---|
| AIN0 | 7 | 7 | Match |
| AIN1 | 6 | 6 | Match |
| AIN2 | 5 | 5 | Match |
| AIN3 | 0 | 0 | Match |
| AIN4 | 1 | 1 | Match |
| AIN5 | 2 | 2 | Match |
| AIN6 | 3 | 3 | Match |
| AIN7 | 4 | 4 | Match |

Artinya: firmware aktif sekarang sudah mengikuti wiring board GLD.

## Bukti source

### 1. Tabel mapping firmware

`firmware/gld/include/BoardPins.h` mendefinisikan urutan sensor, alamat IC,
range DAC, dan dua tabel mapping utama:

```cpp
constexpr const char* SENSOR_NAMES[SENSOR_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};

constexpr uint8_t TCA9548A_ADDR = 0x71;
constexpr uint8_t MCP4725_ADDR = 0x60;
constexpr uint16_t GLD_DAC_CODE_MIN = 0;
constexpr uint16_t GLD_DAC_CODE_MAX = 4095;
constexpr uint8_t SENSOR_TO_MUX_CH[SENSOR_COUNT] = {7, 6, 5, 0, 1, 2, 3, 4};
constexpr uint8_t SENSOR_TO_ADS_CH[SENSOR_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7};
```

Makna langsungnya:

- ADS input masih identity: sensor/program channel 0..7 dibaca dari ADS input
  0..7.
- TCA/MCP mux mengikuti wiring board: sensor/program channel 0..7 memakai mux
  `{7, 6, 5, 0, 1, 2, 3, 4}`.

### 2. Jalur baca ADS

`firmware/gld/src/GldAds1256Reader.cpp` mengambil input ADS dari
`SENSOR_TO_ADS_CH[sensorChannel]`, lalu mengatur register MUX ADS1256 untuk
single-ended read:

```cpp
uint8_t adsInputForSensor(uint8_t sensorChannel) {
    return pgl::gld::board::SENSOR_TO_ADS_CH[sensorChannel];
}

long GldAds1256Reader::readSingleInternal(uint8_t channel) {
    ads_->setMUX(muxSingleEnded(adsInputForSensor(channel)));
    (void)ads_->readSingle();
    return ads_->readSingle();
}
```

Karena `SENSOR_TO_ADS_CH = {0,1,2,3,4,5,6,7}`, maka `readChannel(3)`
membaca ADS3, `readChannel(4)` membaca ADS4, dan seterusnya.

### 3. Jalur tulis DAC/nulling

`firmware/gld/src/GldDacMux.cpp` memakai `SENSOR_TO_MUX_CH[sensorChannel]`
untuk memilih channel TCA9548A, lalu menulis nilai DAC ke MCP4725 `0x60`:

```cpp
bool GldDacMux::writeDac(uint8_t sensorChannel, uint16_t value) {
    const uint8_t muxChannel = static_cast<uint8_t>(board::SENSOR_TO_MUX_CH[sensorChannel]);
    if (!selectMux(muxChannel)) {
        return false;
    }
    if (!writeRaw(value)) {
        return false;
    }
    lastValue_[sensorChannel] = value;
    return true;
}

bool GldDacMux::selectMux(uint8_t muxChannel) {
    return mux != nullptr && mux->selectChannel(muxChannel);
}

bool GldDacMux::writeRaw(uint16_t value) {
    i2c_->beginTransmission(board::MCP4725_ADDR);
    i2c_->write(MCP4725_DAC_REGISTER);
    i2c_->write(high);
    i2c_->write(low);
    return i2c_->endTransmission() == 0;
}
```

Maka `writeDac(3, value)` tidak memilih TCA3; ia memilih TCA0, karena
`SENSOR_TO_MUX_CH[3] = 0`.

### 4. Nulling mengikat read dan write pada program channel yang sama

`firmware/gld/src/GldNullingService.cpp` menjalankan nulling per `ch`, lalu
memakai channel yang sama untuk DAC write dan ADS read:

```cpp
if (!dac.writeDac(ch, 0)) {
    ...
}

for (uint16_t code = 0; code <= BASELINE_PRESCAN_MAX; ++code) {
    const bool writeOk = dac.writeDac(ch, code);
    settle(tickFn);
    const Snapshot s = readAverage(ads, ch, AVG_COUNT, tickFn);
    emitLog(logFn, "NULLING_BASELINE_STEP ch=%u sensor=%s code=%u voltage=%.6f valid=%u write=%u",
            ...);
}
```

Lalu semua 8 channel diproses berurutan:

```cpp
for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
    const ChannelResult cr = nullOneChannel(ads, dac, ch, logFn, tickFn, config);
    out.profile.dacCode[ch]   = cr.dacCode;
    out.profile.baselineV[ch] = cr.baselineV;
    out.profile.afterV[ch]    = cr.afterV;
    out.profile.channelOk[ch] = cr.success ? 1u : 0u;
}
```

Jadi bukti source-nya adalah: untuk `ch=3`, firmware menulis DAC lewat
TCA/MCP0 dan membaca ADS3. Untuk `ch=7`, firmware menulis DAC lewat TCA/MCP4
dan membaca ADS7.

## Tabel uji live 0 vs 4000

Live run post-fix dilakukan pada 2026-07-14 langsung melalui serial `COM9`
pada 115200 baud setelah firmware mapping direkonsiliasi ke schematic board.
Firmware melaporkan:

```text
firmwareName=PertaminaGLD-GLD
firmwareVersion=0.8.12
mode=inference
command=RUN_ADS_MCP_SWEEP
codeLow=0
codeHigh=4000
samples=5
settleMs=250
restore=profile
```

Semua baris live di bawah memiliki `st0=Ok`, `st4000=Ok`, `write0=1`,
`write4000=1`, dan `restoreOk=1`. Artinya DAC target berhasil dipaksa ke 0,
dibaca ADS-nya, lalu DAC target berhasil dipaksa ke 4000 dan dibaca lagi.

Boot check post-fix juga membuktikan semua cabang MCP sesuai mapping baru:
MQ8 mux7, MQ135 mux6, MQ3 mux5, MQ5 mux0, MQ4 mux1, MQ7 mux2, MQ6 mux3,
dan MQ2 mux4, semuanya `OK_TESTED`.

| ADS1256 input | Program channel | Sensor | TCA/MCP mux | V saat DAC=0 | V saat DAC=4000 | Delta V | Delta mV | Kesimpulan |
|---:|---:|---|---:|---:|---:|---:|---:|---|
| 0 | 0 | MQ8 | 7 | -0.000444872 | 0.483793736 | 0.484238595 | 484.238595 | ADS0/AIN0 berubah kuat saat TCA/MCP7 diubah |
| 1 | 1 | MQ135 | 6 | 0.000070115 | 0.483793736 | 0.483723611 | 483.723611 | ADS1/AIN1 berubah kuat saat TCA/MCP6 diubah |
| 2 | 2 | MQ3 | 5 | 0.000145153 | 0.469653904 | 0.469508737 | 469.508737 | ADS2/AIN2 berubah kuat saat TCA/MCP5 diubah |
| 3 | 3 | MQ5 | 0 | -0.000021648 | 0.481253326 | 0.481274962 | 481.274962 | ADS3/AIN3 berubah kuat saat TCA/MCP0 diubah |
| 4 | 4 | MQ4 | 1 | -0.000130590 | 0.481190771 | 0.481321365 | 481.321365 | ADS4/AIN4 berubah kuat saat TCA/MCP1 diubah |
| 5 | 5 | MQ7 | 2 | -0.000228977 | 0.469894648 | 0.470123619 | 470.123619 | ADS5/AIN5 berubah kuat saat TCA/MCP2 diubah |
| 6 | 6 | MQ6 | 3 | -0.000379302 | 0.483793736 | 0.484173030 | 484.173030 | ADS6/AIN6 berubah kuat saat TCA/MCP3 diubah |
| 7 | 7 | MQ2 | 4 | -0.000480302 | 0.483793736 | 0.484274030 | 484.274030 | ADS7/AIN7 berubah kuat saat TCA/MCP4 diubah |

Catatan interpretasi:

- Delta live post-fix besar dan konsisten, sekitar `469..484 mV`.
- Beberapa bacaan `DAC=4000` mencapai raw tinggi `8388607` dengan gain runtime
  turun ke `2`; ini menunjukkan sinyal naik kuat sampai dekat batas baca untuk
  konfigurasi gain saat itu.
- Bukti paling penting untuk mapping adalah kolom `Program channel` dan
  `TCA/MCP mux`: command firmware menulis DAC memakai program channel yang
  sama dengan channel ADS yang dibaca, dan program channel itu memilih mux
  sesuai `SENSOR_TO_MUX_CH`.
- Untuk uji isolasi tambahan, langkah berikutnya adalah negative-control:
  saat membaca satu ADS target, ubah mux/channel lain dan bandingkan apakah
  responnya tidak mengikuti pola direct nulling channel target.

## Final statement

Firmware source after wiring correction says:

```text
ADS0 -> TCA/MCP7
ADS1 -> TCA/MCP6
ADS2 -> TCA/MCP5
ADS3 -> TCA/MCP0
ADS4 -> TCA/MCP1
ADS5 -> TCA/MCP2
ADS6 -> TCA/MCP3
ADS7 -> TCA/MCP4
```

Board schematic artifacts say:

```text
AIN0 -> TCA/MCP7
AIN1 -> TCA/MCP6
AIN2 -> TCA/MCP5
AIN3 -> TCA/MCP0
AIN4 -> TCA/MCP1
AIN5 -> TCA/MCP2
AIN6 -> TCA/MCP3
AIN7 -> TCA/MCP4
```

Jadi pernyataan "ADS channel 0 dipengaruhi MCP channel 0" benar menurut
firmware pre-fix saja. Setelah correction, pernyataan yang benar untuk board
GLD adalah: `ADS0/AIN0` dikendalikan oleh `TCA/MCP7`.

Firmware mapping baru sudah di-upload ke GLD COM9 dan `RUN_ADS_MCP_SWEEP`
post-fix sudah mengisi tabel live di atas.
