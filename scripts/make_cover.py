#!/usr/bin/env python3
"""The Healthcare Paradox — podcast cover, 3000x3000.

Actuarial Cartography: a dark chart of hidden fiscal currents. A faint
orthogonal lattice of conduits; one luminous amber route rising from a small
ringed island (0.3500) to a great calibrated dial (1.0000); nautical-chart
furniture; engraved title block. No author name anywhere.
"""
import math
import random
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 3000
FONTS = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "assets" / "fonts")

INK = (13, 19, 34)          # deep ink-navy ground
INK_EDGE = (9, 13, 24)      # vignette edge
PIPE_DIM = (36, 48, 72)     # quiet lattice
PIPE_MID = (52, 68, 99)     # nearer lattice
CREAM = (238, 228, 205)     # chart furniture / title
CREAM_DIM = (238, 228, 205, 110)
AMBER = (232, 166, 66)      # the sounding current
AMBER_HI = (255, 205, 120)
TEAL = (77, 141, 137)       # secondary accent

random.seed(41)


def font(name, size):
    return ImageFont.truetype(f"{FONTS}/{name}", size)


# ---------------------------------------------------------------- ground
img = Image.new("RGB", (S, S), INK)
d = ImageDraw.Draw(img)

# radial vignette, hand-graded
vign = Image.new("L", (S, S), 0)
vd = ImageDraw.Draw(vign)
cx, cy = S * 0.46, S * 0.40
maxr = S * 0.95
for r in range(int(maxr), 0, -12):
    a = int(70 * (r / maxr) ** 2.2)
    vd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=70 - a)
vign = vign.filter(ImageFilter.GaussianBlur(160))
img = Image.composite(Image.new("RGB", (S, S), (20, 28, 47)), img, vign)
d = ImageDraw.Draw(img)

# ------------------------------------------------------------- the lattice
# Orthogonal conduits wandering the field; kept out of the title reserve
# (bottom band) and the dial's inner sanctum.
TITLE_TOP = int(S * 0.760)          # nothing below this but the title block
DIAL = (int(S * 0.700), int(S * 0.300))
DIAL_R = 430
ISLAND = (int(S * 0.240), int(S * 0.640))

GRID = 100  # lattice pitch


def in_reserve(x, y, pad=0):
    if y > TITLE_TOP - pad:
        return True
    if math.hypot(x - DIAL[0], y - DIAL[1]) < DIAL_R + 60 + pad:
        return True
    if math.hypot(x - ISLAND[0], y - ISLAND[1]) < 300 + pad:
        return True
    return False


def snap(v):
    return round(v / GRID) * GRID


lattice = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ld = ImageDraw.Draw(lattice)

for i in range(58):
    x = snap(random.uniform(S * 0.05, S * 0.95))
    y = snap(random.uniform(S * 0.05, TITLE_TOP - 120))
    if in_reserve(x, y, 40):
        continue
    depth = random.random()
    col = PIPE_MID if depth > 0.62 else PIPE_DIM
    w = 7 if depth > 0.62 else 5
    pts = [(x, y)]
    horiz = random.random() < 0.5
    for _ in range(random.randint(2, 4)):
        step = random.choice([2, 3, 4, 5]) * GRID * random.choice([-1, 1])
        nx, ny = (x + step, y) if horiz else (x, y + step)
        nx = min(max(nx, S * 0.05), S * 0.95)
        ny = min(max(ny, S * 0.05), TITLE_TOP - 120)
        nx, ny = snap(nx), snap(ny)
        if in_reserve(nx, ny, 40):
            break
        pts.append((nx, ny))
        x, y, horiz = nx, ny, not horiz
    if len(pts) < 2:
        continue
    ld.line(pts, fill=col + (255,), width=w, joint="curve")
    for px, py in pts[1:-1]:                       # junction rivets
        ld.ellipse([px - 11, py - 11, px + 11, py + 11], fill=col + (255,))
    ex, ey = pts[-1]                               # terminal fitting
    if random.random() < 0.5:
        ld.ellipse([ex - 16, ey - 16, ex + 16, ey + 16],
                   outline=col + (255,), width=5)
    else:
        ld.rectangle([ex - 13, ey - 13, ex + 13, ey + 13],
                     outline=col + (255,), width=5)

img.paste(Image.new("RGB", (S, S), (0, 0, 0)), (0, 0),
          Image.new("L", (S, S), 0))  # no-op keep type
img = Image.alpha_composite(img.convert("RGBA"), lattice).convert("RGB")
d = ImageDraw.Draw(img)

# ------------------------------------------------------- chart furniture
mono_s = font("IBMPlexMono-Regular.ttf", 34)
frame = 108
d.rectangle([frame, frame, S - frame, S - frame],
            outline=(96, 110, 140), width=3)
# graticule ticks + tiny coordinates (top and left edges only, quiet)
for i in range(1, 20):
    t = frame + (S - 2 * frame) * i / 20
    d.line([(t, frame), (t, frame + (34 if i % 5 == 0 else 18))],
           fill=(96, 110, 140), width=3)
    d.line([(frame, t), (frame + (34 if i % 5 == 0 else 18), t)],
           fill=(96, 110, 140), width=3)
for i in (5, 10):
    t = frame + (S - 2 * frame) * i / 20
    d.text((t + 12, frame + 40), f"{i*4:02d}°", font=mono_s,
           fill=(120, 133, 160))
    d.text((frame + 46, t - 40), f"{66 - i}°", font=mono_s,
           fill=(120, 133, 160))

# ------------------------------------------------------------ archipelago
# a scatter of small landmasses; the smallest is ringed — the anchor island
arch = [(-150, 60, 46), (-46, -18, 34), (66, 26, 40), (10, 116, 26),
        (158, 96, 22), (206, 10, 16)]
for ox, oy, r in arch:
    x, y = ISLAND[0] + ox, ISLAND[1] + oy
    d.ellipse([x - r, y - r, x + r, y + r], fill=(58, 74, 104))
    d.ellipse([x - r, y - r, x + r, y + r], outline=(90, 108, 142), width=4)
ax, ay = ISLAND[0] + 206, ISLAND[1] + 10          # the small ringed island
d.ellipse([ax - 16, ay - 16, ax + 16, ay + 16], fill=AMBER)
for rr, wd, al in ((66, 4, 220), (108, 3, 130)):
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    steps = 48
    for k in range(0, steps, 2):                   # dashed survey rings
        a0 = k * 360 / steps
        rd.arc([ax - rr, ay - rr, ax + rr, ay + rr], a0, a0 + 360 / steps,
               fill=AMBER + (al,), width=wd)
    img = Image.alpha_composite(img.convert("RGBA"), ring).convert("RGB")
    d = ImageDraw.Draw(img)
d.text((ax - 52, ay + 128), "$0.59", font=font("IBMPlexMono-Regular.ttf", 44),
       fill=AMBER)

# ---------------------------------------------------------------- the dial
dx, dy = DIAL
d.ellipse([dx - DIAL_R, dy - DIAL_R, dx + DIAL_R, dy + DIAL_R],
          fill=(16, 23, 40), outline=CREAM, width=6)
d.ellipse([dx - DIAL_R + 40, dy - DIAL_R + 40, dx + DIAL_R - 40,
           dy + DIAL_R - 40], outline=(120, 133, 160), width=3)
# calibration ticks
for k in range(72):
    a = math.radians(k * 5)
    r0 = DIAL_R - 62 if k % 6 == 0 else DIAL_R - 48
    x0, y0 = dx + r0 * math.cos(a), dy + r0 * math.sin(a)
    x1 = dx + (DIAL_R - 40) * math.cos(a)
    y1 = dy + (DIAL_R - 40) * math.sin(a)
    d.line([(x0, y0), (x1, y1)], fill=(150, 162, 186),
           width=5 if k % 6 == 0 else 3)
# inner concentric survey rings
for rr in range(90, DIAL_R - 90, 56):
    d.ellipse([dx - rr, dy - rr, dx + rr, dy + rr],
              outline=(60, 76, 108), width=3)
# crosshair
d.line([(dx - DIAL_R + 70, dy), (dx + DIAL_R - 70, dy)],
       fill=(60, 76, 108), width=3)
d.line([(dx, dy - DIAL_R + 70), (dx, dy + DIAL_R - 70)],
       fill=(60, 76, 108), width=3)
# needle set to the route's bearing, and the unity figure
na = math.radians(208)
d.line([(dx, dy), (dx + (DIAL_R - 120) * math.cos(na),
                   dy + (DIAL_R - 120) * math.sin(na))], fill=AMBER, width=9)
d.ellipse([dx - 20, dy - 20, dx + 20, dy + 20], fill=AMBER)
uni = font("IBMPlexMono-Regular.ttf", 52)
d.text((dx - d.textlength("$1.00", font=uni) / 2, dy + DIAL_R - 190),
       "$1.00", font=uni, fill=CREAM)

# ---------------------------------------------------------------- the route
# one luminous orthogonal current: ringed island -> dial rim
route = [(ax, ay), (ax, ay - 340), (int(S * 0.435), ay - 340),
         (int(S * 0.435), int(dy + DIAL_R * 0.62)),
         (int(dx - DIAL_R * 0.985), int(dy + DIAL_R * 0.62))]
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.line(route, fill=AMBER + (170,), width=44, joint="curve")
glow = glow.filter(ImageFilter.GaussianBlur(38))
img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
d = ImageDraw.Draw(img)
d.line(route, fill=AMBER, width=13, joint="curve")
d.line(route, fill=AMBER_HI, width=5, joint="curve")
for px, py in route[1:-1]:
    d.ellipse([px - 17, py - 17, px + 17, py + 17], fill=AMBER)
    d.ellipse([px - 8, py - 8, px + 8, py + 8], fill=AMBER_HI)
# flow chevrons on the vertical run, pointing toward the dial
vx = int(S * 0.435)
for yy in (1290, 1440):
    d.polygon([(vx - 16, yy + 20), (vx + 16, yy + 20), (vx, yy - 12)],
              fill=(255, 205, 120))

# a teal witness: tiny survey cross where route meets the dial
jx, jy = route[-1]
d.line([(jx - 26, jy), (jx + 26, jy)], fill=TEAL, width=5)
d.line([(jx, jy - 26), (jx, jy + 26)], fill=TEAL, width=5)

# ------------------------------------------------------------- title block
big = font("BigShoulders-Bold.ttf", 308)
line1, line2 = "THE HEALTHCARE", "PARADOX"
tx = frame + 92
ty = TITLE_TOP - 24
d.line([(tx, ty - 34), (tx + d.textlength(line1, font=big), ty - 34)],
       fill=(96, 110, 140), width=3)
d.text((tx + 5, ty + 7), line1, font=big, fill=(0, 0, 0))
d.text((tx, ty), line1, font=big, fill=CREAM)
y2 = ty + 262
d.text((tx + 5, y2 + 7), line2, font=big, fill=(0, 0, 0))
d.text((tx, y2), line2, font=big, fill=CREAM)
w2 = d.textlength(line2, font=big)
# amber full stop after the wordmark
d.ellipse([tx + w2 + 42, y2 + 200, tx + w2 + 88, y2 + 246], fill=AMBER)
# whispered subtitle, inside the frame with clear margin
sub = font("IBMPlexMono-Regular.ttf", 44)
d.text((tx + 8, y2 + 300), "HOW RESOURCES NAVIGATE THE SYSTEM IN PUERTO RICO",
       font=sub, fill=(150, 162, 186))

# chart signature, tiny, upper-right inside frame
sig = font("IBMPlexMono-Regular.ttf", 34)
label = "CHART NO. 001 — FISCAL CURRENTS OF PUERTO RICO"
d.text((S - frame - d.textlength(label, font=sig) - 46, frame + 40),
       label, font=sig, fill=(120, 133, 160))

img.save(str(__import__("pathlib").Path(__file__).resolve().parent.parent / "assets" / "cover.png"), "PNG")
print("assets/cover.png written")
