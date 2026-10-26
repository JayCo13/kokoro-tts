"""Tai san tat ca mo hinh (chi can chay 1 lan sau khi cai dat). Sau buoc nay ung dung chay offline."""
import os, sys, warnings, logging
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")      # tai qua HTTP thuong, tranh bi treo
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from huggingface_hub import snapshot_download, hf_hub_download

def step(i, msg): print(f"\n[{i}/4] {msg}", flush=True)

step(1, "Tai mo hinh giong Anh (Kokoro, ~350 MB)...")
snapshot_download("hexgrad/Kokoro-82M", allow_patterns=["*.json", "*.pth", "voices/*.pt"])
from kokoro import KPipeline
for lang in ("a", "b"):
    p = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    list(p("Hello there.", voice="af_heart" if lang == "a" else "bf_emma"))
print("   OK")

step(2, "Tai mo hinh giong Viet (VieNeu-TTS v3 Turbo, ~0,6 GB)...")
import hfcache
eng = hfcache.load_vieneu()
eng.infer("Xin chào, cài đặt thành công.", voice="Hải Đăng")
import myvoices; myvoices.ensure_clone_files()   # file cho chuc nang nhan ban giong
hfcache.fix_symlinks()
print("   OK")

step(3, "Tai mo hinh kiem tra (PhoWhisper-small, ~1 GB)...")
for f in ("config.json", "generation_config.json", "preprocessor_config.json", "tokenizer_config.json",
          "special_tokens_map.json", "vocab.json", "merges.txt", "normalizer.json", "added_tokens.json", "tokenizer.json"):
    try: hf_hub_download("vinai/PhoWhisper-small", f)
    except Exception: pass
hf_hub_download("vinai/PhoWhisper-small", "pytorch_model.bin")
import checker
print("   Nghe thu:", checker.transcribe(eng.infer("Xin chào các bạn.", voice="Hải Đăng")))

step(4, "Hoan tat! Tat ca mo hinh da san sang, tu gio co the dung offline.")
