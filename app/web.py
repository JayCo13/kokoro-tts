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
            import myvoices; myvoices.register_all(_vi)          # giong nhan ban cua nguoi dung
    return _vi
_pipes, _lock = {}, threading.Lock()
import os
PREV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previews")
os.makedirs(PREV_DIR, exist_ok=True)
ALL_VOICES = list(PRESETS) + list(VI_VOICES) + [v for vs in VOICES.values() for v in vs]
import myvoices
def _add_mine(m):
    k = m["key"]
    VI_VOICES[k] = dict(name=myvoices.vieneu_name(m["id"]), disp=m["name"], g=m["g"], r=m["r"], st="giọng của tôi", pick=0, mine=m)
    if k not in ALL_VOICES: ALL_VOICES.append(k)
for _m in myvoices.list_voices(): _add_mine(_m)
def vname(v): return VI_VOICES[v].get("disp") or VI_VOICES[v]["name"] if v in VI_VOICES else PRESETS[v]["name"] if v in PRESETS else v.split("_", 1)[1].capitalize()
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
_omni_lock = threading.Lock()
def _synth_omni(text, voice, speed, mood, report):
    import omni
    m = MOODS.get(mood, MOODS["natural"])
    def make_ref(t):                                   # mau giong: VieNeu doc 1 cau thuan Viet
        return synth(t, voice, 1.0, "natural", 1, True)
    def prog(msg): PROGRESS["text"] = msg
    # Tu tieng Anh dung le (vd "No", "Yes") de bi doc kieu Viet -> ap dung dong 'en:' trong tu dien (no = nô...)
    import entag
    text = re.sub(r"</?en>", "", entag.tag_english(text, load_en_map(), single_only=True))
    with _omni_lock:
        mine = VI_VOICES[voice].get("mine")
        ref = (os.path.join(myvoices.DIR, mine["id"] + ".wav"), mine.get("ref_text") or None) if mine else (None, None)
        audio, n = omni.synth(text, voice, make_ref, speed=1.0, progress=prog, ref=ref[0], ref_text=ref[1])
        PROGRESS["text"] = ""
    if report is not None: report.update(chunks=n, engine="omni", checked=False, regenerated=0)
    audio = stretch(audio, 48000, speed * m["speed"], m["pitch"])
    buf = io.BytesIO(); sf.write(buf, np.asarray(audio, dtype=np.float32), 48000, format="WAV"); return buf.getvalue()

def synth(text, voice, speed=1.0, mood="natural", seed=1, check=False, report=None, engine="vieneu"):
    if voice in VI_VOICES and engine == "omni":
        return _synth_omni(text, voice, speed, mood, report)
    if voice in VI_VOICES:
        text = apply_pron(text)
        import entag; text = entag.tag_english(text, load_en_map())   # cum tieng Anh -> <en>..</en> de doc kieu Anh
        m = MOODS.get(mood, MOODS["natural"])
        eng = vi_engine()
        with _vi_lock:
            import longform
            def prog(i, n, what): PROGRESS["text"] = f"Đang {what} đoạn {i + 1}/{n}…"
            audio = longform.synth_long(eng, text, VI_VOICES[voice]["name"], temperature=m["temp"], seed=int(seed),
                                        check=check, progress=prog, report=report)
            PROGRESS["text"] = ""
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

def chip(v, label, small, q=""):
    return (f'<button type="button" class="chip vrow" data-v="{v}" data-n="{label}" data-q="{(label + " " + small + " " + q).lower()}">'
            f'<span class="pl" aria-hidden="true">▶</span><span class="vname">{label}</span><small>{small}</small></button>')
def vi_chip(k):
    d = VI_VOICES[k]
    return chip(k, ("⭐ " if d["pick"] else "") + d["name"], f'{d["g"]} · {d["r"]} · {d["st"]}', d["name"])
MINE_HTML = """<div class="mine">
<button type="button" id="newv" class="newv">＋ Tạo giọng mới từ giọng thật</button>
<form id="newform" class="newform" hidden>
 <p class="hint">Ghi âm ở nơi yên tĩnh, đọc rõ và tự nhiên câu dưới đây (khoảng 8 giây). Hoặc chọn một file ghi âm 3–10 giây chỉ có một người nói.</p>
 <blockquote id="sample">Xin chào các bạn, hôm nay mình sẽ kể cho các bạn nghe một câu chuyện rất thú vị về cuộc sống hằng ngày.</blockquote>
 <div class="recrow"><button type="button" id="recb">● Ghi âm</button><span id="rect" class="hint">tối đa 12 giây</span><label class="filebtn">Chọn file…<input type="file" id="vfile" accept="audio/*" hidden></label></div>
 <audio id="vprev" controls hidden></audio>
 <label class="fld">Tên giọng<input id="vname" maxlength="40" placeholder="Ví dụ: Giọng của Tài"></label>
 <div class="row2"><label class="fld">Giới tính<select id="vg"><option>Nam</option><option>Nữ</option></select></label>
 <label class="fld">Vùng miền<select id="vr"><option>Bắc</option><option>Trung</option><option>Nam</option></select></label></div>
 <label class="check"><input type="checkbox" id="vok"><span>Đây là giọng của tôi, hoặc tôi đã được người đó đồng ý cho dùng giọng.</span></label>
 <div class="recrow"><button type="submit" id="vsave">Tạo giọng</button><button type="button" id="vcancel" class="linkbtn">Huỷ</button></div>
 <div id="vmsg" class="hint" aria-live="polite"></div>
</form>
<div id="mylist" class="vlist"></div>
<p id="myempty" class="hint">Chưa có giọng nào. Bấm “Tạo giọng mới” để nhân bản giọng của bạn.</p>
</div>"""
def _grp(title, inner):
    return f'<div class="grp"><h3 class="gl">{title}</h3><div class="vlist">{inner}</div></div>'
opts = ('<div class="tabp" data-tab="vi">'
        + "".join(_grp(f"Giọng {g.lower()}", "".join(vi_chip(k) for k, d in VI_VOICES.items() if d["g"] == g and not d.get("mine"))) for g in ("Nam", "Nữ"))
        + '</div><div class="tabp" data-tab="en" hidden>'
        + "".join(_grp(g, "".join(chip(v, vname(v), v) for v in vs)) for g, vs in VOICES.items())
        + '</div><div class="tabp" data-tab="story" hidden>'
        + _grp("Giọng nam trầm cho truyện trinh thám", "".join(chip(k, p["name"], p["desc"]) for k, p in PRESETS.items()))
        + '</div><div class="tabp" data-tab="mine" hidden>'
        + MINE_HTML + '</div>')

HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Giọng đọc AI</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#e9eeec;--panel:#f8faf9;--ink:#18242b;--mut:#5b6b70;--line:#cbd5d2;--soft:#dfe7e4;--acc:#0d7a68;--acc-ink:#fff;--rec:#c93c32;
 --font:"Be Vietnam Pro",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#10181c;--panel:#172126;--ink:#e2ece9;--mut:#8fa3a6;--line:#2a3a40;--soft:#1f2c31;--acc:#3cc4a8;--acc-ink:#062a24;--rec:#ff6b5e}}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--font)}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.app{display:grid;grid-template-columns:minmax(0,1fr) 400px;height:100vh;height:100dvh}
/* ---- kich ban (trai) ---- */
.script{display:flex;flex-direction:column;min-height:0;padding:20px 28px 0}
.top{display:flex;align-items:baseline;gap:12px;margin-bottom:14px}
.top h1{font-size:17px;font-weight:700;margin:0;letter-spacing:-.01em}
.top .ver{font-size:12px;color:var(--mut)}
.top .tagline{margin-left:auto;font-size:13px;color:var(--mut)}
.sheet{flex:1;min-height:240px;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
#t{flex:1;min-height:0;width:100%;resize:none;border:0;background:transparent;padding:26px 30px;font-size:19px;line-height:1.75;max-width:none}
#t:focus{outline:none}.sheet:focus-within{border-color:var(--acc)}
.tools{display:flex;align-items:center;gap:8px;padding:10px 16px;border-top:1px solid var(--line);font-size:13px;color:var(--mut);flex-wrap:wrap}
.tools .cnt{margin-left:auto}
.tag{border:1px solid var(--line);background:transparent;border-radius:6px;padding:3px 9px;font-size:13px;cursor:pointer}
.tag:hover{border-color:var(--acc);color:var(--acc)}
#hint{display:flex;align-items:center;gap:6px}
/* thanh dieu khien */
.transport{display:grid;grid-template-columns:auto auto 1fr;align-items:center;gap:12px;padding:14px 0 18px}
#b{background:var(--acc);color:var(--acc-ink);border:0;border-radius:12px;padding:13px 26px;font-weight:600;font-size:16px;cursor:pointer;white-space:nowrap}
#b:hover{filter:brightness(1.08)}#b:disabled{opacity:.6;cursor:wait}
#rr{background:transparent;border:1px solid var(--line);border-radius:12px;padding:12px 14px;cursor:pointer;white-space:nowrap}
#rr:hover{border-color:var(--acc)}
.status{min-width:0}
#msg{font-size:14px;color:var(--mut);min-height:1.5em;display:flex;align-items:center;gap:8px}
#msg.busy::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--rec);flex:none;animation:rec 1s ease-in-out infinite alternate}
@keyframes rec{to{opacity:.25}}
#seedrow{font-size:12px;color:var(--mut)}
#out{display:none;grid-column:1/-1;align-items:center;gap:12px}
#out audio{flex:1;min-width:0;height:40px}
#dl{color:var(--acc);font-size:14px;font-weight:500;white-space:nowrap;text-decoration:none}#dl:hover{text-decoration:underline}
/* ---- giong & cai dat (phai) ---- */
.side{border-left:1px solid var(--line);background:var(--panel);display:flex;flex-direction:column;min-height:0}
.side-head{padding:20px 20px 12px;border-bottom:1px solid var(--line)}
.side-head h2{font-size:15px;font-weight:600;margin:0 0 2px}
.cur{font-size:13px;color:var(--mut);margin:0 0 12px}.cur b{color:var(--ink)}
.tabs{display:flex;gap:4px;background:var(--soft);padding:3px;border-radius:10px}
.tabs button{flex:1;border:0;background:transparent;border-radius:8px;padding:7px 4px;font-size:13px;font-weight:500;cursor:pointer;color:var(--mut)}
.tabs button[aria-selected=true]{background:var(--panel);color:var(--ink);box-shadow:0 1px 2px rgba(24,36,43,.12)}
#q{margin-top:10px;width:100%;border:1px solid var(--line);border-radius:9px;padding:8px 11px;background:transparent;font-size:14px}
.side-body{flex:1;min-height:0;overflow:auto;padding:6px 12px 16px}
.grp{margin:12px 0 4px}.gl{font-size:12px;font-weight:600;color:var(--mut);margin:0 8px 6px}
.vlist{display:flex;flex-direction:column}
.vrow{display:grid;grid-template-columns:22px 1fr;column-gap:8px;align-items:center;text-align:left;width:100%;border:0;background:transparent;border-radius:9px;padding:7px 8px;cursor:pointer}
.vrow:hover{background:var(--soft)}
.vrow .pl{grid-row:1/3;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:9px;border:1px solid var(--line);color:var(--mut)}
.vrow .vname{font-weight:500;font-size:14px}.vrow small{grid-column:2;font-size:12px;color:var(--mut)}
.vrow.sel{background:color-mix(in srgb,var(--acc) 13%,transparent)}.vrow.sel .pl{background:var(--acc);border-color:var(--acc);color:var(--acc-ink)}
.vrow.playing .pl{animation:rec .6s infinite alternate}.vrow.loading{opacity:.6;cursor:wait}
.vrow[hidden]{display:none}
.settings{display:grid;grid-template-columns:minmax(0,300px) minmax(150px,200px) minmax(0,1fr);gap:12px 24px;align-items:start;padding:14px 4px 4px}
#chkrow{grid-column:1/-1}#chkrow>label{justify-content:flex-start;font-weight:400;margin:0}#chkrow .hint{display:inline;margin:0 0 0 6px}#chkrow br{display:none}
.set{min-width:0}
.dictwrap{border-top:1px solid var(--line);padding:10px 20px 14px;max-height:55%;overflow:auto}
.set>label,.set .lbl{display:flex;justify-content:space-between;gap:8px;font-size:13px;font-weight:600;margin-bottom:8px}
.set .lbl b{font-weight:500;color:var(--mut)}
input[type=range]{width:100%;accent-color:var(--acc)}input[type=range]:disabled{opacity:.35}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip.mood,.chip.eng{border:1px solid var(--line);background:transparent;border-radius:999px;padding:5px 11px;font-size:13px;cursor:pointer;display:inline-flex;gap:6px;align-items:baseline}
.chip.eng small{font-size:11px;color:var(--mut)}
.chip.mood:hover,.chip.eng:hover{border-color:var(--acc)}
.chip.mood.sel,.chip.eng.sel{border-color:var(--acc);background:color-mix(in srgb,var(--acc) 13%,transparent)}
.chip:disabled{opacity:.45;cursor:not-allowed}
.hint{font-size:12px;color:var(--mut);margin-top:6px;max-width:46ch}.hint code{font-size:12px}
.check{display:flex;gap:8px;align-items:flex-start;font-size:13px;cursor:pointer}.check input{margin-top:3px;accent-color:var(--acc)}
details summary{cursor:pointer;font-size:13px;font-weight:600}
#dict{width:100%;min-height:150px;margin-top:8px;border:1px solid var(--line);border-radius:9px;padding:9px;background:transparent;font:12.5px/1.55 ui-monospace,Menlo,monospace}
#dsave{margin-top:8px;border:1px solid var(--acc);color:var(--acc);background:transparent;border-radius:9px;padding:6px 14px;font-size:13px;font-weight:600;cursor:pointer}
/* ---- man hinh nho ---- */
.mine{padding:8px 4px}
.newv{width:100%;border:1px dashed var(--acc);color:var(--acc);background:transparent;border-radius:10px;padding:10px;font-weight:600;cursor:pointer}
.newv:hover{background:color-mix(in srgb,var(--acc) 10%,transparent)}
.newform{margin:12px 0;padding:14px;border:1px solid var(--line);border-radius:12px;display:flex;flex-direction:column;gap:10px}
.newform[hidden]{display:none}
#sample{margin:0;padding:10px 12px;border-left:3px solid var(--acc);background:var(--soft);border-radius:0 8px 8px 0;font-size:15px;line-height:1.6}
.recrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
#recb{border:1px solid var(--rec);color:var(--rec);background:transparent;border-radius:999px;padding:6px 14px;font-weight:600;cursor:pointer}
#recb.on{background:var(--rec);color:#fff}
.filebtn{border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px;cursor:pointer;margin-left:auto}
.filebtn:hover{border-color:var(--acc)}
#vprev{width:100%;height:36px}#vprev[hidden]{display:none}
.fld{display:flex;flex-direction:column;gap:4px;font-size:12px;font-weight:600;color:var(--mut);flex:1}
.fld input,.fld select{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--panel);font-size:14px;font-weight:400;color:var(--ink)}
.row2{display:flex;gap:10px}
#vsave{background:var(--acc);color:var(--acc-ink);border:0;border-radius:10px;padding:9px 18px;font-weight:600;cursor:pointer}#vsave:disabled{opacity:.5;cursor:wait}
.linkbtn{border:0;background:transparent;color:var(--mut);cursor:pointer;text-decoration:underline}
.myrow{display:flex;align-items:center;gap:4px}.myrow .vrow{flex:1}
.del{border:0;background:transparent;color:var(--mut);border-radius:8px;width:30px;height:30px;cursor:pointer;flex:none}
.del:hover{color:var(--rec);background:var(--soft)}
@media (max-width:900px){
 .app{display:block;height:auto}
 .script{padding:14px 14px 0}.top .tagline{display:none}
 .sheet{height:52vh}
 #t{padding:16px 18px;font-size:17px}
 .transport{position:sticky;bottom:0;background:var(--bg);grid-template-columns:1fr auto;padding:10px 0 12px;z-index:2;border-top:1px solid var(--line)}
 .status{grid-column:1/-1;order:3}
 .side{border-left:0;border-top:1px solid var(--line);margin-top:8px}
 .side-body{max-height:none;overflow:visible}.settings{grid-template-columns:1fr 1fr}#moodrow,#chkrow{grid-column:1/-1}.dictwrap{max-height:none}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
<div class="app">
<main class="script">
 <div class="top"><h1>Kokoro TTS</h1><span class="ver">__VER__</span><span class="tagline">Chạy hoàn toàn trên máy bạn</span></div>
 <div class="sheet">
  <textarea id="t" aria-label="Văn bản cần đọc" placeholder="Dán hoặc gõ văn bản cần đọc vào đây…">Hello! This is Kokoro, an open-source voice running right here on your Mac.</textarea>
  <div class="tools">
   <span id="hint" style="display:none">Chèn biểu cảm: <button type="button" class="tag" data-ins="[cười]">[cười]</button><button type="button" class="tag" data-ins="[thở dài]">[thở dài]</button><button type="button" class="tag" data-ins="[hắng giọng]">[hắng giọng]</button></span>
   <span class="cnt" id="cnt">0 ký tự</span>
  </div>
 </div>
 <div class="settings" aria-label="Cài đặt đọc">
  <div class="set" id="engrow" style="display:none"><div class="lbl">Bộ đọc</div><div class="chips">
   <button type="button" class="chip eng" data-e="vieneu">⚡ VieNeu<small>nhanh</small></button>
   <button type="button" class="chip eng" data-e="omni" __OMNI_DIS__>🌏 Song ngữ<small>tiếng Anh chuẩn, chậm hơn</small></button></div>
   <div class="hint" id="enghint">__OMNI_HINT__</div></div>
  <div class="set"><label for="s">Tốc độ <b id="sv">1.0×</b></label><input id="s" type="range" min="0.5" max="1.8" step="0.05" value="1"></div>
  <div class="set" id="moodrow" style="display:none"><div class="lbl">Tâm trạng</div><div class="chips"><button type="button" class="chip mood" data-m="natural">😊 Tự nhiên</button><button type="button" class="chip mood" data-m="lively">🎉 Sôi nổi</button><button type="button" class="chip mood" data-m="calm">🌙 Trầm lắng</button><button type="button" class="chip mood" data-m="serious">📰 Nghiêm túc</button><button type="button" class="chip mood" data-m="mystery">🕯️ Hồi hộp</button><button type="button" class="chip mood" data-m="sad">🌧️ Buồn</button></div></div>
  <div class="set" id="chkrow" style="display:none"><label class="check"><input type="checkbox" id="chk" checked><span><b>Kiểm tra kỹ</b><br><span class="hint">Nghe lại từng đoạn, đoạn nào đọc lỗi hoặc đọc lướt thì tự đọc lại.</span></span></label></div>
 </div>
 <div class="transport">
  <button id="b" title="⌘/Ctrl + Enter">▶ Đọc</button>
  <button id="rr" type="button" title="Đọc lại cùng văn bản theo kiểu khác">🎲 Kiểu khác</button>
  <div class="status"><div id="msg" aria-live="polite"></div><div id="seedrow">Kiểu đọc #<b id="sd">1</b>. Giữ số này thì lần sau đọc y hệt.</div></div>
  <div id="out"><audio id="a" controls></audio><a id="dl" download="kokoro.wav">Tải file .wav</a></div>
 </div>
</main>
<aside class="side" aria-label="Giọng đọc và cài đặt">
 <div class="side-head">
  <h2>Giọng đọc</h2>
  <p class="cur">Đang chọn <b id="vn">af_heart</b>. Bấm vào giọng để nghe thử.</p>
  <div class="tabs" role="tablist"><button role="tab" data-t="vi" aria-selected="true">Tiếng Việt</button><button role="tab" data-t="en" aria-selected="false">Tiếng Anh</button><button role="tab" data-t="story" aria-selected="false">Kể chuyện</button><button role="tab" data-t="mine" aria-selected="false">Của tôi</button></div>
  <input id="q" type="search" placeholder="Tìm giọng: tên, Bắc, nữ, kể chuyện…" aria-label="Tìm giọng">
 </div>
 <div class="side-body" id="voices">__OPTS__</div>
  <details class="dictwrap" id="dictbox" style="display:none"><summary>📖 Từ điển phát âm</summary>
   <p class="hint">Mỗi dòng <code>TỪ = cách đọc</code>, ví dụ <code>IELTS = /ˈaɪɛlts/</code> (IPA), <code>SAT = &lt;en&gt;S A T&lt;/en&gt;</code>, <code>Zalo = da lô</code>. Thêm <code>en:</code> để chỉ sửa trong câu tiếng Anh, ví dụ <code>en:do = đu</code>. Dòng bắt đầu bằng # là ghi chú.</p>
   <textarea id="dict" spellcheck="false"></textarea>
   <button type="button" id="dsave">Lưu từ điển</button> <span id="dmsg" class="hint"></span>
  </details>
</aside>
</div>
<script>
var engine="vieneu";
const $=id=>document.getElementById(id),t=$("t"),b=$("b"),s=$("s");
const upd=()=>$("cnt").textContent=t.value.length+" ký tự";t.oninput=upd;upd();const EN_T=t.value,VI_T="Xin chào! Đây là giọng đọc tiếng Việt, chạy ngay trên máy của bạn.";
s.oninput=()=>$("sv").textContent=(+s.value).toFixed(2).replace(/0$/,"")+"×";
let voice="af_heart";try{voice=localStorage.getItem("voice")||voice}catch(e){}
let mood="natural";try{mood=localStorage.getItem("mood")||mood}catch(e){}
const moods=[...document.querySelectorAll(".mood")];function selm(m){mood=m;moods.forEach(x=>x.classList.toggle("sel",x.dataset.m===m));try{localStorage.setItem("mood",m)}catch(e){}}
moods.forEach(x=>x.onclick=()=>selm(x.dataset.m));selm(mood);
fetch("/dict").then(r=>r.text()).then(x=>$("dict").value=x);
$("dsave").onclick=async()=>{const r=await fetch("/dict",{method:"POST",headers:{"Content-Type":"text/plain; charset=utf-8"},body:$("dict").value});$("dmsg").textContent=r.ok?"Đã lưu "+(await r.text())+" từ":"Lưu không được, thử lại"};
const pv=new Audio();let chips=[...document.querySelectorAll(".vrow")];
/* tab + tim kiem giong */
const tabs=[...document.querySelectorAll(".tabs button")],panes=[...document.querySelectorAll(".tabp")];
function showTab(k){tabs.forEach(x=>x.setAttribute("aria-selected",x.dataset.t===k));panes.forEach(p=>p.hidden=p.dataset.tab!==k&&!$("q").value.trim());try{localStorage.setItem("tab",k)}catch(e){}}
tabs.forEach(x=>x.onclick=()=>{$("q").value="";filt();showTab(x.dataset.t)});
function filt(){const q=$("q").value.trim().toLowerCase();chips.forEach(c=>c.hidden=!!q&&!c.dataset.q.includes(q));
 document.querySelectorAll(".grp").forEach(g=>g.hidden=![...g.querySelectorAll(".vrow")].some(c=>!c.hidden));
 if(q)panes.forEach(p=>p.hidden=false);else{const cur=tabs.find(x=>x.getAttribute("aria-selected")==="true");showTab(cur?cur.dataset.t:"vi")}}
$("q").oninput=filt;
function tabOf(v){return v.startsWith("my_")?"mine":v.startsWith("vi_")?"vi":v.startsWith("x_")?"story":"en"}
function sel(v){if(!chips.some(c=>c.dataset.v===v))v="af_heart";voice=v;const c0=chips.find(c=>c.dataset.v===v);$("vn").textContent=c0?c0.dataset.n:v;chips.forEach(c=>c.classList.toggle("sel",c.dataset.v===v));try{localStorage.setItem("voice",v)}catch(e){}const vi=v.startsWith("vi_")||v.startsWith("my_");$("hint").style.display=vi?"flex":"none";$("moodrow").style.display=vi?"block":"none";$("engrow").style.display=vi?"block":"none";$("chkrow").style.display=vi&&engine!=="omni"?"block":"none";$("dictbox").style.display=vi&&engine!=="omni"?"block":"none";if(vi&&t.value===EN_T){t.value=VI_T;upd()}else if(!vi&&t.value===VI_T){t.value=EN_T;upd()}}
pv.onended=pv.onpause=()=>chips.forEach(c=>c.classList.remove("playing"));
function playPrev(c){sel(c.dataset.v);$("a").pause();pv.pause();
 c.classList.add("loading");pv.src="/preview/"+c.dataset.v;
 pv.oncanplay=()=>{c.classList.remove("loading");c.classList.add("playing")};
 pv.onerror=()=>{c.classList.remove("loading");$("msg").textContent="Không phát được bản nghe thử"};
 pv.play().catch(()=>{})}
function bindChips(){chips=[...document.querySelectorAll(".vrow")];chips.forEach(c=>c.onclick=()=>playPrev(c))}
/* giong cua toi */
const esc=x=>String(x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function loadMine(){let list=[];try{list=await (await fetch("/myvoices")).json()}catch(e){}
 $("mylist").innerHTML=list.map(m=>`<div class="myrow"><button type="button" class="chip vrow" data-v="${esc(m.key)}" data-n="${esc(m.name)}" data-q="${esc((m.name+" "+m.g+" "+m.r+" giọng của tôi").toLowerCase())}"><span class="pl" aria-hidden="true">▶</span><span class="vname">${esc(m.name)}</span><small>${esc(m.g)} · ${esc(m.r)} · giọng của tôi · ${m.seconds||""} giây mẫu</small></button><button type="button" class="del" data-k="${esc(m.key)}" data-n="${esc(m.name)}" title="Xoá giọng ${esc(m.name)}" aria-label="Xoá giọng ${esc(m.name)}">✕</button></div>`).join("");
 $("myempty").hidden=list.length>0;
 document.querySelectorAll(".del").forEach(x=>x.onclick=async()=>{if(!x.dataset.armed){x.dataset.armed=1;x.textContent="Xoá?";setTimeout(()=>{delete x.dataset.armed;x.textContent="✕"},3000);return}
  const r=await fetch("/myvoices/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:x.dataset.k})});
  if(r.ok){if(voice===x.dataset.k)voice="vi_hai_dang";await loadMine();sel(voice)}});
 bindChips()}
let recBlob=null,mr=null,recT=null;
function setBlob(b){recBlob=b;$("vprev").src=URL.createObjectURL(b);$("vprev").hidden=false}
$("newv").onclick=()=>{$("newform").hidden=!$("newform").hidden;if(!$("newform").hidden)$("vname").focus()};
$("vcancel").onclick=()=>{$("newform").hidden=true};
$("vfile").onchange=()=>{const f=$("vfile").files[0];if(f){setBlob(f);$("rect").textContent=f.name}};
$("recb").onclick=async()=>{if(mr&&mr.state==="recording"){mr.stop();return}
 try{const st=await navigator.mediaDevices.getUserMedia({audio:true});const parts=[];mr=new MediaRecorder(st);
  mr.ondataavailable=e=>parts.push(e.data);
  mr.onstop=()=>{st.getTracks().forEach(t=>t.stop());clearInterval(recT);$("recb").classList.remove("on");$("recb").textContent="● Ghi lại";setBlob(new Blob(parts,{type:mr.mimeType}))};
  mr.start();const t0=Date.now();$("recb").classList.add("on");$("recb").textContent="■ Dừng";
  recT=setInterval(()=>{const sec=(Date.now()-t0)/1000;$("rect").textContent="Đang ghi "+sec.toFixed(0)+" giây";if(sec>=12)mr.stop()},250);
 }catch(e){$("vmsg").textContent="Không mở được micro. Hãy cho phép trình duyệt dùng micro, hoặc chọn file ghi âm."}};
$("newform").onsubmit=async e=>{e.preventDefault();
 if(!recBlob){$("vmsg").textContent="Hãy ghi âm hoặc chọn một file trước.";return}
 if(!$("vname").value.trim()){$("vmsg").textContent="Hãy đặt tên cho giọng.";$("vname").focus();return}
 if(!$("vok").checked){$("vmsg").textContent="Hãy xác nhận bạn có quyền dùng giọng này.";return}
 $("vsave").disabled=true;$("vmsg").textContent="Đang tạo giọng, khoảng 10–30 giây…";
 try{const data=await new Promise((ok,no)=>{const fr=new FileReader();fr.onload=()=>ok(fr.result);fr.onerror=no;fr.readAsDataURL(recBlob)});
  const r=await fetch("/myvoices",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({audio:data,name:$("vname").value,g:$("vg").value,r:$("vr").value})});
  if(!r.ok)throw new Error(await r.text());const m=await r.json();
  $("vmsg").textContent="Đã tạo giọng "+m.name+".";$("newform").reset();recBlob=null;$("vprev").hidden=true;$("rect").textContent="tối đa 12 giây";$("newform").hidden=true;
  await loadMine();const c=chips.find(x=>x.dataset.v===m.key);if(c)playPrev(c)}
 catch(err){$("vmsg").textContent=err.message}finally{$("vsave").disabled=false}};
bindChips();
loadMine().then(()=>{sel(voice);showTab(tabOf(voice))});
/* chen bieu cam tai con tro */
document.querySelectorAll(".tag").forEach(x=>x.onclick=()=>{const a=t.selectionStart,z=t.selectionEnd,ins=" "+x.dataset.ins+" ";t.setRangeText(ins,a,z,"end");t.focus();upd()});
let seed=1;try{seed=+localStorage.getItem("seed")||1}catch(e){}$("sd").textContent=seed;
$("rr").onclick=()=>{seed=1+Math.floor(Math.random()*99999);$("sd").textContent=seed;try{localStorage.setItem("seed",seed)}catch(e){}b.click()};
try{$("chk").checked=localStorage.getItem("check")!=="0"}catch(e){}
try{engine=localStorage.getItem("engine")||"vieneu"}catch(e){}
const engs=[...document.querySelectorAll(".eng")];
function sele(e){const bb=engs.find(x=>x.dataset.e===e);if(!bb||bb.disabled)e="vieneu";engine=e;engs.forEach(x=>x.classList.toggle("sel",x.dataset.e===e));try{localStorage.setItem("engine",e)}catch(_){}
 const vi=voice.startsWith("vi_")||voice.startsWith("my_");$("chkrow").style.display=vi&&e!=="omni"?"block":"none";$("dictbox").style.display=vi&&e!=="omni"?"block":"none"}
engs.forEach(x=>x.onclick=()=>sele(x.dataset.e));sele(engine);
$("chk").onchange=()=>{try{localStorage.setItem("check",$("chk").checked?"1":"0")}catch(e){}};
b.onclick=async()=>{if(!t.value.trim()){$("msg").textContent="Gõ hoặc dán văn bản vào ô bên trái trước đã.";t.focus();return}
b.disabled=true;$("msg").classList.add("busy");$("msg").textContent="Đang tạo giọng nói…";const t0=Date.now();
const poll=setInterval(async()=>{try{const p=await (await fetch("/progress")).json();if(p.text)$("msg").textContent=p.text+" ("+((Date.now()-t0)/1000).toFixed(0)+" giây)"}catch(e){}},1000);
try{const r=await fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t.value,voice:voice,mood:mood,speed:+s.value,seed:seed,check:$("chk").checked,engine:engine})});
if(!r.ok)throw new Error(await r.text());const u=URL.createObjectURL(await r.blob());
pv.pause();$("a").src=u;$("dl").href=u;$("dl").download=voice+".wav";$("out").style.display="flex";$("a").play();
let extra="";try{const rp=JSON.parse(r.headers.get("X-Report")||"{}");if(rp.engine==="omni"){extra=", song ngữ, "+rp.chunks+" đoạn"}else if(rp.chunks){extra=", "+rp.chunks+" đoạn"+(rp.checked?", đọc lại "+rp.regenerated+" đoạn lỗi":"")}}catch(e){}
$("msg").textContent="Xong sau "+((Date.now()-t0)/1000).toFixed(1)+" giây"+extra;}
catch(e){$("msg").textContent="Tạo giọng không được: "+e.message}finally{clearInterval(poll);$("msg").classList.remove("busy");b.disabled=false}};
document.addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key==="Enter"){e.preventDefault();b.click()}});
</script></body></html>""".replace("__OPTS__", opts)

def _version():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(root, ".git")): return "bản phát triển"
    try: return "phiên bản " + open(os.path.join(root, ".version")).read().strip()[:7]
    except Exception: return "phiên bản cài đặt"
HTML = HTML.replace("__VER__", _version())
def _omni_ok():
    try:
        import omni; return omni.available()
    except Exception: return False
HTML = HTML.replace("__OMNI_DIS__", "" if _omni_ok() else "disabled").replace("__OMNI_HINT__",
    "Song ngữ đọc cả câu tiếng Anh bằng chính giọng Việt đã chọn. Lần đầu mất khoảng 1 phút để khởi động." if _omni_ok()
    else "Song ngữ chưa được cài trên máy này — chạy file \"3. Cai them Song ngu\" (tải ~4 GB) để dùng.")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/myvoices":
            return self._send(200, json.dumps(myvoices.list_voices(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
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
        if self.path in ("/myvoices", "/myvoices/delete"):
            try:
                d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/myvoices/delete":
                    k = d.get("key", ""); m = VI_VOICES.get(k, {}).get("mine")
                    if not m: return self._send(404, "Không tìm thấy giọng".encode(), "text/plain; charset=utf-8")
                    myvoices.delete(m["id"], _vi)
                    VI_VOICES.pop(k, None)
                    if k in ALL_VOICES: ALL_VOICES.remove(k)
                    pf = os.path.join(PREV_DIR, k + ".wav")
                    if os.path.exists(pf): os.remove(pf)
                    return self._send(200, b"ok", "text/plain")
                import base64
                raw = base64.b64decode(d["audio"].split(",", 1)[-1])
                tr = None
                try:
                    import checker
                    if checker.available(): tr = checker.transcribe
                except Exception: tr = None
                eng = vi_engine()
                with _vi_lock:
                    PROGRESS["text"] = "Đang tạo giọng mới…"
                    try: meta = myvoices.create(raw, d.get("name"), d.get("g"), d.get("r"), FFMPEG, eng, tr)
                    finally: PROGRESS["text"] = ""
                _add_mine(meta)
                return self._send(200, json.dumps(meta, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            except ValueError as e:
                return self._send(400, str(e).encode(), "text/plain; charset=utf-8")
            except Exception as e:
                return self._send(500, ("Lỗi khi tạo giọng: " + str(e)).encode(), "text/plain; charset=utf-8")
        if self.path != "/tts": return self._send(404, b"not found", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            voice = d.get("voice", "af_heart"); text = d["text"].strip()
            rpt = {}
            body = synth(text, voice, float(d.get("speed", 1)), d.get("mood", "natural"), d.get("seed", 1), bool(d.get("check", True)), rpt,
                         d.get("engine", "vieneu"))
            self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Report", json.dumps({k: rpt.get(k) for k in ("chunks", "checked", "regenerated", "engine")}))
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
