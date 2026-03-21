# MiMo-V2-TTS Playground

一个基于小米 MiMo-V2-TTS 语音合成模型的桌面客户端，支持 GUI 操作和即时播放。

## 技术栈

| 组件 | 说明 |
|------|------|
| **Python 3.10+** | 主语言 |
| **Tkinter** | GUI 框架（Python 内置，无需额外安装） |
| **requests** | HTTP 请求，调用 MiMo API |
| **pygame** | 音频播放（mixer 模块） |

## API

- **Endpoint**: `POST https://api.xiaomimimo.com/v1/chat/completions`
- **模型**: `mimo-v2-tts`
- **协议**: OpenAI chat completions 兼容，使用 `audio` 字段返回语音
- **认证**: `api-key` + `Authorization: Bearer` 双 header

## 快速开始

```bash
pip install requests pygame
python mimo_tts_client.py
```

API Key 从 [platform.xiaomimimo.com](https://platform.xiaomimimo.com) 获取。

## 打包为可执行文件

使用 PyInstaller 打包：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "MiMo-TTS-Playground" mimo_tts_client.py
```

或直接运行构建脚本：
- **Windows**: `build.bat`
- **macOS/Linux**: `bash build.sh`

输出文件在 `dist/` 目录下。

## 配置

配置自动保存到 `~/.mimo_tts/config.json`，包含 API Key、Base URL、模型、语音、格式等。
