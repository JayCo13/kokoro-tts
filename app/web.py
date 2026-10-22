#!/usr/bin/env python3
"""Giao dien web nho cho Kokoro TTS - chay offline tren may. Mo http://localhost:7860"""
import io, json, threading, warnings, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
warnings.filterwarnings("ignore")
import numpy as np, soundfile as sf
from kokoro import KPipeline

PORT = 7860
VOICES = {
    "Mỹ – Nữ":  ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_nova", "af_aoede", "af_kore"],
    "Mỹ – Nam": ["am_michael", "am_fenrir", "am_puck", "am_adam", "am_echo", "am_eric", "am_liam", "am_onyx"],
    "Anh – Nữ": ["bf_emma", "bf_isabella", "bf_alice", "bf_lily"],
    "Anh – Nam": ["bm_george", "bm_fable", "bm_lewis", "bm_daniel"],
}
# Giong tu pha: tron giong goc + ha tong (semitone) + toc do
PRESETS = {
    "x_midnight":  dict(name="Kể chuyện đêm khuya", blend="am_onyx,am_fenrir",   lang="a", pitch=-2.0, speed=0.88, desc="Mỹ · trầm, chậm, u tối"),
    "x_detective": dict(name="Thám tử",             blend="bm_george,bm_fable",  lang="b", pitch=-1.5, speed=0.92, desc="Anh · điềm tĩnh, sắc sảo"),
    "x_professor": dict(name="Giáo sư",             blend="bm_lewis,bm_george",  lang="b", pitch=-1.0, speed=0.90, desc="Anh · ấm, uyên bác"),
    "x_noir":      dict(name="Noir",                blend="am_michael,am_onyx",  lang="a", pitch=-2.5, speed=0.90, desc="Mỹ · khàn trầm kiểu phim noir"),
    "x_podcast":   dict(name="Podcast bí ẩn",       blend="am_michael,bm_george",lang="a", pitch=-1.0, speed=0.95, desc="Ấm, cuốn hút, hợp bàn luận"),
    "x_fenrir":    dict(name="Fenrir trầm",         blend="am_fenrir",           lang="a", pitch=-1.5, speed=0.92, desc="Mỹ · dày, chắc giọng"),
}
# ---- Tieng Viet: VieNeu-TTS v3 Turbo (ONNX, CPU, 48 kHz) ----
import unicodedata
VI_LIST = [  # (ten, gioi tinh, vung, phong cach, de cu)
    ("Hải Đăng","Nam","Bắc","tự nhiên",1), ("Thiện Minh","Nam","Bắc","kể chuyện",1), ("Thiền Tâm Đức","Nam","Bắc","kể chuyện",1),
    ("Adam bựa","Nam","Bắc","tự nhiên",1), ("Quang Sơn","Nam","Trung","tự nhiên",1), ("Minh Đức","Nam","Bắc","tin tức",0),
    ("Phạm Tuyên","Nam","Bắc","tự nhiên",0), ("Xuân Vĩnh","Nam","Bắc","tự nhiên",0), ("Thanh Bình","Nam","Bắc","kể chuyện",0),
    ("Quốc Tuấn","Nam","Bắc","tự nhiên",0), ("Thái Sơn","Nam","Nam","kể chuyện",0), ("Minh Triết","Nam","Nam","tin tức",0),
    ("Đức Trí","Nam","Nam","đọc truyện",0), ("Adam","Nam","Nam","tự nhiên",0),
    ("Trúc Ly","Nữ","Bắc","tự nhiên",1), ("Mai Anh","Nữ","Bắc","tin tức",1), ("Ngọc Huyền","Nữ","Bắc","tự nhiên",1),
    ("Thùy Dung","Nữ","Nam","tin tức",1), ("Ngọc Trân","Nữ","Trung","tự nhiên",1), ("Ngọc Linh","Nữ","Bắc","kể chuyện",0),
    ("Đoan Trang","Nữ","Bắc","tự nhiên",0), ("Quỳnh Anh","Nữ","Bắc","đọc truyện",0), ("Thục Đoan","Nữ","Nam","kể chuyện",0),
    ("Mỹ Duyên","Nữ","Nam","đọc truyện",0), ("Kim Thanh","Nữ","Nam","đọc truyện",0),
]
def _slug(n):
    n = unicodedata.normalize("NFD", n.replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode()
    return "vi_" + "_".join(n.lower().split())
VI_VOICES = {_slug(n): dict(name=n, g=g, r=r, st=st, pick=p) for n, g, r, st, p in VI_LIST}
_vi, _vi_load, _vi_lock = None, threading.Lock(), threading.Lock()
# Tam trang cho giong Viet: temperature (do bien thien bieu cam) + toc do + tong giong (semitone)
MOODS = {
    "natural": dict(label="😊 Tự nhiên",            temp=0.60, speed=1.00, pitch=0.0),
    "lively":  dict(label="🎉 Sôi nổi, vui tươi",   temp=0.80, speed=1.08, pitch=0.7),
    "calm":    dict(label="🌙 Trầm lắng, nhẹ nhàng", temp=0.50, speed=0.92, pitch=-0.7),
    "serious": dict(label="📰 Nghiêm túc, đều giọng", temp=0.40, speed=1.00, pitch=-0.3),
    "mystery": dict(label="🕯️ Hồi hộp, bí ẩn",      temp=0.55, speed=0.88, pitch=-1.5),
    "sad":     dict(label="🌧️ Buồn, chậm rãi",      temp=0.50, speed=0.85, pitch=-1.0),
}
import subprocess, shutil
def _find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p: return p
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()   # ffmpeg dong goi san (Mac/Windows)
    except Exception:
        return "/opt/homebrew/bin/ffmpeg"
FFMPEG = _find_ffmpeg()
def _atempo(t):
    parts = []
    while t < 0.5: parts.append("atempo=0.5"); t /= 0.5
    while t > 2.0: parts.append("atempo=2.0"); t /= 2.0
    parts.append(f"atempo={t:.4f}"); return ",".join(parts)
def stretch(audio, sr, speed=1.0, pitch=0.0):
    """Doi toc do (giu nguyen tong) va/hoac tong giong bang ffmpeg."""
    if abs(speed - 1) < 1e-3 and abs(pitch) < 1e-3: return audio
    r = 2 ** (pitch / 12)
    flt = (f"asetrate={round(sr * r)},aresample={sr}," if abs(pitch) >= 1e-3 else "") + _atempo(speed / r)
    p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                        "-af", flt, "-f", "f32le", "-ar", str(sr), "-ac", "1", "pipe:1"],
                       input=np.asarray(audio, dtype=np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32)
def vi_engine():
    global _vi
    with _vi_load:
        if _vi is None:
            import hfcache
            _vi = hfcache.load_vieneu()
            _install_ipa_hook()
    return _vi
_pipes, _lock = {}, threading.Lock()
import os
PREV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previews")
os.makedirs(PREV_DIR, exist_ok=True)
ALL_VOICES = list(PRESETS) + list(VI_VOICES) + [v for vs in VOICES.values() for v in vs]
def vname(v): return VI_VOICES[v]["name"] if v in VI_VOICES else PRESETS[v]["name"] if v in PRESETS else v.split("_", 1)[1].capitalize()
def spec(v):
    return PRESETS.get(v) or dict(blend=v, lang="b" if v.startswith("b") else "a", pitch=0.0, speed=1.0)
import re
PRON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pronounce.txt")
_PRON_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pronounce.default.txt")
if not os.path.exists(PRON_FILE) and os.path.exists(_PRON_DEFAULT):   # may moi: lay tu dien mac dinh
    import shutil as _sh; _sh.copyfile(_PRON_DEFAULT, PRON_FILE)
_IPA = []          # danh sach phien am IPA, marker = "zqxipa" + chu cai
def _ipa_marker(ipa):
    if ipa not in _IPA: _IPA.append(ipa)
    i = _IPA.index(ipa); tag = ""
    while True:
        tag = chr(97 + i % 26) + tag; i //= 26
        if not i: break
    return "zqxipa" + tag
_MARK_RX = re.compile(r"zqxipa([a-z]+)", re.I)
def _ipa_of(tag):
    i = 0
    for ch in tag.lower(): i = i * 26 + (ord(ch) - 97)
    return _IPA[i] if i < len(_IPA) else ""
def _pron_lines():
    """Tu dien mac dinh (cap nhat theo ban moi) + tu dien rieng cua may nay (uu tien, doc sau)."""
    lines = []
    for f in (_PRON_DEFAULT, PRON_FILE):
        try: lines += open(f, encoding="utf-8").read().splitlines()
        except FileNotFoundError: pass
    return lines
def load_pron():
    rules = []
    for line in _pron_lines():
        if True:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = (x.strip() for x in line.split("=", 1))
            if k.lower().startswith("en:"): continue          # luat chi dung trong cum tieng Anh -> load_en_map()
            if v.startswith("/") and v.endswith("/") and len(v) > 2:
                v = " " + _ipa_marker(v[1:-1].strip()) + " "
            if k and v: rules.append((re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)", re.I), v))
    return rules
def load_en_map():
    """Dong 'en:TU = cach doc': chi ap dung khi TU nam trong cum tieng Anh (vd 'en:do = đu' khong dung den 'do đó')."""
    m = {}
    for line in _pron_lines():
        line = line.strip()
        if not line.lower().startswith("en:") or "=" not in line: continue
        k, v = (x.strip() for x in line[3:].split("=", 1))
        if v.startswith("/") and v.endswith("/") and len(v) > 2: v = _ipa_marker(v[1:-1].strip())
        if k and v: m[k.lower()] = v
    return m
def apply_pron(text):
    for rx, v in load_pron(): text = rx.sub(lambda _m: v, text)
    return re.sub(r"  +", " ", text)

def _install_ipa_hook():
    """Cho phep chen phien am IPA truc tiep: thay marker bang am vi, phan con lai van qua G2P goc."""
    import vieneu.v3turbo as vt
    from sea_g2p import punc_norm
    orig = vt.phonemize_text_with_emotions
    if getattr(orig, "_ipa_hooked", False): return
    PUN = ",.!?;:…"
    def hooked(chunk):
        if not _MARK_RX.search(chunk): return orig(chunk)
        parts = _MARK_RX.split(chunk); out = ""
        for i, part in enumerate(parts):
            if i % 2 == 1:
                ph = _ipa_of(part)
            else:
                p = part.strip()
                if not p: continue
                lead = ""
                while p and p[0] in PUN: lead += p[0]; p = p[1:].lstrip()
                ph = orig(p) if p else ""
                if ph and p and p[-1] not in PUN and ph.endswith("."): ph = ph[:-1]
                if lead: out = out.rstrip() + lead
            if not ph: continue
            out = (out + " " + ph) if out and not ph[0] in PUN else out + ph
        return punc_norm(out.strip())
    hooked._ipa_hooked = True
    vt.phonemize_text_with_emotions = hooked

PROGRESS = {"text": ""}
EN_AUTO = {"Nam": "am_michael", "Nữ": "af_heart"}     # giong ban xu mac dinh theo gioi tinh giong Viet

def _kokoro_48k(text, en_voice):
    import soxr
    p = spec(en_voice)
    with _lock:
        chunks = [a for _, _, a in pipe(p["lang"])(text, voice=p["blend"], speed=p["speed"])]
    w = np.concatenate([np.asarray(c, dtype=np.float32) for c in chunks]) if chunks else np.zeros(0, np.float32)
    return soxr.resample(w, 24000, 48000).astype(np.float32)

def synth(text, voice, speed=1.0, mood="natural", seed=1, check=False, report=None, native_en=True, en_voice="auto"):
    if voice in VI_VOICES:
        import entag, longform, mixed
        m = MOODS.get(mood, MOODS["natural"])
        eng = vi_engine()
        en_map = load_en_map()
        segs = mixed.split_segments(text) if native_en else [("vi", text)]
        if en_voice not in ALL_VOICES or en_voice.startswith("vi_"): en_voice = EN_AUTO[VI_VOICES[voice]["g"]]
        parts, tot = [], {"chunks": 0, "regenerated": 0, "checked": False}
        with _vi_lock:
            for si, (lang, seg) in enumerate(segs):
                tag = f"Phần {si + 1}/{len(segs)} · " if len(segs) > 1 else ""
                if lang == "en":
                    PROGRESS["text"] = f"{tag}Giọng bản xứ đọc câu tiếng Anh…"
                    parts.append(("en", seg, _kokoro_48k(seg, en_voice))); continue
                seg_t = entag.tag_english(apply_pron(seg), en_map)   # tu Anh le con lai -> <en>..</en>
                def prog(i, n, what, tag=tag): PROGRESS["text"] = f"{tag}Đang {what} đoạn {i + 1}/{n}…"
                rpt = {}
                w = longform.synth_long(eng, seg_t, VI_VOICES[voice]["name"], temperature=m["temp"], seed=int(seed) + si,
                                        check=check, progress=prog, report=rpt)
                for k in ("chunks", "regenerated"): tot[k] += rpt.get(k) or 0
                tot["checked"] = tot["checked"] or bool(rpt.get("checked"))
                parts.append(("vi", seg, w))
            PROGRESS["text"] = ""
        if report is not None: report.update(tot, english=sum(1 for p_ in parts if p_[0] == "en"))
        audio = parts[0][2] if len(parts) == 1 else mixed.join(parts)
        audio = stretch(audio, 48000, speed * m["speed"], m["pitch"])
        buf = io.BytesIO(); sf.write(buf, np.asarray(audio, dtype=np.float32), 48000, format="WAV"); return buf.getvalue()
    p = spec(voice); r = 2 ** (p["pitch"] / 12)
    with _lock:
        chunks = [a for _, _, a in pipe(p["lang"])(text, voice=p["blend"], speed=p["speed"] * speed / r)]
    buf = io.BytesIO(); sf.write(buf, np.concatenate(chunks), int(round(24000 * r)), format="WAV"); return buf.getvalue()
def preview(voice):
    path = os.path.join(PREV_DIR, voice + ".wav")
    if not os.path.exists(path):
        txt = (f"Xin chào, mình là {vname(voice)}. Mình đang ôn thi IELTS để đi du học." if voice in VI_VOICES else
               "The door was locked from the inside. And yet... the room was empty." if voice in PRESETS
               else f"Hi, I'm {vname(voice)}. This is how my voice sounds.")
        data = synth(txt, voice)
        open(path, "wb").write(data)
    return open(path, "rb").read()
def pipe(lang):
    if lang not in _pipes:
        _pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    return _pipes[lang]

def chip(v, label, small):
    return f'<button type="button" class="chip" data-v="{v}" data-n="{label}"><span class="pl">▶</span>{label}<small>{small}</small></button>'
def vi_chip(k):
    d = VI_VOICES[k]
    return chip(k, ("⭐ " if d["pick"] else "") + d["name"], f'{d["r"]} · {d["st"]}')
opts = (''.join(f'<div class="grp"><div class="gl">🇻🇳 Tiếng Việt – {g}</div><div class="chips">'
                + "".join(vi_chip(k) for k, d in VI_VOICES.items() if d["g"] == g) + "</div></div>" for g in ("Nam", "Nữ"))
        + '<div class="grp"><div class="gl">🕵️ Trinh thám · Nam trầm ấm</div><div class="chips">'
        + "".join(chip(k, p["name"], p["desc"]) for k, p in PRESETS.items()) + "</div></div>"
        + "".join(f'<div class="grp"><div class="gl">{g}</div><div class="chips">'
                  + "".join(chip(v, vname(v), v) for v in vs) + "</div></div>" for g, vs in VOICES.items()))

HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Giọng đọc AI</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--fg:#1d1d1f;--mut:#6e6e73;--line:#e2e0da;--acc:#c2410c;--acc2:#ea580c}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--fg:#f2f2f2;--mut:#9a9a9a;--line:#333;--acc:#fb923c;--acc2:#fdba74}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;display:flex;justify-content:center;padding:40px 16px}
.c{width:100%;max-width:640px}h1{font-size:28px;margin:0 0 4px;letter-spacing:-.02em}p.s{color:var(--mut);margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}
textarea{width:100%;min-height:180px;resize:vertical;border:1px solid var(--line);border-radius:10px;padding:12px;font:inherit;background:transparent;color:inherit}
textarea:focus,select:focus{outline:2px solid var(--acc);outline-offset:1px}
.row{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0;align-items:end}.row>div{flex:1;min-width:180px}
label{display:block;font-size:13px;color:var(--mut);margin-bottom:6px}
select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--card);color:inherit}
input[type=range]{width:100%;accent-color:var(--acc)}
button{width:100%;padding:12px;border:0;border-radius:10px;background:var(--acc);color:#fff;font:600 16px inherit;cursor:pointer}
button:hover{background:var(--acc2)}button:disabled{opacity:.5;cursor:wait}
#out{margin-top:16px;display:none}audio{width:100%}#out a{color:var(--acc);font-size:14px}
.grp{margin-bottom:10px}.gl{font-size:12px;color:var(--mut);margin:0 0 6px;text-transform:uppercase;letter-spacing:.04em}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{width:auto;display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--fg);font:500 14px inherit;cursor:pointer}
.chip:hover{background:transparent;border-color:var(--acc)}.chip small{color:var(--mut);font-size:11px;font-weight:400}
.chip .pl{font-size:10px;color:var(--mut)}.chip.sel{border-color:var(--acc);background:color-mix(in srgb,var(--acc) 14%,transparent)}
.chip.sel .pl{color:var(--acc)}.chip.playing .pl{animation:p .8s infinite alternate}@keyframes p{to{opacity:.2}}
.chip.loading{opacity:.6;cursor:wait}
.hint{font-size:13px;color:var(--mut);margin-top:6px}.hint code{font-size:12px}input[type=range]:disabled{opacity:.35}
summary{cursor:pointer;font-size:14px;color:var(--fg)}
#msg{color:var(--mut);font-size:14px;margin-top:10px;min-height:1em}.cnt{float:right}
</style></head><body><div class="c">
<h1>Kokoro TTS</h1><p class="s">Biến văn bản tiếng Việt &amp; tiếng Anh thành giọng nói — chạy hoàn toàn trên máy bạn. <span style="opacity:.6;font-size:12px">· __VER__</span></p>
<div class="card">
<label>Văn bản <span class="cnt" id="cnt">0 ký tự</span></label>
<textarea id="t">Hello! This is Kokoro, an open-source voice running right here on your Mac.</textarea>
<div id="hint" class="hint" style="display:none">Giọng Việt: có thể chèn <code>[cười]</code> <code>[thở dài]</code> <code>[hắng giọng]</code> vào văn bản.</div>
<details id="dictbox" style="display:none;margin-top:10px"><summary>📖 Từ điển phát âm (sửa từ tiếng Anh bị đọc sai)</summary>
<p class="hint">Mỗi dòng: <code>TỪ = cách đọc</code>. Ví dụ <code>IELTS = /ˈaɪɛlts/</code> (phiên âm IPA giữa hai dấu /, chuẩn nhất), <code>IELTS = eye elts</code> (viết lại kiểu tiếng Anh), <code>SAT = &lt;en&gt;S A T&lt;/en&gt;</code> (đánh vần tiếng Anh), hoặc <code>Zalo = da lô</code> (viết kiểu Việt). Thêm <code>en:</code> ở đầu để chỉ sửa khi từ nằm trong câu tiếng Anh, ví dụ <code>en:do = đu</code> (không ảnh hưởng chữ "do" tiếng Việt). Dòng bắt đầu bằng # là ghi chú.</p>
<textarea id="dict" style="min-height:140px;font:13px/1.5 ui-monospace,Menlo,monospace"></textarea>
<button type="button" id="dsave" style="margin-top:8px;width:auto;padding:8px 16px;font-size:14px">💾 Lưu từ điển</button> <span id="dmsg" class="hint"></span>
</details>
<div id="enrow" style="display:none;margin-top:12px"><label class="hint" style="cursor:pointer"><input type="checkbox" id="nen" checked> 🇬🇧 <b>Câu tiếng Anh đọc bằng giọng bản xứ</b>: tự tách câu/cụm tiếng Anh cho giọng người bản xứ đọc rồi ghép lại (từ tiếng Anh lẻ như "deadline" vẫn do giọng Việt đọc)</label>
<select id="env" style="margin-top:6px;max-width:360px"><option value="auto">Tự động (nam: Michael · nữ: Heart)</option><option value="af_heart">Heart — Mỹ, nữ</option><option value="af_bella">Bella — Mỹ, nữ</option><option value="af_nicole">Nicole — Mỹ, nữ</option><option value="af_sarah">Sarah — Mỹ, nữ</option><option value="af_sky">Sky — Mỹ, nữ</option><option value="af_nova">Nova — Mỹ, nữ</option><option value="af_aoede">Aoede — Mỹ, nữ</option><option value="af_kore">Kore — Mỹ, nữ</option><option value="am_michael">Michael — Mỹ, nam</option><option value="am_fenrir">Fenrir — Mỹ, nam</option><option value="am_puck">Puck — Mỹ, nam</option><option value="am_adam">Adam — Mỹ, nam</option><option value="am_echo">Echo — Mỹ, nam</option><option value="am_eric">Eric — Mỹ, nam</option><option value="am_liam">Liam — Mỹ, nam</option><option value="am_onyx">Onyx — Mỹ, nam</option><option value="bf_emma">Emma — Anh, nữ</option><option value="bf_isabella">Isabella — Anh, nữ</option><option value="bf_alice">Alice — Anh, nữ</option><option value="bf_lily">Lily — Anh, nữ</option><option value="bm_george">George — Anh, nam</option><option value="bm_fable">Fable — Anh, nam</option><option value="bm_lewis">Lewis — Anh, nam</option><option value="bm_daniel">Daniel — Anh, nam</option></select></div>
<label id="chkrow" class="hint" style="display:none;margin-top:12px;cursor:pointer"><input type="checkbox" id="chk" checked> 🔍 <b>Kiểm tra kỹ</b>: nghe lại từng đoạn bằng PhoWhisper, đoạn nào đọc lỗi/đọc lướt thì tự đọc lại (chậm hơn một chút)</label>
<div id="moodrow" style="display:none;margin-top:14px"><label>Tâm trạng (giọng Việt)</label><div class="chips"><button type="button" class="chip mood" data-m="natural">😊 Tự nhiên</button><button type="button" class="chip mood" data-m="lively">🎉 Sôi nổi, vui tươi</button><button type="button" class="chip mood" data-m="calm">🌙 Trầm lắng, nhẹ nhàng</button><button type="button" class="chip mood" data-m="serious">📰 Nghiêm túc, đều giọng</button><button type="button" class="chip mood" data-m="mystery">🕯️ Hồi hộp, bí ẩn</button><button type="button" class="chip mood" data-m="sad">🌧️ Buồn, chậm rãi</button></div></div>
<label style="margin-top:16px">Giọng <span class="cnt">bấm để nghe thử · đang chọn: <b id="vn">af_heart</b></span></label>
<div id="voices">__OPTS__</div>
<div class="row"><div><label>Tốc độ: <b id="sv">1.0×</b></label><input id="s" type="range" min="0.5" max="1.8" step="0.05" value="1"></div></div>
<div style="display:flex;gap:8px"><button id="b" style="flex:1">▶ Đọc</button><button id="rr" type="button" title="Đọc lại cùng văn bản theo một kiểu khác" style="width:auto;padding:12px 14px;background:transparent;color:var(--fg);border:1px solid var(--line)">🎲 Kiểu khác</button></div>
<div id="seedrow" class="hint">Kiểu đọc #<b id="sd">1</b> — giữ nguyên số này thì lần sau đọc y hệt. Nghe chưa ưng thì bấm 🎲.</div><div id="msg"></div>
<div id="out"><audio id="a" controls></audio><a id="dl" download="kokoro.wav">⬇ Tải file .wav</a></div>
</div></div>
<script>
const $=id=>document.getElementById(id),t=$("t"),b=$("b"),s=$("s");
const upd=()=>$("cnt").textContent=t.value.length+" ký tự";t.oninput=upd;upd();const EN_T=t.value,VI_T="Xin chào! Đây là giọng đọc tiếng Việt, chạy ngay trên máy của bạn.";
s.oninput=()=>$("sv").textContent=(+s.value).toFixed(2).replace(/0$/,"")+"×";
let voice="af_heart";try{voice=localStorage.getItem("voice")||voice}catch(e){}
let mood="natural";try{mood=localStorage.getItem("mood")||mood}catch(e){}
const moods=[...document.querySelectorAll(".mood")];function selm(m){mood=m;moods.forEach(x=>x.classList.toggle("sel",x.dataset.m===m));try{localStorage.setItem("mood",m)}catch(e){}}
moods.forEach(x=>x.onclick=()=>selm(x.dataset.m));selm(mood);
fetch("/dict").then(r=>r.text()).then(x=>$("dict").value=x);
$("dsave").onclick=async()=>{const r=await fetch("/dict",{method:"POST",headers:{"Content-Type":"text/plain; charset=utf-8"},body:$("dict").value});$("dmsg").textContent=r.ok?"Đã lưu "+(await r.text())+" từ ✓":"Lỗi khi lưu"};
const pv=new Audio(),chips=[...document.querySelectorAll(".chip:not(.mood)")];
function sel(v){if(!chips.some(c=>c.dataset.v===v))v="af_heart";voice=v;const c0=chips.find(c=>c.dataset.v===v);$("vn").textContent=c0?c0.dataset.n:v;chips.forEach(c=>c.classList.toggle("sel",c.dataset.v===v));try{localStorage.setItem("voice",v)}catch(e){}const vi=v.startsWith("vi_");$("hint").style.display=vi?"block":"none";$("moodrow").style.display=vi?"block":"none";$("chkrow").style.display=vi?"block":"none";$("enrow").style.display=vi?"block":"none";$("dictbox").style.display=vi?"block":"none";if(vi&&t.value===EN_T){t.value=VI_T;upd()}else if(!vi&&t.value===VI_T){t.value=EN_T;upd()}}
sel(voice);
pv.onended=pv.onpause=()=>chips.forEach(c=>c.classList.remove("playing"));
chips.forEach(c=>c.onclick=()=>{sel(c.dataset.v);$("a").pause();pv.pause();
 c.classList.add("loading");pv.src="/preview/"+c.dataset.v;
 pv.oncanplay=()=>{c.classList.remove("loading");c.classList.add("playing")};
 pv.onerror=()=>{c.classList.remove("loading");$("msg").textContent="Không phát được bản nghe thử"};
 pv.play().catch(()=>{});});
let seed=1;try{seed=+localStorage.getItem("seed")||1}catch(e){}$("sd").textContent=seed;
$("rr").onclick=()=>{seed=1+Math.floor(Math.random()*99999);$("sd").textContent=seed;try{localStorage.setItem("seed",seed)}catch(e){}b.click()};
try{$("chk").checked=localStorage.getItem("check")!=="0";$("nen").checked=localStorage.getItem("nen")!=="0";$("env").value=localStorage.getItem("env")||"auto"}catch(e){}
$("nen").onchange=()=>{try{localStorage.setItem("nen",$("nen").checked?"1":"0")}catch(e){}};$("env").onchange=()=>{try{localStorage.setItem("env",$("env").value)}catch(e){}};
$("chk").onchange=()=>{try{localStorage.setItem("check",$("chk").checked?"1":"0")}catch(e){}};
b.onclick=async()=>{if(!t.value.trim())return;b.disabled=true;$("msg").textContent="Đang tạo giọng nói…";const t0=Date.now();
const poll=setInterval(async()=>{try{const p=await (await fetch("/progress")).json();if(p.text)$("msg").textContent=p.text+" ("+((Date.now()-t0)/1000).toFixed(0)+" giây)"}catch(e){}},1000);
try{const r=await fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t.value,voice:voice,mood:mood,speed:+s.value,seed:seed,check:$("chk").checked,native_en:$("nen").checked,en_voice:$("env").value})});
if(!r.ok)throw new Error(await r.text());const u=URL.createObjectURL(await r.blob());
pv.pause();$("a").src=u;$("dl").href=u;$("dl").download=voice+".wav";$("out").style.display="block";$("a").play();
let extra="";try{const rp=JSON.parse(r.headers.get("X-Report")||"{}");if(rp.english){extra+=" · "+rp.english+" câu tiếng Anh đọc bằng giọng bản xứ"}if(rp.chunks){extra+=" · "+rp.chunks+" đoạn"+(rp.checked?", đã kiểm tra, đọc lại "+rp.regenerated+" đoạn lỗi":"")}}catch(e){}
$("msg").textContent="Xong sau "+((Date.now()-t0)/1000).toFixed(1)+" giây"+extra;}
catch(e){$("msg").textContent="Lỗi: "+e.message}finally{clearInterval(poll);b.disabled=false}};
t.onkeydown=e=>{if((e.metaKey||e.ctrlKey)&&e.key==="Enter")b.click()};
</script></body></html>""".replace("__OPTS__", opts)

def _version():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(root, ".git")): return "bản phát triển"
    try: return "phiên bản " + open(os.path.join(root, ".version")).read().strip()[:7]
    except Exception: return "phiên bản cài đặt"
HTML = HTML.replace("__VER__", _version())

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/progress":
            return self._send(200, json.dumps(PROGRESS, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if self.path == "/dict":
            try: body = open(PRON_FILE, encoding="utf-8").read().encode()
            except FileNotFoundError: body = b""
            return self._send(200, body, "text/plain; charset=utf-8")
        if self.path.startswith("/preview/"):
            v = self.path.split("/")[-1]
            if v not in ALL_VOICES: return self._send(404, b"unknown voice", "text/plain")
            try: return self._send(200, preview(v), "audio/wav")
            except Exception as e: return self._send(500, str(e).encode(), "text/plain; charset=utf-8")
        self._send(200, HTML.encode(), "text/html; charset=utf-8")
    def do_POST(self):
        if self.path == "/dict":
            data = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
            open(PRON_FILE, "w", encoding="utf-8").write(data)
            return self._send(200, f"{len(load_pron())}".encode(), "text/plain")
        if self.path != "/tts": return self._send(404, b"not found", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            voice = d.get("voice", "af_heart"); text = d["text"].strip()
            rpt = {}
            body = synth(text, voice, float(d.get("speed", 1)), d.get("mood", "natural"), d.get("seed", 1), bool(d.get("check", True)), rpt,
                         bool(d.get("native_en", True)), d.get("en_voice", "auto"))
            self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Report", json.dumps({k: rpt.get(k) for k in ("chunks", "checked", "regenerated", "english")}))
            self.end_headers(); self.wfile.write(body)
        except Exception as e:
            self._send(500, str(e).encode(), "text/plain; charset=utf-8")

if __name__ == "__main__":
    import socket, sys
    with socket.socket() as _s:
        if _s.connect_ex(("127.0.0.1", PORT)) == 0:      # da co server chay roi -> chi mo trinh duyet
            print(f"Kokoro TTS dang chay san tai http://localhost:{PORT}")
            if not os.environ.get("KOKORO_NO_BROWSER"): webbrowser.open(f"http://localhost:{PORT}")
            sys.exit(0)
    print("Dang nap mo hinh..."); pipe("a")
    threading.Thread(target=lambda: [preview(v) for v in ALL_VOICES], daemon=True).start()
    def _warm_asr():
        try:
            import checker
            if checker.available(): checker._load()
        except Exception as e: print("PhoWhisper chua san sang:", e)
    threading.Thread(target=_warm_asr, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Kokoro TTS dang chay tai http://localhost:{PORT}  (Ctrl+C de tat)")
    if not os.environ.get("KOKORO_NO_BROWSER"): webbrowser.open(f"http://localhost:{PORT}")
    srv.serve_forever()
