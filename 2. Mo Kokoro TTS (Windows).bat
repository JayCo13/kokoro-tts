@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Chua cai dat! Hay chay "1. Cai dat (Windows).bat" truoc.
  pause
  exit /b 1
)
set PYTHONUTF8=1
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
.venv\Scripts\python.exe app\update.py
set HF_HUB_OFFLINE=1
echo Dang khoi dong Kokoro TTS... (giu cua so nay mo trong luc dung, dong cua so de tat)
.venv\Scripts\python.exe app\web.py
pause
