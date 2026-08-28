#!/usr/bin/env python3
"""The Healthcare Paradox — elegant cover. Real coastline in gold on deep ink.

The true Puerto Rico coastline (US Census 5m cartographic boundary) drawn as
one fine gold line, with Vieques and Culebra beside it; engraved serif title;
whispered small-caps kicker and subtitle; hairline rule. Supersampled 2x.
"""
import json
import math
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
ART = str(ROOT / "assets")
FONTS = str(ROOT / "assets" / "fonts")

SS = 2
S = 3000 * SS

INK = (12, 14, 20)
INK_WARM = (18, 20, 27)
GOLD = (198, 160, 82)
GOLD_HI = (232, 203, 132)
CREAM = (240, 233, 218)
GRAY = (150, 148, 140)


def font(name, size):
    return ImageFont.truetype(f"{FONTS}/{name}", size * SS)


# ---------------------------------------------------------------- ground
img = Image.new("RGB", (S, S), INK)
vign = Image.new("L", (S, S), 0)
vd = ImageDraw.Draw(vign)
cx, cy = S * 0.5, S * 0.34
maxr = S * 1.25
for r in range(int(maxr), 0, -24):
    vd.ellipse([cx - r, cy - r * 0.85, cx + r, cy + r * 0.85],
               fill=int(40 * (1 - r / maxr)))
vign = vign.filter(ImageFilter.GaussianBlur(420))
img = Image.composite(Image.new("RGB", (S, S), INK_WARM), img, vign)
d = ImageDraw.Draw(img)

# --------------------------------------------- the real coastline, in gold
rings = json.load(open(f"{ART}/geo/pr_rings.json"))   # [main, v, c, ...] rings

# classify rings by centroid longitude/latitude
def centroid(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)

main = max(rings, key=len)
east = [r for r in rings if r is not main and centroid(r)[0] > -65.7]

keep = [main] + east                              # skip Mona (far west)

# project: equirectangular with latitude correction
all_pts = [p for ring in keep for p in ring]
lon0 = sum(p[0] for p in all_pts) / len(all_pts)
lat0 = sum(p[1] for p in all_pts) / len(all_pts)
k = math.cos(math.radians(lat0))
proj = [[((p[0] - lon0) * k, -(p[1] - lat0)) for p in ring]
        for ring in keep]

minx = min(x for ring in proj for x, y in ring)
maxx = max(x for ring in proj for x, y in ring)
miny = min(y for ring in proj for x, y in ring)
maxy = max(y for ring in proj for x, y in ring)

IW = S * 0.660                                     # target width on canvas
scale = IW / (maxx - minx)
IH = (maxy - miny) * scale
IX = (S - IW) / 2
IY = S * 0.345 - IH / 2

rings_px = [[(IX + (x - minx) * scale, IY + (y - miny) * scale)
             for x, y in ring] for ring in proj]

# soft gold aura beneath the line
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
for ring in rings_px:
    gd.line(ring + [ring[0]], fill=GOLD + (120,), width=14 * SS)
glow = glow.filter(ImageFilter.GaussianBlur(26 * SS))
img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
d = ImageDraw.Draw(img)

for ring in rings_px:
    d.line(ring + [ring[0]], fill=GOLD, width=3 * SS, joint="curve")

# ------------------------------------------------------------ inscription
def letterspace(draw, text, f, y, fill, tracking):
    widths = [draw.textlength(ch, font=f) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (S - total) / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=f, fill=fill)
        x += w + tracking


def rule_with_diamond(draw, y, half=S * 0.115):
    cx0 = S / 2
    draw.line([(cx0 - half, y), (cx0 - 16 * SS, y)], fill=GOLD, width=1 * SS)
    draw.line([(cx0 + 16 * SS, y), (cx0 + half, y)], fill=GOLD, width=1 * SS)
    r = 7 * SS
    draw.polygon([(cx0, y - r), (cx0 + r, y), (cx0, y + r), (cx0 - r, y)],
                 outline=GOLD, width=1 * SS)


kick = font("InstrumentSans-Regular.ttf", 46)
letterspace(d, "FIFTY-NINE CENTS ON EVERY DOLLAR", kick, S * 0.575,
            GOLD_HI, 14 * SS)

rule_with_diamond(d, S * 0.628)

serif1 = font("Gloock-Regular.ttf", 212)
serif2 = font("Gloock-Regular.ttf", 306)
t1 = "The Healthcare"
w1 = d.textlength(t1, font=serif1)
d.text(((S - w1) / 2, S * 0.655), t1, font=serif1, fill=CREAM)
t2 = "Paradox"
w2 = d.textlength(t2, font=serif2)
d.text(((S - w2) / 2, S * 0.738), t2, font=serif2, fill=CREAM)

sub = font("InstrumentSans-Regular.ttf", 40)
letterspace(d, "HOW RESOURCES NAVIGATE THE SYSTEM IN PUERTO RICO",
            sub, S * 0.900, GRAY, 10 * SS)

final = img.resize((3000, 3000), Image.LANCZOS)
final.save(f"{ART}/cover.png", "PNG")
print("assets/cover.png written")
