# 项目目录与模块边界

[返回项目首页](../README.md)

## 目录导航

```text
.
├── src/                     ESP32 固件实现
├── include/                 固件模块接口与位面定义
├── server/                  FastAPI、图像处理和任务存储
├── web/
│   └── src/
│       ├── App.tsx          工作台流程编排
│       ├── main.tsx         React 入口
│       ├── components/ui/   公共按钮、弹窗、屏幕框和加载提示
│       ├── features/
│       │   ├── editor/      图文画布、属性、取色及编辑状态
│       │   ├── device/      连接指南、设备状态和当前画面
│       │   ├── security/    管理员设置与密码恢复
│       │   └── help/        快捷键说明
│       ├── lib/             API 类型、请求及动画基础工具
│       └── styles/          工作台样式
├── assets/fonts/            中文字体及字体许可
├── tests/                   后端测试与原生收图测试
├── scripts/                 防火墙等系统辅助脚本
└── docs/                    使用、硬件、开发与设计文档
```

根目录保留 `start.cmd`、`pio.cmd`、`set-admin.cmd`，以及依赖清单、PlatformIO 配置和 pytest 配置。入口仍在项目根目录运行，避免目录调整影响既有操作。

## 前端

`App.tsx` 编排编辑状态、当前选择和发送流程。`features/` 按用户任务分组，模块可依赖公共 `components/ui/` 和 `lib/`，公共 UI 不依赖业务功能。

`Dialog.tsx` 仅负责弹窗与焦点管理；设备连接指南属于 `features/device/ConnectionGuide.tsx`。`ScreenFrame.tsx` 只提供 4:3 屏幕外框，编辑器与当前画面查看器共用，避免设备功能依赖整个编辑器。

`features/editor/useDocumentComposer.ts` 管理上传和最新预览，`useImagePan.ts` 管理本地拖动取景，`geometry.ts` 管理坐标与缩放。目录整理不改变文档模型、调色、拖动或发送条件。

## 后端

| 职责 | 入口与模块 |
| --- | --- |
| 启动和 HTTP 边界 | `server/__main__.py`、`app.py`、`password_routes.py` |
| 外部参数与协议常量 | `models.py` |
| 图片与文字合成 | `composition.py`、`text_layout.py` |
| 三色转换与细节处理 | `rendering.py`、`color_math.py`、`image_detail.py`、`optimization.py` |
| 预览与图层缓存 | `preview_service.py` |
| 设备任务和状态存储 | `storage.py` |
| 管理员与重新配网 | `admin.py`、`device_setup.py` |

后端继续使用 `python -m server` 启动。`assets/fonts/` 为代码共享资源，字体许可保留在同目录。

## 固件

PlatformIO 沿用标准 `src/` 和 `include/` 目录。`main.cpp` 与 `application.cpp` 做启动和流程编排；`network_config.cpp` 处理 Wi-Fi 与配网，`device_client.cpp` 处理 HTTP 和位面接收，`display_service.cpp` 负责屏幕访问。

`include/frame_receiver.h` 的接收循环同时用于设备固件和 `tests/native/` 的原生测试；`board_pins.h` 集中接线定义。网站生成的 400×300 黑红位面经完整接收和校验后才显示，两个位面总计 30000 字节。

## 本地生成目录

`data/` 保存运行数据库与口令派生值；`temp/` 保存验证和分析产物。`.venv/`、`.platformio/`、`.pio/`、`web/node_modules/`、`web/dist/` 是本地环境或构建产物，均由 `.gitignore` 排除，不进入远程仓库。
