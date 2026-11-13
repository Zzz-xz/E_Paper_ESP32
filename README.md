# 三色墨水屏图文工作台

在电脑或手机网页中上传图片、输入文字并自由排版，实时对照黑白红预览，确认后通过 Wi-Fi 显示到 ESP32 驱动的墨水屏上。

- 支持最多 **8 张图片与 12 段文字**，每张图片可独立旋转、调色、缩放和取景。
- 编辑画布与实屏预览同时展示，手机也可直接对照；文字可叠放在图片上方。
- 预览与发送使用同一份最终位面；完成固件配置后，日常换图无需重新烧录。
- 普通用户可使用工作台，管理员管理设备网络，固定恢复口令仅用于重置管理员密码。

目标硬件：经典 ESP32、微雪 4.2inch e-Paper (B) V2 SSD1683，**400×300、4:3、黑白红三色**。

## 快速启动

需要 Python 3.14 与 Node.js 24。以下命令在项目根目录的 PowerShell 中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci --prefix web
npm.cmd run build --prefix web
.\start.cmd
```

电脑打开 `http://localhost:8000`。手机使用 `http://<电脑局域网地址>:8000`，与电脑和 ESP32 保持在可互相访问的局域网内。网站由电脑提供，电脑需要保持运行。

已有环境时直接运行 `start.cmd`。修改前端后重新执行 `npm.cmd run build --prefix web`；开发时可另开终端运行 `npm.cmd run dev --prefix web`，请求通过 Vite 代理到后端。

## 首次使用

1. 按 [硬件说明](docs/hardware.md) 核对屏幕版本与接线，使用 `.\pio.cmd run` 编译固件。
2. 查看 `.\pio.cmd device list`，用实际串口替换 `COMx` 后执行烧录和串口监视：

   ```powershell
   .\pio.cmd run --target upload --upload-port COMx
   .\pio.cmd device monitor --port COMx --baud 115200
   ```

3. 按串口提示连接 ESP32 配网热点，在配网页选择 2.4 GHz Wi-Fi，填写密码与电脑工作台地址。
4. 在电脑本机网页的“管理设置”中初始化管理员及固定恢复口令。普通用户显示图文无需登录，修改接入网络需要管理员身份。
5. 工作台收到设备心跳后显示“设备已连接”，即可编辑、预览并发送。

Wi-Fi 密码只提交给 ESP32 并保存在设备中，不经过电脑网站。电脑 IP 变化时，设备保存的工作台地址需要更新；详见 [网络与配网](docs/network.md)。

## 项目结构

| 目录／入口 | 用途 |
| --- | --- |
| [`src/`](src/) 与 [`include/`](include/) | ESP32 固件实现与模块接口，沿用 PlatformIO 标准目录 |
| [`server/`](server/) | FastAPI、图像处理、预览缓存、任务和权限管理 |
| [`web/src/`](web/src/) | React 工作台，按公共组件与功能模块分组 |
| [`assets/fonts/`](assets/fonts/) | 中文字体与字体许可 |
| [`tests/`](tests/) | 后端及原生收图测试 |
| [`scripts/`](scripts/) | 系统辅助脚本 |
| [`docs/`](docs/) | 使用、硬件、网络、开发和设计文档 |
| `start.cmd` / `pio.cmd` / `set-admin.cmd` | 网站、固件工具链与本机口令维护入口 |

完整模块地图、依赖方向和运行数据位置见 [项目结构说明](docs/architecture.md)。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [硬件与固件](docs/hardware.md) | 接线、驱动型号、编译、烧录和串口 |
| [网络与配网](docs/network.md) | Wi-Fi 配置、动态地址、防火墙与失联处理 |
| [使用与管理](docs/usage.md) | 图文编辑、快捷键、三色预览及密码恢复 |
| [开发与验证](docs/development.md) | 环境复现、API、位面格式与测试 |
| [目录与模块](docs/architecture.md) | 前端、后端、固件的职责与边界 |
| [产品约束](docs/product.md) / [界面设计](docs/design.md) | 已确认的产品能力、布局和视觉规则 |

## 验证

```powershell
.\.venv\Scripts\python.exe -W error -m pytest -q
npm.cmd run build --prefix web
.\pio.cmd run
```

PATH 中存在 `g++` 时，pytest 同时编译并验证原生收图循环；未安装时该项跳过。屏幕实际显示仍需硬件验收。

`data/`、`temp/`、本地依赖和构建产物由 `.gitignore` 排除，不提交数据库、口令配置或测试截图。字体许可保留在 `assets/fonts/` 中。

## 许可

项目代码使用 [MIT License](LICENSE)。中文字体的独立许可见 [assets/fonts/OFL.txt](assets/fonts/OFL.txt)。
