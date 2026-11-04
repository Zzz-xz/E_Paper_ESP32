#include <Arduino.h>
#include <GxEPD2_3C.h>
#include <SPI.h>

#include "board_pins.h"
#include "wallpaper_bitmap.h"

namespace {
constexpr uint32_t kSerialBaud = 115200;
constexpr uint32_t kSpiFrequencyHz = 4000000;
constexpr uint16_t kPageHeight = 64; /**< 双色分页缓冲占用 6400 字节，避免分配整屏缓冲。 */
constexpr uint16_t kResetPulseMs = 2; /**< 适配微雪驱动板的复位电路。 */

GxEPD2_3C<GxEPD2_420c_GDEY042Z98, kPageHeight> display(
    GxEPD2_420c_GDEY042Z98(board_pins::epaper_cs, board_pins::epaper_dc,
                         board_pins::epaper_reset, board_pins::epaper_busy));

void initialize_display();
void draw_wallpaper();
}

/** @brief 上电仅全屏刷新一次，随后关闭屏幕高压并保留画面。 */
void setup()
{
    Serial.begin(kSerialBaud);
    initialize_display();
    draw_wallpaper();
    display.hibernate();
    Serial.println("[epaper] Refresh sequence finished; display sleeping.");
}

/** @brief 静态画面无需重复刷新，避免屏幕持续闪烁。 */
void loop()
{
    delay(1000);
}

namespace {
/** @brief 先绑定自定义 SPI 引脚；开启库诊断以输出 BUSY 超时等硬件错误。 */
void initialize_display()
{
    Serial.println("[epaper] Initializing SSD1683, 400 x 300, black/white/red.");
    SPI.begin(board_pins::epaper_sck, -1, board_pins::epaper_mosi,
              board_pins::epaper_cs);
    display.init(kSerialBaud, true, kResetPulseMs, false, SPI,
                 SPISettings(kSpiFrequencyHz, MSBFIRST, SPI_MODE0));
    display.setRotation(0);
}

/** @brief 各页绘制互斥的黑、红位面，未置位区域保留白色，由驱动全屏刷新一次。 */
void draw_wallpaper()
{
    const int16_t origin_x = (display.width() - wallpaper_bitmap::kWidth) / 2;
    const int16_t origin_y = (display.height() - wallpaper_bitmap::kHeight) / 2;

    Serial.println("[epaper] Refreshing black/white/red wallpaper.");
    display.setFullWindow();
    display.firstPage();
    do {
        display.fillScreen(GxEPD_WHITE);
        display.drawBitmap(origin_x, origin_y, wallpaper_bitmap::kBlack,
                           wallpaper_bitmap::kWidth, wallpaper_bitmap::kHeight,
                           GxEPD_BLACK);
        display.drawBitmap(origin_x, origin_y, wallpaper_bitmap::kRed,
                           wallpaper_bitmap::kWidth, wallpaper_bitmap::kHeight,
                           GxEPD_RED);
    } while (display.nextPage());
}
}
