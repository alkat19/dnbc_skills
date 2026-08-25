#!/usr/bin/env python3
"""Hex sticker for lookdnbc.

A field of small marks -- the codebook, thousands of variables deep -- with a glass held
over it. Inside the lens the same lattice is drawn at 2.4x, because that is what the tool
does: it does not summarise the codebook, it enlarges the part you asked about. One mark
under the glass is red. That is the variable you were looking for.

The composition is mirror-symmetric about the vertical axis.
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = ("/Users/jkv465/Library/Application Support/Claude/local-agent-mode-sessions/"
         "skills-plugin/daa3638d-5ae5-4513-8df9-a726bbb712de/"
         "98737ba6-a80d-4334-97d1-73e917b749e2/skills/canvas-design/canvas-fonts")

SS = 4
W, H = 1200, 1386
INK = (18, 26, 34, 255)
RED = (200, 16, 46, 255)
GLASS = (34, 44, 54, 255)         # what the lens resolves

# paper, field marks, lens interior. The lens reads a shade lighter than the
# ground around it, so the glass lifts off the page.
PALETTES = {
    "sand":  ((243, 238, 229), (158, 174, 189), (252, 250, 246)),
    "mist":  ((234, 239, 244), (139, 158, 176), (250, 252, 253)),
    "linen": ((240, 236, 230), (166, 166, 170), (251, 249, 246)),
    "slate": ((228, 233, 237), (128, 147, 165), (248, 251, 252)),
}
NAME = os.environ.get("HEXPAL", "sand")
_pa, _fi, _le = PALETTES[NAME]
PAPER = _pa + (255,)
FIELD = _fi + (255,)
LENSBG = _le + (255,)

MAG = 2.4


def hexpath(cx, cy, r):
    return [(cx + r * math.cos(math.radians(t)), cy - r * math.sin(math.radians(t)))
            for t in (90, 30, -30, -90, -150, 150)]


def half_width(dy, R):
    a = abs(dy)
    if a >= R:
        return 0.0
    return math.sqrt(3) * R / 2.0 if a <= R / 2.0 else math.sqrt(3) * (R - a)


def lattice(cx, cy, R, s):
    """Hex-packed points filling a pointy-top hexagon."""
    pts, row = [], 0
    dy = s * math.sqrt(3) / 2.0
    y = cy - R
    while y <= cy + R:
        hw = half_width(y - cy, R)
        if hw > 0:
            off = (s / 2.0) if (row % 2) else 0.0
            k = int((hw - off) / s)
            for i in range(-k, k + 1):
                x = off + i * s
                if abs(x) <= hw:
                    pts.append((cx + x, y))
        y += dy
        row += 1
    return pts


def dot(d, x, y, r, fill):
    d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def letterspaced(draw, text, font, cx, y, tracking, fill):
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2.0
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking
    return total


def build():
    w, h = W * SS, H * SS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx, cy = w / 2.0, h / 2.0
    R = h / 2.0 - 9 * SS
    BW = 44 * SS                       # perpendicular border thickness
    R_in = R - BW / math.cos(math.radians(30))
    d.polygon(hexpath(cx, cy, R), fill=INK)
    d.polygon(hexpath(cx, cy, R_in), fill=PAPER)

    # --- the codebook: a field of small marks -----------------------------
    R_field = R_in - 26 * SS
    s = 0.0715 * R
    r_small = s * 0.235

    lr = 0.320 * R                       # lens radius
    plate_top = cy + 0.450 * R

    pts = lattice(cx, cy, R_field, s)

    # Seat the lens on a lattice point that already lies on the axis, so the found
    # mark sits exactly at the centre of the glass and the enlarged pattern stays
    # mirror-symmetric. Snapping the lens to the marks, rather than the reverse,
    # keeps the field a single uninterrupted lattice.
    lx = cx
    axis = [q for q in pts if abs(q[0] - cx) < 1e-6]
    best = min(axis, key=lambda q: abs(q[1] - (cy - 0.075 * R)))
    ly = best[1]
    for (x, y) in pts:
        if y > plate_top:
            continue                     # nameplate keeps its own ground
        dot(d, x, y, r_small, FIELD)

    # --- the handle, on the axis ------------------------------------------
    hw_ = 0.050 * R
    d.rounded_rectangle([cx - hw_, ly + lr - 0.02 * R, cx + hw_, ly + lr + 0.240 * R],
                        radius=hw_, fill=INK)

    # --- the glass ---------------------------------------------------------
    lens = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lens)
    ld.ellipse([lx - lr, ly - lr, lx + lr, ly + lr], fill=LENSBG)

    # the same lattice, enlarged about the lens centre
    inner = lr / MAG + s
    for (x, y) in pts:
        if abs(x - lx) > inner or abs(y - ly) > inner:
            continue
        mx = lx + (x - lx) * MAG
        my = ly + (y - ly) * MAG
        if (mx - lx) ** 2 + (my - ly) ** 2 > (lr - r_small * MAG * 0.7) ** 2:
            continue
        dot(ld, mx, my, r_small * MAG, RED if (x, y) == best else GLASS)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([lx - lr, ly - lr, lx + lr, ly + lr], fill=255)
    img.paste(lens, (0, 0), mask)

    rim = int(0.036 * R)
    d.ellipse([lx - lr, ly - lr, lx + lr, ly + lr], outline=INK, width=rim)

    # --- nameplate ---------------------------------------------------------
    y_text = cy + 0.625 * R
    avail = 2 * half_width(y_text - cy, R_in) * 0.78
    size, track = int(100 * SS), 5.0 * SS
    while size > 20:
        f = ImageFont.truetype(os.path.join(FONTS, "GeistMono-Bold.ttf"), size)
        wmark = sum(d.textlength(c, font=f) for c in "lookdnbc") + track * 7
        if wmark <= avail:
            break
        size -= 2 * SS
    asc, _ = f.getmetrics()
    letterspaced(d, "lookdnbc", f, cx, y_text - asc * 0.78, track, INK)

    out = img.resize((W, H), Image.LANCZOS)
    p = os.path.join(HERE, os.environ.get("HEXOUT", "lookdnbc-hex.png"))
    out.save(p)
    print("wrote %s  (%d marks in the field, lens at %.1fx)" % (p, len(pts), MAG))


if __name__ == "__main__":
    build()
