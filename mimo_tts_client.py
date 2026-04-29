#!/usr/bin/env python3
"""MiMo TTS Playground - Xiaomi MiMo speech synthesis client."""

from __future__ import annotations

import base64
import copy
import io
import json
import os
import re
import threading
import tkinter as tk
import wave
import webbrowser
from dataclasses import dataclass
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".mimo_tts")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
API_BASE = "https://api.xiaomimimo.com/v1"
API_KEY_URL = "https://platform.xiaomimimo.com/#/console/api-keys"
DOC_URL = "https://platform.xiaomimimo.com/docs/zh-CN/usage-guide/speech-synthesis-v2.5"
PCM16_SAMPLE_RATE = 24000
MAX_CLONE_BASE64_BYTES = 10 * 1024 * 1024

MODEL_V25_TTS = "mimo-v2.5-tts"
MODEL_V25_VOICE_DESIGN = "mimo-v2.5-tts-voicedesign"
MODEL_V25_VOICE_CLONE = "mimo-v2.5-tts-voiceclone"
MODEL_V2_TTS = "mimo-v2-tts"

TTS_MODELS = [
    MODEL_V25_TTS,
    MODEL_V25_VOICE_DESIGN,
    MODEL_V25_VOICE_CLONE,
    MODEL_V2_TTS,
]

BUILTIN_VOICES = [
    "mimo_default",
    "冰糖",
    "茉莉",
    "苏打",
    "白桦",
    "Mia",
    "Chloe",
    "Milo",
    "Dean",
]

AUDIO_FORMATS = ["wav", "mp3", "pcm16"]

STYLE_PRESETS = [
    "开心",
    "悲伤",
    "生气",
    "害怕",
    "惊讶",
    "激动",
    "委屈",
    "平静",
    "温柔",
    "冷淡",
    "活泼",
    "严肃",
    "慵懒",
    "俏皮",
    "磁性",
    "圆润",
    "清澈",
    "甜美",
    "沙哑",
    "东北话",
    "四川话",
    "河南话",
    "粤语",
    "台湾腔",
    "孙悟空",
    "林黛玉",
    "唱歌",
]

AUDIO_TAG_PRESETS = [
    "吸气",
    "深吸一口气",
    "叹气",
    "长叹一口气",
    "喘气",
    "屏住呼吸",
    "紧张",
    "害怕",
    "兴奋",
    "疲惫",
    "委屈",
    "撒娇",
    "愧疚",
    "震惊",
    "不耐烦",
    "颤抖",
    "声音颤抖",
    "变调",
    "破音",
    "鼻音",
    "气声",
    "沙哑",
    "微笑",
    "轻笑",
    "大笑",
    "冷笑",
    "抽泣",
    "呜咽",
    "哽咽",
    "嚎哭",
]

VOICE_CLONE_MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}

LEADING_TAG_RE = re.compile(r"^\s*(?:\([^)]*\)|（[^）]*）|\[[^\]]*\])\s*")
SINGING_TAG_RE = re.compile(
    r"^\s*[\(（\[][^)\]）]*(?:唱歌|sing(?:ing)?)[^)\]）]*[\)）\]]",
    re.IGNORECASE,
)


@dataclass
class TTSResult:
    audio: bytes
    format: str


def normalize_model_id(model: str) -> str:
    return model.strip().lower()


def normalize_audio_format(fmt: str) -> str:
    fmt = (fmt or "wav").strip().lower()
    if fmt == "pcm":
        return "pcm16"
    if fmt not in AUDIO_FORMATS:
        return "wav"
    return fmt


def is_voice_design_model(model: str) -> bool:
    return normalize_model_id(model) == MODEL_V25_VOICE_DESIGN


def is_voice_clone_model(model: str) -> bool:
    return normalize_model_id(model) == MODEL_V25_VOICE_CLONE


def uses_builtin_voice(model: str) -> bool:
    return not is_voice_design_model(model) and not is_voice_clone_model(model)


def load_config() -> dict:
    cfg = {
        "api_key": "",
        "api_base": API_BASE,
        "model": MODEL_V25_TTS,
        "voice": "mimo_default",
        "format": "wav",
        "style_instruction": "",
        "voice_clone_path": "",
        "stream": False,
    }
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    cfg["model"] = normalize_model_id(cfg.get("model", MODEL_V25_TTS))
    cfg["format"] = normalize_audio_format(cfg.get("format", "wav"))
    cfg["stream"] = bool(cfg.get("stream", False))
    return cfg


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------


def add_leading_tag(text: str, tag: str) -> str:
    rest = LEADING_TAG_RE.sub("", text.strip(), count=1)
    return f"({tag}){rest}"


def remove_leading_tag(text: str) -> str:
    return LEADING_TAG_RE.sub("", text.strip(), count=1)


def has_singing_tag(text: str) -> bool:
    return bool(SINGING_TAG_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def encode_voice_clone_sample(path: str) -> str:
    path = os.path.expanduser(path.strip())
    if not path:
        raise ValueError("VoiceClone 模型需要选择一个 mp3 或 wav 参考音频")
    if not os.path.isfile(path):
        raise ValueError(f"参考音频不存在: {path}")

    ext = os.path.splitext(path)[1].lower()
    mime_type = VOICE_CLONE_MIME_BY_EXT.get(ext)
    if not mime_type:
        raise ValueError("VoiceClone 参考音频只支持 .mp3 或 .wav")

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    if len(encoded.encode("utf-8")) > MAX_CLONE_BASE64_BYTES:
        raise ValueError("参考音频 Base64 编码后不能超过 10 MB")

    return f"data:{mime_type};base64,{encoded}"


def build_tts_payload(cfg: dict, text: str) -> tuple[dict, str]:
    model = normalize_model_id(cfg["model"])
    user_content = cfg.get("style_instruction", "").strip()
    audio_format = normalize_audio_format(cfg.get("format", "wav"))
    stream = bool(cfg.get("stream", False))

    if is_voice_design_model(model) and not user_content:
        raise ValueError("VoiceDesign 模型需要在“自然语言指令 / 音色描述”中填写音色描述")

    if stream:
        audio_format = "pcm16"

    audio = {"format": audio_format}
    if is_voice_clone_model(model):
        audio["voice"] = encode_voice_clone_sample(cfg.get("voice_clone_path", ""))
    elif uses_builtin_voice(model):
        audio["voice"] = cfg.get("voice", "").strip() or "mimo_default"

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": text},
        ],
        "audio": audio,
    }
    if stream:
        payload["stream"] = True
    return payload, audio_format


def compact_payload_for_log(payload: dict) -> dict:
    compact = copy.deepcopy(payload)
    voice = compact.get("audio", {}).get("voice")
    if isinstance(voice, str) and voice.startswith("data:"):
        prefix = voice.split(",", 1)[0]
        compact["audio"]["voice"] = f"{prefix},<base64 {len(voice)} chars>"
    return compact


def raise_for_api_error(resp: requests.Response):
    if resp.ok:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text
    raise requests.HTTPError(f"{resp.status_code}: {detail}", response=resp)


def extract_non_stream_audio(data: dict) -> str:
    try:
        audio = data["choices"][0]["message"]["audio"]
        return audio["data"]
    except Exception as exc:
        preview = json.dumps(data, ensure_ascii=False)[:500]
        raise ValueError(f"响应中未找到 audio.data: {preview}") from exc


def extract_stream_audio_piece(data: dict) -> str | None:
    try:
        choice = data["choices"][0]
    except Exception:
        return None

    delta = choice.get("delta") or {}
    audio = delta.get("audio")
    if isinstance(audio, dict) and audio.get("data"):
        return audio["data"]

    message = choice.get("message") or {}
    audio = message.get("audio")
    if isinstance(audio, dict) and audio.get("data"):
        return audio["data"]

    return None


def call_tts(cfg: dict, text: str, status_cb=None) -> TTSResult:
    """Call MiMo TTS API and return audio bytes plus the effective format."""
    payload, effective_format = build_tts_payload(cfg, text)
    url = f"{cfg['api_base'].rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "api-key": cfg["api_key"],
    }

    print(f"[TTS] POST {url}")
    print(f"[TTS] payload: {json.dumps(compact_payload_for_log(payload), ensure_ascii=False)}")

    if payload.get("stream"):
        return call_tts_stream(url, headers, payload, effective_format, status_cb)

    if status_cb:
        status_cb("正在请求 API ...")

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"[TTS] status: {resp.status_code}")
    raise_for_api_error(resp)
    data = resp.json()

    if status_cb:
        status_cb("正在解码音频 ...")

    audio_b64 = extract_non_stream_audio(data)
    return TTSResult(audio=base64.b64decode(audio_b64), format=effective_format)


def call_tts_stream(
    url: str,
    headers: dict,
    payload: dict,
    effective_format: str,
    status_cb=None,
) -> TTSResult:
    if status_cb:
        status_cb("正在请求流式兼容接口 ...")

    chunks: list[bytes] = []
    with requests.post(url, headers=headers, json=payload, timeout=120, stream=True) as resp:
        print(f"[TTS] status: {resp.status_code}")
        raise_for_api_error(resp)

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            audio_b64 = extract_stream_audio_piece(data)
            if audio_b64:
                chunks.append(base64.b64decode(audio_b64))
                if status_cb:
                    status_cb(f"已接收音频片段: {len(chunks)}")

    if not chunks:
        raise ValueError("流式响应中未找到 audio.data")

    if status_cb:
        status_cb("正在拼接音频 ...")
    return TTSResult(audio=b"".join(chunks), format=effective_format)


def pcm16_to_wav_bytes(pcm: bytes, sample_rate: int = PCM16_SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def playable_audio_bytes(audio: bytes, fmt: str) -> bytes:
    if normalize_audio_format(fmt) == "pcm16":
        return pcm16_to_wav_bytes(audio)
    return audio


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MiMo TTS Playground")
        self.geometry("820x760")
        self.minsize(720, 680)

        self.cfg = load_config()
        self._audio_data: bytes | None = None
        self._audio_format = "wav"

        self._build_ui()
        self._load_fields()
        self._sync_model_controls()

    # ---- UI construction --------------------------------------------------

    def _build_ui(self):
        frm = ttk.LabelFrame(self, text="设置", padding=8)
        frm.pack(fill="x", padx=10, pady=(10, 0))

        r1 = ttk.Frame(frm)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="API Key:", width=12).pack(side="left")
        self.var_key = tk.StringVar()
        self._ent_key = ttk.Entry(r1, textvariable=self.var_key, show="*")
        self._ent_key.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._show = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            r1,
            text="显示",
            variable=self._show,
            command=lambda: self._ent_key.configure(
                show="" if self._show.get() else "*"
            ),
        ).pack(side="left")
        ttk.Button(r1, text="获取 Key", command=lambda: webbrowser.open(API_KEY_URL)).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(r1, text="2.5 文档", command=lambda: webbrowser.open(DOC_URL)).pack(
            side="left", padx=(4, 0)
        )

        r2 = ttk.Frame(frm)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="API Base:", width=12).pack(side="left")
        self.var_base = tk.StringVar()
        ttk.Entry(r2, textvariable=self.var_base).pack(
            side="left", fill="x", expand=True
        )

        r3 = ttk.Frame(frm)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="模型:", width=12).pack(side="left")
        self.var_model = tk.StringVar()
        self.cbo_model = ttk.Combobox(
            r3,
            textvariable=self.var_model,
            values=TTS_MODELS,
            state="normal",
            width=32,
        )
        self.cbo_model.pack(side="left")
        self.cbo_model.bind("<<ComboboxSelected>>", lambda _e: self._sync_model_controls())
        self.var_stream = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            r3,
            text="流式兼容模式（强制 pcm16）",
            variable=self.var_stream,
        ).pack(side="left", padx=(12, 0))

        r4 = ttk.Frame(frm)
        r4.pack(fill="x", pady=2)
        ttk.Label(r4, text="内置音色:", width=12).pack(side="left")
        self.var_voice = tk.StringVar()
        self.cbo_voice = ttk.Combobox(
            r4,
            textvariable=self.var_voice,
            values=BUILTIN_VOICES,
            state="normal",
            width=18,
        )
        self.cbo_voice.pack(side="left")
        ttk.Label(r4, text=" 输出格式:").pack(side="left", padx=(12, 0))
        self.var_fmt = tk.StringVar()
        ttk.Combobox(
            r4,
            textvariable=self.var_fmt,
            values=AUDIO_FORMATS,
            state="readonly",
            width=7,
        ).pack(side="left")
        self.lbl_model_note = ttk.Label(r4, text="")
        self.lbl_model_note.pack(side="left", padx=(12, 0))

        r5 = ttk.Frame(frm)
        r5.pack(fill="x", pady=2)
        ttk.Label(r5, text="克隆音频:", width=12).pack(side="left")
        self.var_clone_path = tk.StringVar()
        self.ent_clone = ttk.Entry(r5, textvariable=self.var_clone_path)
        self.ent_clone.pack(side="left", fill="x", expand=True)
        self.btn_clone_browse = ttk.Button(r5, text="选择 mp3/wav", command=self._browse_clone_audio)
        self.btn_clone_browse.pack(side="left", padx=(4, 0))

        self.frm_instr = ttk.LabelFrame(
            self,
            text="自然语言指令 / 音色描述（user 消息）",
            padding=8,
        )
        self.frm_instr.pack(fill="x", padx=10, pady=(8, 0))
        self.txt_instr = scrolledtext.ScrolledText(self.frm_instr, height=4, wrap="word")
        self.txt_instr.pack(fill="x")

        frm_tag = ttk.LabelFrame(self, text="2.5 标签控制（assistant 合成文本内）", padding=8)
        frm_tag.pack(fill="x", padx=10, pady=(8, 0))

        tr1 = ttk.Frame(frm_tag)
        tr1.pack(fill="x")
        ttk.Label(tr1, text="开头风格:").pack(side="left")
        self.var_style = tk.StringVar()
        ttk.Combobox(
            tr1,
            textvariable=self.var_style,
            values=STYLE_PRESETS,
            width=16,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(tr1, text="添加 (风格)", command=self._on_add_leading_tag).pack(
            side="left", padx=(8, 0)
        )
        self.btn_singing = ttk.Button(tr1, text="添加 (唱歌)", command=self._on_add_singing_tag)
        self.btn_singing.pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(tr1, text="移除开头标签", command=self._on_remove_leading_tag).pack(
            side="left", padx=(4, 0)
        )

        tr2 = ttk.Frame(frm_tag)
        tr2.pack(fill="x", pady=(6, 0))
        ttk.Label(tr2, text="行内音频标签:").pack(side="left")
        self.var_audio_tag = tk.StringVar()
        ttk.Combobox(
            tr2,
            textvariable=self.var_audio_tag,
            values=AUDIO_TAG_PRESETS,
            width=16,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(tr2, text="插入 [标签]", command=self._on_insert_audio_tag).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            tr2,
            text="开头风格用于整体语气；行内标签插入到光标处控制局部呼吸、笑哭、节奏等。",
        ).pack(side="left", padx=(8, 0))

        frm_text = ttk.LabelFrame(self, text="要合成的文本（assistant 消息）", padding=8)
        frm_text.pack(fill="both", padx=10, pady=(8, 0), expand=True)
        self.txt = scrolledtext.ScrolledText(frm_text, height=10, wrap="word")
        self.txt.pack(fill="both", expand=True)

        bf = ttk.Frame(self, padding=8)
        bf.pack(fill="x", padx=10)

        self.btn_gen = ttk.Button(bf, text="合成语音", command=self._on_gen)
        self.btn_gen.pack(side="left", padx=(0, 4))

        self.btn_play = ttk.Button(
            bf, text="播放", command=self._on_play, state="disabled"
        )
        self.btn_play.pack(side="left", padx=4)

        self.btn_stop = ttk.Button(bf, text="停止", command=self._on_stop)
        self.btn_stop.pack(side="left", padx=4)

        self.btn_save = ttk.Button(
            bf, text="保存音频", command=self._on_save, state="disabled"
        )
        self.btn_save.pack(side="left", padx=4)

        ttk.Button(bf, text="保存配置", command=self._on_save_cfg).pack(side="right")

        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(
            self, textvariable=self.var_status, relief="sunken", anchor="w"
        ).pack(fill="x", padx=10, pady=(0, 10))

    # ---- field load -------------------------------------------------------

    def _load_fields(self):
        c = self.cfg
        self.var_key.set(c.get("api_key", ""))
        self.var_base.set(c.get("api_base", API_BASE))
        self.var_model.set(c.get("model", MODEL_V25_TTS))
        self.var_voice.set(c.get("voice", "mimo_default"))
        self.var_fmt.set(c.get("format", "wav"))
        self.var_clone_path.set(c.get("voice_clone_path", ""))
        self.var_stream.set(bool(c.get("stream", False)))
        self.txt_instr.insert("1.0", c.get("style_instruction", ""))
        self.txt.insert("1.0", "你好，我是 MiMo，很高兴认识你！")

    # ---- helpers ----------------------------------------------------------

    def _collect(self) -> dict:
        return {
            "api_key": self.var_key.get().strip(),
            "api_base": self.var_base.get().strip() or API_BASE,
            "model": normalize_model_id(self.var_model.get()),
            "voice": self.var_voice.get().strip(),
            "format": normalize_audio_format(self.var_fmt.get()),
            "style_instruction": self.txt_instr.get("1.0", "end").strip(),
            "voice_clone_path": self.var_clone_path.get().strip(),
            "stream": self.var_stream.get(),
        }

    def _set_busy(self, busy: bool, msg: str = ""):
        self.btn_gen.configure(state="disabled" if busy else "normal")
        if msg:
            self.var_status.set(msg)

    def _sync_model_controls(self):
        model = normalize_model_id(self.var_model.get())
        voice_state = "disabled" if not uses_builtin_voice(model) else "normal"
        clone_state = "normal" if is_voice_clone_model(model) else "disabled"
        self.cbo_voice.configure(state=voice_state)
        self.ent_clone.configure(state=clone_state)
        self.btn_clone_browse.configure(state=clone_state)
        self.btn_singing.configure(state="normal" if uses_builtin_voice(model) else "disabled")

        if is_voice_design_model(model):
            self.frm_instr.configure(text="自然语言指令 / 音色描述（user 消息，VoiceDesign 必填）")
            self.lbl_model_note.configure(text="VoiceDesign 不使用内置音色")
        elif is_voice_clone_model(model):
            self.frm_instr.configure(text="自然语言指令 / 风格控制（user 消息，可选）")
            self.lbl_model_note.configure(text="VoiceClone 使用参考音频作为 voice")
        else:
            self.frm_instr.configure(text="自然语言指令 / 风格控制（user 消息，可选）")
            self.lbl_model_note.configure(text="内置音色模型可使用 voice")

    def _browse_clone_audio(self):
        path = filedialog.askopenfilename(
            title="选择 VoiceClone 参考音频",
            filetypes=[
                ("音频样本", "*.mp3 *.wav"),
                ("MP3", "*.mp3"),
                ("WAV", "*.wav"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.var_clone_path.set(path)

    # ---- tag actions ------------------------------------------------------

    def _on_add_leading_tag(self):
        tag = self.var_style.get().strip()
        if not tag:
            messagebox.showinfo("提示", "请输入或选择一个风格")
            return
        text = self.txt.get("1.0", "end").strip()
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", add_leading_tag(text, tag))
        self.var_status.set(f"已添加 ({tag})")

    def _on_add_singing_tag(self):
        text = self.txt.get("1.0", "end").strip()
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", add_leading_tag(text, "唱歌"))
        self.var_status.set("已添加 (唱歌)")

    def _on_remove_leading_tag(self):
        text = self.txt.get("1.0", "end").strip()
        new_text = remove_leading_tag(text)
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", new_text)
        self.var_status.set("已移除开头标签")

    def _on_insert_audio_tag(self):
        tag = self.var_audio_tag.get().strip()
        if not tag:
            messagebox.showinfo("提示", "请输入或选择一个行内音频标签")
            return
        self.txt.insert("insert", f"[{tag}]")
        self.var_status.set(f"已插入 [{tag}]")

    # ---- synthesis --------------------------------------------------------

    def _validate_before_gen(self, cfg: dict, text: str) -> bool:
        if not cfg["api_key"]:
            messagebox.showwarning("提示", "请先填写 API Key")
            return False
        if not text:
            messagebox.showwarning("提示", "请输入要合成的文本")
            return False
        if is_voice_design_model(cfg["model"]) and not cfg["style_instruction"]:
            messagebox.showwarning("提示", "VoiceDesign 模型需要填写音色描述")
            return False
        if is_voice_clone_model(cfg["model"]) and not cfg["voice_clone_path"]:
            messagebox.showwarning("提示", "VoiceClone 模型需要选择 mp3 或 wav 参考音频")
            return False
        if has_singing_tag(text) and not uses_builtin_voice(cfg["model"]):
            messagebox.showwarning(
                "提示",
                "(唱歌) 标签只支持内置音色 TTS 模型，不支持 VoiceDesign/VoiceClone",
            )
            return False
        return True

    def _on_gen(self):
        cfg = self._collect()
        text = self.txt.get("1.0", "end").strip()
        if not self._validate_before_gen(cfg, text):
            return

        self._set_busy(True, "正在合成 ...")
        self.btn_play.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self._audio_data = None
        self._audio_format = "wav"

        def work():
            try:
                result = call_tts(
                    cfg,
                    text,
                    status_cb=lambda m: self.after(0, self.var_status.set, m),
                )
                self._audio_data = result.audio
                self._audio_format = result.format
                self.after(0, self._on_done)
            except Exception as exc:
                self.after(0, self._on_error, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self):
        self._set_busy(False, "合成完成，正在播放 ...")
        self.btn_play.configure(state="normal")
        self.btn_save.configure(state="normal")
        self._on_play()

    def _on_error(self, msg: str):
        self._set_busy(False, f"错误: {msg}")
        messagebox.showerror("合成失败", msg)

    # ---- playback ---------------------------------------------------------

    def _on_play(self):
        if not self._audio_data:
            return

        def work():
            try:
                import time

                import pygame

                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                audio_for_playback = playable_audio_bytes(
                    self._audio_data,
                    self._audio_format,
                )
                buf = io.BytesIO(audio_for_playback)
                pygame.mixer.music.load(buf)
                pygame.mixer.music.play()
                self.after(0, self.var_status.set, "正在播放 ...")
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                self.after(0, self.var_status.set, "播放完成")
            except Exception as exc:
                self.after(0, self.var_status.set, f"播放错误: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def _on_stop(self):
        try:
            import pygame

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self.var_status.set("已停止")

    def _on_save(self):
        if not self._audio_data:
            return

        fmt = normalize_audio_format(self._audio_format)
        if fmt == "pcm16":
            def_ext = ".pcm"
            filetypes = [
                ("PCM16 原始文件", "*.pcm"),
                ("WAV 文件（自动封装 24kHz PCM16）", "*.wav"),
                ("所有文件", "*.*"),
            ]
        else:
            def_ext = f".{fmt}"
            filetypes = [
                (f"{fmt.upper()} 文件", f"*.{fmt}"),
                ("所有文件", "*.*"),
            ]

        path = filedialog.asksaveasfilename(
            defaultextension=def_ext,
            filetypes=filetypes,
        )
        if not path:
            return

        data = self._audio_data
        if fmt == "pcm16" and path.lower().endswith(".wav"):
            data = pcm16_to_wav_bytes(data)

        with open(path, "wb") as f:
            f.write(data)
        self.var_status.set(f"已保存到 {path}")

    def _on_save_cfg(self):
        self.cfg = self._collect()
        save_config(self.cfg)
        self.var_status.set("配置已保存")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    app = App()
    app.mainloop()
