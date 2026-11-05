#pragma once
#include <array>
#include <stddef.h>
#include <stdint.h>

namespace epaper {
constexpr uint16_t width = 400;
constexpr uint16_t height = 300;
constexpr size_t plane_bytes = width * height / 8;
constexpr size_t frame_bytes = plane_bytes * 2;
constexpr uint32_t cooldown_ms = 30000;
using Frame = std::array<uint8_t, frame_bytes>;
}
