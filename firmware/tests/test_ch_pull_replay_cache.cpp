#include "ChPullReplayCache.h"
#include <cassert>
#include <cstdint>
#include <cstring>

int main() {
    pgl::ch::ChPullReplayCache<8, 2> cache;
    const uint8_t first[] = {1, 2, 3, 4};
    const uint8_t second[] = {9, 8};
    size_t size = 0;
    assert(cache.remember(1, 42, 3, 100, first, sizeof(first)));
    const uint8_t* replay = cache.find(1, 42, 3, 150, 100, size);
    assert(replay && size == sizeof(first) && std::memcmp(replay, first, size) == 0);
    assert(!cache.find(2, 42, 3, 150, 100, size));
    assert(!cache.find(1, 42, 4, 150, 100, size));
    assert(!cache.find(1, 42, 3, 201, 100, size));
    assert(cache.remember(1, 43, 4, 0xfffffff0U, second, sizeof(second)));
    replay = cache.find(1, 43, 4, 0x10U, 100, size);
    assert(replay && size == sizeof(second) && replay[0] == 9);
    assert(cache.remember(1, 44, 5, 200, second, sizeof(second)));
    assert(!cache.find(1, 42, 3, 200, 1000, size));
    assert(!cache.remember(1, 45, 6, 200, nullptr, 1));
}
