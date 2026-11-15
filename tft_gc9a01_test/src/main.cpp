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
bool calibration = true;
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
}

void loop() {
  static int stable = digitalRead(22), observed = stable;
  static unsigned long changed = 0;
  int reading = digitalRead(22);
  if (reading != observed) { observed = reading; changed = millis(); }
  if (millis() - changed >= 30) stable = observed;
  static unsigned long lastChange = 0;
  if (millis() - lastChange >= 200) {
    lastChange = millis();
    if (calibration) {
      frame.fillSprite(static_cast<uint16_t>(TFT_BLACK));
      frame.drawCircle(circleX, circleY, circleR, static_cast<uint16_t>(TFT_WHITE));
      frame.drawFastHLine(circleX - 8, circleY, 17, static_cast<uint16_t>(TFT_RED));
      frame.drawFastVLine(circleX, circleY - 8, 17, static_cast<uint16_t>(TFT_RED));
      frame.pushSprite(0, 0);
    } else {
    int b2 = stable;
    frame.fillSprite(static_cast<uint16_t>(TFT_BLACK));
    frame.setTextDatum(lgfx::middle_center);
    frame.setTextColor(static_cast<uint16_t>(TFT_WHITE));
    frame.setTextSize(2);
    frame.drawString("TES TOMBOL", 120, 65);
    frame.drawString(b2 ? "TOMBOL 2: HIGH" : "TOMBOL 2: LOW", 120, 125);
    frame.pushSprite(0, 0);
    }
  }
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (line.length()) {
        line.trim();
        if (line.startsWith("CIRCLE ")) {
          int x, y, r;
          if (sscanf(line.c_str(), "CIRCLE %d %d %d", &x, &y, &r) == 3 && x >= 0 && x <= 239 && y >= 0 && y <= 239 && r >= 1 && r <= 120) {
            circleX = x; circleY = y; circleR = r; calibration = true;
            Serial.printf("OK CIRCLE %d %d %d\n", x, y, r);
          } else Serial.println("ERR CIRCLE");
        } else if (line == "BUTTON") {
          calibration = false; Serial.println("OK BUTTON");
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
