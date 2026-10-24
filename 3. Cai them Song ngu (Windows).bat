@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cai them bo doc Song ngu (OmniVoice) ===
echo Luu y: may khong co card NVIDIA se doc song ngu RAT CHAM.
if not exist .venv\Scripts\python.exe (
  echo Hay chay "1. Cai dat (Windows).bat" truoc.
  pause
  exit /b 1
)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul || goto :err
echo -^> Tao moi truong rieng cho OmniVoice...
uv venv -q --clear --python 3.11 .venv-omni || goto :err
echo -^> Cai thu vien (~1 GB)...
uv pip install --python .venv-omni\Scripts\python.exe -r app\requirements-omni.txt || goto :err
echo -^> Tai mo hinh OmniVoice (~3 GB)...
set HF_HUB_DISABLE_XET=1
.venv-omni\Scripts\python.exe -c "from huggingface_hub import snapshot_download as s; s('k2-fsa/OmniVoice'); print('OK')" || goto :err
echo.
echo XONG! Mo lai Kokoro TTS, chon giong Viet roi chon bo doc Song ngu.
pause
exit /b 0
:err
echo.
echo LOI: cai dat that bai. Kiem tra mang roi chay lai file nay.
pause
exit /b 1
