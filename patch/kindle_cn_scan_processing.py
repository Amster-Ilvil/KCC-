# -*- coding: utf-8 -*-
"""Conservative manga scan preprocessing for KCC Kindle CN.

This module borrows design principles from Novel-formatter's scan preprocessing
and Colortina's paper/ink protection, but is intentionally self-contained and
Pillow-only so the Kindle converter does not gain an OpenCV dependency.

The default compression path never calls this module.  It is only used when the
user explicitly enables scan preprocessing, because crop/deskew/luminance
flattening changes image pixels and is therefore not a lossless operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import statistics
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat


@dataclass(frozen=True)
class ScanProcessOptions:
    enabled: bool = False
    auto_crop: bool = True
    deskew: bool = True
    enhancement: str = "soft"  # none / soft / strong
    preserve_color: bool = True
    crop_margin_percent: float = 0.8
    max_deskew_degrees: float = 3.0

    def normalized(self) -> "ScanProcessOptions":
        enhancement = str(self.enhancement or "soft").strip().lower()
        if enhancement not in {"none", "soft", "strong"}:
            enhancement = "soft"
        return ScanProcessOptions(
            enabled=bool(self.enabled),
            auto_crop=bool(self.auto_crop),
            deskew=bool(self.deskew),
            enhancement=enhancement,
            preserve_color=bool(self.preserve_color),
            crop_margin_percent=max(0.0, min(4.0, float(self.crop_margin_percent))),
            max_deskew_degrees=max(0.0, min(5.0, float(self.max_deskew_degrees))),
        )


@dataclass(frozen=True)
class ScanProcessReport:
    crop_applied: bool = False
    deskew_applied: bool = False
    enhancement_applied: str = "none"
    crop_box: tuple[int, int, int, int] | None = None
    deskew_angle: float = 0.0

    @property
    def changed(self) -> bool:
        return self.crop_applied or self.deskew_applied or self.enhancement_applied != "none"


def _resample(name: str):
    enum = getattr(Image, "Resampling", Image)
    return getattr(enum, name)


def _median(values, default=255.0) -> float:
    values = list(values)
    return float(statistics.median(values)) if values else float(default)


def _downsample_gray(image: Image.Image, max_side: int = 640) -> tuple[Image.Image, float, float]:
    width, height = image.size
    gray = ImageOps.grayscale(image)
    scale = min(1.0, float(max_side) / max(width, height, 1))
    target = (max(24, round(width * scale)), max(24, round(height * scale)))
    if target != image.size:
        resized = gray.resize(target, _resample("LANCZOS"))
        gray.close()
        gray = resized
    return gray, width / gray.width, height / gray.height


def _border_samples(gray: Image.Image) -> list[int]:
    width, height = gray.size
    px = gray.load()
    strip_x = max(1, round(width * 0.035))
    strip_y = max(1, round(height * 0.035))
    step = max(1, min(width, height) // 180)
    values: list[int] = []
    for y in range(0, height, step):
        for x in range(0, strip_x, step):
            values.append(int(px[x, y]))
        for x in range(max(0, width - strip_x), width, step):
            values.append(int(px[x, y]))
    for x in range(0, width, step):
        for y in range(0, strip_y, step):
            values.append(int(px[x, y]))
        for y in range(max(0, height - strip_y), height, step):
            values.append(int(px[x, y]))
    return values


def _center_samples(gray: Image.Image) -> list[int]:
    width, height = gray.size
    px = gray.load()
    left, right = round(width * 0.28), round(width * 0.72)
    top, bottom = round(height * 0.28), round(height * 0.72)
    step = max(1, min(width, height) // 100)
    return [int(px[x, y]) for y in range(top, bottom, step) for x in range(left, right, step)]


def estimate_safe_crop_box(image: Image.Image, margin_percent: float = 0.8) -> tuple[int, int, int, int] | None:
    """Detect only obvious paper/background borders; refuse uncertain pages.

    Full-bleed illustrations and already-cropped pages intentionally return
    ``None``.  This is a rectangular crop, not a perspective guess.
    """
    gray, scale_x, scale_y = _downsample_gray(image, max_side=680)
    try:
        border = _border_samples(gray)
        center = _center_samples(gray)
        border_level = _median(border)
        center_level = _median(center)
        contrast = abs(center_level - border_level)
        # When border and centre look alike the page probably fills the frame.
        if contrast < 11.0:
            return None

        # Build a conservative foreground mask relative to the estimated paper.
        diff = gray.point(lambda value: min(255, int(abs(value - border_level) * 5.0)), mode="L")
        try:
            mask = diff.point(lambda value: 255 if value >= 58 else 0, mode="L")
        finally:
            diff.close()
        try:
            kernel = 5 if min(gray.size) < 360 else 7
            joined = mask.filter(ImageFilter.MaxFilter(kernel))
            mask.close()
            mask = joined.filter(ImageFilter.MinFilter(kernel))
            joined.close()
            bbox = mask.getbbox()
        finally:
            mask.close()
        if not bbox:
            return None

        left, top, right, bottom = bbox
        # Do not accept aggressive crops. Manga panels can intentionally touch
        # the physical edge; large cuts are therefore treated as uncertainty.
        if left > gray.width * 0.13 or gray.width - right > gray.width * 0.13:
            return None
        if top > gray.height * 0.13 or gray.height - bottom > gray.height * 0.13:
            return None
        area = max(1, (right - left) * (bottom - top))
        removed = 1.0 - area / max(1, gray.width * gray.height)
        if removed < 0.008 or removed > 0.28:
            return None

        left = max(0, round(left * scale_x))
        right = min(image.width, round(right * scale_x))
        top = max(0, round(top * scale_y))
        bottom = min(image.height, round(bottom * scale_y))
        margin = round(min(image.size) * max(0.0, margin_percent) / 100.0)
        left = max(0, left - margin)
        top = max(0, top - margin)
        right = min(image.width, right + margin)
        bottom = min(image.height, bottom + margin)
        if right - left < image.width * 0.72 or bottom - top < image.height * 0.72:
            return None
        return int(left), int(top), int(right), int(bottom)
    finally:
        gray.close()


def _projection_score(gray: Image.Image) -> float:
    ink = ImageOps.invert(ImageOps.autocontrast(gray, cutoff=0.3))
    try:
        width, height = ink.size
        row = ink.resize((1, height), _resample("BOX"))
        col = ink.resize((width, 1), _resample("BOX"))
        try:
            rows = list(row.getdata())
            cols = list(col.getdata())
        finally:
            row.close(); col.close()

        def variance(values):
            if not values:
                return 0.0
            mean = sum(values) / len(values)
            return sum((v - mean) ** 2 for v in values) / len(values)

        return max(variance(rows), variance(cols))
    finally:
        ink.close()


def estimate_deskew_angle(image: Image.Image, max_degrees: float = 3.0) -> float:
    limit = max(0.0, min(5.0, float(max_degrees)))
    if limit < 0.5:
        return 0.0
    gray, _, _ = _downsample_gray(image, max_side=520)
    try:
        baseline = _projection_score(gray)
        candidates: list[tuple[float, float]] = [(baseline, 0.0)]
        count = int(round(limit / 0.5))
        for index in range(-count, count + 1):
            angle = index * 0.5
            if abs(angle) < 1e-9:
                continue
            rotated = gray.rotate(angle, resample=_resample("BILINEAR"), expand=False, fillcolor=255)
            try:
                candidates.append((_projection_score(rotated), angle))
            finally:
                rotated.close()
        best_score, best_angle = max(candidates, key=lambda pair: pair[0])
        # Coloured/full-bleed art often creates noisy projection peaks. Require
        # a meaningful improvement before touching geometry.
        if abs(best_angle) < 0.45 or best_score < baseline * 1.04:
            return 0.0
        return float(best_angle)
    finally:
        gray.close()


def _protection_mask(image: Image.Image) -> Image.Image:
    """Protect paper white, solid ink, strong edges and saturated artwork."""
    gray = ImageOps.grayscale(image)
    paper = gray.point(lambda v: 255 if v >= 246 else max(0, min(255, (v - 226) * 12)), mode="L")
    ink = gray.point(lambda v: 255 if v <= 24 else max(0, min(255, (54 - v) * 8)), mode="L")
    edges = gray.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v >= 46 else 0, mode="L")
    edges = edges.filter(ImageFilter.GaussianBlur(radius=0.9))
    base = ImageChops.lighter(paper, ink)
    paper.close(); ink.close(); gray.close()
    combined = ImageChops.lighter(base, edges)
    base.close(); edges.close()

    if image.mode not in {"L", "1"}:
        hsv = image.convert("HSV")
        _, saturation, _ = hsv.split()
        colour = saturation.point(lambda v: 0 if v <= 30 else min(230, round((v - 30) * 1.45)), mode="L")
        saturation.close(); hsv.close()
        colour = colour.filter(ImageFilter.GaussianBlur(radius=1.5))
        final = ImageChops.lighter(combined, colour)
        combined.close(); colour.close()
        combined = final
    return combined.filter(ImageFilter.GaussianBlur(radius=0.6))


def enhance_scan(image: Image.Image, mode: str = "soft", preserve_color: bool = True) -> Image.Image:
    mode = str(mode or "none").lower()
    if mode == "none":
        return image.copy()

    original = image.convert("RGB")
    gray = ImageOps.grayscale(original)
    shortest = max(1, min(original.size))
    radius = max(10, min(70, round(shortest * 0.028)))
    background = gray.filter(ImageFilter.GaussianBlur(radius=radius))
    try:
        normalized = ImageChops.subtract(gray, background, scale=1.0, offset=255)
    finally:
        background.close()
    cutoff = 0.25 if mode == "soft" else 0.45
    auto = ImageOps.autocontrast(normalized, cutoff=cutoff)
    normalized.close()
    strength = 0.56 if mode == "soft" else 0.76
    mixed = Image.blend(gray, auto, strength)
    auto.close()
    contrast = 1.04 if mode == "soft" else 1.10
    toned = ImageEnhance.Contrast(mixed).enhance(contrast)
    mixed.close()
    sharpened = toned.filter(ImageFilter.UnsharpMask(
        radius=0.60 if mode == "soft" else 0.78,
        percent=38 if mode == "soft" else 58,
        threshold=5,
    ))
    toned.close(); gray.close()

    if preserve_color:
        ycbcr = original.convert("YCbCr")
        old_y, cb, cr = ycbcr.split()
        old_y.close()
        enhanced = Image.merge("YCbCr", (sharpened, cb, cr)).convert("RGB")
        cb.close(); cr.close(); ycbcr.close(); sharpened.close()
    else:
        enhanced = sharpened.convert("RGB")
        sharpened.close()

    protect = _protection_mask(original)
    # Image.composite(a, b, mask): 255 selects a. Protected regions therefore
    # come from the untouched source while midtones use the cleaned candidate.
    result = Image.composite(original, enhanced, protect)
    protect.close(); enhanced.close(); original.close()
    return result


def process_scan_image(image: Image.Image, options: ScanProcessOptions) -> tuple[Image.Image, ScanProcessReport]:
    options = options.normalized()
    oriented = ImageOps.exif_transpose(image)
    try:
        current = oriented.convert("RGB")
    finally:
        if oriented is not image:
            oriented.close()

    crop_box = None
    crop_applied = False
    deskew_applied = False
    angle = 0.0
    try:
        if options.auto_crop:
            crop_box = estimate_safe_crop_box(current, options.crop_margin_percent)
            if crop_box is not None and crop_box != (0, 0, current.width, current.height):
                cropped = current.crop(crop_box)
                current.close()
                current = cropped
                crop_applied = True

        if options.deskew:
            angle = estimate_deskew_angle(current, options.max_deskew_degrees)
            if abs(angle) >= 0.01:
                rotated = current.rotate(
                    angle,
                    resample=_resample("BICUBIC"),
                    expand=True,
                    fillcolor=(255, 255, 255),
                )
                current.close()
                current = rotated
                deskew_applied = True

        if options.enhancement != "none":
            enhanced = enhance_scan(current, options.enhancement, options.preserve_color)
            current.close()
            current = enhanced

        report = ScanProcessReport(
            crop_applied=crop_applied,
            deskew_applied=deskew_applied,
            enhancement_applied=options.enhancement,
            crop_box=crop_box,
            deskew_angle=angle,
        )
        return current, report
    except Exception:
        current.close()
        raise
