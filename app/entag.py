"""Danh dau cum tu tieng Anh trong van ban tieng Viet bang <en>...</en>.

Bo chuyen chu->am cua VieNeu tu doan tung tu la tieng Viet hay tieng Anh. Nhung tu tieng Anh
trung chinh ta voi tu tieng Viet ("do", "no", "you", "I", "to", "an"...) de bi doc kieu Viet
khi dung trong cau tieng Viet: "no I do not" -> "no i zo not". Bao no trong <en> de doc kieu Anh.
"""
import re

# Tu chuc nang tieng Anh hay gap (nhieu tu trung chinh ta tieng Viet)
EN_WORDS = set("""
i you he she it we they me him her us them my your his its our their mine yours
do does did done doing don't doesn't didn't no not yes yeah to in on at of for by with from into about up out
so go goes going went an a the is am are was were be been being can can't could will won't would should must may might
have has had having this that these those what why who whom whose how when where which all any some every
oh hi hello hey ok okay please thank thanks sorry and or but if then than very too also just only really
like likes liked love loves enjoy enjoys want wants need needs know think see look get got make take give come
one two three four five six seven eight nine ten good bad great nice new old big small more most much many
i'm you're he's she's it's we're they're i've you've we've i'll you'll i'd let's there here
""".split())

_VN_CHARS = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
_VN_SYL = re.compile(
    r"^(ngh|ng|nh|ch|gh|gi|kh|ph|qu|th|tr|[bcdghklmnpqrstvx])?[aeiouy]{1,3}(ng|nh|ch|[cmnpt])?$")
_PROTECT = re.compile(r"<en>.*?</en>|\[[^\]]*\]|<\|[^|]*\|>|zqxipa[a-z]+", re.I | re.S)
_CLAUSE = re.compile(r"[.!?…;:,\n\"“”()]+")
_TOKEN = re.compile(r"[A-Za-z" + _VN_CHARS + _VN_CHARS.upper() + r"'’]+")

def _kind(tok):
    low = tok.lower().replace("’", "'")
    if any(c in _VN_CHARS for c in low): return "vi"            # co dau tieng Viet -> chac chan Viet
    if low in EN_WORDS: return "en_fn"                           # tu chuc nang tieng Anh (de nham)
    if "'" in low or not _VN_SYL.match(low): return "en"         # khong the la am tiet tieng Viet
    return "amb"                                                 # khong dau, co the la tieng Viet

def _tag_clause(s, en_map):
    toks = [(m.start(), m.end(), m.group(), _kind(m.group())) for m in _TOKEN.finditer(s)]
    spans, cur = [], []
    for t in toks:
        if t[3] in ("en", "en_fn"): cur.append(t)
        else:
            if cur: spans.append(cur)
            cur = []
    if cur: spans.append(cur)
    out, last = [], 0
    for sp in spans:
        n_fn = sum(1 for t in sp if t[3] == "en_fn")
        if len(sp) >= 2:
            keep = n_fn >= 1                                      # cum >= 2 tu co tu de nham -> boc
        else:
            w = sp[0][2]; first = sp[0][0] == toks[0][0]
            # 1 tu chuc nang dung le: chi boc khi viet hoa giua cau (vd: "tra loi No")
            # hoac dung mot minh thanh 1 menh de, vd "No, toi khong thich" / "Yes!"
            keep = sp[0][3] == "en_fn" and (w[0].isupper() or w.isupper()) and (len(toks) == 1 or not first)
        if not keep: continue
        a, b = sp[0][0], sp[-1][1]
        out.append(s[last:a]); out.append(_render(s, sp, en_map)); last = b
    out.append(s[last:])
    return "".join(out)

def _render(s, sp, en_map):
    """Boc cum trong <en>; tu nao co trong en_map (tu dien 'en:') thi thay bang cach doc rieng, nam ngoai the."""
    if not en_map or not any(t[2].lower().replace("’", "'") in en_map for t in sp):
        return "<en>" + s[sp[0][0]:sp[-1][1]] + "</en>"
    parts, grp = [], []
    def flush():
        if grp: parts.append("<en>" + s[grp[0][0]:grp[-1][1]] + "</en>"); grp.clear()
    for t in sp:
        r = en_map.get(t[2].lower().replace("’", "'"))
        if r is None: grp.append(t)
        else: flush(); parts.append(r)
    flush()
    return " ".join(parts)

def tag_english(text, en_map=None):
    res, pos = [], 0
    for m in _PROTECT.finditer(text):
        res.append(_tag_plain(text[pos:m.start()], en_map)); res.append(m.group()); pos = m.end()
    res.append(_tag_plain(text[pos:], en_map))
    return "".join(res)

def _tag_plain(s, en_map=None):
    res, pos = [], 0
    for m in _CLAUSE.finditer(s):
        res.append(_tag_clause(s[pos:m.start()], en_map)); res.append(m.group()); pos = m.end()
    res.append(_tag_clause(s[pos:], en_map))
    return "".join(res)
