"""Ledger of Empires pipeline (long videos and Shorts).

    python3 engine/make_video.py stock  <id> [--retry b --only s3_0,s5_1]   # robot downloads footage/images, contact sheet
    python3 engine/make_video.py sheet  <id>                               # contact sheet of build/<id>/stock
    python3 engine/make_video.py voice  <id>                               # voice lines only (fast; prints total length)
    python3 engine/make_video.py render <id>                               # voice + full render -> videos/<id>/final.mp4
    python3 engine/make_video.py frames <id> [t1,t2,...]                   # check frames from final.mp4

script.json format: see engine/film.py. Each narrated scene may have "find": [{"q": "search words", "kind":
"video"|"photo"|"commons"}, ...]; `stock` turns them into files s<scene>_<n>.* and fills "shots".
"""
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "empiresledgerof-del/ledger-of-empires-videos"
sys.path.insert(0, str(ROOT / "engine"))


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def load(vid): return json.load(open(ROOT / "videos" / vid / "script.json"))
def save(vid, spec): json.dump(spec, open(ROOT / "videos" / vid / "script.json", "w"), indent=1, ensure_ascii=False)


def bdir(vid):
    d = ROOT / "build" / vid; (d / "stock").mkdir(parents=True, exist_ok=True); return d


def stock(vid, retry="", only=None):
    spec = load(vid); req_id = vid + (f"-{retry}" if retry else "")
    items = []
    for i, sc in enumerate(spec["scenes"]):
        for n, f in enumerate(sc.get("find", [])):
            name = f"s{i}_{n}"
            if only and name not in only: continue
            items.append({"name": name, "q": f["q"], "kind": f.get("kind", "video")})
    orient = "portrait" if spec.get("format") == "short" else "landscape"
    json.dump({"id": req_id, "orient": orient, "items": items}, open(ROOT / "requests" / f"{req_id}.json", "w"), indent=1)
    sh("git", "-C", ROOT, "add", "requests", f"videos/{vid}")
    sh("git", "-C", ROOT, "commit", "-qm", f"Stock request {req_id}")
    sh("git", "-C", ROOT, "-c", "push.negotiate=true", "push", "-q", "origin", "HEAD:main")
    base = f"https://github.com/{REPO}/releases/download/stock-{req_id}/"
    print("waiting for the stock robot (GitHub Action)...", flush=True)
    for _ in range(60):
        time.sleep(15)
        r = subprocess.run(["curl", "-sSL", "-o", "/tmp/manifest.json", "-w", "%{http_code}", base + "manifest.json"],
                           capture_output=True, text=True)
        if r.stdout.strip() == "200": break
    else:
        raise SystemExit("stock release did not appear in 15 min - check the repo's Actions tab")
    man = json.load(open("/tmp/manifest.json")); bd = bdir(vid)
    for m in man:
        if "file" in m:
            sh("curl", "-sSL", "-o", bd / "stock" / m["file"], base + m["file"])
            print("ok ", m["name"], m["kind"], m["q"], "|", (m.get("title") or m.get("tags") or "")[:90])
        else:
            print("ERR", m["name"], m["q"], m.get("error"))
    old = bd / "stock" / "manifest.json"
    merged = json.load(open(old)) if old.exists() else []
    merged = [x for x in merged if x["name"] not in {m["name"] for m in man}] + man
    json.dump(merged, open(old, "w"), indent=1)
    files = {m["name"]: m["file"] for m in merged if "file" in m}
    for i, sc in enumerate(spec["scenes"]):
        touched = only and any(f"s{i}_{n}" in only for n in range(len(sc.get("find", []))))
        if sc.get("find") and (not sc.get("shots") or touched):
            new = [files[f"s{i}_{n}"] + ("@1" if files[f"s{i}_{n}"].endswith(".mp4") else "")
                   for n in range(len(sc["find"])) if f"s{i}_{n}" in files]
            if touched and sc.get("shots"):   # keep hand-picked shots, swap in only the re-fetched ones
                keep = [x for x in sc["shots"] if x.split("@")[0].split("#")[0].rsplit(".", 1)[0] not in only]
                new = keep + [x for x in new if x.split("@")[0].rsplit(".", 1)[0] in only]
            sc["shots"] = new
    save(vid, spec); sheet(vid)


def sheet(vid):
    from PIL import Image, ImageDraw
    bd = bdir(vid); ims = []
    for f in sorted((bd / "stock").iterdir()):
        if f.suffix == ".mp4":
            sh("ffmpeg", "-loglevel", "error", "-y", "-ss", "1.5", "-i", f, "-frames:v", "1", "-vf", "scale=-2:240", "/tmp/_s.jpg")
            im = Image.open("/tmp/_s.jpg").copy()
        elif f.suffix in (".jpg", ".png"):
            im = Image.open(f).convert("RGB"); im.thumbnail((430, 240))
        else: continue
        ImageDraw.Draw(im).text((6, 6), f.stem, fill="yellow"); ims.append(im)
    if not ims: return
    rows, row, w = [], [], 0
    for im in ims:
        if w + im.width > 2000 and row: rows.append(row); row, w = [], 0
        row.append(im); w += im.width + 6
    rows.append(row)
    S = Image.new("RGB", (2000, 246 * len(rows)), (30, 30, 30))
    for r, rw in enumerate(rows):
        x = 0
        for im in rw: S.paste(im, (x, r * 246)); x += im.width + 6
    S.save(bd / "sheet.jpg", quality=85); print("sheet:", bd / "sheet.jpg")


def voices(vid):
    import voice as V, numpy as np
    spec = load(vid); bd = bdir(vid); v = V.Voice(); out = {}
    total = 0.0
    for i, sc in enumerate(spec["scenes"]):
        if "say" not in sc: continue
        a = v.speak(sc["say"], sc.get("voice", spec["voice"]), spec.get("speed", 0.95))
        idx = np.where(np.abs(a) > 0.01)[0]; a = a[max(idx[0] - 240, 0): idx[-1] + 2400]
        p = bd / f"vo_{i}.wav"; V.save_wav(p, a); out[i] = p; total += len(a) / V.SR
    if V.MISSING:
        raise SystemExit(f"STOP: these words would be spelled out letter by letter: {sorted(V.MISSING)}. "
                         "Add them to CUSTOM in engine/voice.py (misaki symbols) and run again.")
    words = sum(len(sc.get("say", "").split()) for sc in spec["scenes"])
    print(f"voice: {words} words, {total:.1f} s of speech")
    return out


def render(vid):
    import film
    spec = load(vid); bd = bdir(vid)
    wavs = voices(vid)
    state = json.load(open(ROOT / "state.json"))
    recent = [m for v in state.get("videos", [])[-2:] for m in v.get("music", [])]
    out = ROOT / "videos" / vid / "final.mp4"
    t0 = time.time()
    info = film.render(spec, bd, bd / "stock", ROOT / "music", out, wavs, used_recent=recent)
    json.dump(info, open(bd / "render_info.json", "w"), indent=1)
    print(f"rendered {out} ({info['duration']:.1f} s) in {time.time() - t0:.0f} s; music: {info['music']}")
    if info.get("chapters") and len(info["chapters"]) > 1:
        print("YouTube chapters:")
        for c in info["chapters"]:
            print(f"{int(c['t'] // 60)}:{int(c['t'] % 60):02d} {c['title']}")
    frames(vid)
    if spec.get("thumbs"):
        from thumbnail import make as make_thumb
        make_thumb(vid)
    return info


def frames(vid, times=None):
    bd = bdir(vid); out = ROOT / "videos" / vid / "final.mp4"
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True)
    d = float(r.stdout.strip())
    times = times or [0.5, 2.0] + [round(d * k / 8, 1) for k in range(1, 8)]
    for t in times:
        sh("ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", out, "-frames:v", "1", "-vf", "scale=640:-2",
           bd / f"check_{t}.jpg")
    print("check frames:", ", ".join(f"check_{t}.jpg" for t in times), "in", bd)


if __name__ == "__main__":
    cmd, vid = sys.argv[1], sys.argv[2]
    if cmd == "stock":
        retry = sys.argv[sys.argv.index("--retry") + 1] if "--retry" in sys.argv else ""
        only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
        stock(vid, retry, only)
    elif cmd == "sheet": sheet(vid)
    elif cmd == "voice": voices(vid)
    elif cmd == "render": render(vid)
    elif cmd == "frames": frames(vid, [float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None)
