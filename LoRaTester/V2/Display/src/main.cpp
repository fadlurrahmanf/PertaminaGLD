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
#include "UiTiming.h"
#include "SampleEvents.h"
#include "BatteryText.h"
#include "DebouncedButton.h"
#include "SampleAge.h"

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
bool uiSubmenu = false, uiRealtime = false;
int uiLoRaSelected = 0;
int uiSelected = 0, uiPage = 0;
bool uiDirty = true;
loratester::NowMessage uiStatus{};
uint32_t uiStatusReceivedAt=0;
bool uiStatusReceiptValid=false;
bool uiLink = false;
bool uiSimulation = false, sessionInterrupted = false, stopUnconfirmed = false, stopPending = false;
bool retryAfterUnknown = false;
uint32_t retryReadyAt = 0;
uint32_t stopRequestedAt = 0, stopLastAttempt = 0;
uint32_t shortFlashUntil = 0, longFlashUntil = 0;
uint32_t simulationStarted = 0;
uint32_t startAnimationAt = 0, packetFlashCh1 = 0, packetFlashCh2 = 0;
uint32_t resultAnimationAt = 0;
bool lastPdrValid = false, lastPdrReverseValid = false;
uint16_t lastPdr = 0, lastPdrReverse = 0;
int circleX = 123, circleY = 120, circleR = 116;
// Battery ADC is intentionally disabled until a safe divider, GPIO and
// calibrated transfer curve have been verified on the actual monitor.
#ifndef LT_DISPLAY_BATTERY_ENABLED
#define LT_DISPLAY_BATTERY_ENABLED 0
#endif
#ifndef LT_DISPLAY_BATTERY_DIVIDER_MILLI
#define LT_DISPLAY_BATTERY_DIVIDER_MILLI 2000
#endif
#ifndef LT_DISPLAY_BATTERY_OFFSET_MV
#define LT_DISPLAY_BATTERY_OFFSET_MV 0
#endif
constexpr bool kDisplayBatteryAdcEnabled = LT_DISPLAY_BATTERY_ENABLED != 0;
constexpr int kCandidateDisplayBatteryAdc1Gpio = 34;
int displayBatteryPercent = -1;
int displayBatteryAdcMv = -1, displayBatteryMv = -1;

void drawBatteryIcon(int x, int y, const char* label, int mv, int pct) {
  const uint16_t color = 0xB5F6;
  frame.setTextSize(1); frame.setTextColor(color);
  frame.drawString(label, x-13, y);
  frame.drawRect(x+1, y-4, 13, 8, color);
  frame.fillRect(x+14, y-2, 2, 4, color);
  if (pct > 0) frame.fillRect(x+3, y-2, (pct*9+50)/100, 4, color);
  const auto text=formatBattery(pct>=0,mv,pct);
  frame.drawString(text.percent,x+27,y);
  frame.drawString(text.voltage,x+6,y+12);
}
void chooseLoRaMode() {
  if (uiLoRaSelected == 2) { uiSubmenu=false; uiSelected=0; return; }
  if (!uiRunning) {
    if (!uiSimulation) monitorlink::rediscoverStaleCh2(uiRunning,stopPending,stopUnconfirmed,retryAfterUnknown && static_cast<int32_t>(millis()-retryReadyAt)<0);
    if (!uiSimulation && !stopPending && !stopUnconfirmed && (!retryAfterUnknown || static_cast<int32_t>(millis()-retryReadyAt)>=0)) monitorlink::rediscoverOfflineIdle();
    uiRealtime=uiLoRaSelected==1; monitorlink::forgetSession(); memset(&uiStatus,0,sizeof(uiStatus));
  }
  uiSubmenu=false; uiTester=true; uiPage=0;
}

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
#if LT_DISPLAY_BATTERY_ENABLED
  analogSetPinAttenuation(kCandidateDisplayBatteryAdc1Gpio, ADC_11db);
#endif
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
  static DebouncedButton button;
  const DebouncedButton::Event buttonEvent=button.update(digitalRead(22)==LOW,millis());
  const int stable=button.pressed()?LOW:HIGH;
  const bool longHandled=button.longHandled();
  const uint32_t pressedAt=button.pressedAt();
  if (buttonEvent==DebouncedButton::Event::Short) {
      shortFlashUntil = millis() + 700;
      if (calibration) calibration = false;
      else if (uiSubmenu) uiLoRaSelected = (uiLoRaSelected + 1) % 3;
      else if (!uiTester) uiSelected = (uiSelected + 1) % 2;
      else if (uiRealtime) uiPage = uiPage == 3 ? 0 : 3;
      else uiPage = (uiPage + 1) % 5;
      uiDirty = true;
  }
  if (buttonEvent==DebouncedButton::Event::Long) {
    longFlashUntil = millis() + 700;
    if (calibration) calibration = false;
    else if (uiSubmenu) { chooseLoRaMode(); }
    else if (!uiTester) { if (uiSelected == 0) { uiSubmenu = true; uiLoRaSelected = 0; } }
    else if (uiPage == 3) { uiTester = false; uiSubmenu=true; }
    else if (!uiRunning && !stopPending && (!retryAfterUnknown || static_cast<int32_t>(millis()-retryReadyAt)>=0) && (!stopUnconfirmed || retryAfterUnknown)) { uiSimulation = false; sessionInterrupted=false; stopPending=false; stopUnconfirmed=false; retryAfterUnknown=false; uiRunning = monitorlink::start(uiRealtime); if (uiRunning) startAnimationAt=millis(); }
    else if (uiRunning) { retryAfterUnknown=false; monitorlink::stopStartRetries(); monitorlink::stop(); stopPending=true; stopRequestedAt=stopLastAttempt=millis(); }
    uiDirty = true;
  }
  monitorlink::poll();
#if LT_DISPLAY_BATTERY_ENABLED
  static uint32_t batteryAt=0;
  if (!batteryAt || millis()-batteryAt>=5000) {
    batteryAt=millis();
    // GPIO34 is behind an equal 100k/100k divider. The result is only a
    // voltage-based estimate; calibration and wiring must first be verified.
    displayBatteryAdcMv=analogReadMilliVolts(kCandidateDisplayBatteryAdc1Gpio);
    const int mv=displayBatteryAdcMv*LT_DISPLAY_BATTERY_DIVIDER_MILLI/1000+LT_DISPLAY_BATTERY_OFFSET_MV;
    displayBatteryMv=(mv>=2800 && mv<=4500) ? mv : -1;
    displayBatteryPercent=displayBatteryMv>=0 ? constrain((mv-3300)*100/900,0,100) : -1;
  }
#endif
  if (stopPending && millis()-stopLastAttempt >= 2000) { monitorlink::stop(); stopLastAttempt=millis(); }
  if (stopPending && millis()-stopRequestedAt >= 10000) { stopPending=false; stopUnconfirmed=true; uiDirty=true; }
  if (monitorlink::takeInterrupted()) { uiRunning=false; sessionInterrupted=true; stopPending=false; stopUnconfirmed=true; retryAfterUnknown=true; retryReadyAt=millis()+14000; lastPdrValid=false; lastPdrReverseValid=false; uiDirty=true; }
  static unsigned long uiUpdate = 0;
  static uint8_t previousState = 0;
  static uint32_t previousReport = 0, previousSession = 0;
  static SampleEvents sampleEvents;
  static PdrPacketEvents pdrEvents;
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
      a.avgRssiDbm10=-820; a.minRssiDbm=-88; a.maxRssiDbm=-76; a.avgSnrDb10=85; a.minSnrDb10=60; a.maxSnrDb10=100;
      a.latestRssiDbm=-82; a.latestSnrDb10=85;
      b.available = 1; b.received = min(100UL, elapsed / 200UL); b.final = elapsed >= 20000;
      b.avgRssiDbm10=-790; b.minRssiDbm=-85; b.maxRssiDbm=-72; b.avgSnrDb10=90; b.minSnrDb10=70; b.maxSnrDb10=110;
      b.latestRssiDbm=-79; b.latestSnrDb10=90;
    } else uiLink = monitorlink::snapshot(uiStatus,&uiStatusReceivedAt,&uiStatusReceiptValid);
    if (uiStatus.session && uiStatus.session!=previousSession) { previousSession=uiStatus.session; previousReport=0; }
    if (!uiSimulation && uiLink && uiStatus.state==2 && uiStatus.reportSeq!=previousReport) {
      if (uiStatus.phase==5) {
        const uint8_t changes=sampleEvents.update(uiStatus.session,uiStatus.sampleSeqValid,uiStatus.sampleSeqFromCh2,uiStatus.sampleSeqFromCh1);
        if (changes&1) packetFlashCh2=millis(); if (changes&2) packetFlashCh1=millis();
      } else {
        const uint8_t changes=pdrEvents.update(uiStatus.session,uiStatus.fromCh2.received,uiStatus.fromCh1.received);
        if (changes&1) packetFlashCh2=millis(); if (changes&2) packetFlashCh1=millis();
      }
      previousReport=uiStatus.reportSeq;
    }
    if (!uiSimulation && uiStatus.session && !uiRunning && !uiTester && !uiSubmenu) uiRealtime = uiStatus.phase == 5;
    if (!uiSimulation && uiLink && (uiStatus.state == 1 || uiStatus.state == 2 || uiStatus.state == 6)) {
      if (!uiRunning) { uiTester = true; uiSubmenu=false; }
      uiRealtime = uiStatus.phase == 5;
      if (!stopPending && !stopUnconfirmed) retryAfterUnknown=false;
      uiRunning = true;
    }
    if (uiLink && uiStatus.state == 3 && previousState != 3) { uiPage = 4; resultAnimationAt=millis(); }
    if (uiLink && (uiStatus.state == 3 || uiStatus.state == 4 || uiStatus.state == 5 || uiStatus.state == 7)) uiRunning = false;
    if (uiLink && (uiStatus.state == 7 || uiStatus.state == 3)) { stopPending=false; stopUnconfirmed=false; retryAfterUnknown=false; }
    if (!retryAfterUnknown && uiLink && (uiStatus.state == 4 || uiStatus.state == 5)) { retryAfterUnknown=true; retryReadyAt=millis()+14000; }
    previousState = uiStatus.state;
    if (!uiSimulation && uiLink && uiStatus.state == 3 && uiStatus.fromCh2.available && uiStatus.fromCh2.final) {
      lastPdr = uiStatus.fromCh2.received; lastPdrValid = true;
    }
    if (!uiSimulation && uiLink && uiStatus.state == 3 && uiStatus.fromCh1.available && uiStatus.fromCh1.final) {
      lastPdrReverse = uiStatus.fromCh1.received; lastPdrReverseValid = true;
    }
    uiDirty = true;
  }
  static uint32_t animationAt = 0, sceneStarted = 0;
  static int previousScene = -1;
  int scene = calibration ? 100 : (uiSubmenu ? 200+uiLoRaSelected : !uiTester ? uiSelected : 10 + uiPage * 10 + min((int)uiStatus.state, 7));
  if (scene != previousScene) { previousScene = scene; sceneStarted = millis(); uiDirty = true; }
  // During a hold, avoid repeated full 240x240 SPI transfers; update just
  // the progress strip below. Normal scenes continue to redraw as needed.
  if (!calibration && (stable!=LOW || longHandled) && millis() - animationAt >= 40) { animationAt = millis(); uiDirty = true; }
  if (uiDirty) {
    uiDirty = false;
    const uint16_t bg=0x0000, mint=0x4DFB, muted=0xB5F6, white=0xFFFF, dim=0x49D3, selected=0x2253;
    const uint16_t ch2Color=0x5DFF, ch1Color=0xFD47, header=0x5DFF, warning=0xFD20, success=0x57EC;
    const auto health=monitorlink::healthSnapshot();
    const uint16_t effectiveAgeCh2=uiSimulation ? 0 : sampleage::effective(uiStatus.ageCh2Ms,uiStatusReceivedAt,millis(),uiStatusReceiptValid);
    const uint16_t effectiveAgeCh1=uiSimulation ? 0 : sampleage::effective(uiStatus.ageCh1Ms,uiStatusReceivedAt,millis(),uiStatusReceiptValid);
    const auto batteryPct=[](bool fresh,const loratester::NodeHealth &h) -> int {
      return fresh && (h.flags & loratester::kHealthBatteryValid) && h.batteryPct<=100 ? h.batteryPct : -1;
    };
    frame.fillSprite(bg);
    frame.drawCircle(circleX,circleY,circleR,dim);
    int ringPercent = !uiTester ? 0 : (!uiLink || uiStatus.sentCh1 > 100 || uiStatus.sentCh2 > 100 ? 0 : min(uiStatus.sentCh1, uiStatus.sentCh2));
    if (uiTester && uiRealtime && uiStatus.state == 2 && uiStatus.fromCh2.received && effectiveAgeCh2 != sampleage::kUnknown) {
      uint32_t age = effectiveAgeCh2;
      ringPercent = min(100UL, age*100UL/2000UL);
    }
    for (int n = 0; n < ringPercent; ++n) {
      float a = (n * 6.2831853f / 100.0f) - 1.5707963f;
      int px = circleX + static_cast<int>((circleR - 5) * cosf(a));
      int py = circleY + static_cast<int>((circleR - 5) * sinf(a));
      int flash = ringPercent ? (millis()/24) % ringPercent : 0;
      bool highlight = n >= flash && n < flash + 3;
      frame.fillCircle(px, py, 2, highlight ? static_cast<uint16_t>(0xA6FF) : ch2Color);
    }
    frame.setTextDatum(lgfx::middle_center);
    frame.setTextSize(1); frame.setTextColor(uiTester && !uiRealtime && !uiSimulation ? white : header);
    frame.drawString(uiSimulation ? "SIMULASI" : uiTester ? (uiRealtime ? "REALTIME TEST" : "PDR TEST") : uiSubmenu ? "LORA TESTER" : "DEVICE TESTER",123,48);
    frame.setTextColor(uiLink ? success : warning);
    if (uiTester || uiSubmenu) {
      drawBatteryIcon(91,56,"CH1",health.ch1.batteryMv,batteryPct(health.ch1Fresh,health.ch1));
      drawBatteryIcon(164,56,"CH2",health.ch2.batteryMv,batteryPct(health.ch2Fresh,health.ch2));
    }
    int entryWidth = min(102UL, (millis() - sceneStarted) * 102UL / 400UL);
    frame.drawFastHLine(123-entryWidth/2,75,entryWidth,dim);
    if (calibration) {
      frame.drawCircle(circleX,circleY,circleR,white);
      frame.drawFastHLine(circleX-8,circleY,17,static_cast<uint16_t>(TFT_RED));
      frame.drawFastVLine(circleX,circleY-8,17,static_cast<uint16_t>(TFT_RED));
    } else if (uiSubmenu) {
      static float submenuMarkerY=93;
      const float submenuTarget = uiLoRaSelected==0 ? 93 : uiLoRaSelected==1 ? 123 : 153;
      submenuMarkerY+=(submenuTarget-submenuMarkerY)*0.32f;
      frame.drawRoundRect(34,76,88,15,3,dim); frame.drawRoundRect(125,76,88,15,3,dim);
      frame.setTextColor(health.ch1Fresh ? ((health.ch1.flags & loratester::kHealthRadioReady)?success:warning) : muted);
      frame.drawString(!health.ch1Fresh ? ((millis()/400)%2 ? "CH1 UNKNOWN." : "CH1 UNKNOWN") : (health.ch1.flags & loratester::kHealthRadioReady) ? "CH1 READY v" : "CH1 NOT READY",78,83);
      frame.setTextColor(health.ch2Fresh ? ((health.ch2.flags & loratester::kHealthRadioReady)?success:warning) : muted);
      frame.drawString(health.conflict ? "CH2 CONFLICT" : !health.ch2Fresh ? ((millis()/400)%2 ? "CH2 UNKNOWN." : "CH2 UNKNOWN") : (health.ch2.flags & loratester::kHealthRadioReady) ? "CH2 READY v" : "CH2 NOT READY",168,83);
      frame.drawRoundRect(34,93,178,26,7,dim); frame.drawRoundRect(34,123,178,26,7,dim); frame.drawRoundRect(44,153,158,20,7,dim);
      frame.drawRoundRect(35,int(submenuMarkerY),176,uiLoRaSelected==2?20:26,7,ch2Color);
      frame.fillRect(46,105,3,7,ch2Color); frame.fillRect(51,101,3,11,ch2Color); frame.fillRect(56,97,3,15,ch2Color);
      frame.drawLine(45,138,49,138,ch1Color); frame.drawLine(49,138,52,132,ch1Color); frame.drawLine(52,132,55,141,ch1Color); frame.drawLine(55,141,59,135,ch1Color);
      frame.setTextColor(white); frame.setTextSize(2);
      frame.drawString("PDR Test",123,106); frame.setTextSize(1); frame.drawString("Realtime Test",128,136);
      frame.setTextSize(1); frame.drawString("Kembali",123,163);
    } else if (!uiTester) {
      static float menuMarkerY=94;
      menuMarkerY+=((uiSelected==0?94.0f:132.0f)-menuMarkerY)*0.32f;
      frame.setTextColor(muted); frame.drawString("MENU UTAMA",123,85);
      frame.drawRoundRect(32,94,182,34,8,dim); frame.drawRoundRect(32,132,182,34,8,dim);
      frame.drawRoundRect(33,int(menuMarkerY),180,34,8,ch2Color);
      frame.setTextColor(white); frame.setTextSize(2);
      frame.drawString("LoRa Tester",123,105);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Uji CH1 dan CH2",123,120);
      frame.setTextColor(white); frame.setTextSize(2); frame.drawString("Fitur lain",123,143);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Segera hadir",123,158);
      const auto monBattery=formatBattery(displayBatteryPercent>=0,displayBatteryMv,displayBatteryPercent);
      char batteryText[32]; snprintf(batteryText,sizeof(batteryText),"MON %s %s",monBattery.voltage,monBattery.percent);
      frame.drawString(batteryText,123,170);
    } else if (uiPage == 3) {
      frame.setTextColor(white); frame.setTextSize(2); frame.drawString("KEMBALI",123,105);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Ke menu utama",123,126);
      frame.drawString(uiRunning ? "TES AKTIF" : "TES BERHENTI",123,148);
    } else if (uiPage == 4) {
      frame.setTextColor(header); frame.drawString("RINGKASAN DUA ARAH",123,84);
      char row[48];
      auto showSummary = [&](const loratester::DirectionStats &s, int x, uint16_t color, const char *name) {
        frame.setTextSize(1); frame.setTextColor(color); frame.drawString(name,x,100);
        frame.setTextSize(2); frame.setTextColor(resultAnimationAt && millis()-resultAnimationAt<1000 && (millis()/140)%2 ? color : white);
        if (uiStatus.state==3 && s.available && s.final) snprintf(row,sizeof(row),"%u%%",s.received);
        else snprintf(row,sizeof(row),"--");
        frame.drawString(row,x,116); frame.setTextSize(1);
      };
      showSummary(uiStatus.fromCh2,78,ch2Color,"CH2 > CH1");
      showSummary(uiStatus.fromCh1,168,ch1Color,"CH1 > CH2");
      auto stability = [&](const loratester::DirectionStats &s) -> const char* {
        if (uiStatus.state!=3 || !s.available || !s.final || s.received<10) return "DATA KURANG";
        return (s.maxRssiDbm-s.minRssiDbm<=6 && s.maxSnrDb10-s.minSnrDb10<=30) ? "STABIL" : "BERFLUKTUASI";
      };
      frame.setTextColor(ch2Color); snprintf(row,sizeof(row),"2>1 %s",stability(uiStatus.fromCh2)); frame.drawString(row,123,149);
      frame.setTextColor(ch1Color); snprintf(row,sizeof(row),"1>2 %s",stability(uiStatus.fromCh1)); frame.drawString(row,123,162);
      frame.setTextColor(muted); frame.drawString("R 6dB / S 3dB",123,172);
    } else {
      frame.setTextColor((stopUnconfirmed || uiStatus.state==4 || uiStatus.state==5)?warning:uiLink?success:muted);
      const char* stateText = retryAfterUnknown && !uiRunning && static_cast<int32_t>(millis()-retryReadyAt)<0 ? "TUNGGU CH2" : stopUnconfirmed ? "STOP BELUM PASTI" : stopPending ? "STOP DIPROSES" : !uiLink ? (uiRunning ? "MENUNGGU CH1" : "BELUM TERHUBUNG") : uiStatus.state == 1 ? "MEMULAI" : uiStatus.state == 2 ? "PENGUJIAN" : uiStatus.state == 3 ? "SELESAI" : uiStatus.state == 4 ? "TIMEOUT" : uiStatus.state == 5 ? "ERROR" : uiStatus.state == 6 ? "MENGHENTIKAN" : uiStatus.state == 7 ? "BERHENTI" : uiRunning ? "MENUNGGU DATA" : sessionInterrupted ? "TES TERPUTUS" : "SIAP";
      if (uiStatus.state==1 && !stopPending && !stopUnconfirmed) {
        char starting[24]; const int dots=(millis()/350)%4;
        snprintf(starting,sizeof(starting),"MEMULAI%.*s",dots,"..."); frame.drawString(starting,123,84);
      } else frame.drawString(stateText,123,84);
      frame.setTextColor(white); frame.setTextSize(1);
      const bool reverse = uiPage == 2;
      const loratester::DirectionStats &stats = reverse ? uiStatus.fromCh1 : uiStatus.fromCh2;
      if (uiRealtime && uiPage == 0) {
        char row[24]; frame.setTextColor(ch2Color); frame.drawString(millis()-packetFlashCh2<400 && packetFlashCh2 ? "CH2 >> CH1" : "CH2 > CH1",123,99);
        frame.setTextColor(white); frame.setTextSize(2);
        if (uiStatus.fromCh2.received) snprintf(row,sizeof(row),"%4d %5.1f%s",uiStatus.fromCh2.latestRssiDbm,uiStatus.fromCh2.latestSnrDb10/10.0f,effectiveAgeCh2==sampleage::kUnknown?"?":effectiveAgeCh2>5000?"*":""); else snprintf(row,sizeof(row)," --   --");
        const int offset2=packetFlashCh2 && millis()-packetFlashCh2<250 ? (250-(millis()-packetFlashCh2))/125 : 0;
        frame.drawString(row,123,115-offset2); frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("RSSI dBm          SNR dB",123,127);
        frame.setTextColor(ch1Color); frame.drawString(millis()-packetFlashCh1<400 && packetFlashCh1 ? "CH1 >> CH2" : "CH1 > CH2",123,143);
        frame.setTextColor(white); frame.setTextSize(2);
        if (uiStatus.fromCh1.received) snprintf(row,sizeof(row),"%4d %5.1f%s",uiStatus.fromCh1.latestRssiDbm,uiStatus.fromCh1.latestSnrDb10/10.0f,effectiveAgeCh1==sampleage::kUnknown?"?":effectiveAgeCh1>5000?"*":""); else snprintf(row,sizeof(row)," --   --");
        const int offset1=packetFlashCh1 && millis()-packetFlashCh1<250 ? (250-(millis()-packetFlashCh1))/125 : 0;
        frame.drawString(row,123,158-offset1); frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("RSSI dBm          SNR dB",123,170);
      } else if (uiPage == 0 && uiStatus.state != 3) {
        char row[40];
        frame.setTextColor(ch2Color); frame.drawString(millis()-packetFlashCh2<400 && packetFlashCh2 ? "CH2 >> CH1" : "CH2 > CH1",123,98);
        if (uiStatus.fromCh2.available) snprintf(row,sizeof(row),"%u / 100%s",uiStatus.fromCh2.received,effectiveAgeCh2==sampleage::kUnknown?" (?)":effectiveAgeCh2>5000?" (LAMA)":""); else snprintf(row,sizeof(row),"MENUNGGU DATA");
        frame.setTextColor(white); frame.drawString(row,123,109);
        if (uiStatus.fromCh2.received) snprintf(row,sizeof(row),"R %d dBm  S %.1f dB",uiStatus.fromCh2.latestRssiDbm,uiStatus.fromCh2.latestSnrDb10 / 10.0f); else snprintf(row,sizeof(row),"R -- dBm  S -- dB");
        frame.drawString(row,123,120);
        frame.setTextColor(ch1Color); frame.drawString(millis()-packetFlashCh1<400 && packetFlashCh1 ? "CH1 >> CH2" : "CH1 > CH2",123,137);
        if (uiStatus.fromCh1.available) snprintf(row,sizeof(row),"%u / 100%s",uiStatus.fromCh1.received,effectiveAgeCh1==sampleage::kUnknown?" (?)":effectiveAgeCh1>5000?" (LAMA)":""); else snprintf(row,sizeof(row),"MENUNGGU DATA");
        frame.setTextColor(white); frame.drawString(row,123,151);
        if (uiStatus.fromCh1.received) snprintf(row,sizeof(row),"R %d dBm  S %.1f dB",uiStatus.fromCh1.latestRssiDbm,uiStatus.fromCh1.latestSnrDb10 / 10.0f); else snprintf(row,sizeof(row),"R -- dBm  S -- dB");
        frame.drawString(row,123,162);
      } else {
      frame.setTextColor(reverse ? ch1Color : ch2Color);
      frame.drawString(reverse ? "CH1 -> CH2" : "CH2 -> CH1",123,101);
      frame.setTextColor(white);
      char row[44];
      if (uiLink && stats.available && stats.received) {
        snprintf(row,sizeof(row),"RSSI AVG %.1f dBm",stats.avgRssiDbm10 / 10.0f); frame.drawString(row,123,114);
        snprintf(row,sizeof(row),"MIN %d    MAX %d",stats.minRssiDbm,stats.maxRssiDbm); frame.drawString(row,123,125);
        snprintf(row,sizeof(row),"SNR AVG %.1f dB",stats.avgSnrDb10 / 10.0f); frame.drawString(row,123,136);
        snprintf(row,sizeof(row),"MIN %.1f  MAX %.1f",stats.minSnrDb10 / 10.0f,stats.maxSnrDb10 / 10.0f); frame.drawString(row,123,147);
        if (stats.final && uiStatus.state == 3) snprintf(row,sizeof(row),"PDR %u%% (%u/100)",stats.received,stats.received);
        else snprintf(row,sizeof(row),"PAKET %u / 100",stats.received);
      } else if (uiLink && stats.available && stats.final && uiStatus.state == 3) snprintf(row,sizeof(row),"PDR 0%% (0/100)");
      else snprintf(row,sizeof(row),"DATA BELUM ADA");
      frame.setTextColor(mint); frame.drawString(row,123,161);
      }
    }
    if (!calibration) {
      frame.drawFastHLine(83,177,80,dim); frame.setTextSize(1); frame.setTextColor(muted);
      bool blinkOn = ((millis() / 100) % 2) == 0;
      bool shortFlash = static_cast<int32_t>(shortFlashUntil - millis()) > 0;
      bool longFlash = static_cast<int32_t>(longFlashUntil - millis()) > 0 || (stable == LOW && longHandled);
      frame.setTextColor(shortFlash && blinkOn ? white : muted);
      frame.drawString(uiTester && uiLink && uiStatus.state == 3 && (uiPage == 1 || uiPage == 2) ? "TEKAN: ARAH LAIN" : "TEKAN: PILIH",123,184);
      frame.setTextColor(longFlash && blinkOn ? white : muted);
      frame.drawString(!uiTester || uiPage==3 ? "TAHAN: OK" : uiRunning?"TAHAN: STOP":"TAHAN: MULAI",123,195);
      if (stable==LOW && !longHandled) {
        const uint32_t held=millis()-pressedAt;
        const int amount=uitiming::holdBarPixels(held);
        frame.drawRoundRect(91,201,64,5,2,dim);
        if (amount>0) frame.fillRoundRect(92,202,amount,3,1,ch2Color);
        frame.drawFastVLine(123,200,7,white);
      }
    }
    if (startAnimationAt && millis()-startAnimationAt<1500 && uiTester && !uiRealtime && uiPage==0 && !calibration) {
      frame.fillSprite(bg); frame.drawCircle(circleX,circleY,circleR,dim);
      frame.setTextDatum(lgfx::middle_center); frame.setTextSize(2); frame.setTextColor(white);
      frame.drawString("CH1",72,120); frame.drawString("CH2",174,120);
      frame.drawFastHLine(96,120,54,dim);
      frame.drawLine(96,120,101,116,dim); frame.drawLine(96,120,101,124,dim);
      frame.drawLine(149,120,144,116,dim); frame.drawLine(149,120,144,124,dim);
      const uint32_t phase=(millis()-startAnimationAt)%1000;
      const int dx=phase<500 ? phase*48/500 : (1000-phase)*48/500;
      frame.fillCircle(99+dx,120,3,phase<500?ch2Color:ch1Color);
    } else if (millis() < 3000 && !calibration) {
      frame.fillSprite(bg);
      int introProgress = min(100UL, millis()*100UL/2600UL);
      for (int n=0; n<introProgress; ++n) {
        float a=(n*6.2831853f/100.0f)-1.5707963f;
        frame.fillCircle(circleX+static_cast<int>((circleR-13)*cosf(a)),circleY+static_cast<int>((circleR-13)*sinf(a)),2,ch2Color);
      }
      frame.setTextDatum(lgfx::middle_center); frame.setTextColor(header); frame.setTextSize(2);
      frame.drawString("DEVICE",123,107); frame.drawString("TESTER",123,132);
      frame.setTextSize(1); frame.setTextColor(muted); frame.drawString("Menyiapkan perangkat",123,153);
    }
    frame.pushSprite(0,0);
  }
  static uint32_t holdPaintAt=0;
  if (!calibration && stable==LOW && !longHandled && millis()-holdPaintAt>=12) {
    holdPaintAt=millis();
    const uint32_t held=millis()-pressedAt;
    const int amount=uitiming::holdBarPixels(held);
    lcd.drawRoundRect(91,201,64,5,2,0x49D3);
    lcd.fillRect(92,202,62,3,0x0000);
    if (amount>0) lcd.fillRect(92,202,amount,3,0x5DFF);
    lcd.drawFastVLine(123,200,7,0xFFFF);
  }
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (line.length()) {
        line.trim();
        if (line == "SIM") {
          if (!monitorlink::simulationAllowed(uiRunning,stopPending,stopUnconfirmed)) Serial.println("ERR SIM TEST ACTIVE OR UNCERTAIN");
          else {
            monitorlink::cancelPending(); memset(&uiStatus,0,sizeof(uiStatus));
            uiSimulation=true; uiSubmenu=false; uiRealtime=false; simulationStarted=millis(); uiTester=true; uiPage=0; uiRunning=true; uiDirty=true;
            Serial.println("OK SIM");
          }
        } else if (line == "SHORT") {
          shortFlashUntil = millis() + 700;
          if (calibration) calibration = false;
          else if (uiSubmenu) uiLoRaSelected = (uiLoRaSelected + 1) % 3;
          else if (!uiTester) uiSelected = (uiSelected + 1) % 2;
          else if (uiRealtime) uiPage = uiPage == 3 ? 0 : 3;
          else uiPage = (uiPage + 1) % 5;
          uiDirty = true; Serial.println("OK SHORT");
        } else if (line == "LONG") {
          longFlashUntil = millis() + 700;
          if (calibration) calibration = false;
          else if (uiSubmenu) { chooseLoRaMode(); }
          else if (!uiTester) { if (uiSelected == 0) { uiSubmenu=true; uiLoRaSelected=0; } }
          else if (uiPage == 3) { uiTester = false; uiSubmenu=true; }
          else if (!uiRunning && !stopPending && (!retryAfterUnknown || static_cast<int32_t>(millis()-retryReadyAt)>=0) && (!stopUnconfirmed || retryAfterUnknown)) { uiSimulation = false; sessionInterrupted=false; stopPending=false; stopUnconfirmed=false; retryAfterUnknown=false; uiRunning = monitorlink::start(uiRealtime); if (uiRunning) startAnimationAt=millis(); }
          else if (uiRunning) { retryAfterUnknown=false; monitorlink::stopStartRetries(); monitorlink::stop(); stopPending=true; stopRequestedAt=stopLastAttempt=millis(); }
          uiDirty = true; Serial.println("OK LONG");
        } else if (line == "RESTART") { Serial.println("OK RESTART"); Serial.flush(); delay(50); ESP.restart();
        } else if (line == "STATUS") {
          loratester::NowMessage s{}; bool online = monitorlink::snapshot(s);
          uint8_t wifiChannel=0; wifi_second_chan_t secondary=WIFI_SECOND_CHAN_NONE;
          esp_wifi_get_channel(&wifiChannel, &secondary);
          Serial.printf("STATUS now=%d channel=%u online=%d running=%d state=%u received=%u expected=%u rssi=%d snr=%d tx_result=%d tx_cb=%u tx_ok=%u\n", monitorlink::ready, wifiChannel, online, uiRunning, s.state, s.received, s.expected, s.rssiDbm, s.snrDb, monitorlink::lastSendResult, (unsigned)monitorlink::txCallbacks, (unsigned)monitorlink::txDelivered);
          Serial.printf("PEER %02X:%02X:%02X:%02X:%02X:%02X\n",monitorlink::peerMac[0],monitorlink::peerMac[1],monitorlink::peerMac[2],monitorlink::peerMac[3],monitorlink::peerMac[4],monitorlink::peerMac[5]);
          Serial.printf("RX raw=%lu accepted=%lu len=%lu fmt=%lu boot=%lu source=%lu old=%lu\n",(unsigned long)monitorlink::rxRaw,(unsigned long)monitorlink::rxAccepted,(unsigned long)monitorlink::rxBadLength,(unsigned long)monitorlink::rxBadFormat,(unsigned long)monitorlink::rxBadBoot,(unsigned long)monitorlink::rxBadSource,(unsigned long)monitorlink::rxOldStatus);
          Serial.printf("SCREEN mode=%s page=%d sim=%d sim_state=%u phase=%u ch2_to_ch1=%u ch1_to_ch2=%u\n", uiTester?"tester":"menu", uiPage, uiSimulation, uiStatus.state, uiStatus.phase, uiStatus.fromCh2.received, uiStatus.fromCh1.received);
          Serial.printf("METRICS 2to1=%d,%d age=%u 1to2=%d,%d age=%u\n", uiStatus.fromCh2.latestRssiDbm, uiStatus.fromCh2.latestSnrDb10, uiStatus.ageCh2Ms, uiStatus.fromCh1.latestRssiDbm, uiStatus.fromCh1.latestSnrDb10, uiStatus.ageCh1Ms);
        } else if (line.startsWith("CIRCLE ")) {
          int x, y, r;
          if (sscanf(line.c_str(), "CIRCLE %d %d %d", &x, &y, &r) == 3 && x >= 0 && x <= 239 && y >= 0 && y <= 239 && r >= 1 && r <= 120) {
            circleX = x; circleY = y; circleR = r; calibration = true; uiDirty = true;
            Serial.printf("OK CIRCLE %d %d %d\n", x, y, r);
          } else Serial.println("ERR CIRCLE");
        } else if (line == "BATTERY") {
          Serial.printf("BATTERY enabled=%d adc_mv=%d battery_mv=%d estimate_pct=%d divider_milli=%d offset_mv=%d\n",kDisplayBatteryAdcEnabled,displayBatteryAdcMv,displayBatteryMv,displayBatteryPercent,LT_DISPLAY_BATTERY_DIVIDER_MILLI,LT_DISPLAY_BATTERY_OFFSET_MV);
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
