"""Doc van ban dai cho VieNeu v3 Turbo:
- chia doan ngan hon (mac dinh <= 140 ky tu) de mo hinh khong bi 'tuot' o doan dai
- kiem tra tung doan bang PhoWhisper (nghe lai, so voi van ban goc) + kiem tra toc do doc
- doan nao loi thi doc lai toi da `retries` lan voi kieu khac, giu ban tot nhat
"""
import logging, time
import numpy as np
from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, _get_normalizer
from vieneu_utils.core_utils import syllable_count, join_audio_chunks, gaps_to_silence
import vieneu.v3turbo as vt
import checker

log = logging.getLogger("longform")
SR = 48000
WER_OK = 0.12      # <= muc nay coi la doc dung (chua tinh sai so cua chinh PhoWhisper)
EN_TEMP = 0.4      # doan co tu tieng Anh: giam do ngau nhien de doc tu Anh chuan hon (do tren nhieu giong)
EN_OK = 0.5        # ti le tu tieng Anh PhoWhisper nghe ra dung chinh ta

import re as _re
def english_words(chunk):
    """Tu tieng Anh trong doan (khong tinh tu da thay bang IPA / <en>..</en>)."""
    t = _re.sub(r"</?en>|zqxipa[a-z]+|<\|emotion_\d+\|>", " ", chunk.lower())
    return [w for w in _re.findall(r"[a-z]{3,}", t) if not checker.is_vietnamese_word(w)]

def voiced_seconds(wav, sr=SR, win=0.02):
    w = np.asarray(wav, dtype=np.float32); n = int(sr * win)
    if len(w) < n: return len(w) / sr
    rms = np.sqrt((w[: len(w) // n * n].reshape(-1, n) ** 2).mean(axis=1) + 1e-12)
    return float((rms > max(rms.max() * 0.06, 1e-3)).sum() * win)

def synth_long(eng, text, voice, temperature=0.6, seed=1, max_chars=140, retries=3,
               check=True, progress=None, report=None, use_ref=True):
    t0 = time.time()
    spk, ref = eng._resolve_ref(voice, None, True, use_ref)
    chunks, gaps = normalize_to_chunks_v3_with_gaps(text, max_chars=max_chars)
    if not chunks: return np.zeros(0, np.float32)
    sampling = dict(temperature=temperature, top_k=25, top_p=0.95, max_new_frames=300,
                    repetition_penalty=1.2, repetition_window=vt.DEFAULT_REP_WINDOW)
    check = check and checker.available()
    norm = _get_normalizer() if check else None
    syl = [max(1, syllable_count(vt.phonemize_text_with_emotions(c))) for c in chunks]

    en = [english_words(c) for c in chunks]

    def gen(i, k):
        np.random.seed((seed * 1000 + i + 7919 * k) % (2 ** 32))
        smp = dict(sampling, temperature=min(temperature, EN_TEMP)) if en[i] else sampling
        w = eng._infer_chunks([chunks[i]], spk, ref, use_ref, 1, smp)[0]
        rate = syl[i] / max(voiced_seconds(w), 0.05)
        wer, nref, hyp = 0.0, 0, ""
        if check:
            r = checker.prep_ref(chunks[i])
            if len(r.split()) >= 2:
                hyp = checker.transcribe(w)
                wer, nref, _ = checker.score(r, checker.prep_hyp(hyp, norm))
        en_rec = 1.0
        if check and len(en[i]) >= 2:
            if not hyp: hyp = checker.transcribe(w)
            heard = set(_re.findall(r"[a-z]+", hyp.lower()))
            en_rec = sum(1 for x in en[i] if x in heard) / len(en[i])
        return dict(w=w, rate=rate, wer=wer, hyp=hyp, en=en_rec)

    res = []
    for i in range(len(chunks)):
        if progress: progress(i, len(chunks), "đọc")
        res.append(gen(i, 0))
    long_rates = [r["rate"] for r, s in zip(res, syl) if s >= 6] or [r["rate"] for r in res]
    med = float(np.median(long_rates))

    def badness(r, i):
        b = max(0.0, r["wer"] - WER_OK) * 4                    # sai chu / doc khong ro
        b += max(0.0, EN_OK - r["en"]) * 2                     # tu tieng Anh doc khong ra
        if syl[i] >= 6:                                         # doc luot qua nhanh / keo dai bat thuong
            b += max(0.0, np.log(r["rate"] / med) - np.log(1.22)) * 3
            b += max(0.0, np.log(0.72) - np.log(r["rate"] / med)) * 3
        return b

    fixed, details = 0, []
    for i in range(len(chunks)):
        best = res[i]; bb = badness(best, i)
        if bb <= 0: continue
        if progress: progress(i, len(chunks), "sửa")
        first_wer = best["wer"]
        for k in range(1, retries + 1):
            cand = gen(i, k); cb = badness(cand, i)
            if cb < bb: best, bb = cand, cb
            if bb <= 0: break
        res[i] = best; fixed += 1
        details.append(dict(chunk=i, text=chunks[i][:60], en_after=round(best["en"], 2), wer_before=round(first_wer, 2),
                            wer_after=round(best["wer"], 2), heard=best["hyp"][:80]))

    if report is not None:
        report.update(chunks=len(chunks), checked=check, regenerated=fixed, seconds=round(time.time() - t0, 1),
                      median_rate=round(med, 2), wers=[round(r["wer"], 2) for r in res], details=details)
    out = join_audio_chunks([r["w"] for r in res], SR, silence_ps=gaps_to_silence(gaps))
    return eng._apply_watermark(out)
