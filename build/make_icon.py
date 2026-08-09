#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the macOS iconset from the unified project avatar source."""
from __future__ import annotations

import base64
import hashlib
import io
import sys
from pathlib import Path

from PIL import Image, ImageOps

SIZE = 1024
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "assets" / "project_avatar.webp.b64"
EXPECTED_AVATAR_SHA256 = "15ba2af56e36073feed28811bf89ef65707cb129659871f78041db7d330ad5f8"


def _read_b64(path: Path) -> bytes:
    if path.is_file():
        parts = [path]
    else:
        parts = sorted(path.parent.glob(path.name + ".*"))
    if not parts:
        raise FileNotFoundError(f"project avatar source not found: {path} or {path.name}.*")

    encoded = "".join(
        "".join(part.read_text(encoding="utf-8").split())
        for part in parts
    )
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) < 12 or not raw.startswith(b"RIFF") or raw[8:12] != b"WEBP":
        raise ValueError("project avatar payload is not a valid WebP container")

    if path == DEFAULT_SOURCE:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != EXPECTED_AVATAR_SHA256:
            raise ValueError(
                f"project avatar SHA-256 mismatch: expected {EXPECTED_AVATAR_SHA256}, got {digest}"
            )
    return raw


def _load_source(path: Path) -> Image.Image:
    if ".b64" in path.name:
        image = Image.open(io.BytesIO(_read_b64(path)))
    else:
        image = Image.open(path)
    image.load()
    return image.convert("RGBA")


def _build_master(source: Path) -> Image.Image:
    image = _load_source(source)
    # Preserve the supplied artwork. Only fit to a square transparent canvas and
    # resize. Do not add generated decoration, text, watermark or colour changes.
    image = ImageOps.contain(image, (SIZE, SIZE), method=Image.Resampling.LANCZOS)
    master = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    master.alpha_composite(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2))
    return master


def save_iconset(out_dir: Path, source: Path = DEFAULT_SOURCE) -> None:
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
