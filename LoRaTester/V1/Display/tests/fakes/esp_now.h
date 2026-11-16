#pragma once
#include <cstdint>
#include <cstddef>
#include <vector>
extern std::vector<std::vector<uint8_t>> fakeNowTx;
extern std::vector<std::vector<uint8_t>> fakeNowTargets;
#define ESP_OK 0
struct esp_now_peer_info_t { uint8_t peer_addr[6]{}; int channel=0; bool encrypt=false; };
enum esp_now_send_status_t { ESP_NOW_SEND_SUCCESS, ESP_NOW_SEND_FAIL };
inline int esp_now_init() { return 0; }
inline int esp_now_register_recv_cb(void (*)(const uint8_t*,const uint8_t*,int)) { return 0; }
inline int esp_now_register_send_cb(void (*)(const uint8_t*,esp_now_send_status_t)) { return 0; }
inline bool esp_now_is_peer_exist(const uint8_t*) { return false; }
inline int esp_now_add_peer(esp_now_peer_info_t*) { return 0; }
inline int esp_now_del_peer(const uint8_t*) { return 0; }
inline int esp_now_send(const uint8_t* target,const uint8_t* data,size_t n) { fakeNowTargets.emplace_back(target,target+6); fakeNowTx.emplace_back(data,data+n); return 0; }
