"""Runs on GitHub Actions: download Pixabay stock clips/photos and Wikimedia Commons public-domain images.

Item kinds: "video" (Pixabay), "photo" (Pixabay), "commons" (Wikimedia Commons, public domain / CC0 only).
Optional request key "orient": "landscape" (long videos, default) or "portrait" (Shorts).

Request file: requests/<id>.json
  {"id": "002-...", "items": [{"name": "s1", "q": "person typing laptop", "kind": "video"}, ...]}
Result: GitHub release "stock-<id>" with <name>.mp4 / <name>.jpg and manifest.json (sources).
Pixabay Content License: free for commercial use, no attribution required.
"""
import json, os, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

KEY = os.environ["PIXABAY_API_KEY"]
UA = {"User-Agent": "ledger-of-empires-stock/1.0 (https://github.com/empiresledgerof-del/ledger-of-empires-videos)"}
ORIENT = "landscape"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def download(url, dest):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


BLOCK = {"jesus", "christianity", "religion", "cross", "buddha", "buddhism", "meditation", "zen", "god", "church",
         "cartoon", "2d", "animated wallpaper", "nature animation video", "wallpaper engine", "sexy", "bikini",
         "lingerie", "nude", "green screen", "chroma key", "greenscreen", "chromakey", "transition", "glitch", "mockup", "weapon", "gun", "blood", "war", "flag", "politics"}


def relevance(q, tags):
    tags = [t.strip().lower() for t in (tags or "").split(",")]
    if any(t in BLOCK for t in tags): return -1
    words = [w for w in q.lower().split() if len(w) > 2]
    text = " ".join(tags)
    return sum(1 for w in words if w in text or w.rstrip("s") in text) / max(1, len(words))


def pick_video(q, used, min_dur=4, max_dur=60):
    data = get("https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
        {"key": KEY, "q": q, "per_page": 30, "safesearch": "true", "order": "popular"}))
    best = None
    for h in data.get("hits", []):
        if h["id"] in used or not min_dur <= h.get("duration", 0) <= max_dur: continue
        rel = relevance(q, h.get("tags"))
        if rel < 0.34: continue
        vids = {k: v for k, v in h["videos"].items() if v.get("url") and v.get("width")}
        if not vids: continue
        vertical = any(v["height"] > v["width"] for v in vids.values())
        # want a file that can fill 1080x1920 after a centre crop, without huge 4K downloads when possible
        def ok(v):
            if ORIENT == "landscape":
                return v["width"] >= 1920 and v["width"] >= v["height"]
            return (v["width"] >= 1080 and v["height"] >= 1920) if v["height"] > v["width"] else v["height"] >= 2160
        cands = sorted(vids.values(), key=lambda v: (not ok(v), v.get("size", 0) or v["width"] * v["height"]))
        f = cands[0]
        if not ok(f):
            f = max(vids.values(), key=lambda v: v["width"] * v["height"])
        score = (round(rel, 1), ok(f), vertical if ORIENT == "portrait" else not vertical, h.get("likes", 0) + h.get("downloads", 0) / 50)
        if best is None or score > best[0]:
            best = (score, h, f)
    return (best[1], best[2]) if best else (None, None)


def pick_photo(q, used):
    data = get("https://pixabay.com/api/?" + urllib.parse.urlencode(
        {"key": KEY, "q": q, "image_type": "photo", "orientation": "vertical" if ORIENT == "portrait" else "horizontal",
         "per_page": 30, "safesearch": "true", "min_width": 1920 if ORIENT == "landscape" else 1080}))
    hits = [h for h in data.get("hits", []) if h["id"] not in used and relevance(q, h.get("tags")) >= 0.34]
    hits.sort(key=lambda h: -relevance(q, h.get("tags")))
    return hits[0] if hits else None
    return None


PD_OK = ("public domain", "pd", "cc0", "cc-zero", "no restrictions")


def pick_commons(q, used):
    """Public-domain / CC0 image from Wikimedia Commons (paintings, maps, engravings, archive photos)."""
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 25,
        "gsrsearch": f"{q} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": 2600})
    data = get(url)
    best = None
    for p in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if p["pageid"] in used or ii.get("mime") not in ("image/jpeg", "image/png", "image/tiff"): continue
        meta = ii.get("extmetadata", {})
        lic = (meta.get("LicenseShortName", {}).get("value", "") + " " + meta.get("License", {}).get("value", "")).lower()
        if not any(k in lic for k in PD_OK): continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if max(w, h) < 1200: continue
        title = p.get("title", "").lower()
        if any(b in title for b in ("logo", "flag of", "coat of arms", "map legend", "icon")): continue
        words = [x for x in q.lower().split() if len(x) > 2]
        rel = sum(1 for x in words if x in title) / max(1, len(words))
        score = (rel, min(w, 4000) * min(h, 4000), -p.get("index", 0))
        if best is None or score > best[0]:
            best = (score, p, ii, meta)
    return best[1:] if best else None


def main():
    out_root = Path("stock_out"); out_root.mkdir(exist_ok=True)
    for req_path in sorted(Path("requests").glob("*.json")):
        req = json.load(open(req_path))
        global ORIENT
        ORIENT = req.get("orient", "landscape")
        tag = f"stock-{req['id']}"
        if subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0:
            print("skip", tag); continue
        out = out_root / req["id"]; out.mkdir(exist_ok=True)
        manifest, used = [], set()
        for item in req["items"]:
            try:
                if item.get("kind", "video") == "video":
                    h, f = pick_video(item["q"], used)
                    if not h:
                        manifest.append({"name": item["name"], "q": item["q"], "error": "no result"}); continue
                    used.add(h["id"]); dest = out / f"{item['name']}.mp4"
                    download(f["url"], dest)
                    manifest.append({"name": item["name"], "q": item["q"], "file": dest.name, "kind": "video",
                                     "source": h["pageURL"], "author": h.get("user"), "duration": h["duration"],
                                     "width": f["width"], "height": f["height"], "tags": h.get("tags")})
                elif item.get("kind") == "commons":
                    r = pick_commons(item["q"], used)
                    if not r:
                        manifest.append({"name": item["name"], "q": item["q"], "error": "no result"}); continue
                    p, ii, meta = r
                    used.add(p["pageid"]); ext = ".png" if ii["mime"] == "image/png" else ".jpg"
                    dest = out / f"{item['name']}{ext}"
                    download(ii.get("thumburl") or ii["url"], dest)
                    clean = lambda k: __import__("re").sub("<[^>]+>", "", meta.get(k, {}).get("value", ""))[:200]
                    manifest.append({"name": item["name"], "q": item["q"], "file": dest.name, "kind": "commons",
                                     "source": ii.get("descriptionurl"), "title": p.get("title"),
                                     "author": clean("Artist"), "license": clean("LicenseShortName"),
                                     "date": clean("DateTimeOriginal"), "tags": p.get("title")})
                else:
                    h = pick_photo(item["q"], used)
                    if not h:
                        manifest.append({"name": item["name"], "q": item["q"], "error": "no result"}); continue
                    used.add(h["id"]); dest = out / f"{item['name']}.jpg"
                    download(h["largeImageURL"], dest)
                    manifest.append({"name": item["name"], "q": item["q"], "file": dest.name, "kind": "photo",
                                     "source": h["pageURL"], "author": h.get("user"), "tags": h.get("tags")})
                print("ok", item["name"], item["q"])
            except Exception as e:
                manifest.append({"name": item["name"], "q": item["q"], "error": str(e)})
                print("fail", item["name"], e, file=sys.stderr)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
        subprocess.run(["gh", "release", "create", tag, *[str(p) for p in out.iterdir()], "--title", tag,
                        "--notes", "Pixabay stock media (Pixabay Content License). Sources in manifest.json."], check=True)
        print("released", tag)


if __name__ == "__main__":
    main()
