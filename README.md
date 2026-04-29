# MiMo TTS Playground

一个基于小米 MiMo 语音合成 API 的桌面客户端，支持 GUI 操作、即时播放和保存音频。

当前已支持 MiMo-V2.5-TTS 系列的主要能力：

- `mimo-v2.5-tts`：内置音色语音合成、自然语言风格控制、音频标签、唱歌标签
- `mimo-v2.5-tts-voicedesign`：通过文本描述生成音色
- `mimo-v2.5-tts-voiceclone`：通过 mp3/wav 参考音频克隆音色
- `mimo-v2-tts`：保留旧版 TTS 模型入口

官方文档：[Speech synthesis (MiMo-V2.5-TTS Series)](https://platform.xiaomimimo.com/docs/zh-CN/usage-guide/speech-synthesis-v2.5)

## 技术栈

| 组件 | 说明 |
|------|------|
| **Python 3.10+** | 主语言 |
| **Tkinter** | GUI 框架（Python 内置，无需额外安装） |
| **requests** | HTTP 请求，调用 MiMo API |
| **pygame** | 音频播放（mixer 模块） |

## API

- **Endpoint**: `POST https://api.xiaomimimo.com/v1/chat/completions`
- **协议**: OpenAI chat completions 兼容，使用 `audio` 字段返回语音
- **认证**: `api-key` + `Authorization: Bearer` 双 header
- **配置文件**: `~/.mimo_tts/config.json`

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python mimo_tts_client.py
```

API Key 从 [platform.xiaomimimo.com](https://platform.xiaomimimo.com) 获取。

## 使用说明

### 内置音色

选择 `mimo-v2.5-tts`，再选择内置音色：

```text
mimo_default、冰糖、茉莉、苏打、白桦、Mia、Chloe、Milo、Dean
```

`自然语言指令 / 风格控制` 会作为 `role: user` 消息发送，适合描述语速、情绪、角色、场景等。`要合成的文本` 会作为 `role: assistant` 消息发送，这是最终会被读出来的内容。

### 标签控制

2.5 文档要求标签写在 `assistant` 合成文本内：

- 开头整体风格：`(温柔)你好，我是 MiMo。`
- 唱歌模式：`(唱歌)歌词内容`
- 行内音频标签：`我有点[哽咽]不知道该怎么说。`

界面里的“添加 (风格)”“添加 (唱歌)”和“插入 [标签]”按钮会自动按这个格式插入。

### VoiceDesign

选择 `mimo-v2.5-tts-voicedesign` 后，必须在 `自然语言指令 / 音色描述` 中填写音色描述，例如：

```text
年轻男性，声音清澈有活力，语速稍快，像在轻松地分享一个好消息。
```

这个模型不使用内置音色，也不需要参考音频。

### VoiceClone

选择 `mimo-v2.5-tts-voiceclone` 后，点击“选择 mp3/wav”选择参考音频。程序会按官方要求把参考音频编码成：

```text
data:{MIME_TYPE};base64,{BASE64_AUDIO}
```

限制：

- 只支持 `.mp3` 和 `.wav`
- Base64 编码后不能超过 10 MB
- 可以继续使用自然语言指令和标签控制合成风格

### 流式兼容模式

官方文档说明 MiMo-V2.5-TTS 系列的低延迟流式输出暂未开放，目前流式接口会在推理完成后一次性返回结果。界面保留“流式兼容模式”，开启后会按文档强制使用 `pcm16` 输出并自动拼接音频片段。

`pcm16` 播放时会自动封装为 24kHz WAV；保存时可保存原始 `.pcm`，也可选择 `.wav` 自动封装。

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
