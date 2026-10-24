"""Tien trinh phu chay OmniVoice (moi truong .venv-omni rieng, tranh xung dot thu vien voi ung dung chinh).
HTTP noi bo 127.0.0.1:7861
  GET  /health                          -> "ok" khi mo hinh da nap
  POST /tts  {text, ref_audio, ref_text, speed}  -> WAV 24 kHz
Tu tat sau IDLE_MIN phut khong dung de tra RAM.
"""
import io, json, os, sys, threading, time, warnings
os.environ.setdefault("HF_HUB_OFFLINE", "1")
warnings.filterwarnings("ignore")
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import numpy as np, soundfile as sf, torch
from omnivoice import OmniVoice

PORT = int(os.environ.get("OMNI_PORT", "7861"))
IDLE_MIN = float(os.environ.get("OMNI_IDLE_MIN", "20"))
if torch.cuda.is_available(): DEV, DT = "cuda:0", torch.float16
elif torch.backends.mps.is_available(): DEV, DT = "mps", torch.float16
else: DEV, DT = "cpu", torch.float32
print(f"[omni] nap mo hinh tren {DEV}...", flush=True)
MODEL = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=DEV, dtype=DT)
PROMPTS, LOCK, LAST = {}, threading.Lock(), [time.time()]
print("[omni] san sang", flush=True)

def prompt_for(ref_audio, ref_text):
    key = (ref_audio, os.path.getmtime(ref_audio))
    if key not in PROMPTS:
        PROMPTS[key] = MODEL.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text)
    return PROMPTS[key]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self._send(200, b"ok", "text/plain")
    def do_POST(self):
        try:
            d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with LOCK:
                LAST[0] = time.time()
                p = prompt_for(d["ref_audio"], d.get("ref_text") or None)
                out = MODEL.generate(text=d["text"], voice_clone_prompt=p, speed=float(d.get("speed") or 1.0))
                LAST[0] = time.time()
            buf = io.BytesIO(); sf.write(buf, np.asarray(out[0], dtype=np.float32), 24000, format="WAV")
            self._send(200, buf.getvalue(), "audio/wav")
        except Exception as e:
            self._send(500, str(e).encode(), "text/plain; charset=utf-8")

def _idle_watch():
    while True:
        time.sleep(30)
        if not LOCK.locked() and time.time() - LAST[0] > IDLE_MIN * 60:
            print("[omni] lau khong dung -> tat de tra RAM", flush=True); os._exit(0)

threading.Thread(target=_idle_watch, daemon=True).start()
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
