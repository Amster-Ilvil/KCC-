#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a clean Kindle-focused macOS iconset using Pillow."""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageDraw

SIZE = 1024
BG = (17, 24, 39, 255)
SCREEN = (248, 250, 252, 255)
INK = (31, 41, 55, 255)
ACCENT = (47, 111, 235, 255)
MUTED = (148, 163, 184, 255)
WHITE = (255, 255, 255, 255)


def rr(draw, xy, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def build_master():
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # App tile
    rr(d, (80, 80, 944, 944), 190, BG)

    # Kindle/e-reader body
    rr(d, (250, 145, 774, 875), 70, (9, 14, 24, 255))
    rr(d, (286, 190, 738, 810), 28, SCREEN)

    # Manga page/panel motif
    rr(d, (326, 235, 698, 765), 18, WHITE, outline=(221, 226, 232, 255), width=6)
    d.line((512, 250, 512, 745), fill=(226, 232, 240, 255), width=5)
    rr(d, (352, 280, 486, 438), 14, (235, 239, 244, 255))
    rr(d, (540, 280, 672, 520), 14, (235, 239, 244, 255))
    rr(d, (352, 470, 486, 690), 14, (235, 239, 244, 255))
    rr(d, (540, 552, 672, 690), 14, (235, 239, 244, 255))

    # Right-to-left reading arrow, understated but recognizable.
    d.line((650, 730, 565, 730), fill=ACCENT, width=22)
    d.polygon([(565, 730), (604, 698), (604, 762)], fill=ACCENT)

    # Home indicator / Kindle detail
    rr(d, (456, 832, 568, 850), 9, MUTED)

    # Small blue corner mark for identity.
    d.pieslice((706, 94, 936, 324), 270, 360, fill=ACCENT)
    return im


def save_iconset(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    master = build_master()
    specs = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for px, name in specs:
        master.resize((px, px), Image.Resampling.LANCZOS).save(out_dir / name, "PNG", optimize=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_icon.py OUTPUT.iconset")
    save_iconset(Path(sys.argv[1]))
