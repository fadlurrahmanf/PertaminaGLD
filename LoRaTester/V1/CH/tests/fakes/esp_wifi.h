#pragma once
#include <cstdint>
#include <cstring>
enum wifi_second_chan_t { WIFI_SECOND_CHAN_NONE };
enum wifi_storage_t { WIFI_STORAGE_RAM };
enum wifi_interface_t { WIFI_IF_STA };
extern uint8_t fakeStaMac[6];
extern int fakeMacResult, fakeSetMacCount, fakeStorageCount;
extern int fakeStorageResult, fakeReadResult;
extern int fakePowerReadResult;
extern int8_t fakeMaxTxQuarterDbm;
extern bool fakeWifiStopped;
inline int esp_wifi_set_storage(wifi_storage_t) { ++fakeStorageCount; return fakeStorageResult; }
inline int esp_wifi_stop() { fakeWifiStopped=true; return 0; }
inline int esp_wifi_start() { fakeWifiStopped=false; return 0; }
inline int esp_wifi_set_mac(wifi_interface_t,const uint8_t* mac) {
  ++fakeSetMacCount;
  if (!fakeWifiStopped || fakeMacResult) return -1;
  std::memcpy(fakeStaMac,mac,6); return 0;
}
inline int esp_wifi_get_mac(wifi_interface_t,uint8_t* mac) { std::memcpy(mac,fakeStaMac,6); return fakeReadResult; }
inline int esp_wifi_get_max_tx_power(int8_t* power) { *power=fakeMaxTxQuarterDbm; return fakePowerReadResult; }
inline int esp_wifi_set_channel(int,wifi_second_chan_t) { return 0; }
inline int esp_wifi_get_channel(uint8_t* c,wifi_second_chan_t*) { *c=1; return 0; }
