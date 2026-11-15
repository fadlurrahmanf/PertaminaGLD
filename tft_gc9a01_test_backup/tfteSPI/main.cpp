// TFT_eSPI + GC9A01, pin video YT: MOSI13 SCLK15 CS17 DC21 RST22, VCC=5V
#include <Arduino.h>
#include <esp_system.h>
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();

void drawHalo() {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("HALO", 120, 120, 4);
  tft.drawString("HALO", 120, 160, 2);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.printf("reset reason = %d (1=POWERON, 9=BROWNOUT)\n", (int)esp_reset_reason());
  tft.init();
  tft.setRotation(0);
  drawHalo();
  Serial.println("init selesai (TFT_eSPI) - HALO");
}

void loop() {
  delay(3000);
  drawHalo();
  Serial.printf("t=%lu s HALO\n", millis() / 1000);
}
