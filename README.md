# ESP32 4.2 寸墨水屏工程

使用 PlatformIO + Arduino + GxEPD2。工具保存在项目内，不依赖全局 PlatformIO 或 ESP-IDF 环境。

## 硬件范围

工程面向经典 ESP32，使用 `esp32dev` 配置和 4 MB Flash。更换开发板时需核对实际 ESP32 芯片及 Flash 容量。CH340 是 USB 转串口芯片，不能据此判断 ESP32 的具体型号。

目标屏幕为微雪 4.2inch e-Paper (B) V2 的 SSD1683 版本，400×300、黑白红。对应的 GxEPD2 驱动选型为 `GxEPD2_420c_GDEY042Z98`，图形封装使用 `GxEPD2_3C`。同名产品存在历史版本，后续更换屏幕时需重新核对控制器。

固件上电后全屏刷新一次，显示黑、白、红三色壁纸，随后让屏幕休眠并保留画面。主循环不重复刷新；再次复位或上电会重新执行显示流程。三色屏刷新时闪烁属于正常现象，请等待刷新完成。

壁纸在 `include/wallpaper_bitmap.h` 中存储为互斥的黑、红位面，两者均未置位时显示白色，共占 22500 字节 Flash。原图按 16:9 等比缩小为 400×225，在 400×300 屏幕上下留白；天空用黑白网点表达明暗，草地映射为红色并保留黑色阴影，标志保留白色。屏幕只支持黑白红，无法还原原图中的蓝色和绿色。设备不在运行时解码图片或进行颜色转换。

| ESP32 GPIO | 驱动模块 | 用途 |
| --- | --- | --- |
| 3V3 | 3V3 | 电源 |
| GND | GND | 共地 |
| 27 | SI | SPI MOSI |
| 26 | SCK | SPI 时钟 |
| 25 | CS | 片选 |
| 33 | DC | 数据/命令 |
| 32 | RES | 复位 |
| 35 | BUS | BUSY 状态输入 |

开发板 D 编号按同号 GPIO 解释。GPIO35 仅支持输入，没有内部上下拉。程序使用上述自定义 SPI 引脚、4 MHz SPI 时钟和 2 ms 复位脉冲。双色分页缓冲使用 6400 字节，不需要整屏缓冲。

## 编译与串口

在项目根目录打开 PowerShell：

```powershell
# 编译
.\pio.cmd run

# 枚举串口，查找 USB-SERIAL CH340
.\pio.cmd device list

# 生成或更新 VS Code C/C++ 的编译数据库
.\pio.cmd run --target compiledb
```

VS Code 可按 `Ctrl+Shift+B` 编译，在“终端 → 运行任务”中选择串口枚举、上传和串口监视任务。无需另外安装 PlatformIO 扩展；C/C++ 扩展通过编译数据库获取头文件路径。

确认开发板型号和目标端口后，可上传显示固件。以下 `COMx` 需替换为实际的 CH340 端口：

```powershell
.\pio.cmd run --target upload --upload-port COMx
.\pio.cmd device monitor --port COMx --baud 115200
```

固件输出初始化、刷新和休眠日志；库的硬件诊断也会输出到串口。出现 `Busy Timeout!` 时，应检查屏幕版本、接线和供电，不能仅凭流程结束日志判断显示成功。屏幕实际画面需要目视确认。

`Ctrl+C` 退出串口监视器。上传前关闭占用同一端口的串口监视器。若上传停在 `Connecting...`，可按住 BOOT，连接建立后松开。避免连续复位反复触发全屏刷新；微雪建议此型号常规刷新间隔至少 180 秒。

## 环境复现

需要 Python 3 和网络连接，在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\pio.cmd run
.\pio.cmd run --target compiledb
```

PlatformIO Core 版本由 `requirements-dev.txt` 固定；ESP32 平台与屏幕库版本由 `platformio.ini` 固定。`.venv/` 存放 Python 环境，`.platformio/` 存放工具链及框架，`.pio/` 存放库和构建产物；这些目录均不提交 Git。临时分析或验证文件统一放入 `temp/`。

## 参考资料

- [PlatformIO ESP32 Dev Module 配置](https://docs.platformio.org/en/latest/boards/espressif32/esp32dev.html)
- [PlatformIO 工具链存储目录](https://docs.platformio.org/en/latest/projectconf/sections/platformio/options/directory/core_dir.html)
- [GxEPD2 支持的屏幕与使用说明](https://github.com/ZinggJM/GxEPD2)
- [微雪 4.2inch e-Paper (B) V2 SSD1683 数据手册](https://files.waveshare.com/wiki/4.2inch%20e-Paper%20Module%20%28B%29/4.2inch%20e-Paper%20%28B%29%20V2.pdf)
- [ESP32 GPIO 限制](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html)
