#!/bin/bash
echo "=== MiMo-TTS Playground 打包 (macOS) ==="
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "MiMo-TTS-Playground" mimo_tts_client.py
echo ""
echo "打包完成！输出目录: dist/"
