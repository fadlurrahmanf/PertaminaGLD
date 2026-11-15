#pragma once
#include <cstdint>
extern uint32_t fakeRandom;
inline uint32_t esp_random() { return ++fakeRandom; }
