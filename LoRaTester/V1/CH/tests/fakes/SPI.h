#pragma once
#define MSBFIRST 1
#define SPI_MODE0 0
struct SPISettings { SPISettings(int,int,int) {} };
struct FakeSpi { void begin(int,int,int) {} };
extern FakeSpi SPI;
