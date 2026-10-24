#!/bin/bash
# Cai them bo doc SONG NGU (OmniVoice): giong Viet doc tieng Anh chuan. Tuy chon, tai ~4 GB, can Internet.
cd "$(dirname "$0")"
echo "=== Cai them bo doc Song ngu (OmniVoice) ==="
[ -x .venv/bin/python ] || { echo "Hay chay '1. Cai dat (Mac).command' truoc."; read -n1; exit 1; }
UV="$(command -v uv || true)"; [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
[ -z "$UV" ] && [ -x /opt/homebrew/bin/uv ] && UV=/opt/homebrew/bin/uv
[ -z "$UV" ] && { echo "Khong tim thay uv - hay chay lai '1. Cai dat (Mac).command'"; read -n1; exit 1; }
echo "-> Tao moi truong rieng cho OmniVoice..."
"$UV" venv -q --clear --python 3.11 .venv-omni || { echo "LOI tao moi truong"; read -n1; exit 1; }
echo "-> Cai thu vien (~1 GB)..."
"$UV" pip install --python .venv-omni/bin/python -r app/requirements-omni.txt || { echo "LOI cai thu vien"; read -n1; exit 1; }
echo "-> Tai mo hinh OmniVoice (~3 GB)..."
HF_HUB_DISABLE_XET=1 .venv-omni/bin/python -c "from huggingface_hub import snapshot_download as s; s('k2-fsa/OmniVoice'); print('OK')" || { echo "LOI tai mo hinh, hay chay lai file nay"; read -n1; exit 1; }
echo ""; echo "XONG! Mo lai Kokoro TTS, chon giong Viet roi chon bo doc '🌏 Song ngu'."
read -n 1 -s -r -p "Bam phim bat ky de dong..."
