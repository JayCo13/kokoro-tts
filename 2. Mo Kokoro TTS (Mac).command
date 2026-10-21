#!/bin/bash
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Chua cai dat! Hay chay '1. Cai dat (Mac).command' truoc."; read -n1; exit 1; }
./.venv/bin/python app/update.py
HF_HUB_OFFLINE=1 exec ./.venv/bin/python app/web.py
