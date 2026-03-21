@echo off
setlocal
set CONDA_PREFIX=C:\Jinhy\Develop\Environment\miniconda3
set TCL_LIBRARY=%CONDA_PREFIX%\Library\lib\tcl8.6
set TK_LIBRARY=%CONDA_PREFIX%\Library\lib\tk8.6

echo === MiMo-TTS Playground 打包 ===
pyinstaller --noconfirm --onefile --windowed --name "MiMo-TTS-Playground" ^
  --paths "%CONDA_PREFIX%\Library\bin" ^
  --add-binary "%CONDA_PREFIX%\Library\bin\tcl86t.dll;." ^
  --add-binary "%CONDA_PREFIX%\Library\bin\tk86t.dll;." ^
  mimo_tts_client.py

echo.
echo 打包完成！输出目录: dist\
pause
