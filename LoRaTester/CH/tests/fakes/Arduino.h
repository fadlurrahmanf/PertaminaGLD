#pragma once
#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>
#include <cstring>
#include <cstdarg>
#include <cstdio>
extern uint32_t fakeMillis;
inline uint32_t millis() { return fakeMillis; }
inline void delay(uint32_t n) { fakeMillis += n; }
#define IRAM_ATTR
#define HIGH 1
#define LOW 0
#define OUTPUT 1
inline void pinMode(int,int) {}
inline void digitalWrite(int,int) {}
struct String {
  std::string s;
  String() = default;
  String(const char* p) : s(p) {}
  void trim() {}
  bool operator==(const char* p) const { return s == p; }
};
struct FakeSerial {
  std::string input, output;
  void begin(int) {}
  int available() { return static_cast<int>(input.size()); }
  int read() { if (input.empty()) return -1; char value=input[0]; input.erase(0,1); return static_cast<unsigned char>(value); }
  void println(const char* s) { output += s; output += '\n'; }
  void printf(const char* format, ...) {
    char buf[1024]; va_list args; va_start(args,format);
    std::vsnprintf(buf,sizeof(buf),format,args); va_end(args); output += buf;
  }
};
extern FakeSerial Serial0;
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)0)
#define portEXIT_CRITICAL(x) ((void)0)
#define portENTER_CRITICAL_ISR(x) ((void)0)
#define portEXIT_CRITICAL_ISR(x) ((void)0)
