#!/usr/bin/env python3
"""Generate podcast cover art (assets/cover.png, 3000x3000) from the config title.

A placeholder until real artwork is supplied — drop any square 3000x3000 PNG/JPG
at assets/cover.png to replace it.

Usage: python3 scripts/make_cover.py [--size 3000]
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

TOP = (26, 22, 38)      # deep indigo
BOTTOM = (150, 61, 28)  # burnt orange
ACCENT = (242, 146, 92)


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_DIRS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_title(draw, title: str, font, max_width: int) -> list[str]:
    words, lines, cur = title.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--size", type=int, default=3000)
    args = p.parse_args()
    size = args.size

    config = json.loads((ROOT / "podcast.config.json").read_text())
    title = config["title"]
    author = config.get("author", "")

    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)

    for y in range(size):  # vertical gradient
        t = y / size
        color = tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
        draw.line([(0, y), (size, y)], fill=color)

    # concentric sound-wave arcs behind the text
    cx, cy = size // 2, int(size * 0.62)
    for i, r in enumerate(range(size // 6, size, size // 6)):
        width = max(6, size // 250)
        alpha_color = tuple(min(255, c + 25 + i * 4) for c in BOTTOM)
        draw.arc([cx - r, cy - r, cx + r, cy + r], start=200, end=340,
                 fill=alpha_color, width=width)

    title_font = find_font(size // 10)
    max_w = int(size * 0.84)
    lines = wrap_title(draw, title, title_font, max_w)
    while len(lines) > 3 and title_font.size > size // 20:
        title_font = find_font(int(title_font.size * 0.85))
        lines = wrap_title(draw, title, title_font, max_w)

    line_h = int(title_font.size * 1.18)
    block_h = line_h * len(lines)
    y0 = int(size * 0.40) - block_h // 2
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=title_font)
        draw.text(((size - w) / 2 + size // 300, y0 + i * line_h + size // 300),
                  line, font=title_font, fill=(0, 0, 0))  # soft shadow
        draw.text(((size - w) / 2, y0 + i * line_h), line,
                  font=title_font, fill=(255, 250, 244))

    if author:
        small = find_font(size // 28)
        text = author.upper()
        w = draw.textlength(text, font=small)
        draw.text(((size - w) / 2, int(size * 0.82)), text,
                  font=small, fill=ACCENT)

    out = ROOT / "assets" / "cover.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out.relative_to(ROOT)} ({size}x{size})")


if __name__ == "__main__":
    main()
