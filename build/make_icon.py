#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the macOS iconset from the project avatar supplied by the project owner.

The source image is stored as base64 text in assets/project_avatar.webp.b64 so it
can be kept losslessly/portably through the GitHub connector.  CI decodes the
same source for the visible repository asset and DMG volume icon.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageOps

SIZE = 1024
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "assets" / "project_avatar.webp.b64"


def _load_source(path: Path) -> Image.Image:
    if path.suffix.lower() == ".b64":
        raw = base64.b64decode("".join(path.read_text(encoding="utf-8").split()))
        image = Image.open(io.BytesIO(raw))
    else:
        image = Image.open(path)
    return image.convert("RGBA")


def _build_master(source: Path) -> Image.Image:
    image = _load_source(source)
    # Preserve the supplied artwork.  Only fit it to a square canvas and resize;
    # no generated decorations, text, watermark, sharpening or colour changes.
    image = ImageOps.contain(image, (SIZE, SIZE), method=Image.Resampling.LANCZOS)
    master = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    master.alpha_composite(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2))
    return master


def save_iconset(out_dir: Path, source: Path = DEFAULT_SOURCE) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"project avatar source not found: {source}")

    out_dir.mkdir(parents=True, exist_ok=True)
    master = _build_master(source)
    specs = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for px, name in specs:
        master.resize((px, px), Image.Resampling.LANCZOS).save(
            out_dir / name, "PNG", optimize=True
        )


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: make_icon.py OUTPUT.iconset [SOURCE_IMAGE_OR_B64]")
    output = Path(sys.argv[1])
    source = Path(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_SOURCE
    save_iconset(output, source)
