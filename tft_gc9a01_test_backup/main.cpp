#include <Arduino.h>
#include <esp_system.h>
#include <Arduino_GFX_Library.h>

#define PIN_RST  25
#define PIN_CS   27
#define PIN_DC   26
#define PIN_MOSI 23   // SDA
#define PIN_SCK  18   // SCL
#define SPI_HZ   1000000

Arduino_DataBus *bus = new Arduino_ESP32SPI(PIN_DC, PIN_CS, PIN_SCK, PIN_MOSI, GFX_NOT_DEFINED);
Arduino_GFX *gfx = new Arduino_GC9A01(bus, PIN_RST, 0, true);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.printf("reset reason = %d (1=POWERON, 9=BROWNOUT)\n", (int)esp_reset_reason());
  if (!gfx->begin(SPI_HZ)) Serial.println("gfx->begin GAGAL");
  gfx->fillScreen(RED);
  gfx->setTextColor(WHITE);
  gfx->setTextSize(3);
  gfx->setCursor(50, 100);
  gfx->println("HALO");
  Serial.println("init selesai");
}

void loop() {
  static bool inv = false;
  inv = !inv;
  gfx->invertDisplay(inv);
  Serial.printf("t=%lu s inv=%d\n", millis() / 1000, inv);
  delay(3000);
}
