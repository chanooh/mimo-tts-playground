#!/usr/bin/env python3
"""MiMo-V2-TTS Playground - Xiaomi MiMo 语音合成客户端"""

import base64
import json
import os
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".mimo_tts")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
API_BASE = "https://api.xiaomimimo.com/v1"
API_KEY_URL = "https://platform.xiaomimimo.com/#/console/api-keys"

STYLE_PRESETS = [
    "开心",
    "生气",
    "温柔",
    "悄悄话",
    "东北话",
    "四川话",
    "粤语",
    "台湾腔",
    "焦急",
    "悲伤",
    "紧张",
    "虚弱",
    "激昂慷慨",
    "慵懒",
]


def load_config() -> dict:
    cfg = {
        "api_key": "",
        "api_base": API_BASE,
        "model": "mimo-v2-tts",
        "voice": "mimo_default",
        "format": "wav",
    }
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Style tag helpers
# ---------------------------------------------------------------------------

STYLE_RE = re.compile(r"^<style>(.*?)</style>\s*", re.DOTALL)


def extract_style(text: str):
    """Return (style, rest) if text starts with <style>...</style>, else (None, text)."""
    m = STYLE_RE.match(text)
    if m:
        return m.group(1), text[m.end():]
    return None, text


def wrap_style(text: str, style: str) -> str:
    """Prepend <style>...</style> to text."""
    return f"<style>{style}</style>{text}"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def call_tts(cfg: dict, text: str, status_cb=None) -> bytes:
    """Call MiMo TTS API and return raw audio bytes."""
    url = f"{cfg['api_base'].rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "api-key": cfg["api_key"],
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": text},
        ],
        "audio": {
            "format": cfg["format"],
            "voice": cfg["voice"],
        },
    }

    print(f"[TTS] POST {url}")
    print(f"[TTS] payload: {json.dumps(payload, ensure_ascii=False)}")

    if status_cb:
        status_cb("正在请求 API …")

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"[TTS] status: {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()

    if status_cb:
        status_cb("正在解码音频 …")

    audio_b64 = data["choices"][0]["message"]["audio"]["data"]
    return base64.b64decode(audio_b64)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MiMo-V2-TTS Playground")
        self.geometry("680x620")
        self.minsize(600, 520)

        self.cfg = load_config()
        self._audio_data: bytes | None = None

        self._build_ui()
        self._load_fields()

    # ---- UI construction --------------------------------------------------

    def _build_ui(self):
        # -- settings --
        frm = ttk.LabelFrame(self, text="设置", padding=8)
        frm.pack(fill="x", padx=10, pady=(10, 0))

        # API Key row
        r1 = ttk.Frame(frm)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="API Key:", width=10).pack(side="left")
        self.var_key = tk.StringVar()
        self._ent = ttk.Entry(r1, textvariable=self.var_key, show="*")
        self._ent.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._show = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            r1,
            text="显示",
            variable=self._show,
            command=lambda: self._ent.configure(
                show="" if self._show.get() else "*"
            ),
        ).pack(side="left")
        ttk.Button(r1, text="获取 Key", command=lambda: webbrowser.open(API_KEY_URL)).pack(
            side="left", padx=(4, 0)
        )

        # API Base row
        r2 = ttk.Frame(frm)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="API Base:", width=10).pack(side="left")
        self.var_base = tk.StringVar()
        ttk.Entry(r2, textvariable=self.var_base).pack(
            side="left", fill="x", expand=True
        )

        # Model / Voice / Format row
        r3 = ttk.Frame(frm)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="模型:", width=10).pack(side="left")
        self.var_model = tk.StringVar()
        ttk.Entry(r3, textvariable=self.var_model, width=14).pack(side="left")
        ttk.Label(r3, text=" 语音:").pack(side="left")
        self.var_voice = tk.StringVar()
        ttk.Entry(r3, textvariable=self.var_voice, width=14).pack(side="left")
        ttk.Label(r3, text=" 格式:").pack(side="left")
        self.var_fmt = tk.StringVar()
        ttk.Combobox(
            r3,
            textvariable=self.var_fmt,
            values=["wav", "mp3", "pcm"],
            state="readonly",
            width=5,
        ).pack(side="left")

        # -- style bar --
        frm_style = ttk.LabelFrame(self, text="风格指令 <style>标签", padding=8)
        frm_style.pack(fill="x", padx=10, pady=(8, 0))

        sr = ttk.Frame(frm_style)
        sr.pack(fill="x")
        ttk.Label(sr, text="预设:").pack(side="left")
        self.var_style = tk.StringVar()
        ttk.Combobox(
            sr,
            textvariable=self.var_style,
            values=STYLE_PRESETS,
            width=12,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(sr, text="添加标签", command=self._on_add_style).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(sr, text="移除标签", command=self._on_remove_style).pack(
            side="left", padx=(4, 0)
        )
        ttk.Label(
            sr, text="  在下拉框输入或选择风格，点击添加会自动在文本前插入 <style>xxx</style>"
        ).pack(side="left")

        # -- text input --
        frm2 = ttk.LabelFrame(self, text="要合成的文本", padding=8)
        frm2.pack(fill="both", padx=10, pady=(8, 0), expand=True)
        self.txt = scrolledtext.ScrolledText(frm2, height=10, wrap="word")
        self.txt.pack(fill="both", expand=True)

        # -- buttons --
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

        ttk.Button(bf, text="保存配置", command=self._on_save_cfg).pack(
            side="right"
        )

        # -- status bar --
        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(
            self, textvariable=self.var_status, relief="sunken", anchor="w"
        ).pack(fill="x", padx=10, pady=(0, 10))

    # ---- field load -------------------------------------------------------

    def _load_fields(self):
        c = self.cfg
        self.var_key.set(c.get("api_key", ""))
        self.var_base.set(c.get("api_base", API_BASE))
        self.var_model.set(c.get("model", "mimo-v2-tts"))
        self.var_voice.set(c.get("voice", "mimo_default"))
        self.var_fmt.set(c.get("format", "wav"))
        self.txt.insert("1.0", "你好，我是MiMo，很高兴认识你！")

    # ---- helpers ----------------------------------------------------------

    def _collect(self) -> dict:
        return {
            "api_key": self.var_key.get().strip(),
            "api_base": self.var_base.get().strip(),
            "model": self.var_model.get().strip(),
            "voice": self.var_voice.get().strip(),
            "format": self.var_fmt.get(),
        }

    def _set_busy(self, busy: bool, msg: str = ""):
        self.btn_gen.configure(state="disabled" if busy else "normal")
        if msg:
            self.var_status.set(msg)

    # ---- style tag actions ------------------------------------------------

    def _on_add_style(self):
        style = self.var_style.get().strip()
        if not style:
            messagebox.showinfo("提示", "请输入或选择一个风格")
            return
        text = self.txt.get("1.0", "end").strip()
        existing, rest = extract_style(text)
        if existing:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", wrap_style(rest, style))
        else:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", wrap_style(text, style))
        self.var_status.set(f"已添加 <style>{style}</style>")

    def _on_remove_style(self):
        text = self.txt.get("1.0", "end").strip()
        style, rest = extract_style(text)
        if style:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", rest)
            self.var_status.set("已移除 <style> 标签")
        else:
            self.var_status.set("未检测到 <style> 标签")

    # ---- synthesis --------------------------------------------------------

    def _on_gen(self):
        cfg = self._collect()
        text = self.txt.get("1.0", "end").strip()
        if not cfg["api_key"]:
            messagebox.showwarning("提示", "请先填写 API Key")
            return
        if not text:
            messagebox.showwarning("提示", "请输入要合成的文本")
            return
        self._set_busy(True, "正在合成 …")
        self.btn_play.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self._audio_data = None

        def work():
            try:
                audio = call_tts(
                    cfg,
                    text,
                    status_cb=lambda m: self.after(0, self.var_status.set, m),
                )
                self._audio_data = audio
                self.after(0, self._on_done)
            except Exception as exc:
                self.after(0, self._on_error, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self):
        self._set_busy(False, "合成完成，正在播放 …")
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
                import io as _io
                import time

                import pygame

                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                buf = _io.BytesIO(self._audio_data)  # type: ignore[arg-type]
                pygame.mixer.music.load(buf)
                pygame.mixer.music.play()
                self.after(0, self.var_status.set, "正在播放 …")
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
        fmt = self.var_fmt.get()
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[
                (f"{fmt.upper()} 文件", f"*.{fmt}"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            with open(path, "wb") as f:
                f.write(self._audio_data)
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
