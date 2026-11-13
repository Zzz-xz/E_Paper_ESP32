# 开发、接口与验证

[返回项目首页](../README.md) · [目录与模块说明](architecture.md)

以下命令均在项目根目录执行。

## 环境复现

需要 Python 3 和网络连接，在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\pio.cmd run
.\pio.cmd run --target compiledb
```

Python 依赖由 `requirements.txt` 与 `requirements-dev.txt` 固定，前端依赖由 `web/package-lock.json` 锁定，ESP32 平台与库由 `platformio.ini` 固定。`.venv/`、`.platformio/`、`.pio/`、`web/node_modules/`、`web/dist/`、`data/` 都不提交 Git。临时分析或验证文件统一放入 `temp/`。可用环境变量 `EPAPER_DATA_DIR` 更改运行数据目录，示例文件中的占位配置不包含私人凭据。

源码、网页资源和中文提示统一保存为 UTF-8；C/C++、Python、前端源码使用 LF，Windows 批处理使用 CRLF。检查网页编码时需同时检查 HTTP 字符集声明与实际资源字节。

## 接口与模块

| 接口 | 用途 |
| --- | --- |
| `POST /api/render` | multipart 图片与 JSON `options`，返回预览标识、PNG 和颜色统计 |
| `POST /api/images` | 上传一次原图，返回图片标识、推荐参数与初始预览 |
| `POST /api/images/{id}/render` | 复用内存原图生成图片预览 |
| `POST /api/documents/render` | 合成可选图片与文字列表，返回最终预览及编辑图层 |
| `POST /api/display-jobs` | JSON `preview_id`，创建唯一显示任务 |
| `GET /api/status` | 设备连接、当前任务及冷却倒计时 |
| `GET /api/display/current` | 最近确认完成的画面和确认时间；5 秒内重复获取返回 429，附带 Retry-After |
| `POST /api/device/poll` | 设备心跳和任务获取，无任务返回 204 |
| `GET /api/device/jobs/{id}/frame` | 下载固定 30000 字节位面 |
| `POST /api/device/jobs/{id}/result` | 回报 refreshing、completed 或 failed |
| `GET /api/security/status` | 管理口令配置状态及当前访问是否可首次初始化 |
| `POST /api/admin/initialize` | 仅电脑本机网页首次设置管理员密码，不能覆盖已有密码 |
| `POST /api/recovery/initialize` | 仅电脑本机网页首次设置固定恢复口令，不能覆盖已有口令 |
| `POST /api/admin/password` | 已验证的普通管理员修改密码，旧会话随即失效 |
| `/api/admin/{login,status,logout}` | 普通管理员验证、状态与退出 |
| `/api/recovery/{login,status,logout,reset-admin}` | 超级管理员验证及普通管理员密码重置 |
| `GET/POST /api/device/setup` | 管理员查询或下发重新配网指令 |
| `POST /api/device/setup/{id}/result` | 设备回报动态配网页地址及临时授权 |

后端 `server/` 按参数模型、图像转换、存储和 API 分层。固件入口只做流程调度，配网、HTTP 通信和屏幕访问各自独立。上传参数在 API 边界校验，网络帧在设备通信模块入口校验，显示层消费已验证的位面。

图文文档增加 `foreground`、`background`，默认 `black`、`white` 且不得相同；文字 `color` 可用 `foreground` 跟随前景色。图片 `zoom` 范围 0.25～4，`offset_x`、`offset_y` 为相对图片框宽高的偏移，范围 -3～3，默认 0；`recommendation` 为 `auto` 或 `manual`，旧接口缺省保持 `manual`。渲染响应通过 `applied_options` 返回实际使用的图片参数。图片框比例锁定仅属于编辑状态，不进入设备协议。

多图请求使用 `images` 数组，每项包含唯一 `id`、`image_id`、`box`、`options` 和取景参数，上限为 8；图片按数组顺序合成，全部文字在图片之后绘制。响应 `applied_images` 按图层标识返回实际使用的参数。旧的单图 `image` 请求保持兼容，但不能同时提供 `image` 和 `images`；图片与文字标识不得冲突。

网页创建的文字使用 `auto_size: true`，响应 `text_boxes` 按文字标识返回最终框尺寸与位置，前端与实际位面同步使用；空间不足返回 422，不生成被裁切的文字预览。旧接口缺省 `auto_size: false`，保持调用方指定框及溢出警告，便于兼容已有请求。

## 验证

```powershell
.\.venv\Scripts\python.exe -W error -m pytest -q
npm.cmd run build --prefix web
.\pio.cmd run
```

测试覆盖三色映射、灰度图、透明图片、像素画、旋转、预览与位面一致性，以及任务状态、失败、重启持久化和冷却限制。浏览器和硬件验证需要实际浏览器与设备，不能仅凭单元测试认定硬件已显示。

PATH 中有 `g++` 时，测试会使用 `-Wall -Wextra -Werror` 编译并运行固件同一份收图循环，覆盖分片、断流、零碎数据及硬期限；未安装编译器时该项显示跳过。
