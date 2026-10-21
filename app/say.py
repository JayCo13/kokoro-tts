#!/usr/bin/env python3
"""Kokoro TTS - doc van ban tieng Anh thanh giong noi.
Cach dung:
  ./say "Hello world"                     # doc va phat ngay
  ./say "Hello" -v am_michael -o hi.wav   # chon giong, luu file
  ./say -f input.txt -o book.wav          # doc tu file van ban
  ./say --list                            # xem danh sach giong
"""
import argparse, sys, subprocess, warnings
warnings.filterwarnings("ignore")

VOICES = {
    "My - nu":  ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_nova", "af_aoede", "af_kore"],
    "My - nam": ["am_michael", "am_fenrir", "am_puck", "am_adam", "am_echo", "am_eric", "am_liam", "am_onyx"],
    "Anh - nu": ["bf_emma", "bf_isabella", "bf_alice", "bf_lily"],
    "Anh - nam": ["bm_george", "bm_fable", "bm_lewis", "bm_daniel"],
}

p = argparse.ArgumentParser()
p.add_argument("text", nargs="?")
p.add_argument("-f", "--file")
p.add_argument("-v", "--voice", default="af_heart")
p.add_argument("-s", "--speed", type=float, default=1.0)
p.add_argument("-o", "--out", default="output.wav")
p.add_argument("--no-play", action="store_true")
p.add_argument("--list", action="store_true")
a = p.parse_args()

if a.list:
    for k, v in VOICES.items():
        print(f"{k}: {', '.join(v)}")
    sys.exit()

text = open(a.file, encoding="utf-8").read() if a.file else a.text
if not text:
    p.error("Can nhap van ban hoac -f file.txt")

import numpy as np, soundfile as sf
from kokoro import KPipeline
lang = "b" if a.voice.startswith("b") else "a"
pipe = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
chunks = [audio for _, _, audio in pipe(text, voice=a.voice, speed=a.speed)]
sf.write(a.out, np.concatenate(chunks), 24000)
print(f"Da luu: {a.out}")
if not a.no_play:
    if sys.platform == "darwin": subprocess.run(["afplay", a.out])
    elif sys.platform == "win32":
        import winsound; winsound.PlaySound(a.out, winsound.SND_FILENAME)
    else: subprocess.run(["aplay", a.out])
