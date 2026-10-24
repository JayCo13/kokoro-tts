#!/bin/bash
# Cai dat Kokoro TTS tren macOS (chi can chay 1 lan). Can Internet; tai khoang 3 GB.
cd "$(dirname "$0")"
echo "=== Cai dat Kokoro TTS ==="
UV="$(command -v uv || true)"; [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
if [ -z "$UV" ]; then
  echo "-> Cai cong cu uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh || exit 1
  UV="$HOME/.local/bin/uv"
fi
echo "-> Tao moi truong Python 3.11..."
"$UV" venv --clear --python 3.11 .venv || { echo "LOI: khong tao duoc moi truong Python"; read -n1; exit 1; }
echo "-> Cai thu vien (~1 GB, vai phut)..."
"$UV" pip install --python .venv/bin/python -r app/requirements.txt || { echo "LOI: cai thu vien that bai"; read -n1; exit 1; }
echo "-> Tai mo hinh (~2 GB)..."
HF_HUB_DISABLE_XET=1 .venv/bin/python app/setup_models.py || { echo "LOI: tai mo hinh that bai, hay chay lai file nay"; read -n1; exit 1; }
chmod +x "2. Mo Kokoro TTS (Mac).command"
echo ""; echo "XONG! Tu gio bam dup '2. Mo Kokoro TTS (Mac).command' de su dung."
read -n 1 -s -r -p "Bam phim bat ky de dong cua so..."
