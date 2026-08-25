#!/usr/bin/env python3
"""Hex sticker for lookdnbc, drawn under the Sediment Logic philosophy.

The composition is derived, not styled. One hairline ring is drawn for every 50 DNBC
variables, laid down from the centre outward in questionnaire order, so a band's width is
the wave's actual share of the codebooks: Interview 2 is broad because it holds 2,365
variables, the 7-year follow-up is a seam because it holds 285. Growth rings, because that
is what a birth cohort deposits.

The single red ring falls between the two prenatal interviews and the six postnatal ones
-- birth, the one event in the record that changes what a question can be about.
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = ("/Users/jkv465/Library/Application Support/Claude/local-agent-mode-sessions/"
         "skills-plugin/daa3638d-5ae5-4513-8df9-a726bbb712de/"
         "98737ba6-a80d-4334-97d1-73e917b749e2/skills/canvas-design/canvas-fonts")

SS = 4                       # supersample factor
W, H = 1200, 1386            # 2:sqrt(3), the hexb.in sticker proportion
PAPER = (252, 252, 250, 255)
INK = (16, 24, 32, 255)
RED = (200, 16, 46, 255)     # Dansk flag red

# wave, variables -- innermost (earliest) to outermost (latest)
WAVES = [
    ("i1",   980),
    ("i2",   2365),
    ("i3",   2162),
    ("i4",   801),
    ("y7",   285),
    ("y11c", 342),
    ("y11a", 745),
    ("y18",  309),
]
TOTAL = sum(n for _, n in WAVES)
BIRTH_AFTER = 2              # red ring closes the prenatal record

# tone lightens outward: the deep record is dense, the recent record thin
# The prenatal record is chromatic; everything after birth is ink. The boundary
# between the two zones IS birth -- the one event that changes what may be asked.
RAMP = [
    (139, 11, 35), (200, 16, 46),                       # i1, i2  -- in utero
    (16, 24, 32), (56, 67, 78), (94, 105, 115),         # i3, i4, y7
    (124, 134, 143), (152, 160, 168), (176, 184, 191),  # y11c, y11a, y18
]


def hexpath(cx, cy, r):
    return [(cx + r * math.cos(math.radians(t)), cy - r * math.sin(math.radians(t)))
            for t in (90, 30, -30, -90, -150, 150)]


def ring(d, cx, cy, r, colour, width):
    p = hexpath(cx, cy, r)
    d.line(p + [p[0]], fill=colour, width=width, joint="curve")


def letterspaced(draw, text, font, cx, y, tracking, fill):
    """Draw text centred on cx with explicit tracking, PIL having no such notion."""
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
    R = h / 2.0 - 9 * SS                       # outer hexagon circumradius

    d.polygon(hexpath(cx, cy, R), fill=PAPER)

    # --- growth rings ------------------------------------------------------
    # One band per wave. Radial thickness is the wave's share of the codebooks,
    # the way a tree ring's width records a year. Rings sit above centre so the
    # nameplate has clean ground beneath them.
    yc = cy - 0.150 * R
    r_out = 0.700 * R
    r_core = 0.0

    edges, acc = [r_core], 0.0
    for _, n in WAVES:
        acc += n / float(TOTAL)
        edges.append(r_core + (r_out - r_core) * acc)

    # painter's order: outermost first, each inner band laid over the last
    for wi in range(len(WAVES) - 1, -1, -1):
        d.polygon(hexpath(cx, yc, edges[wi + 1]), fill=RAMP[wi] + (255,))

    # hairline seams so each deposit reads as its own layer
    for r in edges[1:-1]:
        ring(d, cx, yc, r, PAPER, max(2, int(1.5 * SS)))
    ring(d, cx, yc, edges[-1], (138, 147, 155, 255), max(2, int(1.8 * SS)))

    # --- birth: the edge of the chromatic zone -----------------------------
    ring(d, cx, yc, edges[BIRTH_AFTER], PAPER, int(5 * SS))

    # --- nameplate ---------------------------------------------------------
    f = ImageFont.truetype(os.path.join(FONTS, "GeistMono-Bold.ttf"), int(93 * SS))
    asc, _ = f.getmetrics()
    letterspaced(d, "lookdnbc", f, cx, cy + 0.738 * R - asc * 0.78, 6.0 * SS, INK)

    # --- border ------------------------------------------------------------
    ring(d, cx, cy, R, INK, int(9 * SS))

    out = img.resize((W, H), Image.LANCZOS)
    path = os.path.join(HERE, "lookdnbc-hex.png")
    out.save(path)
    print("wrote %s" % path)
    for wi, (name, cnt) in enumerate(WAVES):
        t = (edges[wi + 1] - edges[wi]) / (r_out - r_core)
        print("   %-5s %5d vars (%4.1f%%) -> band %4.1f%% of radius"
              % (name, cnt, 100.0 * cnt / TOTAL, 100.0 * t))


if __name__ == "__main__":
    build()
