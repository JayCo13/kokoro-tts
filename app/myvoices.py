"""Giong nhan ban cua nguoi dung ("Giong cua toi"). Luu tai app/my_voices/ (khong day len GitHub).
Moi giong: <id>.wav (doan mau da cat lang, mono 24 kHz, toi da 10 giay), <id>.json (ten, gioi tinh, vung, loi),
<id>.npz (dac trung giong VieNeu da trich, de lan sau nap nhanh)."""
import json, os, re, subprocess, time, unicodedata
import numpy as np, soundfile as sf

APP = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(APP, "my_voices")
MIN_SEC, MAX_SEC = 3.0, 10.0

def _p(vid, ext): return os.path.join(DIR, f"{vid}.{ext}")
def key_of(vid): return "my_" + vid
def vieneu_name(vid): return "my_" + vid

def list_voices():
    out = []
    if not os.path.isdir(DIR): return out
    for f in os.listdir(DIR):
        if not f.endswith(".json"): continue
        try:
            m = json.load(open(os.path.join(DIR, f), encoding="utf-8"))
            if os.path.exists(_p(m["id"], "wav")): out.append(m)
        except Exception: pass
    return sorted(out, key=lambda m: m.get("created", 0))

def _slug(name):
    s = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:24] or "giong"
    return f"{s}_{int(time.time()) % 100000:05d}"

CLONE_FILES = [("pnnbao-ump/VieNeu-TTS-v3-Turbo", "denoiser.onnx"), ("pnnbao-ump/VieNeu-TTS-v3-Turbo", "speaker_encoder.onnx"),
               ("OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX", "moss_audio_tokenizer_encode.onnx"),
               ("OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX", "moss_audio_tokenizer_encode.data")]

def ensure_clone_files():
    """Cac file can cho viec nhan ban giong (bo loc on, trich dac trung). May cai tu ban cu co the chua co -> tai bo sung."""
    from huggingface_hub import constants, hf_hub_download, try_to_load_from_cache
    missing = [(r, f) for r, f in CLONE_FILES if not isinstance(try_to_load_from_cache(r, f), str)]
    if not missing: return
    old = constants.HF_HUB_OFFLINE
    try:
        constants.HF_HUB_OFFLINE = False
        for r, f in missing: hf_hub_download(r, f)
    except Exception as e:
        raise ValueError("Lần đầu nhân bản giọng cần Internet để tải thêm khoảng 100 MB. Hãy kết nối mạng rồi thử lại.") from e
    finally:
        constants.HF_HUB_OFFLINE = old
    import hfcache; hfcache.fix_symlinks()

def _enroll(eng, vid):
    """Dang ky giong vao VieNeu; luu dac trung ra .npz de lan sau khoi phai trich lai."""
    name = vieneu_name(vid)
    if os.path.exists(_p(vid, "npz")):
        z = np.load(_p(vid, "npz"))
        eng._preset_voices[name] = {"description": "", "gender": "", "style": getattr(eng, "default_style", None),
                                    "speaker_emb": z["emb"], "codes": z["codes"] if z["codes"].size else None}
        return
    eng.add_voice(name, _p(vid, "wav"), denoise=True)
    v = eng._preset_voices[name]
    np.savez(_p(vid, "npz"), emb=v["speaker_emb"], codes=v["codes"] if v["codes"] is not None else np.zeros(0, np.int64))

def register_all(eng):
    for m in list_voices():
        try: _enroll(eng, m["id"])
        except Exception as e: print("Khong nap duoc giong", m.get("name"), e)

def create(raw, name, gender, region, ffmpeg, eng, transcribe=None):
    name = (name or "").strip()[:40]
    if not name: raise ValueError("Hãy đặt tên cho giọng.")
    if any(m["name"].lower() == name.lower() for m in list_voices()): raise ValueError("Đã có giọng tên này, hãy đặt tên khác.")
    os.makedirs(DIR, exist_ok=True)
    vid = _slug(name); src = _p(vid, "src"); wav = _p(vid, "wav")
    open(src, "wb").write(raw)
    try:
        # chuyen moi dinh dang (webm/ogg/mp3/m4a/wav) -> wav mono 24 kHz, cat khoang lang 2 dau, toi da 10 giay
        flt = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
               "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse")
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af", flt,
                            "-ac", "1", "-ar", "24000", "-t", str(MAX_SEC), wav], capture_output=True)
        if r.returncode != 0 or not os.path.exists(wav):
            raise ValueError("Không đọc được file âm thanh này. Hãy dùng .wav, .mp3 hoặc .m4a.")
    finally:
        if os.path.exists(src): os.remove(src)
    dur = sf.info(wav).duration
    if dur < MIN_SEC:
        os.remove(wav); raise ValueError(f"Đoạn ghi âm chỉ có {dur:.1f} giây giọng nói, cần ít nhất {MIN_SEC:.0f} giây.")
    text = ""
    if transcribe:
        try:
            w, sr = sf.read(wav, dtype="float32"); text = transcribe(w, sr).strip()
        except Exception: text = ""
    meta = {"id": vid, "key": key_of(vid), "name": name, "g": gender if gender in ("Nam", "Nữ") else "Nam",
            "r": region if region in ("Bắc", "Trung", "Nam") else "Bắc", "ref_text": text, "created": time.time(),
            "seconds": round(dur, 1)}
    json.dump(meta, open(_p(vid, "json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        ensure_clone_files()
        _enroll(eng, vid)
    except Exception:
        delete(vid); raise
    return meta

def delete(vid, eng=None):
    for ext in ("wav", "json", "npz", "src"):
        if os.path.exists(_p(vid, ext)): os.remove(_p(vid, ext))
    if eng is not None: eng._preset_voices.pop(vieneu_name(vid), None)
