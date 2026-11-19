import math
NAVY = "#0E1B2C"

def defs(uid):
    return f'''<defs>
<radialGradient id="bg{uid}" cx="50%" cy="45%" r="65%"><stop offset="0" stop-color="#1A2F4D"/><stop offset="1" stop-color="#070F1B"/></radialGradient>
<linearGradient id="rim{uid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF1BF"/><stop offset="0.35" stop-color="#E7BE55"/><stop offset="0.7" stop-color="#B9862A"/><stop offset="1" stop-color="#7C5612"/></linearGradient>
<linearGradient id="face{uid}" x1="1" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#F3D27A"/><stop offset="0.55" stop-color="#D3A43E"/><stop offset="1" stop-color="#A97A22"/></linearGradient>
<linearGradient id="gold{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FBE6A6"/><stop offset="0.5" stop-color="#E0B24A"/><stop offset="1" stop-color="#A9781E"/></linearGradient>
</defs>'''

def laurel(cx, cy, r, a0, a1, n, leaf_rx, leaf_ry, fill, mirror=False):
    out = []
    for i in range(n):
        t = a0 + (a1 - a0) * i / (n - 1)
        a = math.radians(t)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        tang = t + 90
        for side in (-1, 1):
            off = math.radians(t)
            lx = x + side * 16 * math.cos(off)
            ly = y + side * 16 * math.sin(off)
            rot = t + (28 if side > 0 else -28)
            out.append(f'<ellipse cx="{lx:.1f}" cy="{ly:.1f}" rx="{leaf_rx}" ry="{leaf_ry}" transform="rotate({rot:.1f} {lx:.1f} {ly:.1f})" fill="{fill}"/>')
    # stem
    p0 = (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)))
    large = 1 if abs(a1 - a0) > 180 else 0
    sweep = 1 if a1 > a0 else 0
    out.insert(0, f'<path d="M {p0[0]:.1f} {p0[1]:.1f} A {r} {r} 0 {large} {sweep} {p1[0]:.1f} {p1[1]:.1f}" fill="none" stroke="{fill}" stroke-width="6" stroke-linecap="round"/>')
    return "".join(out)

def coin(size="100%", uid="a"):
    beads = "".join(f'<circle cx="{400+298*math.cos(math.radians(k*6)):.1f}" cy="{400+298*math.sin(math.radians(k*6)):.1f}" r="5.5" fill="#FFF1BF" opacity="0.9"/>' for k in range(60))
    lau = laurel(400, 400, 228, 110, 225, 9, 11, 26, "#7A5512") + laurel(400, 400, 228, 70, -45, 9, 11, 26, "#7A5512", True)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 800 800" role="img" aria-label="Ledger of Empires logo: gold coin stamped with an L and laurel" style="display:block">{defs(uid)}'
            f'<rect width="800" height="800" fill="url(#bg{uid})"/>'
            f'<circle cx="408" cy="414" r="336" fill="#000" opacity="0.35"/>'
            f'<circle cx="400" cy="400" r="336" fill="url(#rim{uid})"/>'
            f'<circle cx="400" cy="400" r="312" fill="#8A6116"/>'
            f'<circle cx="400" cy="400" r="306" fill="url(#face{uid})"/>' + beads +
            f'<circle cx="400" cy="400" r="282" fill="none" stroke="#8A6116" stroke-width="4"/>' + lau +
            f'<text x="404" y="512" text-anchor="middle" font-family="Cinzel, serif" font-weight="700" font-size="330" fill="#FFF1BF" opacity="0.85">L</text>'
            f'<text x="398" y="506" text-anchor="middle" font-family="Cinzel, serif" font-weight="700" font-size="330" fill="#6E4A0E">L</text>'
            '</svg>')

def hourglass(size="100%", uid="b"):
    g = f"url(#gold{uid})"
    def stack(cx, y, w, n, step=16):
        s = ""
        for i in range(n):
            yy = y - i * step
            s += f'<ellipse cx="{cx}" cy="{yy+6}" rx="{w}" ry="{w*0.28:.1f}" fill="#7C5612"/><ellipse cx="{cx}" cy="{yy}" rx="{w}" ry="{w*0.28:.1f}" fill="{g}" stroke="#7C5612" stroke-width="3"/>'
        return s
    glass = ('M 262 196 C 262 330, 386 360, 386 400 C 386 440, 262 470, 262 604 L 538 604 '
             'C 538 470, 414 440, 414 400 C 414 360, 538 330, 538 196 Z')
    bottom = stack(330, 586, 46, 3) + stack(470, 586, 46, 3) + stack(400, 586, 52, 5)
    top = stack(400, 300, 44, 3, 14) + stack(352, 262, 30, 2, 14) + stack(448, 262, 30, 2, 14)
    falling = "".join(f'<ellipse cx="400" cy="{y}" rx="16" ry="6" fill="{g}" stroke="#7C5612" stroke-width="2"/>' for y in (430, 466, 504))
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 800 800" role="img" aria-label="Ledger of Empires logo: hourglass filled with gold coins" style="display:block">{defs(uid)}'
            f'<rect width="800" height="800" fill="url(#bg{uid})"/>'
            f'<path d="{glass}" fill="#FFFFFF" fill-opacity="0.06"/>' + top + falling + bottom +
            f'<path d="{glass}" fill="none" stroke="#F3D27A" stroke-width="12" stroke-linejoin="round"/>'
            f'<rect x="214" y="160" width="372" height="44" rx="10" fill="{g}"/>'
            f'<rect x="214" y="596" width="372" height="44" rx="10" fill="{g}"/>'
            f'<rect x="230" y="200" width="16" height="400" rx="6" fill="{g}"/>'
            f'<rect x="554" y="200" width="16" height="400" rx="6" fill="{g}"/>'
            '</svg>')

def crest(size="100%", uid="c"):
    g = f"url(#gold{uid})"
    lau = laurel(400, 400, 250, 100, 240, 11, 13, 30, g) + laurel(400, 400, 250, 80, -60, 11, 13, 30, g, True)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 800 800" role="img" aria-label="Ledger of Empires logo: LE monogram in a laurel wreath" style="display:block">{defs(uid)}'
            f'<rect width="800" height="800" fill="url(#bg{uid})"/>' + lau +
            f'<path d="M 344 196 L 372 168 L 400 192 L 428 168 L 456 196 L 448 222 L 352 222 Z" fill="{g}"/>'
            f'<text x="400" y="478" text-anchor="middle" font-family="Cinzel, serif" font-weight="700" font-size="220" fill="{g}" letter-spacing="-8">LE</text>'
            f'<rect x="300" y="512" width="200" height="8" rx="4" fill="{g}"/>'
            '</svg>')

LOGOS = [("Coin", coin), ("Hourglass", hourglass), ("Crest", crest)]

if __name__ == "__main__":
    import cairosvg
    from PIL import Image, ImageDraw
    for n, f in LOGOS:
        cairosvg.svg2png(bytestring=f("800").encode(), write_to=f"/tmp/L_{n}.png")
    W = Image.new("RGB", (3 * 820, 820 + 260), "#0F0F0F")
    for i, (n, _) in enumerate(LOGOS):
        L = Image.open(f"/tmp/L_{n}.png").convert("RGB")
        m = Image.new("L", (800, 800), 0); ImageDraw.Draw(m).ellipse((0, 0, 799, 799), fill=255)
        W.paste(L, (i * 820 + 10, 10), m)
        for j, s in enumerate((98, 48, 32)):
            t = L.resize((s, s), Image.LANCZOS); mm = Image.new("L", (s, s), 0); ImageDraw.Draw(mm).ellipse((0, 0, s - 1, s - 1), fill=255)
            W.paste(t, (i * 820 + 60 + j * 200, 860), mm)
    W.save("/tmp/logos2.png")
