#pragma once
#include <cstdint>
#include <cstring>

// 240x240 8-bit sprite, split into 15x15 16-pixel tiles. No allocation or I/O.
namespace dirtyframe {
constexpr int kWidth=240, kHeight=240, kTile=16, kColumns=15, kRows=15;
struct Plan { uint16_t rows[kRows]{}; uint16_t tiles=0; };
inline Plan compare(const uint8_t* current, const uint8_t* previous, bool valid, bool holdOverlay) {
  Plan result{};
  for (int ty=0; ty<kRows; ++ty) for (int tx=0; tx<kColumns; ++tx) {
    bool changed=!valid;
    if (!changed && holdOverlay && ty==12 && tx>=5 && tx<=9) changed=true;
    for (int y=0; !changed && y<kTile; ++y) {
      const auto offset=(ty*kTile+y)*kWidth+tx*kTile;
      changed=std::memcmp(current+offset,previous+offset,kTile)!=0;
    }
    if (changed) { result.rows[ty] |= uint16_t(1U<<tx); ++result.tiles; }
  }
  return result;
}
}
