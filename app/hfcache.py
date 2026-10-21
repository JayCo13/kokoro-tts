"""Tien ich cho cache Hugging Face.
ONNX Runtime moi tu choi doc file '.data' neu file .onnx la symlink tro sang thu muc blobs
(kieu luu mac dinh cua huggingface_hub tren macOS/Linux). Ham duoi doi symlink thanh hard link
(khong ton them dung luong), roi nap lai VieNeu."""
import os, shutil
from pathlib import Path

PREFIXES = ("models--pnnbao-ump--", "models--OpenMOSS-Team--")

def fix_symlinks():
    from huggingface_hub.constants import HF_HUB_CACHE
    root = Path(HF_HUB_CACHE); n = 0
    if not root.exists(): return 0
    for repo in root.iterdir():
        if not repo.name.startswith(PREFIXES): continue
        for p in (repo / "snapshots").rglob("*"):
            if not p.is_symlink(): continue
            tgt = p.resolve(); tmp = p.with_name(p.name + ".tmp")
            try: os.link(tgt, tmp)
            except OSError: shutil.copy2(tgt, tmp)
            os.replace(tmp, p); n += 1
    return n

def load_vieneu():
    from vieneu import Vieneu
    try:
        return Vieneu(backend="onnx")
    except Exception as e:
        if "External data" not in str(e): raise
        fix_symlinks()
        return Vieneu(backend="onnx")
