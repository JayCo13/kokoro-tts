"""Tu cap nhat Kokoro TTS tu GitHub moi lan mo ung dung.
- Khong can git. Chi tai phan code (vai tram KB), khong tai lai mo hinh.
- Giu nguyen du lieu rieng cua tung may (app/pronounce.txt, .venv ...).
- Mat mang / GitHub loi -> bo qua, mo ung dung binh thuong.
- May dang phat trien (co thu muc .git) -> khong tu cap nhat de khong de len code dang sua.
"""
import io, json, os, shutil, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path

REPO = "JayCo13/kokoro-tts"
BRANCH = "main"
ROOT = Path(__file__).resolve().parent.parent          # thu muc goc (chua app/, .venv/)
STAMP = ROOT / ".version"                               # commit dang dung
KEEP = {".venv", ".git", ".version", "app/pronounce.txt"}   # khong bao gio ghi de / xoa

def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "kokoro-tts-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _find_uv():
    for c in (shutil.which("uv"), Path.home() / ".local/bin/uv", Path.home() / ".local/bin/uv.exe",
              Path("/opt/homebrew/bin/uv"), Path.home() / ".cargo/bin/uv"):
        if c and Path(c).exists(): return str(c)
    return None

def main():
    if (ROOT / ".git").exists():
        print("[cap nhat] May phat trien (co .git) -> bo qua tu cap nhat."); return
    try:
        latest = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}", 6))["sha"]
    except Exception as e:
        print(f"[cap nhat] Khong kiem tra duoc ban moi ({type(e).__name__}) -> dung ban hien tai."); return
    current = STAMP.read_text().strip() if STAMP.exists() else ""
    if latest == current:
        print("[cap nhat] Dang dung ban moi nhat."); return

    print(f"[cap nhat] Co ban moi ({latest[:7]}), dang tai...")
    try:
        data = _get(f"https://codeload.github.com/{REPO}/zip/{latest}", 60)
    except Exception as e:
        print(f"[cap nhat] Tai that bai ({type(e).__name__}) -> dung ban hien tai."); return

    old_req = (ROOT / "app/requirements.txt").read_bytes() if (ROOT / "app/requirements.txt").exists() else b""
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        src = next(Path(tmp).iterdir())                 # thu muc kokoro-tts-<sha>/
        new_files = {p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file()}
        for rel in sorted(new_files):
            if rel in KEEP or rel.split("/")[0] in KEEP: continue
            dst = ROOT / rel; dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dst)
        # xoa file code cu khong con trong ban moi (chi trong app/, tru du lieu rieng)
        for p in (ROOT / "app").rglob("*"):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and rel not in new_files and rel not in KEEP and "__pycache__" not in rel:
                p.unlink()
    for f in ROOT.glob("*.command"):
        try: f.chmod(0o755)
        except Exception: pass

    if (ROOT / "app/requirements.txt").read_bytes() != old_req:
        print("[cap nhat] Ban moi can them thu vien, dang cai...")
        uv = _find_uv()
        if uv:
            r = subprocess.run([uv, "pip", "install", "--python", sys.executable, "-r", str(ROOT / "app/requirements.txt")])
            if r.returncode != 0:
                print("[cap nhat] Cai thu vien loi -> se thu lai lan mo sau."); return
        else:
            print("[cap nhat] Khong tim thay uv -> hay chay lai file '1. Cai dat' de cai thu vien moi."); return
    STAMP.write_text(latest)
    print(f"[cap nhat] Da cap nhat len ban {latest[:7]}.")

if __name__ == "__main__":
    try: main()
    except Exception as e: print(f"[cap nhat] Loi khong mong muon: {e} -> dung ban hien tai.")
