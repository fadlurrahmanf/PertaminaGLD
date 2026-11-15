// Tes LovyanGFX - GC9A01 240x240 (wiring sama: RST25 CS27 DC26 MOSI23 SCK18)
#include <Arduino.h>
#include <esp_system.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

class LGFX : public lgfx::LGFX_Device {
  lgfx::Panel_GC9A01 _panel;
  lgfx::Bus_SPI _bus;
public:
  LGFX() {
    { auto c = _bus.config();
      c.spi_host = VSPI_HOST; c.spi_mode = 0;
      c.freq_write = 4000000; c.freq_read = 0;
      c.spi_3wire = true; c.use_lock = true; c.dma_channel = SPI_DMA_CH_AUTO;
      c.pin_sclk = 18; c.pin_mosi = 23; c.pin_miso = -1; c.pin_dc = 26;
      _bus.config(c); _panel.setBus(&_bus); }
    { auto c = _panel.config();
      c.pin_cs = 27; c.pin_rst = 25; c.pin_busy = -1;
      c.panel_width = 240; c.panel_height = 240; c.offset_x = 0; c.offset_y = 0;
      c.readable = false; c.invert = true; c.rgb_order = false; c.dlen_16bit = false; c.bus_shared = false;
      _panel.config(c); }
    setPanel(&_panel);
  }
};
LGFX lcd;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.printf("reset reason = %d (1=POWERON, 9=BROWNOUT)\n", (int)esp_reset_reason());
  lcd.init();
  lcd.fillScreen(TFT_RED);
  lcd.setTextColor(TFT_WHITE);
  lcd.setTextSize(3);
  lcd.setCursor(50, 100);
  lcd.print("HALO");
  Serial.println("init selesai (LovyanGFX)");
}

void loop() {
  static int i = 0;
  const uint32_t c[] = {TFT_RED, TFT_GREEN, TFT_BLUE, TFT_WHITE};
  lcd.fillScreen(c[i % 4]);
  lcd.setTextColor(i % 4 == 3 ? TFT_BLACK : TFT_WHITE);
  lcd.setCursor(50, 100);
  lcd.print("HALO");
  Serial.printf("t=%lu s warna=%d\n", millis() / 1000, i % 4);
  i++;
  delay(3000);
}
