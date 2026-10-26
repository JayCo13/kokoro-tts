"""Ket noi ung dung chinh voi tien trinh phu OmniVoice (bo doc song ngu Viet-Anh).
Giong Viet cua VieNeu duoc dung lam MAU GIONG: OmniVoice nhan ban am sac do roi doc ca bai,
ca phan tieng Anh, bang cung mot giong."""
import io, json, os, re, subprocess, sys, time, urllib.request
import numpy as np, soundfile as sf

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
PORT = 7861
URL = f"http://127.0.0.1:{PORT}"
PY = os.path.join(ROOT, ".venv-omni", "Scripts" if sys.platform == "win32" else "bin",
                  "python.exe" if sys.platform == "win32" else "python")
REF_DIR = os.path.join(APP, "omni_refs")
REF_TEXT = "Xin chào các bạn, hôm nay mình sẽ kể cho các bạn nghe một câu chuyện rất thú vị về cuộc sống hằng ngày."
_proc = None

def available():
    if not os.path.exists(PY): return False
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache("k2-fsa/OmniVoice", "config.json"), str)
    except Exception:
        return False

def _healthy():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=2) as r: return r.read() == b"ok"
    except Exception:
        return False

def ensure_worker(progress=None, timeout=300):
    global _proc
    if _healthy(): return
    if _proc is None or _proc.poll() is not None:
        log = open(os.path.join(APP, "omni_worker.log"), "w")
        env = dict(os.environ, HF_HUB_OFFLINE="1", PYTHONUTF8="1")
        _proc = subprocess.Popen([PY, os.path.join(APP, "omni_worker.py")], stdout=log, stderr=subprocess.STDOUT, env=env, cwd=APP)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _healthy(): return
        if _proc.poll() is not None:
            raise RuntimeError("Bộ đọc song ngữ không khởi động được (xem app/omni_worker.log)")
        if progress: progress(f"Đang khởi động bộ đọc song ngữ… {int(time.time() - t0)} giây (lần đầu khoảng 1 phút)")
        time.sleep(1)
    raise RuntimeError("Bộ đọc song ngữ khởi động quá lâu")

def ref_path(voice_key, make_ref):
    """Mau giong cho tung giong Viet (tao 1 lan bang VieNeu, luu lai)."""
    os.makedirs(REF_DIR, exist_ok=True)
    p = os.path.join(REF_DIR, voice_key + ".wav")
    if not os.path.exists(p):
        open(p, "wb").write(make_ref(REF_TEXT))
    return p

def split_chunks(text, max_chars=220):
    text = re.sub(r"\[[^\]]*\]", " ", text)                       # the bieu cam: OmniVoice khong ho tro
    out = []
    for para in [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]:
        sents = re.split(r"(?<=[.!?…])\s+", para)
        cur = ""
        for s in sents:
            while len(s) > max_chars:                                 # cau qua dai: cat o dau phay
                cut = s.rfind(",", 0, max_chars); cut = cut if cut > 40 else max_chars
                if cur: out.append((cur, False)); cur = ""
                out.append((s[:cut + 1].strip(), False)); s = s[cut + 1:].strip()
            if cur and len(cur) + 1 + len(s) > max_chars:
                out.append((cur, False)); cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur: out.append((cur, True))                               # True = het doan van
    return out

def synth(text, voice_key, make_ref, speed=1.0, progress=None, ref=None, ref_text=None):
    import soxr
    ensure_worker(progress)
    if ref is None: ref, ref_text = ref_path(voice_key, make_ref), REF_TEXT
    chunks = split_chunks(text)
    parts = []
    for i, (c, para_end) in enumerate(chunks):
        if progress: progress(f"Song ngữ: đang đọc đoạn {i + 1}/{len(chunks)}…")
        body = json.dumps({"text": c, "ref_audio": ref, "ref_text": ref_text, "speed": speed}).encode()
        req = urllib.request.Request(URL + "/tts", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            w, sr = sf.read(io.BytesIO(r.read()), dtype="float32")
        parts.append(w)
        if i < len(chunks) - 1: parts.append(np.zeros(int(sr * (0.6 if para_end else 0.3)), np.float32))
    w = np.concatenate(parts) if parts else np.zeros(0, np.float32)
    return soxr.resample(w, 24000, 48000).astype(np.float32), len(chunks)
