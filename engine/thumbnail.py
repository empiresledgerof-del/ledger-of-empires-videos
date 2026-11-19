"""Thumbnails for Ledger of Empires (see channel/thumbnail_playbook.md).

    python3 engine/thumbnail.py <id>      -> videos/<id>/thumb_1.jpg .. thumb_3.jpg (+ thumb.jpg = chosen one)
                                             and build/<id>/thumb_check.jpg (full size + 320x180 previews)
Long videos: 1280x720. Shorts: 1080x1920.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "engine" / "fonts"
GOLD = (240, 196, 92); WHITE = (255, 255, 255); NAVY_D = (7, 15, 27)


def load_image(stock, ref):
    name, start = (ref.split("@") + [None])[:2]
    p = stock / name
    if p.suffix == ".mp4":
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(start or 2), "-i", str(p), "-frames:v", "1",
                        "/tmp/_th.png"], check=True)
        return Image.open("/tmp/_th.png").convert("RGB")
    return Image.open(p).convert("RGB")


def cover(im, W, H, focus="center"):
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    fx = {"left": 0.0, "center": 0.5, "right": 1.0, "top": 0.5}.get(focus, 0.5)
    fy = 0.0 if focus == "top" else 0.5
    l = int((im.width - W) * fx); t = int((im.height - H) * fy)
    return im.crop((l, t, l + W, t + H))


def grade(im):
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Color(im).enhance(1.08)
    a = np.asarray(im).astype(np.float32)
    a[..., 0] *= 1.04; a[..., 2] *= 0.94                      # warm
    H, W = a.shape[:2]; yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.35 * np.clip(np.sqrt(((xx - W / 2) / (W / 1.3)) ** 2 + ((yy - H / 2) / (H / 1.3)) ** 2), 0, 1) ** 2
    return Image.fromarray(np.clip(a * v[..., None], 0, 255).astype(np.uint8))


def side_shade(W, H, side, strength=0.82):
    a = np.zeros((H, W), np.float32); x = np.linspace(0, 1, W)
    if side == "left": g = np.clip(1.25 - 1.6 * x, 0, 1)
    elif side == "right": g = np.clip(1.6 * x - 0.35, 0, 1)
    else:
        y = np.linspace(0, 1, H)[:, None]; return Image.fromarray((np.clip(1.1 - 1.8 * y, 0, 1) * 255 * strength).astype(np.uint8).repeat(W, 1))
    a[:] = g ** 1.3 * strength
    return Image.fromarray((a * 255).astype(np.uint8))


def draw_lines(canvas, lines, accent, side, short):
    W, H = canvas.size
    maxw = W * (0.92 if short else 0.56)
    size = 210 if short else 150
    f = ImageFont.truetype(str(FONTS / "Inter-Black.otf"), size)
    while max(f.getlength(l) for l in lines) > maxw and size > 60:
        size -= 6; f = ImageFont.truetype(str(FONTS / "Inter-Black.otf"), size)
    lh = int(size * 0.98); total = lh * len(lines)
    y = int(H * 0.08) if short else (H - total) // 2 - 10
    d = ImageDraw.Draw(canvas)
    for i, l in enumerate(lines):
        w = f.getlength(l)
        x = (W - w) / 2 if short else (int(W * 0.05) if side == "left" else int(W * 0.95 - w))
        col = GOLD if i == accent else WHITE
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((x + 6, y + 8), l, font=f, fill=(0, 0, 0, 200))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
        d.text((x, y), l, font=f, fill=col, stroke_width=max(4, size // 22), stroke_fill=NAVY_D)
        y += lh


def make_one(spec_t, stock, W, H, short):
    src = load_image(stock, spec_t["image"]); side = spec_t.get("side", "left")
    if not short and src.width / src.height < 1.2:
        # portrait art: blurred fill + the whole picture on the side opposite the text
        bg = cover(src, W, H).filter(ImageFilter.GaussianBlur(30))
        bg = Image.blend(bg, Image.new("RGB", (W, H), NAVY_D), 0.5)
        s_ = H * 1.04 / src.height; fg = src.resize((int(src.width * s_), int(src.height * s_)), Image.LANCZOS)
        x = int(W * 0.97 - fg.width) if side == "left" else int(W * 0.03)
        bg.paste(fg, (x, (H - fg.height) // 2)); im = grade(bg)
    else:
        im = grade(cover(src, W, H, spec_t.get("focus", "center")))
    shade = side_shade(W, H, "top" if short else side)
    canvas = Image.composite(Image.new("RGB", (W, H), NAVY_D), im, shade).convert("RGBA")
    draw_lines(canvas, [l.upper() for l in spec_t["lines"]], spec_t.get("accent", len(spec_t["lines"]) - 1), side, short)
    if spec_t.get("frame", True):
        ImageDraw.Draw(canvas).rectangle((8, 8, W - 9, H - 9), outline=GOLD + (170,), width=4)
    return canvas.convert("RGB")


def make(vid, choose=None):
    spec = json.load(open(ROOT / "videos" / vid / "script.json"))
    short = spec.get("format") == "short"
    W, H = (1080, 1920) if short else (1280, 720)
    stock = ROOT / "build" / vid / "stock"; out = ROOT / "videos" / vid
    thumbs = spec.get("thumbs") or []
    if not thumbs: print("no 'thumbs' in script.json"); return
    ims = []
    for i, t in enumerate(thumbs[:3], 1):
        im = make_one(t, stock, W, H, short); im.save(out / f"thumb_{i}.jpg", quality=90); ims.append(im)
    # check sheet: full size row + phone-size row
    sw, shh = (320, 180) if not short else (180, 320)
    big = [i.resize((W // 2, H // 2)) for i in ims]
    sheet = Image.new("RGB", (max(sum(b.width for b in big) + 20 * len(big), 900), big[0].height + shh + 60), (24, 24, 24))
    x = 0
    for b in big: sheet.paste(b, (x, 0)); x += b.width + 20
    x = 0
    for i in ims: sheet.paste(i.resize((sw, shh), Image.LANCZOS), (x, big[0].height + 40)); x += sw + 30
    (ROOT / "build" / vid).mkdir(parents=True, exist_ok=True)
    sheet.save(ROOT / "build" / vid / "thumb_check.jpg", quality=88)
    k = choose or spec.get("thumb_choice", 1)
    ims[k - 1].save(out / "thumb.jpg", quality=92)
    print("thumbs:", [f"thumb_{i}.jpg" for i in range(1, len(ims) + 1)], "chosen", k, "| check: build/%s/thumb_check.jpg" % vid)


if __name__ == "__main__":
    make(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
