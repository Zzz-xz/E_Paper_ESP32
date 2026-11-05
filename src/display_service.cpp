#include <Arduino.h>
#include <GxEPD2_3C.h>
#include <SPI.h>
#include "board_pins.h"
#include "display_service.h"

namespace {
/** @brief 分页缓冲仅占 6400 字节，网络帧独立存储，完整收图后才访问屏幕。 */
GxEPD2_3C<GxEPD2_420c_GDEY042Z98, 64> display(
    GxEPD2_420c_GDEY042Z98(board_pins::epaper_cs, board_pins::epaper_dc,
                          board_pins::epaper_reset, board_pins::epaper_busy));
}

void display_service::begin()
{
    SPI.begin(board_pins::epaper_sck, -1, board_pins::epaper_mosi, board_pins::epaper_cs);
}

/** @brief 返回 BUSY 是否已解除；SPI 无光学回读，结果不代表目视画面验证。 */
bool display_service::refresh(const epaper::Frame& frame)
{
    display.init(115200, true, 2, false, SPI, SPISettings(4000000, MSBFIRST, SPI_MODE0));
    display.setRotation(0);
    display.setFullWindow();
    display.firstPage();
    do {
        display.fillScreen(GxEPD_WHITE);
        display.drawBitmap(0, 0, frame.data(), epaper::width, epaper::height, GxEPD_BLACK);
        display.drawBitmap(0, 0, frame.data() + epaper::plane_bytes,
                           epaper::width, epaper::height, GxEPD_RED);
    } while (display.nextPage());
    const bool idle = digitalRead(board_pins::epaper_busy) == LOW;
    display.hibernate();
    return idle;
}
