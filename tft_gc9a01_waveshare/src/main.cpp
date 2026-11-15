#include <Arduino.h>
#include <esp_system.h>
#include "LCD_Driver.h"
#include "GUI_Paint.h"

void setup() {
  Config_Init();
  delay(300);
  Serial.printf("reset reason = %d (1=POWERON, 9=BROWNOUT)\n", (int)esp_reset_reason());
  LCD_Init();
  Paint_NewImage(LCD_WIDTH, LCD_HEIGHT, 0, BLACK);
  Serial.println("init selesai (Waveshare vendor, SPI mode3)");
}

void loop() {
  static int i = 0;
  const uint16_t bg[]   = {RED, GREEN, BLUE, WHITE, YELLOW, BLACK};
  const uint16_t fg[]   = {WHITE, BLACK, WHITE, BLACK, BLACK, GREEN};
  const char *name[]    = {"MERAH", "HIJAU", "BIRU", "PUTIH", "KUNING", "HITAM"};
  int k = i % 6;
  Paint_Clear(bg[k]);
  Paint_DrawString_EN(60, 90, "HALO", &Font24, bg[k], fg[k]);
  Paint_DrawString_EN(60, 125, name[k], &Font24, bg[k], fg[k]);
  Serial.printf("t=%lu s %s\n", millis() / 1000, name[k]);
  i++;
  delay(3000);
}
