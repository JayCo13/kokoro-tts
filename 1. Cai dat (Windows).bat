@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cai dat Kokoro TTS ===
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo -^> Cai cong cu uv...
  powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)
where uv >nul 2>nul || goto :err
echo -^> Tao moi truong Python 3.11...
uv venv --clear --python 3.11 .venv || goto :err
echo -^> Cai thu vien (~1 GB, vai phut)...
uv pip install --python .venv\Scripts\python.exe -r app\requirements.txt || goto :err
echo -^> Tai mo hinh (~2 GB)...
set HF_HUB_DISABLE_XET=1
set PYTHONUTF8=1
.venv\Scripts\python.exe app\setup_models.py || goto :err
echo.
echo XONG! Tu gio bam dup "2. Mo Kokoro TTS (Windows).bat" de su dung.
pause
exit /b 0
:err
echo.
echo LOI: cai dat that bai. Kiem tra ket noi mang roi chay lai file nay.
pause
exit /b 1
