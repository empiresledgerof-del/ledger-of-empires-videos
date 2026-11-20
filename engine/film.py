"""Ledger of Empires renderer: long videos (1920x1080) and Shorts (1080x1920).

Pipeline (fast on 2 CPUs: every frame is encoded about twice):
  1. each shot -> its own graded clip with a slow push-in or Ken Burns pan (ffmpeg)
  2. chapter cards and stat count-ups -> PIL frames piped to ffmpeg
  3. concat + burned captions (ASS/libass: sentence lower-thirds for long, big word captions for Shorts)
  4. audio: voice, mood music per chapter (crossfaded, ducked ~16 dB under voice), whooshes, -14 LUFS, stereo

script.json (videos/<id>/script.json):
{
 "id": "001-tulip-mania", "format": "long" | "short", "title": "...", "voice": "bm_george", "speed": 0.95,
 "scenes": [
   {"card": {"kicker": "CHAPTER 1", "title": "A Flower From the East"}, "mood": "mystery"},
   {"say": "Narration...", "mood": "tension", "shots": ["s1_0.mp4@2", "s1_1.jpg"],
    "stat": {"value": 5000, "prefix": "", "suffix": " guilders", "label": "for a single bulb", "decimals": 0},
    "hook": "TEXT ON SCREEN"}          # hook: big on-screen text (Shorts first scene)
 ]
}
Shots: files in build/<id>/stock/ (from the robot), "file@start" for video start seconds,
"file#pan=left|right|up|down|in|out" for still images.
"""
import json, math, random, re, subprocess, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ENGINE = Path(__file__).resolve().parent
FONTS = ENGINE / "fonts"
FPS = 30
NAVY = (14, 27, 44); NAVY_D = (7, 15, 27); NAVY_L = (26, 47, 77)
GOLD = (224, 178, 74); GOLD_L = (251, 230, 166); GOLD_D = (169, 120, 30); PARCH = (234, 220, 192); WHITE = (255, 255, 255)
PAD = 0.35            # silence after each narrated scene
CARD_DUR = 3.0
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
GRADE = ("eq=contrast=1.06:saturation=0.86:brightness=-0.01,"
         "colorbalance=rs=0.035:gs=0.01:bs=-0.04:rh=0.03:gh=0.01:bh=-0.03,vignette=angle=PI/5,noise=alls=5:allf=t")


def F(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def sh(*cmd, inp=None):
    r = subprocess.run([str(c) for c in cmd], input=inp, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr.decode()[-1500:]}")
    return r


def wav_dur(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def media_dur(p):
    r = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p)
    try: return float(r.stdout.decode().strip())
    except ValueError: return 0.0


def ease(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3


# ---------------------------------------------------------------- backgrounds / brand
def map_bg(W, H):
    """Navy background with faint old-map grid, like the banner."""
    im = Image.new("RGB", (W, H), NAVY)
    g = Image.new("L", (W, H), 0); d = ImageDraw.Draw(g)
    for y in range(-H, 2 * H, max(60, H // 12)):
        pts = [(x, y + 0.00012 * (x - W / 2) ** 2) for x in range(0, W + 40, 40)]
        d.line(pts, fill=40, width=2)
    for x in range(0, W + 1, max(80, W // 16)):
        pts = [(x + 0.08 * (W / 2 - x) * math.sin(math.pi * yy / H), yy) for yy in range(0, H + 40, 40)]
        d.line(pts, fill=30, width=2)
    gold = Image.new("RGB", (W, H), GOLD)
    im = Image.composite(gold, im, g.point(lambda v: v // 3))
    # radial lift in the middle
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 1.6)) ** 2 + ((yy - H / 2) / (H / 1.4)) ** 2)
    lift = np.clip(1 - r, 0, 1)[..., None] * np.array(NAVY_L) * 0.5
    arr = np.clip(np.asarray(im).astype(np.float32) * (1 - 0.25 * np.clip(r, 0, 1))[..., None] + lift, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def logo(size):
    p = ENGINE.parent / "brand" / "logo-800.png"
    im = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    m = Image.new("L", (size, size), 0); ImageDraw.Draw(m).ellipse((0, 0, size - 1, size - 1), fill=255)
    im.putalpha(m); return im


def text_img(text, fnt, fill, spacing=0):
    if spacing:
        widths = [fnt.getlength(c) for c in text]; w = int(sum(widths) + spacing * (len(text) - 1)) + 8
        box = fnt.getbbox("Hg"); h = box[3] + 12
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im); x = 4
        for c, cw in zip(text, widths):
            d.text((x, 4), c, font=fnt, fill=fill); x += cw + spacing
        return im
    box = fnt.getbbox(text)
    im = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - box[0], 4 - box[1]), text, font=fnt, fill=fill)
    return im


def wrap(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if fnt.getlength(t) <= max_w or not cur: cur = t
        else: lines.append(cur); cur = w
    return lines + ([cur] if cur else [])


def paste_alpha(canvas, sprite, x, y, alpha=1.0):
    if alpha <= 0.01: return
    s = sprite
    if alpha < 0.99:
        s = sprite.copy(); s.putalpha(sprite.split()[3].point(lambda v: int(v * alpha)))
    canvas.alpha_composite(s, (int(x), int(y)))


def pipe_frames(frames_fn, n, W, H, out):
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", *X264, "-r", str(FPS), str(out)], stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frames_fn(i / FPS).convert("RGB").tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError("frame pipe failed")


# ---------------------------------------------------------------- special segments
INK = (52, 36, 22); SEPIA = (128, 88, 40)


def parchment(W, H, seed=3):
    """Aged paper: warm base, soft mottling, darker burnt edges, faint map lines (no external texture needed)."""
    rng = np.random.default_rng(seed)
    base = np.array([233, 218, 184], np.float32)
    def blob(scale, amp):
        small = rng.standard_normal((max(2, H // scale), max(2, W // scale))).astype(np.float32)
        im = Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
        return (np.asarray(im).astype(np.float32) / 255 - 0.5) * amp
    m = blob(64, 26) + blob(16, 12) + blob(4, 6)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    burn = np.clip(r - 0.62, 0, 1) ** 1.6 * 150
    arr = base[None, None, :] + m[..., None] - burn[..., None] * np.array([0.75, 0.95, 1.2])
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    g = Image.new("L", (W, H), 0); d = ImageDraw.Draw(g)
    for y in range(-H, 2 * H, max(70, H // 10)):
        d.line([(x, y + 0.0001 * (x - W / 2) ** 2) for x in range(0, W + 40, 40)], fill=46, width=2)
    for x in range(0, W + 1, max(90, W // 14)):
        d.line([(x + 0.06 * (W / 2 - x) * math.sin(math.pi * yy_ / H), yy_) for yy_ in range(0, H + 40, 40)], fill=34, width=2)
    return Image.composite(Image.new("RGB", (W, H), SEPIA), im, g.point(lambda v: v // 2))


def ornament(width, color, t=1.0):
    """Two engraved rules with a centre diamond, grown by t (0..1)."""
    h = 36; im = Image.new("RGBA", (width, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, cy = width / 2, h / 2; half = (width / 2 - 30) * ease(t)
    if half > 2:
        d.line((cx - 26 - half, cy, cx - 26, cy), fill=color, width=3); d.line((cx + 26, cy, cx + 26 + half, cy), fill=color, width=3)
        d.line((cx - 26 - half * 0.8, cy + 7, cx - 30, cy + 7), fill=color + (140,), width=1)
        d.line((cx + 30, cy + 7, cx + 26 + half * 0.8, cy + 7), fill=color + (140,), width=1)
    k = 14 * ease(t * 1.5)
    if k > 1: d.polygon([(cx, cy - k), (cx + k, cy), (cx, cy + k), (cx - k, cy)], fill=color)
    return im


def chapter_card(card, W, H, out, dur=CARD_DUR):
    bg = parchment(W, H).convert("RGBA")
    long = W > H
    lg = logo(120 if long else 160)
    kick = text_img(card.get("kicker", ""), F("Cormorant-MediumItalic.ttf", 58 if long else 70), SEPIA)
    tf = F("Cinzel-Bold.ttf", 108 if long else 104)
    lines = wrap(card["title"].upper(), tf, W * 0.78)
    while len(lines) > (2 if long else 3) and tf.size > 60:
        tf = F("Cinzel-Bold.ttf", tf.size - 8); lines = wrap(card["title"].upper(), tf, W * 0.78)
    tl = [text_img(l, tf, INK) for l in lines]
    th = sum(t.height for t in tl) + 10 * (len(tl) - 1)
    total = lg.height + 34 + kick.height + 26 + th + 70
    y0 = (H - total) / 2
    ow = int(W * (0.42 if long else 0.7))

    def frame(t):
        z = 1 + 0.025 * t / dur
        c = bg.resize((int(W * z), int(H * z)), Image.BILINEAR).crop(
            (int((W * z - W) / 2), int((H * z - H) / 2), int((W * z - W) / 2) + W, int((H * z - H) / 2) + H))
        fo = 1 - max(0, (t - (dur - 0.4)) / 0.4)
        a1, a2, a3 = ease(t / 0.5), ease((t - 0.2) / 0.5), ease((t - 0.4) / 0.7)
        paste_alpha(c, lg, (W - lg.width) / 2, y0, a1 * fo)
        yk = y0 + lg.height + 34
        paste_alpha(c, kick, (W - kick.width) / 2, yk + 10 * (1 - a2), a2 * fo)
        y = yk + kick.height + 26
        for t_ in tl:
            paste_alpha(c, t_, (W - t_.width) / 2, y + 18 * (1 - a3), a3 * fo); y += t_.height + 10
        paste_alpha(c, ornament(ow, SEPIA, (t - 0.6) / 0.8), (W - ow) / 2, y + 24, fo)
        if fo < 1:   # fade to black for a clean cut back to the film
            c = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), c, fo)
        return c
    pipe_frames(frame, int(round(dur * FPS)), W, H, out)


def still_of(path, W, H, start=1.0):
    """A frame of a shot (video or image) scaled to cover W x H."""
    p = Path(path)
    if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
        im = Image.open(p).convert("RGB")
    else:
        sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start:.2f}", "-i", p, "-frames:v", "1", "/tmp/_still.png")
        im = Image.open("/tmp/_still.png").convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    l, t = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((l, t, l + W, t + H))


def stat_segment(stat, still, W, H, out, dur):
    long = W > H
    bg = still.filter(ImageFilter.GaussianBlur(18))
    bg = Image.blend(bg, Image.new("RGB", (W, H), NAVY_D), 0.62).convert("RGBA")
    nf = F("Cinzel-Bold.ttf", 190 if long else 170)
    lf = F("Cormorant-MediumItalic.ttf", 64 if long else 70)
    dec = int(stat.get("decimals", 0)); val = float(stat["value"])
    label_lines = wrap(stat.get("label", ""), lf, W * 0.75)
    labels = [text_img(l, lf, PARCH) for l in label_lines]

    def fmt(v):
        s = f"{v:,.{dec}f}"
        return f"{stat.get('prefix', '')}{s}{stat.get('suffix', '')}"
    final = text_img(fmt(val), nf, GOLD_L)
    cy = H * (0.45 if long else 0.42)

    def frame(t):
        z = 1 + 0.04 * t / dur
        c = bg.resize((int(W * z), int(H * z)), Image.BILINEAR).crop(
            (int((W * z - W) / 2), int((H * z - H) / 2), int((W * z - W) / 2) + W, int((H * z - H) / 2) + H))
        k = ease(t / 1.4)
        num = text_img(fmt(val * k), nf, GOLD_L)
        a = ease(t / 0.3)
        paste_alpha(c, num, (W - final.width) / 2 + (final.width - num.width) / 2, cy - final.height / 2, a)
        y = cy + final.height / 2 + 30
        d = ImageDraw.Draw(c); half = int(final.width * 0.35 * ease((t - 0.2) / 0.6))
        if half > 2: d.rectangle((W / 2 - half, y - 14, W / 2 + half, y - 10), fill=GOLD + (230,))
        for lb in labels:
            paste_alpha(c, lb, (W - lb.width) / 2, y + 10, ease((t - 0.5) / 0.5)); y += lb.height + 6
        return c
    pipe_frames(frame, int(round(dur * FPS)), W, H, out)


# ---------------------------------------------------------------- normal shots
def parse_shot(s):
    name, start, pan = s, None, None
    if "#fit" in name: name = name.replace("#fit", ""); pan = "fit"
    if "#pan=" in name: name, pan = name.split("#pan=")
    if "@" in name: name, start = name.split("@"); start = float(start)
    return name, start, pan


def prep_image(src, W, H, dst, fit=None):
    """Cover-fit an image at 1.2x the frame. fit=True: whole image on a blurred fill (portrait paintings in long
    videos by default, or any shot marked '#fit'); Shorts crop landscape art to fill the screen and pan across it."""
    im = Image.open(src).convert("RGB")
    BW, BH = int(W * 1.2), int(H * 1.2)
    ar_img, ar_frame = im.width / im.height, W / H
    if fit is None: fit = ar_frame > 1 and ar_img < 1.15
    if fit:
        s = max(BW / im.width, BH / im.height)
        bg = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.BILINEAR)
        bg = bg.crop(((bg.width - BW) // 2, (bg.height - BH) // 2, (bg.width - BW) // 2 + BW, (bg.height - BH) // 2 + BH))
        bg = Image.blend(bg.filter(ImageFilter.GaussianBlur(40)), Image.new("RGB", (BW, BH), NAVY_D), 0.45)
        s = min(BW * 0.92 / im.width, BH * 0.92 / im.height)
        fg = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        bg.paste(fg, ((BW - fg.width) // 2, (BH - fg.height) // 2)); out = bg
    else:
        s = max(BW / im.width, BH / im.height)
        out = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
        out = out.crop(((out.width - BW) // 2, (out.height - BH) // 2, (out.width - BW) // 2 + BW, (out.height - BH) // 2 + BH))
    out.save(dst, quality=93)


def render_shot(src, W, H, dur, out, start=None, pan=None, flash=False, rng=random):
    p = Path(src); n = int(round(dur * FPS))
    fl = ",fade=t=in:st=0:d=0.14:color=white" if flash else ""
    if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
        tmp = out.with_suffix(".prep.jpg"); prep_image(p, W, H, tmp, fit=True if pan == "fit" else None)
        BW, BH = int(W * 1.2), int(H * 1.2)
        if pan == "fit": pan = "in"
        if not pan:
            im_ar = Image.open(p).size; im_ar = im_ar[0] / im_ar[1]
            pan = rng.choice(["left", "right"]) if (W < H and im_ar > 1.1) else rng.choice(["in", "left", "right", "in", "out", "up"])
        # zoom z(t) and crop offsets; output always W x H from a BW x BH plate
        zt = f"(on/{n})"
        if pan == "in":    z, x, y = f"1.0+0.12*{zt}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
        elif pan == "out": z, x, y = f"1.12-0.12*{zt}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
        elif pan == "left": z, x, y = "1.06", f"(iw-iw/zoom)*(1-{zt})", "(ih-ih/zoom)/2"
        elif pan == "right": z, x, y = "1.06", f"(iw-iw/zoom)*{zt}", "(ih-ih/zoom)/2"
        elif pan == "up":   z, x, y = "1.06", "(iw-iw/zoom)/2", f"(ih-ih/zoom)*(1-{zt})"
        else:               z, x, y = "1.06", "(iw-iw/zoom)/2", f"(ih-ih/zoom)*{zt}"
        # supersample 2x to keep zoompan smooth
        vf = (f"scale={BW*2}:{BH*2},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},"
              f"{GRADE}{fl},format=yuv420p")
        sh("ffmpeg", "-loglevel", "error", "-y", "-i", tmp, "-vf", vf, "-frames:v", n, *X264, out)
    else:
        total = media_dur(p)
        st = start if start is not None else 1.0
        if total and st + dur > total - 0.2: st = max(0.0, total - dur - 0.3)
        slow = total and total - 0.3 < dur          # clip too short: slow it down a little
        pts = f"setpts={min(1.6, (dur + 0.4) / max(0.5, total - 0.3)):.3f}*PTS," if slow else ""
        zoom = rng.choice([0.05, 0.07])
        vf = (f"{pts}fps={FPS},scale=w='{W}*(1+{zoom}*t/{dur:.2f})':h='{H}*(1+{zoom}*t/{dur:.2f})':"
              f"force_original_aspect_ratio=increase:eval=frame,crop={W}:{H},{GRADE}{fl},format=yuv420p")
        sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{st:.2f}", "-i", p, "-vf", vf, "-frames:v", n, "-an", *X264, out)


# ---------------------------------------------------------------- captions (ASS)
def ass_time(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _balance(text):
    """One caption = one or two balanced lines (break at a comma near the middle if there is one)."""
    if len(text) <= 46: return text
    words = text.split(); best, bi = 1e9, 1
    for i in range(1, len(words)):
        left = " ".join(words[:i]); diff = abs(len(left) - len(text) / 2)
        if left.endswith(","): diff -= 8
        if diff < best: best, bi = diff, i
    return " ".join(words[:bi]) + "\\N" + " ".join(words[bi:])


def sentences(text):
    """Caption chunks: whole sentences up to ~92 chars (two lines), longer ones split at commas / near the middle."""
    out = []
    for p in re.split(r"(?<=[.!?])\s+", text.strip()):
        parts = [p]
        while any(len(x) > 92 for x in parts):
            nxt = []
            for x in parts:
                if len(x) <= 92: nxt.append(x); continue
                commas = [m.end() for m in re.finditer(r",\s", x)]
                cut = min(commas, key=lambda c: abs(c - len(x) / 2)) if commas else None
                if not cut or not (0.25 < cut / len(x) < 0.75):
                    w = x.split(); acc = 0; cut = None
                    for i, ww in enumerate(w):
                        acc += len(ww) + 1
                        if acc >= len(x) / 2: cut = acc; break
                nxt += [x[:cut].strip(), x[cut:].strip()]
            parts = nxt
        out += [x for x in parts if x]
    return out


def make_ass(timeline, W, H, short, path):
    gold = "&H004AB2E0"; white = "&H00FFFFFF"; cream = "&H00D9ECF6"
    if short:
        style = (f"Style: Cap,LoE Display,84,{cream},{gold},&H00101A26,&H8C000000,0,0,0,0,100,100,2,0,1,6,3,2,70,70,{int(H*0.30)},1\n"
                 f"Style: Hook,LoE Display,88,{cream},{gold},&H00101A26,&H96000000,0,0,0,0,100,100,2,0,1,6,4,8,60,60,{int(H*0.11)},1\n")
    else:
        style = (f"Style: Cap,LoE Serif Bold,70,{cream},{gold},&H00141A22,&H96000000,0,0,0,0,100,100,0.5,0,1,2.4,2,2,330,330,62,1\n"
                 f"Style: Hook,LoE Display,78,{cream},{gold},&H00141A22,&H96000000,0,0,0,0,100,100,3,0,1,3,3,8,120,120,90,1\n")
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
             "MarginR, MarginV, Encoding", style.strip(), "", "[Events]",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for seg in timeline:
        if seg["kind"] != "say": continue
        t0, dur, text = seg["t0"], seg["voice_dur"], seg["say"]
        if seg.get("hook"):
            lines.append(f"Dialogue: 1,{ass_time(t0)},{ass_time(t0 + min(3.2, dur))},Hook,,0,0,0,,{{\\fad(120,250)}}{seg['hook']}")
        if short:
            words = text.split(); total = sum(len(w) + 1 for w in words); t = t0; chunk = []
            for i, w in enumerate(words):
                chunk.append(w)
                if len(chunk) == 3 or w[-1] in ".,!?;:" or i == len(words) - 1:
                    d = dur * sum(len(x) + 1 for x in chunk) / total
                    txt = " ".join(chunk).upper().replace("{", "(").replace("}", ")")
                    lines.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},Cap,,0,0,0,,{{\\fad(40,0)\\t(0,90,\\fscx108\\fscy108)\\t(90,180,\\fscx100\\fscy100)}}{txt}")
                    t += d; chunk = []
        else:
            sents = sentences(text); total = sum(len(s) for s in sents); t = t0
            for s in sents:
                d = dur * len(s) / total
                lines.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d - 0.05)},Cap,,0,0,0,,{{\\fad(120,120)}}{_balance(s)}")
                t += d
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- audio
def whoosh(sr=48000, dur=0.5, seed=1):
    rng = np.random.default_rng(seed); n = int(sr * dur)
    noise = rng.standard_normal(n).astype(np.float32)
    b = np.cumsum(noise); b -= np.convolve(b, np.ones(64) / 64, mode="same")       # band-ish noise
    env = np.sin(np.linspace(0, math.pi, n)) ** 2
    out = b * env; return (out / (np.abs(out).max() + 1e-6) * 0.5).astype(np.float32)


def build_audio(timeline, bd, music_dir, tracks_meta, used_recent, total, short):
    sr = 48000
    # voice track
    voice = np.zeros(int(total * sr) + sr, np.float32)
    sfx = np.zeros_like(voice)
    for seg in timeline:
        i0 = int(seg["t0"] * sr)
        if seg["kind"] == "say":
            sh("ffmpeg", "-loglevel", "error", "-y", "-i", seg["wav"], "-ar", str(sr), "-ac", "1", "-f", "f32le", bd / "_v.raw")
            a = np.fromfile(bd / "_v.raw", np.float32); voice[i0:i0 + len(a)] += a[:len(voice) - i0]
        if seg["kind"] in ("card", "stat") or seg.get("flash"):
            w = whoosh(seed=int(seg["t0"] * 10)) * (0.9 if seg["kind"] == "card" else 0.45)
            j = max(0, i0 - int(0.18 * sr)); sfx[j:j + len(w)] += w[:len(sfx) - j]
    voice.tofile(bd / "voice.f32"); sfx.tofile(bd / "sfx.f32")
    # music: one track per mood run, crossfaded
    runs = []
    for seg in timeline:
        m = seg.get("mood") or "reflective"
        if runs and runs[-1][0] == m: runs[-1][2] = seg["t0"] + seg["dur"]
        else: runs.append([m, seg["t0"], seg["t0"] + seg["dur"]])
    chosen, parts = [], []
    for k, (mood, a, b) in enumerate(runs):
        cands = [t for t in tracks_meta if mood in t["moods"]] or tracks_meta
        fresh = [t for t in cands if t["file"] not in used_recent and t["file"] not in chosen[-1:]]
        tr = (fresh or cands)[k % len(fresh or cands)] if short else random.choice(fresh or cands)
        chosen.append(tr["file"])
        d = b - a + (1.6 if k < len(runs) - 1 else 2.0)
        tdur = media_dur(music_dir / tr["file"]); off = random.uniform(0, max(0, min(30, tdur - d - 1))) if tdur > d + 2 else 0
        out = bd / f"_m{k}.wav"
        sh("ffmpeg", "-loglevel", "error", "-y", "-stream_loop", "-1", "-ss", f"{off:.1f}", "-i", music_dir / tr["file"],
           "-t", f"{d:.2f}", "-ar", str(sr), "-ac", "2", "-af", "loudnorm=I=-30:TP=-6", out)
        parts.append(out)
    # chain crossfades
    if len(parts) == 1:
        sh("cp", parts[0], bd / "music.wav")
    else:
        ins = []; fc = ""; last = "[0:a]"
        for k, p in enumerate(parts): ins += ["-i", p]
        for k in range(1, len(parts)):
            nxt = f"[x{k}]" if k < len(parts) - 1 else "[mus]"
            fc += f"{last}[{k}:a]acrossfade=d=1.6:c1=tri:c2=tri{nxt};"; last = nxt
        sh("ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", fc.rstrip(";"), "-map", "[mus]", bd / "music.wav")
    fc = ("[0:a]aformat=channel_layouts=mono,loudnorm=I=-15:TP=-2:LRA=9,asplit=2[v1][v2];"
          "[1:a]atrim=0:" + f"{total:.2f}" + ",afade=t=out:st=" + f"{max(0, total - 2.5):.2f}" + ":d=2.5[m];"
          "[m][v1]sidechaincompress=threshold=0.03:ratio=4:attack=30:release=500[md];"
          "[2:a]aformat=channel_layouts=mono,volume=0.35[s];"
          "[v2][md][s]amix=inputs=3:normalize=0:duration=longest,atrim=0:" + f"{total:.2f}" +
          ",loudnorm=I=-14:TP=-1.5:LRA=11,aformat=channel_layouts=stereo[a]")
    sh("ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", bd / "voice.f32",
       "-i", bd / "music.wav", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", bd / "sfx.f32",
       "-filter_complex", fc, "-map", "[a]", "-ar", str(sr), bd / "mix.wav")
    return chosen


# ---------------------------------------------------------------- main render
def fit_size(path, limit_mb=95):
    """Cloudinary free plan and GitHub both cap files at 100 MB: 2-pass re-encode to fit if needed."""
    path = Path(path)
    if path.stat().st_size <= limit_mb * 1e6: return False
    d = media_dur(path); a_k = 160
    v_k = int((limit_mb * 8e6 * 0.97 / d) / 1000) - a_k
    tmp = path.with_suffix(".fit.mp4"); log = str(path.parent / "_2pass")
    base = ["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-c:v", "libx264", "-preset", "medium", "-b:v", f"{v_k}k",
            "-maxrate", f"{int(v_k * 1.6)}k", "-bufsize", f"{v_k * 3}k", "-pix_fmt", "yuv420p", "-passlogfile", log]
    sh(*base, "-pass", "1", "-an", "-f", "mp4", "/dev/null")
    sh(*base, "-pass", "2", "-c:a", "aac", "-b:a", f"{a_k}k", "-movflags", "+faststart", tmp)
    tmp.replace(path)
    for f in path.parent.glob("_2pass*"): f.unlink()
    return True


def render(spec, bd, stock_dir, music_dir, out, voice_wavs, used_recent=(), seed=7):
    random.seed(seed); rng = random.Random(seed)
    short = spec.get("format") == "short"
    W, H = (1080, 1920) if short else (1920, 1080)
    meta = json.load(open(music_dir / "tracks.json"))["tracks"]
    segs_dir = bd / "segs"; segs_dir.mkdir(parents=True, exist_ok=True)
    for f in segs_dir.glob("*"): f.unlink()
    timeline, t, seg_files, mood = [], 0.0, [], "mystery"
    k = 0
    for i, sc in enumerate(spec["scenes"]):
        mood = sc.get("mood", mood)
        if "card" in sc:
            f = segs_dir / f"{k:03d}_card.mp4"; chapter_card(sc["card"], W, H, f)
            timeline.append({"kind": "card", "t0": t, "dur": CARD_DUR, "mood": mood}); seg_files.append(f)
            t += CARD_DUR; k += 1; continue
        vd = wav_dur(voice_wavs[i]); dur = vd + (PAD if not short else 0.12)
        shots = [parse_shot(s) for s in sc.get("shots", [])]
        entry = {"kind": "say", "t0": t, "dur": dur, "voice_dur": vd, "say": sc["say"], "wav": voice_wavs[i],
                 "mood": mood, "hook": sc.get("hook")}
        if "stat" in sc:
            src = stock_dir / shots[0][0] if shots else None
            still = still_of(src, W, H, shots[0][1] or 1.0) if src and src.exists() else map_bg(W, H)
            f = segs_dir / f"{k:03d}_stat.mp4"; stat_segment(sc["stat"], still, W, H, f, dur)
            seg_files.append(f); k += 1
            timeline.append(entry); timeline.append({"kind": "stat", "t0": t, "dur": 0, "mood": mood})
            t += dur; continue
        if not shots: raise SystemExit(f"scene {i} has no shots")
        # split the scene into 2-5 s shots, cycling through its files with different moves
        n = max(len(shots), math.ceil(dur / (3.2 if short else 4.6)))
        n = max(1, min(n, int(dur // 1.8) or 1))
        lens = [dur / n] * n
        for j in range(n):
            name, start, pan = shots[j % len(shots)]
            if j >= len(shots) and start is not None: start = start + 3.5 * (j // len(shots))
            f = segs_dir / f"{k:03d}_shot.mp4"
            render_shot(stock_dir / name, W, H, lens[j], f, start, pan, flash=(j == 0 and i > 0 and rng.random() < 0.35), rng=rng)
            seg_files.append(f); k += 1
        timeline.append(entry); t += dur
    total = t
    (bd / "concat.txt").write_text("".join(f"file '{f.resolve()}'\n" for f in seg_files))
    sh("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", bd / "concat.txt", "-c", "copy", bd / "video_raw.mp4")
    make_ass(timeline, W, H, short, bd / "captions.ass")
    chosen = build_audio(timeline, bd, music_dir, meta, set(used_recent), total, short)
    grad = np.zeros((H, W, 4), np.uint8); h0 = int(H * (0.62 if not short else 0.0))
    if not short:
        ramp = np.clip((np.arange(H) - h0) / (H - h0), 0, 1) ** 1.4 * 150
        grad[..., 3] = ramp[:, None].astype(np.uint8)
    Image.fromarray(grad, "RGBA").save(bd / "grad.png")
    sub = f"[0:v][2:v]overlay=0:0[g];[g]subtitles={bd / 'captions.ass'}:fontsdir={FONTS}[v]"
    sh("ffmpeg", "-loglevel", "error", "-y", "-i", bd / "video_raw.mp4", "-i", bd / "mix.wav", "-i", bd / "grad.png",
       "-filter_complex", sub, "-map", "[v]", "-map", "1:a",
       *X264, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out)
    fit_size(out)
    chapters = [{"t": 0.0, "title": spec.get("cold_open_title", "Intro")}]
    cards = [s_ for s_ in timeline if s_["kind"] == "card"]
    titles = [sc["card"]["title"] for sc in spec["scenes"] if "card" in sc]
    for c_, ti in zip(cards, titles):
        chapters.append({"t": round(c_["t0"], 1), "title": ti})
    return {"duration": total, "chapters": chapters, "music": chosen, "timeline": [{k_: v for k_, v in s.items() if k_ != "wav"} for s in timeline]}
