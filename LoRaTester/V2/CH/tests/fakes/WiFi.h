#pragma once
#define WIFI_STA 1
struct FakeWiFi { void mode(int) {} void disconnect() {} void persistent(bool) {} };
extern FakeWiFi WiFi;
