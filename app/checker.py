"""Buoc 'nghe lai' bang PhoWhisper: chep lai tung doan va cham diem do khop voi van ban goc."""
import re, threading, unicodedata, logging
import numpy as np

log = logging.getLogger("checker")
MODEL_ID = "vinai/PhoWhisper-small"
_asr, _lock = None, threading.Lock()

def _load():
    global _asr
    if _asr is None:
        import torch
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        dt = torch.float32 if dev == "cpu" else torch.float16
        proc = WhisperProcessor.from_pretrained(MODEL_ID)
        model = WhisperForConditionalGeneration.from_pretrained(MODEL_ID, torch_dtype=dt, use_safetensors=False).to(dev).eval()
        _asr = (proc, model, dev, dt)
    return _asr

def available():
    try:
        from huggingface_hub import try_to_load_from_cache
        p = try_to_load_from_cache(MODEL_ID, "pytorch_model.bin")
        return isinstance(p, str)
    except Exception:
        return False

def transcribe(wav, sr=48000):
    import torch, soxr
    with _lock:
        proc, model, dev, dt = _load()
        w16 = soxr.resample(np.asarray(wav, dtype=np.float32), sr, 16000)
        feats = proc(w16, sampling_rate=16000, return_tensors="pt").input_features.to(dev, dt)
        with torch.no_grad():
            ids = model.generate(feats, language="vi", task="transcribe", max_new_tokens=220)
        return proc.batch_decode(ids, skip_special_tokens=True)[0]

def _words(s):
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"<\|emotion_\d+\|>|</?en>", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return s.split()

def _ed(a, b, span=3):
    """Khoang cach chinh sua theo tu. Tu zzwild trong a (tu nuoc ngoai) khop voi 0..span tu bat ky cua b, khong tinh loi."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        if x == "zzwild":
            cur = [min(prev[max(0, j - span): j + 1]) for j in range(len(b) + 1)]
        else:
            cur = [prev[0] + 1] + [0] * len(b)
            for j, y in enumerate(b, 1):
                cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]

def _strip_tone(w):
    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn").replace("đ", "d")

def score(ref_text, hyp_text, skip=()):
    """Ti le loi tu (WER) giua van ban goc va ban chep lai. Bo qua cac tu trong `skip`
    (tu tieng Anh / tu trong tu dien phat am ma ASR co the viet khac di).
    Tra ve (wer, so_tu_goc, chi_tiet)."""
    skip = {w.lower() for w in skip}
    ref = [w for w in _words(ref_text) if w not in skip]
    hyp = [w for w in _words(hyp_text) if w not in skip]
    n = len([w for w in ref if w != "zzwild"])
    if not n: return 0.0, 0, ""
    # loi sai dau nang hon loi sai chu: tinh ca 2 muc, lay trung binh
    e_full = _ed(ref, hyp)
    e_base = _ed([_strip_tone(w) for w in ref], [_strip_tone(w) for w in hyp])
    wer = (e_full + e_base) / 2 / n
    return float(wer), n, hyp_text

# ---- nhan dien tu khong phai tieng Viet (tu tieng Anh, ten rieng nuoc ngoai) de bo qua khi cham ----
_VI_SYL = re.compile(
    r"^(ngh|ng|nh|ch|gh|gi|kh|ph|qu|th|tr|[bcdđghklmnpqrstvx])?"
    r"[aăâeêioôơuưyáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]{1,3}"
    r"(ng|nh|ch|[cmnpt])?$")
def is_vietnamese_word(w):
    return bool(_VI_SYL.match(w))

def prep_ref(chunk_text):
    """Lay danh sach tu de cham tu doan da chuan hoa: bo marker IPA, bo phan trong <en>..</en>, bo tu nuoc ngoai."""
    t = re.sub(r"<en>.*?</en>", " zzforeign ", chunk_text)
    t = re.sub(r"zqxipa[a-z]+", " zzforeign ", t)
    out = []
    for w in _words(t):
        tok = w if (w != "zzforeign" and is_vietnamese_word(w)) else "zzwild"
        if not (tok == "zzwild" and out and out[-1] == "zzwild"): out.append(tok)
    return " ".join(out)

def prep_hyp(hyp_text, normalizer=None):
    if normalizer is not None:
        try: hyp_text = normalizer.normalize(hyp_text)
        except Exception: pass
    return " ".join(_words(hyp_text))
