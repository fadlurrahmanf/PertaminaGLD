#pragma once
#include <cstddef>
class Preferences {
public:
    bool begin(const char*, bool);
    void end();
    size_t putBytes(const char*, const void*, size_t);
    size_t getBytes(const char*, void*, size_t);
};
