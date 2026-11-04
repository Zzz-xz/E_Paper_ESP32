#pragma once

#include <stdint.h>

/** @brief 经典 ESP32 的屏幕接线，板上 D 编号按同号 GPIO 解释。 */
namespace board_pins {
constexpr int8_t epaper_mosi = 27; /**< 屏幕 SI，仅发送，不使用 MISO。 */
constexpr int8_t epaper_sck = 26;
constexpr int8_t epaper_cs = 25;
constexpr int8_t epaper_dc = 33;
constexpr int8_t epaper_reset = 32;
constexpr int8_t epaper_busy = 35; /**< 仅输入，无内部上下拉。 */
}
