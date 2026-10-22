"""Tach van ban thanh doan tieng Viet / tieng Anh de doc phan tieng Anh bang giong ban xu (Kokoro).

Cach chia:
- Cat van ban theo cau (. ? ! ...), xet tung cau: chuoi tu tieng Anh lien tiep co it nhat 1 tu chuc nang
  (do, you, I, the, is...) va dai >= 2 tu -> la cau/cum tieng Anh -> giong ban xu doc.
- Tu/cum danh tu tieng Anh le trong cau Viet ("update file Excel", "deadline", "meeting") van de giong Viet
  doc cho lien mach (nguoi Viet van noi xen nhu vay).
- Cac cau tieng Anh lien tiep duoc gop thanh mot doan.
"""
import re
import numpy as np
from entag import _kind, _TOKEN

_SENT = re.compile(r"[.?!…]+[\"”’)]*|\n|\[[^\]]*\]")       # ranh gioi cau / the bieu cam

def _english_runs(text, base):
    """Cac doan [a, b) tieng Anh trong MOT cau."""
    toks = [(base + m.start(), base + m.end(), m.group(), _kind(m.group())) for m in _TOKEN.finditer(text)]
    runs, cur = [], []
    for i, t in enumerate(toks):
        kind = t[3]
        if kind == "amb" and cur and i + 1 < len(toks) and toks[i + 1][3] in ("en", "en_fn"):
            kind = "en"                                   # tu khong dau kep giua 2 tu Anh -> coi la Anh
        if kind in ("en", "en_fn"): cur.append(t)
        else:
            if cur: runs.append(cur)
            cur = []
    if cur: runs.append(cur)
    out = []
    for r in runs:
        n_fn = sum(1 for t in r if t[3] == "en_fn")
        if (len(r) >= 2 and n_fn >= 1) or len(r) >= 5:
            out.append((r[0][0], r[-1][1]))
    return out

def split_segments(text):
    spans, pos = [], 0
    for m in list(_SENT.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        for a, b in _english_runs(text[pos:end], pos):
            if m and b == end - len(text[pos:end]) + len(text[pos:end].rstrip()):   # het cau -> lay ca dau cau
                b = m.end() if not m.group().startswith("[") and m.group() != "\n" else b
            spans.append([a, b])
        pos = m.end() if m else len(text)
    # gop cac doan Anh chi cach nhau boi dau cau / khoang trang
    merged = []
    for a, b in spans:
        if merged and not re.search(r"[^\s.,;:!?…\"”’()'-]", text[merged[-1][1]:a]):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    segs, pos = [], 0
    for a, b in merged:
        tail = re.match(r"[\s]*[,;:]+", text[b:])          # dau phay/hai cham ngay sau cum Anh
        if tail: b += tail.end()
        if text[pos:a].strip(): segs.append(("vi", text[pos:a].strip()))
        segs.append(("en", text[a:b].strip())); pos = b
    if text[pos:].strip(): segs.append(("vi", text[pos:].strip()))
    return segs or [("vi", text)]

def voiced_rms(w, sr=48000, win=0.02):
    w = np.asarray(w, dtype=np.float32); n = int(sr * win)
    if len(w) < n: return float(np.sqrt((w ** 2).mean() + 1e-12))
    rms = np.sqrt((w[: len(w) // n * n].reshape(-1, n) ** 2).mean(axis=1) + 1e-12)
    v = rms[rms > rms.max() * 0.1]
    return float(np.median(v)) if len(v) else float(rms.mean())

def join(parts, sr=48000):
    """parts: list (lang, text, wav). Can am luong phan Anh theo phan Viet, them khoang nghi tu nhien."""
    vi_levels = [voiced_rms(w) for l, _, w in parts if l == "vi" and len(w)]
    target = float(np.median(vi_levels)) if vi_levels else None
    out = []
    for i, (lang, txt, w) in enumerate(parts):
        w = np.asarray(w, dtype=np.float32)
        if lang == "en" and target and len(w):
            w = np.clip(w * (target / max(voiced_rms(w), 1e-4)), -1, 1)
        out.append(w)
        if i < len(parts) - 1:
            end = txt.rstrip()[-1:] if txt.strip() else ""
            pause = 0.45 if end in ".?!…" else 0.25 if end in ",;:" else 0.12
            out.append(np.zeros(int(sr * pause), np.float32))
    return np.concatenate(out) if out else np.zeros(0, np.float32)
