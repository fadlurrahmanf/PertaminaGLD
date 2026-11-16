#pragma once
#include <cstdint>
extern uint32_t fakeRandom;
extern int fakeResetReason;
inline uint32_t esp_random() { return fakeRandom; }
inline int esp_reset_reason() { return fakeResetReason; }
