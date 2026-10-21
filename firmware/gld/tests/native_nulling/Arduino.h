#pragma once
#include <cstdint>
template <typename T> T min(T a, T b) { return a < b ? a : b; }
template <typename T> T max(T a, T b) { return a > b ? a : b; }
uint32_t millis();
void delay(uint32_t ms);
