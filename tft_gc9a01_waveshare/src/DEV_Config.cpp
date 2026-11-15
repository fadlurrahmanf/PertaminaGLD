#include "DEV_Config.h"
// Port ESP32: SPI MODE3 seperti kode vendor Waveshare. SCK18 MOSI23, CS/DC/RST manual.
void Config_Init()
{
  pinMode(DEV_CS_PIN, OUTPUT);
  pinMode(DEV_RST_PIN, OUTPUT);
  pinMode(DEV_DC_PIN, OUTPUT);
  Serial.begin(115200);
  SPI.begin(15, -1, 13, -1);
  SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE3));
}
