#pragma once
#include "SPI.h"
#include <vector>
#include <cstring>
#define RADIOLIB_ERR_NONE 0
#define RADIOLIB_ERR_SPI_CMD_INVALID -2
#define RADIOLIB_ERR_SPI_CMD_FAILED -3
#define RADIOLIB_SX126X_IRQ_RX_DONE 2
#define RADIOLIB_SX126X_CMD_GET_IRQ_STATUS 0x12
extern std::vector<std::vector<uint8_t>> fakeTx;
extern std::vector<uint8_t> fakeRx;
extern bool fakeInjectOnDetach;
extern bool fakeInjectInStandby;
extern int fakeStandbyResult;
extern int fakeIrqResult;
extern int fakeStartRxResult;
extern uint32_t fakeIrq;
struct Module {
  Module(int,int,int,int,FakeSpi&,SPISettings) {}
  int SPIreadStream(uint16_t,uint8_t* data,size_t) {
    data[0]=static_cast<uint8_t>(fakeIrq >> 8); data[1]=static_cast<uint8_t>(fakeIrq);
    return fakeIrqResult;
  }
};
struct SX1262 {
  explicit SX1262(Module*) {}
  int begin(double,double,int,int,int,int,int,double,bool) { return 0; }
  void setRfSwitchPins(int,int) {}
  void setPacketReceivedAction(void (*)()) {}
  void clearPacketReceivedAction() { if (fakeInjectOnDetach) { fakeIrq=2; fakeInjectOnDetach=false; } }
  int standby() { if (fakeInjectInStandby) { fakeIrq=2; fakeInjectInStandby=false; } return fakeStandbyResult; }
  uint32_t getIrqFlags() { return fakeIrq; }
  int startReceive() { fakeIrq=0; return fakeStartRxResult; }
  int transmit(uint8_t* b,size_t n) { fakeTx.emplace_back(b,b+n); return 0; }
  size_t getPacketLength() { return fakeRx.size(); }
  int readData(uint8_t* b,size_t n) { memcpy(b,fakeRx.data(),n); fakeIrq=0; return 0; }
  float getRSSI() { return -80; }
  float getSNR() { return -7.25f; }
};
