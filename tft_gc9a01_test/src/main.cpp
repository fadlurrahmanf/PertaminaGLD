// Firmware tuner GC9A01 (LovyanGFX). Konfigurasi diubah lewat serial 115200, tanpa upload ulang.
// Perintah (satu baris):
//   CFG sclk mosi cs dc rst freq mode invert order     -> terapkan & gambar HALO
//        mode: 0/3   invert: 0/1   order: 0=RGB 1=BGR
//   PAT n    -> 0 = HALO, 1 = merah, 2 = hijau, 3 = biru, 4 = putih, 5 = batang warna
//   PING     -> balas PONG
#include <Arduino.h>
#include <esp_system.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>
#include "tester_monitor.h"

class LGFX : public lgfx::LGFX_Device {
public:
  lgfx::Panel_GC9A01 panel;
  lgfx::Bus_SPI bus;
  bool configured = false;

  bool apply(int sclk, int mosi, int cs, int dc, int rst, long freq, int mode, bool inv, bool bgr) {
    if (configured) bus.release();
    {
      auto c = bus.config();
      c.spi_host = VSPI_HOST;
      c.spi_mode = mode;
      c.freq_write = freq;
      c.freq_read = 0;
      c.spi_3wire = true;
      c.use_lock = true;
      c.dma_channel = SPI_DMA_CH_AUTO;
      c.pin_sclk = sclk;
      c.pin_mosi = mosi;
      c.pin_miso = -1;
      c.pin_dc = dc;
      bus.config(c);
      panel.setBus(&bus);
    }
    {
      auto c = panel.config();
      c.pin_cs = cs;
      c.pin_rst = rst;
      c.pin_busy = -1;
      c.panel_width = 240;
      c.panel_height = 240;
      c.offset_x = 0;
      c.offset_y = 0;
      c.readable = false;
      c.invert = inv;
      c.rgb_order = bgr;
      c.dlen_16bit = false;
      c.bus_shared = false;
      panel.config(c);
    }
    if (!configured) setPanel(&panel);
    configured = true;
    return init();
  }
};
LGFX lcd;
lgfx::LGFX_Sprite frame(&lcd);
bool calibration = false;
bool uiTester = false, uiRunning = false;
int uiSelected = 0, uiPage = 0;
bool uiDirty = true;
loratester::NowMessage uiStatus{};
bool uiLink = false;
bool uiSimulation = false, sessionInterrupted = false;
uint32_t simulationStarted = 0;
bool lastPdrValid = false, lastPdrReverseValid = false;
uint16_t lastPdr = 0, lastPdrReverse = 0;
int circleX = 123, circleY = 120, circleR = 116;

void pattern(int n) {
  if (!lcd.configured) return;
  const uint32_t col[] = {TFT_BLACK, TFT_RED, TFT_GREEN, TFT_BLUE, TFT_WHITE};
  if (n == 5) {
    const uint32_t b[] = {TFT_RED, TFT_GREEN, TFT_BLUE, TFT_WHITE, TFT_YELLOW, TFT_BLACK};
    for (int i = 0; i < 6; i++) lcd.fillRect(i * 40, 0, 40, 240, b[i]);
    return;
  }
  lcd.fillScreen(n == 0 ? TFT_BLACK : col[n]);
  if (n == 0) {
    lcd.setTextColor(TFT_WHITE, TFT_BLACK);
    lcd.setTextDatum(lgfx::middle_center);
    lcd.setTextSize(4);
    lcd.drawString("HALO", 120, 120);
  }
}

void setup() {
  pinMode(32, OUTPUT);
  digitalWrite(32, HIGH); // Backlight enable for the 8-pin TFT.
  pinMode(22, INPUT_PULLUP);
  Serial.begin(115200);
  delay(300);
  Serial.printf("reset reason = %d (1=POWERON, 9=BROWNOUT)\n", (int)esp_reset_reason());
  Serial.println("READY tuner");
  bool ok = lcd.apply(18, 23, 27, 26, 25, 10000000, 0, true, false);
  frame.setColorDepth(8);
  bool spriteOk = frame.createSprite(240, 240) != nullptr;
  Serial.printf("Sprite=%d free=%u\n", spriteOk, ESP.getFreeHeap());
  if (!spriteOk) Serial.println("Sprite allocation failed");
  Serial.printf("Boot display init=%d\n", ok);
  Serial.printf("ESP-NOW init=%d\n", monitorlink::begin());
}

void loop() {
  static int stable = HIGH, observed = HIGH;
  static unsigned long changed = 0, pressedAt = 0;
  static bool longHandled = false;
  int reading = digitalRead(22);
  if (reading != observed) { observed = reading; changed = millis(); }
  if (observed != stable && millis() - changed >= 30) {
    stable = observed;
    if (stable == LOW) { pressedAt = millis(); longHandled = false; }
    else if (!longHandled) {
      if (calibration) calibration = false;
      else if (!uiTester) uiSelected = (uiSelected + 1) % 2;
      else uiPage = (uiPage + 1) % 4;
      uiDirty = true;
    }
  }
  if (stable == LOW && !longHandled && millis() - pressedAt >= 800) {
    longHandled = true;
    if (calibration) calibration = false;
    else if (!uiTester) { if (uiSelected == 0) { uiTester = true; uiPage = 0; } }
    else if (uiPage == 3) { uiTester = false; uiSelected = 0; }
    else if (!uiRunning) { uiSimulation = false; sessionInterrupted=false; uiRunning = monitorlink::start(); }
    else if (!uiLink || uiStatus.state == 0) { monitorlink::cancelPending(); uiRunning = false; }
    else { monitorlink::stop(); }
    uiDirty = true;
  }
  monitorlink::poll();
  if (monitorlink::takeInterrupted()) { uiRunning=false; sessionInterrupted=true; lastPdrValid=false; lastPdrReverseValid=false; uiDirty=true; }
  static unsigned long uiUpdate = 0;
  static uint8_t previousState = 0;
  if (millis() - uiUpdate >= 500) {
    uiUpdate = millis();
    if (uiSimulation) {
      uint32_t elapsed = millis() - simulationStarted;
      uiLink = true; uiStatus.expected = 100;
      uiStatus.state = elapsed >= 20000 ? 3 : 2;
      uiStatus.phase = elapsed < 20000 ? 1 : 3;
      uiStatus.sentCh2 = uiStatus.sentCh1 = min(100UL, elapsed / 200UL);
      uiStatus.ageCh2Ms = uiStatus.ageCh1Ms = 0;
      auto &a = uiStatus.fromCh2; auto &b = uiStatus.fromCh1;
      a.available = 1; a.received = min(100UL, elapsed / 200UL); a.final = elapsed >= 20000;
      a.avgRssiDbm10=-820; a.minRssiDbm=-88; a.maxRssiDbm=-76; a.avgSnrDb10=85; a.minSnrDb=6; a.maxSnrDb=10;
      b.available = 1; b.received = min(100UL, elapsed / 200UL); b.final = elapsed >= 20000;
      b.avgRssiDbm10=-790; b.minRssiDbm=-85; b.maxRssiDbm=-72; b.avgSnrDb10=90; b.minSnrDb=7; b.maxSnrDb=11;
    } else uiLink = monitorlink::snapshot(uiStatus);
    if (!uiSimulation && uiLink && (uiStatus.state == 1 || uiStatus.state == 2 || uiStatus.state == 6)) {
      uiRunning = true; uiTester = true;
    }
    if (uiLink && uiStatus.state == 3 && previousState != 3) uiPage = 1;
    if (uiLink && (uiStatus.state == 3 || uiStatus.state == 4 || uiStatus.state == 5 || uiStatus.state == 7)) uiRunning = false;
    previousState = uiStatus.state;
    if (!uiSimulation && uiLink && uiStatus.state == 3 && uiStatus.fromCh2.available && uiStatus.fromCh2.final) {
      lastPdr = uiStatus.fromCh2.received; lastPdrValid = true;
    }
    if (!uiSimulation && uiLink && uiStatus.state == 3 && uiStatus.fromCh1.available && uiStatus.fromCh1.final) {
      lastPdrReverse = uiStatus.fromCh1.received; lastPdrReverseValid = true;
    }
    uiDirty = true;
  }
  if (uiDirty) {
    uiDirty = false;
    const uint16_t bg=0x0845, mint=0x07D3, muted=0xB5F6, white=0xFFFF, dim=0x318B, selected=0x2253;
    const uint16_t ch2Color=0x45FF, ch1Color=0xFD65;
    frame.fillSprite(bg);
    frame.drawCircle(circleX,circleY,circleR,dim);
    int ringPercent = !uiTester ? (lastPdrValid ? lastPdr : 0) : (!uiLink || uiStatus.sentCh1 > 100 || uiStatus.sentCh2 > 100 ? 0 : min(uiStatus.sentCh1, uiStatus.sentCh2));
    for (int n = 0; n < ringPercent; ++n) {
      float a = (n * 6.2831853f / 100.0f) - 1.5707963f;
      int px = circleX + static_cast<int>((circleR - 5) * cosf(a));
      int py = circleY + static_cast<int>((circleR - 5) * sinf(a));
      frame.fillCircle(px, py, 2, mint);
    }
    frame.setTextDatum(lgfx::middle_center);
    frame.setTextSize(1); frame.setTextColor(muted);
    frame.drawString(uiSimulation ? "SIMULASI" : "LORA TESTER",123,48);
    frame.setTextColor(uiLink ? mint : muted);
    frame.drawString(uiSimulation ? "CH1 SIMULASI" : uiLink ? "CH1 TERHUBUNG" : "CH1 BELUM TERHUBUNG",123,62);
    frame.drawFastHLine(72,72,102,dim);
    if (calibration) {
      frame.drawCircle(circleX,circleY,circleR,white);
      frame.drawFastHLine(circleX-8,circleY,17,static_cast<uint16_t>(TFT_RED));
      frame.drawFastVLine(circleX,circleY-8,17,static_cast<uint16_t>(TFT_RED));
    } else if (!uiTester) {
      frame.setTextColor(muted); frame.drawString("MENU UTAMA",123,85);
      frame.fillRoundRect(32,94,182,34,8,uiSelected==0?selected:bg);
      frame.fillRoundRect(32,132,182,34,8,uiSelected==1?selected:bg);
      frame.setTextColor(white); frame.setTextSize(2);
      frame.drawString("LoRa Tester",123,105);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Uji CH1 dan CH2",123,120);
      frame.setTextColor(white); frame.setTextSize(2); frame.drawString("Fitur lain",123,143);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Segera hadir",123,158);
      char homePdr[30];
      if (lastPdrValid && lastPdrReverseValid) snprintf(homePdr,sizeof(homePdr),"PDR 2>1 %u%%  1>2 %u%%",lastPdr,lastPdrReverse);
      else snprintf(homePdr,sizeof(homePdr),"PDR: BELUM ADA TES");
      frame.drawString(homePdr,123,172);
    } else if (uiPage == 3) {
      frame.setTextColor(white); frame.setTextSize(2); frame.drawString("KEMBALI",123,105);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Ke menu utama",123,126);
      frame.drawString(uiRunning ? "TES AKTIF" : "TES BERHENTI",123,148);
    } else {
      frame.setTextColor(uiLink?mint:muted);
      const char* stateText = !uiLink ? (uiRunning ? "MENUNGGU CH1" : "BELUM TERHUBUNG") : uiStatus.state == 1 ? "MEMULAI" : uiStatus.state == 2 ? "PENGUJIAN" : uiStatus.state == 3 ? "SELESAI" : uiStatus.state == 4 ? "TIMEOUT" : uiStatus.state == 5 ? "ERROR" : uiStatus.state == 6 ? "MENGHENTIKAN" : uiStatus.state == 7 ? "BERHENTI" : uiRunning ? "MENUNGGU DATA" : sessionInterrupted ? "TES TERPUTUS" : "SIAP";
      frame.drawString(stateText,123,84);
      frame.setTextColor(white); frame.setTextSize(1);
      const bool reverse = uiPage == 2;
      const loratester::DirectionStats &stats = reverse ? uiStatus.fromCh1 : uiStatus.fromCh2;
      if (uiPage == 0 && uiStatus.state != 3) {
        char row[40];
        frame.setTextColor(ch2Color); frame.drawString("CH2 -> CH1",123,103);
        if (uiStatus.fromCh2.available) snprintf(row,sizeof(row),"%u / 100%s",uiStatus.fromCh2.received,uiStatus.ageCh2Ms > 5000 ? " (LAMA)" : ""); else snprintf(row,sizeof(row),"MENUNGGU DATA");
        frame.setTextColor(white); frame.drawString(row,123,117);
        frame.setTextColor(ch1Color); frame.drawString("CH1 -> CH2",123,137);
        if (uiStatus.fromCh1.available) snprintf(row,sizeof(row),"%u / 100%s",uiStatus.fromCh1.received,uiStatus.ageCh1Ms > 5000 ? " (LAMA)" : ""); else snprintf(row,sizeof(row),"MENUNGGU DATA");
        frame.setTextColor(white); frame.drawString(row,123,151);
      } else {
      frame.setTextColor(reverse ? ch1Color : ch2Color);
      frame.drawString(reverse ? "CH1 -> CH2" : "CH2 -> CH1",123,101);
      frame.setTextColor(white);
      char row[44];
      if (uiLink && stats.available && stats.received) {
        snprintf(row,sizeof(row),"RSSI AVG %.1f dBm",stats.avgRssiDbm10 / 10.0f); frame.drawString(row,123,114);
        snprintf(row,sizeof(row),"MIN %d    MAX %d",stats.minRssiDbm,stats.maxRssiDbm); frame.drawString(row,123,125);
        snprintf(row,sizeof(row),"SNR AVG %.1f dB",stats.avgSnrDb10 / 10.0f); frame.drawString(row,123,136);
        snprintf(row,sizeof(row),"MIN %d    MAX %d",stats.minSnrDb,stats.maxSnrDb); frame.drawString(row,123,147);
        if (stats.final && uiStatus.state == 3) snprintf(row,sizeof(row),"PDR %u%% (%u/100)",stats.received,stats.received);
        else snprintf(row,sizeof(row),"PAKET %u / 100",stats.received);
      } else if (uiLink && stats.available && stats.final && uiStatus.state == 3) snprintf(row,sizeof(row),"PDR 0%% (0/100)");
      else snprintf(row,sizeof(row),"DATA BELUM ADA");
      frame.setTextColor(mint); frame.drawString(row,123,161);
      }
    }
    if (!calibration) {
      frame.drawFastHLine(83,177,80,dim); frame.setTextSize(1); frame.setTextColor(muted);
      frame.drawString(uiTester && uiLink && uiStatus.state == 3 && (uiPage == 1 || uiPage == 2) ? "TEKAN: ARAH LAIN" : "TEKAN: PILIH",123,184);
      frame.drawString(!uiTester || uiPage==3 ? "TAHAN: OK" : uiRunning?"TAHAN: STOP":"TAHAN: MULAI",123,195);
    }
    frame.pushSprite(0,0);
  }
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (line.length()) {
        line.trim();
        if (line == "SIM") {
          monitorlink::cancelPending(); memset(&uiStatus,0,sizeof(uiStatus));
          uiSimulation=true; simulationStarted=millis(); uiTester=true; uiPage=0; uiRunning=true; uiDirty=true;
          Serial.println("OK SIM");
        } else if (line == "SHORT") {
          if (calibration) calibration = false;
          else if (!uiTester) uiSelected = (uiSelected + 1) % 2;
          else uiPage = (uiPage + 1) % 4;
          uiDirty = true; Serial.println("OK SHORT");
        } else if (line == "LONG") {
          if (calibration) calibration = false;
          else if (!uiTester) { if (uiSelected == 0) { uiTester = true; uiPage = 0; } }
          else if (uiPage == 3) { uiTester = false; uiSelected = 0; }
          else if (!uiRunning) { uiSimulation = false; sessionInterrupted=false; uiRunning = monitorlink::start(); }
          else if (!uiLink || uiStatus.state == 0) { monitorlink::cancelPending(); uiRunning = false; }
          else { monitorlink::stop(); }
          uiDirty = true; Serial.println("OK LONG");
        } else if (line == "RESTART") { Serial.println("OK RESTART"); Serial.flush(); delay(50); ESP.restart();
        } else if (line == "STATUS") {
          loratester::NowMessage s{}; bool online = monitorlink::snapshot(s);
          uint8_t wifiChannel=0; wifi_second_chan_t secondary=WIFI_SECOND_CHAN_NONE;
          esp_wifi_get_channel(&wifiChannel, &secondary);
          Serial.printf("STATUS now=%d channel=%u online=%d running=%d state=%u received=%u expected=%u rssi=%d snr=%d tx_result=%d tx_cb=%u tx_ok=%u\n", monitorlink::ready, wifiChannel, online, uiRunning, s.state, s.received, s.expected, s.rssiDbm, s.snrDb, monitorlink::lastSendResult, (unsigned)monitorlink::txCallbacks, (unsigned)monitorlink::txDelivered);
          Serial.printf("SCREEN mode=%s page=%d sim=%d sim_state=%u phase=%u ch2_to_ch1=%u ch1_to_ch2=%u\n", uiTester?"tester":"menu", uiPage, uiSimulation, uiStatus.state, uiStatus.phase, uiStatus.fromCh2.received, uiStatus.fromCh1.received);
        } else if (line.startsWith("CIRCLE ")) {
          int x, y, r;
          if (sscanf(line.c_str(), "CIRCLE %d %d %d", &x, &y, &r) == 3 && x >= 0 && x <= 239 && y >= 0 && y <= 239 && r >= 1 && r <= 120) {
            circleX = x; circleY = y; circleR = r; calibration = true; uiDirty = true;
            Serial.printf("OK CIRCLE %d %d %d\n", x, y, r);
          } else Serial.println("ERR CIRCLE");
        } else if (line == "BUTTON") {
          calibration = false; uiDirty = true; Serial.println("OK BUTTON");
        } else if (line == "PING") {
          Serial.println("PONG");
        } else if (line.startsWith("CFG")) {
          int sclk, mosi, cs, dc, rst, mode, inv, order;
          long freq;
          int n = sscanf(line.c_str(), "CFG %d %d %d %d %d %ld %d %d %d", &sclk, &mosi, &cs, &dc, &rst, &freq, &mode, &inv, &order);
          if (n == 9) {
            bool ok = lcd.apply(sclk, mosi, cs, dc, rst, freq, mode, inv, order);
            pattern(0);
            Serial.printf("OK init=%d sclk=%d mosi=%d cs=%d dc=%d rst=%d freq=%ld mode=%d inv=%d bgr=%d\n",
                          ok, sclk, mosi, cs, dc, rst, freq, mode, inv, order);
          } else {
            Serial.printf("ERR parse n=%d\n", n);
          }
        } else if (line.startsWith("PAT")) {
          pattern(line.substring(3).toInt());
          Serial.println("OK pat");
        } else {
          Serial.println("ERR unknown");
        }
        line = "";
      }
    } else {
      line += ch;
    }
  }
}
