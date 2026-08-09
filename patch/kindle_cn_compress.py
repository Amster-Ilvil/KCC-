# -*- coding: utf-8 -*-
"""Adaptive comic image/container optimizer for the Kindle-only KCC edition.

The default path is pixel-lossless:
- detect JPEG/PNG by magic bytes instead of trusting filename extensions;
- run multiple lossless candidates when useful and keep only the smallest;
- verify decoded pixels before replacing an image;
- preserve rendering-relevant JPEG metadata (ICC/orientation/non-RGB markers);
- preserve EPUB mimetype rules and original ZIP entry metadata where practical;
- never overwrite or delete source files.

Optional scan preprocessing is deliberately separate because crop/deskew/paper
cleanup changes pixels. It must be explicitly enabled by the user.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from typing import Callable, Iterable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
import io
import os
import shutil
import subprocess
import sys

import mozjpeg_lossless_optimization
from PIL import Image, JpegImagePlugin, PngImagePlugin

from .kindle_cn_scan_processing import ScanProcessOptions, process_scan_image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ARCHIVE_EXTENSIONS = {".cbz", ".zip", ".epub"}
COMPRESSED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".jxl",
    ".mp3", ".mp4", ".m4a", ".woff", ".woff2",
}
ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_UNCOMPRESSED = 25 * 1024 * 1024 * 1024


class CompressionCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class CompressionOptions:
    strip_metadata: bool = True
    strategy: str = "smart"  # standard / smart / maximum
    verify_pixels: bool = True
    scan: ScanProcessOptions | None = None

    def normalized(self) -> "CompressionOptions":
        strategy = str(self.strategy or "smart").strip().lower()
        if strategy not in {"standard", "smart", "maximum"}:
            strategy = "smart"
        scan = self.scan.normalized() if self.scan is not None else ScanProcessOptions(enabled=False)
        return CompressionOptions(
            strip_metadata=bool(self.strip_metadata),
            strategy=strategy,
            verify_pixels=bool(self.verify_pixels),
            scan=scan,
        )


@dataclass
class CompressionResult:
    source: str
    output: str
    original_size: int
    output_size: int
    images_seen: int = 0
    images_optimized: int = 0
    bytes_saved_in_images: int = 0
    used_oxipng: bool = False
    copied_original_container: bool = False
    warnings: tuple[str, ...] = ()
    strategy: str = "smart"
    pixel_verified: int = 0
    candidate_trials: int = 0
    scan_processed: int = 0
    format_mismatch_count: int = 0

    @property
    def saved_bytes(self) -> int:
        return max(0, self.original_size - self.output_size)

    @property
    def ratio(self) -> float:
        if self.original_size <= 0:
            return 0.0
        return self.saved_bytes / self.original_size


@dataclass(frozen=True)
class _ImageOutcome:
    changed: bool = False
    saved: int = 0
    used_oxipng: bool = False
    verified: bool = False
    candidate_trials: int = 0
    scan_processed: bool = False
    format_mismatch: bool = False
    warning: str = ""


@dataclass(frozen=True)
class _ArchiveMetadata:
    entries: dict[str, ZipInfo]
    comment: bytes = b""


def _app_contents() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    try:
        exe = Path(sys.executable).resolve()
        if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
            return exe.parent.parent
        for parent in exe.parents:
            if parent.name == "Contents" and parent.parent.suffix == ".app":
                return parent
    except Exception:
        return None
    return None


def find_oxipng() -> Path | None:
    """Resolve bundled/source/PATH OxiPNG without installing anything at runtime."""
    candidates: list[Path] = []
    contents = _app_contents()
    if contents is not None:
        candidates.append(contents / "Resources" / "tools" / "oxipng")
    package_root = Path(__file__).resolve().parent.parent
    candidates.append(package_root / "tools" / "oxipng")
    found = shutil.which("oxipng")
    if found:
        candidates.append(Path(found))
    for path in candidates:
        try:
            if path.is_file() and os.access(path, os.X_OK):
                return path
        except OSError:
            continue
    return None


def _is_cancelled(cancel_cb: CancelCallback | None) -> bool:
    return bool(cancel_cb and cancel_cb())


def _check_cancel(cancel_cb: CancelCallback | None) -> None:
    if _is_cancelled(cancel_cb):
        raise CompressionCancelled("已取消压缩。")


def _format_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _sniff_image_kind_from_head(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def sniff_image_kind(path: Path) -> str | None:
    try:
        with open(path, "rb") as handle:
            return _sniff_image_kind_from_head(handle.read(16))
    except OSError:
        return None


def _canonical_suffix(kind: str | None, fallback: str = ".img") -> str:
    return {"jpeg": ".jpg", "png": ".png", "gif": ".gif", "webp": ".webp"}.get(kind, fallback)


def _supported_lossless_kind(path: Path) -> str | None:
    kind = sniff_image_kind(path)
    return kind if kind in {"jpeg", "png"} else None


def _is_direct_supported_image(path: Path) -> bool:
    if not path.is_file():
        return False
    kind = sniff_image_kind(path)
    if kind in {"jpeg", "png"}:
        return True
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _safe_target(root: Path, member_name: str) -> Path:
    member = member_name.replace("\\", "/").lstrip("/")
    target = (root / member).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"压缩包包含不安全路径：{member_name}") from exc
    return target


def _copy_zipinfo(info: ZipInfo) -> ZipInfo:
    clone = ZipInfo(filename=info.filename, date_time=info.date_time)
    clone.comment = info.comment
    clone.extra = info.extra
    clone.create_system = info.create_system
    clone.create_version = info.create_version
    clone.extract_version = info.extract_version
    clone.flag_bits = info.flag_bits & ~0x1
    clone.volume = info.volume
    clone.internal_attr = info.internal_attr
    clone.external_attr = info.external_attr
    return clone


def _safe_extract_zip(source: Path, destination: Path) -> tuple[list[str], _ArchiveMetadata]:
    order: list[str] = []
    metadata: dict[str, ZipInfo] = {}
    with ZipFile(source, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(f"压缩包文件数异常（{len(infos)}），已拒绝展开。")
        total_uncompressed = sum(max(0, int(info.file_size)) for info in infos)
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED:
            raise ValueError("压缩包展开体积超过安全上限，已拒绝处理。")
        for info in infos:
            name = info.filename
            if not name:
                continue
            target = _safe_target(destination, name)
            order.append(name)
            metadata[name.rstrip("/")] = _copy_zipinfo(info)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        return order, _ArchiveMetadata(metadata, bytes(zf.comment or b""))


def _copy_tree(source: Path, destination: Path) -> list[str]:
    order: list[str] = []
    for item in sorted(source.rglob("*"), key=lambda p: p.as_posix().casefold()):
        rel = item.relative_to(source)
        target = destination / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            order.append(rel.as_posix())
    return order


def _copy_images(sources: Iterable[Path], destination: Path) -> list[str]:
    order: list[str] = []
    for index, source in enumerate(sources, 1):
        kind = sniff_image_kind(source)
        suffix = _canonical_suffix(kind, source.suffix.lower() or ".img")
        name = f"{index:04d}{suffix}"
        shutil.copy2(source, destination / name)
        order.append(name)
    return order


def _decoded_pixel_digest(data: bytes) -> bytes | None:
    """Hash decoded RGBA pixels frame-by-frame; return None for unsupported images."""
    try:
        digest = sha256()
        with Image.open(io.BytesIO(data)) as image:
            frames = int(getattr(image, "n_frames", 1) or 1)
            indices = range(frames) if frames > 1 else (0,)
            for index in indices:
                if frames > 1:
                    image.seek(index)
                frame = image.convert("RGBA")
                try:
                    digest.update(frame.width.to_bytes(4, "big"))
                    digest.update(frame.height.to_bytes(4, "big"))
                    band = max(1, min(256, frame.height))
                    for top in range(0, frame.height, band):
                        crop = frame.crop((0, top, frame.width, min(frame.height, top + band)))
                        try:
                            digest.update(crop.tobytes())
                        finally:
                            crop.close()
                finally:
                    frame.close()
        return digest.digest()
    except Exception:
        return None


def _jpeg_rendering_metadata(data: bytes) -> tuple[bool, int, str]:
    """Return (must_preserve_markers, orientation, mode)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            orientation = int(image.getexif().get(274, 1) or 1)
            has_icc = bool(image.info.get("icc_profile"))
            mode = str(image.mode or "")
            preserve = has_icc or orientation not in (0, 1) or mode not in {"RGB", "L"}
            return preserve, orientation, mode
    except Exception:
        return True, 1, ""


def _atomic_replace_bytes(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + ".kcc-opt-partial")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def _optimize_jpeg(path: Path, options: CompressionOptions) -> _ImageOutcome:
    original = path.read_bytes()
    if not original:
        return _ImageOutcome()
    original_digest = _decoded_pixel_digest(original) if options.verify_pixels else None
    preserve_for_rendering, _, _ = _jpeg_rendering_metadata(original)
    preserve_markers = (not options.strip_metadata) or preserve_for_rendering
    try:
        if preserve_markers:
            optimized = mozjpeg_lossless_optimization.optimize(
                original,
                copy=mozjpeg_lossless_optimization.COPY_MARKERS.ALL,
            )
        else:
            optimized = mozjpeg_lossless_optimization.optimize(original)
    except Exception:
        return _ImageOutcome(warning=f"JPEG 无损优化失败：{path.name}")
    if not optimized or len(optimized) >= len(original):
        return _ImageOutcome(candidate_trials=1)

    verified = False
    if options.verify_pixels:
        candidate_digest = _decoded_pixel_digest(optimized)
        verified = original_digest is not None and candidate_digest == original_digest
        if not verified:
            return _ImageOutcome(candidate_trials=1, warning=f"JPEG 像素校验未通过，已保留原图：{path.name}")
    else:
        verified = True
    _atomic_replace_bytes(path, optimized)
    return _ImageOutcome(
        changed=True,
        saved=len(original) - len(optimized),
        verified=verified,
        candidate_trials=1,
    )


def _png_save_kwargs(image: Image.Image, strip_metadata: bool) -> dict:
    kwargs: dict = {"optimize": True, "compress_level": 9}
    for key in ("icc_profile", "transparency", "exif", "dpi"):
        if key in image.info:
            kwargs[key] = image.info[key]
    if strip_metadata:
        return kwargs
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in image.info.items():
        if isinstance(value, str):
            try:
                pnginfo.add_text(key, value)
            except Exception:
                pass
    if pnginfo.chunks:
        kwargs["pnginfo"] = pnginfo
    return kwargs


def _optimize_png_with_pillow(path: Path, options: CompressionOptions) -> _ImageOutcome:
    original = path.read_bytes()
    if not original:
        return _ImageOutcome()
    try:
        with Image.open(io.BytesIO(original)) as image:
            image.load()
            if options.strip_metadata and any(key in image.info for key in ("gamma", "chromaticity", "srgb")):
                return _ImageOutcome(warning=f"缺少 OxiPNG，PNG 含颜色渲染信息，已保留原图：{path.name}")
            out = io.BytesIO()
            image.save(out, format="PNG", **_png_save_kwargs(image, options.strip_metadata))
            optimized = out.getvalue()
        if not optimized or len(optimized) >= len(original):
            return _ImageOutcome(candidate_trials=1)
        verified = True
        if options.verify_pixels:
            verified = _decoded_pixel_digest(original) == _decoded_pixel_digest(optimized)
            if not verified:
                return _ImageOutcome(candidate_trials=1, warning=f"PNG 像素校验未通过，已保留原图：{path.name}")
        _atomic_replace_bytes(path, optimized)
        return _ImageOutcome(
            changed=True,
            saved=len(original) - len(optimized),
            verified=verified,
            candidate_trials=1,
        )
    except Exception:
        return _ImageOutcome(warning=f"PNG 后备优化失败：{path.name}")


def _run_process_cancellable(
    cmd: list[str],
    *,
    cancel_cb: CancelCallback | None,
    timeout: float,
) -> tuple[int, str]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    start = monotonic()
    try:
        while proc.poll() is None:
            if _is_cancelled(cancel_cb):
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise CompressionCancelled("已取消压缩。")
            if monotonic() - start > timeout:
                proc.kill()
                proc.wait(timeout=5)
                return 124, "OxiPNG 超时"
            sleep(0.08)
        output = ""
        if proc.stdout is not None:
            output = proc.stdout.read() or ""
        return int(proc.returncode or 0), output
    finally:
        if proc.stdout is not None:
            proc.stdout.close()


def _png_traits(path: Path) -> tuple[bool, float, int]:
    """Return (line_art_like, grayscale_entropy, megapixels)."""
    try:
        with Image.open(path) as image:
            pixels = int(image.width) * int(image.height)
            mode = image.mode
            gray = ImageOps.grayscale(image)
            try:
                max_side = 512
                scale = min(1.0, max_side / max(gray.size))
                if scale < 1.0:
                    sample = gray.resize(
                        (max(1, round(gray.width * scale)), max(1, round(gray.height * scale))),
                        getattr(Image, "Resampling", Image).BOX,
                    )
                else:
                    sample = gray.copy()
                try:
                    entropy = float(sample.entropy())
                finally:
                    sample.close()
            finally:
                gray.close()
            line_art = mode in {"1", "L", "P"} or entropy < 5.65
            return line_art, entropy, max(1, round(pixels / 1_000_000))
    except Exception:
        return False, 8.0, 1


def _oxipng_plans(path: Path, strategy: str) -> list[tuple[str, bool]]:
    if strategy == "standard":
        return [("4", False)]
    if strategy == "maximum":
        return [("4", False), ("6", False), ("max", True)]
    size = path.stat().st_size
    line_art, _, megapixels = _png_traits(path)
    plans: list[tuple[str, bool]] = [("4", False)]
    if size >= 192 * 1024:
        plans.append(("6", False))
    if size >= 384 * 1024 and (line_art or size >= 2 * 1024 * 1024) and megapixels <= 28:
        plans.append(("max", True))
    return plans


def _optimize_png_with_oxipng(
    path: Path,
    oxipng: Path,
    options: CompressionOptions,
    cancel_cb: CancelCallback | None,
) -> _ImageOutcome:
    original = path.read_bytes()
    if not original:
        return _ImageOutcome(used_oxipng=True)
    original_digest = _decoded_pixel_digest(original) if options.verify_pixels else None
    best_size = len(original)
    best_candidate: Path | None = None
    trials = 0
    warning = ""

    for index, (level, zopfli) in enumerate(_oxipng_plans(path, options.strategy), 1):
        _check_cancel(cancel_cb)
        candidate = path.with_name(f".{path.name}.kcc-oxi-{index}.png")
        shutil.copy2(path, candidate)
        cmd = [os.fspath(oxipng), "-o", level, "--quiet", "--preserve"]
        if zopfli:
            cmd.append("-z")
        if options.strip_metadata:
            cmd.extend(["--strip", "safe"])
        cmd.append(os.fspath(candidate))
        trials += 1
        try:
            rc, _ = _run_process_cancellable(
                cmd,
                cancel_cb=cancel_cb,
                timeout=420.0 if zopfli else 240.0,
            )
            if rc != 0:
                warning = f"OxiPNG 候选失败（{level}{'+Zopfli' if zopfli else ''}）：{path.name}"
                candidate.unlink(missing_ok=True)
                continue
            candidate_size = candidate.stat().st_size
            if candidate_size >= best_size:
                candidate.unlink(missing_ok=True)
                continue
            verified = True
            if options.verify_pixels:
                verified = original_digest is not None and _decoded_pixel_digest(candidate.read_bytes()) == original_digest
            if not verified:
                candidate.unlink(missing_ok=True)
                warning = f"OxiPNG 像素校验未通过，已忽略该候选：{path.name}"
                continue
            if best_candidate is not None:
                best_candidate.unlink(missing_ok=True)
            best_candidate = candidate
            best_size = candidate_size
        except CompressionCancelled:
            candidate.unlink(missing_ok=True)
            if best_candidate is not None:
                best_candidate.unlink(missing_ok=True)
            raise
        except Exception:
            candidate.unlink(missing_ok=True)
            warning = f"OxiPNG 候选异常，已自动跳过：{path.name}"

    if best_candidate is None:
        fallback = _optimize_png_with_pillow(path, options)
        return _ImageOutcome(
            changed=fallback.changed,
            saved=fallback.saved,
            used_oxipng=True,
            verified=fallback.verified,
            candidate_trials=trials + fallback.candidate_trials,
            warning=warning or fallback.warning,
        )

    os.replace(best_candidate, path)
    return _ImageOutcome(
        changed=True,
        saved=len(original) - best_size,
        used_oxipng=True,
        verified=True,
        candidate_trials=trials,
        warning=warning,
    )


def _jpeg_scan_save_kwargs(source: Image.Image, strip_metadata: bool) -> dict:
    kwargs: dict = {"format": "JPEG", "optimize": True, "progressive": True}
    qtables = getattr(source, "quantization", None)
    if qtables:
        kwargs["qtables"] = qtables
    else:
        kwargs["quality"] = 95
    try:
        sampling = JpegImagePlugin.get_sampling(source)
        if sampling in (0, 1, 2):
            kwargs["subsampling"] = sampling
    except Exception:
        pass
    icc = source.info.get("icc_profile")
    if icc:
        kwargs["icc_profile"] = icc
    if not strip_metadata:
        try:
            exif = source.getexif()
            if exif:
                exif[274] = 1
                kwargs["exif"] = exif.tobytes()
        except Exception:
            pass
    return kwargs


def _apply_scan_processing(path: Path, kind: str, options: CompressionOptions) -> tuple[bool, str]:
    scan = options.scan or ScanProcessOptions(enabled=False)
    if not scan.enabled:
        return False, ""
    original = path.read_bytes()
    try:
        with Image.open(io.BytesIO(original)) as source:
            source.load()
            result, report = process_scan_image(source, scan)
            try:
                if not report.changed:
                    return False, ""
                out = io.BytesIO()
                if kind == "png":
                    kwargs = {"format": "PNG", "compress_level": 6}
                    icc = source.info.get("icc_profile")
                    if icc:
                        kwargs["icc_profile"] = icc
                    if not options.strip_metadata:
                        for key in ("dpi", "exif"):
                            if key in source.info:
                                kwargs[key] = source.info[key]
                    result.save(out, **kwargs)
                elif kind == "jpeg":
                    result.save(out, **_jpeg_scan_save_kwargs(source, options.strip_metadata))
                else:
                    return False, ""
                data = out.getvalue()
                if not data or _decoded_pixel_digest(data) is None:
                    return False, f"扫描件预处理输出校验失败，已保留原图：{path.name}"
                _atomic_replace_bytes(path, data)
                details: list[str] = []
                if report.crop_applied:
                    details.append("裁边")
                if report.deskew_applied:
                    details.append(f"纠斜 {report.deskew_angle:+.1f}°")
                if report.enhancement_applied != "none":
                    details.append("纸面/线稿增强")
                return True, f"{path.name}：" + "、".join(details)
            finally:
                result.close()
    except Exception as exc:
        _atomic_replace_bytes(path, original)
        return False, f"扫描件预处理已回退原图：{path.name}（{exc}）"


def optimize_image(
    path: Path,
    *,
    strip_metadata: bool = True,
    oxipng: Path | None = None,
    strategy: str = "smart",
    verify_pixels: bool = True,
    scan_options: ScanProcessOptions | None = None,
    cancel_cb: CancelCallback | None = None,
) -> _ImageOutcome:
    options = CompressionOptions(
        strip_metadata=strip_metadata,
        strategy=strategy,
        verify_pixels=verify_pixels,
        scan=scan_options,
    ).normalized()
    kind = _supported_lossless_kind(path)
    if kind is None:
        return _ImageOutcome()
    suffix_kind = "jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else ("png" if path.suffix.lower() == ".png" else None)
    mismatch = suffix_kind is not None and suffix_kind != kind
    scan_changed, scan_note = _apply_scan_processing(path, kind, options)
    _check_cancel(cancel_cb)
    if kind == "jpeg":
        outcome = _optimize_jpeg(path, options)
    else:
        outcome = (
            _optimize_png_with_oxipng(path, oxipng, options, cancel_cb)
            if oxipng is not None
            else _optimize_png_with_pillow(path, options)
        )
    warning_parts = [part for part in (scan_note, outcome.warning) if part]
    if mismatch:
        warning_parts.append(f"检测到扩展名与真实图片格式不一致：{path.name}（按真实 {kind.upper()} 处理）")
    return _ImageOutcome(
        changed=outcome.changed or scan_changed,
        saved=outcome.saved,
        used_oxipng=outcome.used_oxipng,
        verified=outcome.verified,
        candidate_trials=outcome.candidate_trials,
        scan_processed=scan_changed,
        format_mismatch=mismatch,
        warning="；".join(warning_parts),
    )


def optimize_tree(
    root: Path,
    *,
    strip_metadata: bool = True,
    strategy: str = "smart",
    verify_pixels: bool = True,
    scan_options: ScanProcessOptions | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> tuple[int, int, int, bool, int, int, int, int, list[str]]:
    images: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and _supported_lossless_kind(path) in {"jpeg", "png"}:
            images.append(path)
    images.sort(key=lambda p: p.as_posix().casefold())
    total = len(images)
    optimized_count = 0
    saved = 0
    used_oxipng = False
    verified_count = 0
    candidate_trials = 0
    scan_processed = 0
    mismatches = 0
    warnings: list[str] = []
    oxipng = find_oxipng()

    for index, path in enumerate(images, 1):
        _check_cancel(cancel_cb)
        if progress_cb:
            progress_cb(index - 1, total, f"正在分析并优化：{path.name}")
        outcome = optimize_image(
            path,
            strip_metadata=strip_metadata,
            oxipng=oxipng,
            strategy=strategy,
            verify_pixels=verify_pixels,
            scan_options=scan_options,
            cancel_cb=cancel_cb,
        )
        used_oxipng = used_oxipng or outcome.used_oxipng
        candidate_trials += outcome.candidate_trials
        verified_count += int(outcome.verified)
        scan_processed += int(outcome.scan_processed)
        mismatches += int(outcome.format_mismatch)
        if outcome.changed:
            optimized_count += 1
            saved += max(0, outcome.saved)
        if outcome.warning:
            warnings.append(outcome.warning)
        if progress_cb:
            progress_cb(index, total, f"已处理 {index}/{total}：{path.name}")

    return (
        total, optimized_count, saved, used_oxipng, verified_count,
        candidate_trials, scan_processed, mismatches, warnings,
    )


def _iter_repack_names(root: Path, original_order: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for name in original_order:
        normalized = name.replace("\\", "/").rstrip("/")
        if not normalized or normalized in seen:
            continue
        path = root / normalized
        if path.is_file():
            seen.add(normalized)
            names.append(normalized)
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix().casefold()):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in seen:
            seen.add(rel)
            names.append(rel)
    return names


def _entry_compression(path: Path) -> int:
    kind = sniff_image_kind(path)
    if kind in {"jpeg", "png", "gif", "webp"}:
        return ZIP_STORED
    return ZIP_STORED if path.suffix.lower() in COMPRESSED_EXTENSIONS else ZIP_DEFLATED


def _zipinfo_for_path(name: str, path: Path, original: ZipInfo | None, compression: int) -> ZipInfo:
    if original is not None:
        info = _copy_zipinfo(original)
        info.filename = name
    else:
        info = ZipInfo(filename=name)
        try:
            mode = path.stat().st_mode
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
        except OSError:
            pass
    info.compress_type = compression
    if compression == ZIP_DEFLATED:
        try:
            info._compresslevel = 9
        except Exception:
            pass
    return info


def _repack_zip(
    root: Path,
    output: Path,
    *,
    is_epub: bool,
    order: Iterable[str],
    metadata: _ArchiveMetadata | None = None,
) -> None:
    names = _iter_repack_names(root, order)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(output.name + ".partial")
    if temp_output.exists():
        temp_output.unlink()
    meta = metadata or _ArchiveMetadata({})

    with ZipFile(temp_output, "w") as zf:
        zf.comment = meta.comment
        if is_epub:
            mimetype = root / "mimetype"
            if not mimetype.is_file():
                raise ValueError("EPUB 缺少 mimetype 文件。")
            mime_info = ZipInfo("mimetype")
            mime_info.compress_type = ZIP_STORED
            with zf.open(mime_info, "w", force_zip64=True) as dst, open(mimetype, "rb") as src:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            names = [name for name in names if name != "mimetype"]

        for name in names:
            path = root / name
            if not path.is_file():
                continue
            compression = _entry_compression(path)
            original_info = meta.entries.get(name) or meta.entries.get(name.rstrip("/"))
            info = _zipinfo_for_path(name, path, original_info, compression)
            with zf.open(info, "w", force_zip64=True) as dst, open(path, "rb") as src:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    os.replace(temp_output, output)


def _unique_output(out_dir: Path, base_name: str, suffix: str, scan_enabled: bool = False) -> Path:
    tag = "智能处理压缩" if scan_enabled else "无损压缩"
    candidate = out_dir / f"{base_name}_{tag}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{base_name}_{tag}_{counter}{suffix}"
        counter += 1
    return candidate


def _compress_one(
    source: Path,
    out_dir: Path,
    *,
    options: CompressionOptions,
    progress_cb: ProgressCallback | None,
    cancel_cb: CancelCallback | None,
) -> CompressionResult:
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"源文件不存在：{source}")
    options = options.normalized()
    scan_enabled = bool(options.scan and options.scan.enabled)
    original_size = _directory_size(source) if source.is_dir() else source.stat().st_size
    warnings: list[str] = []

    with TemporaryDirectory(prefix="KCC-Optimize-") as td:
        work = Path(td) / "payload"
        work.mkdir(parents=True, exist_ok=True)
        archive_meta = _ArchiveMetadata({})

        if source.is_dir():
            order = _copy_tree(source, work)
            suffix = ".cbz"
            output = _unique_output(out_dir, source.name, suffix, scan_enabled)
            is_epub = False
            source_was_archive = False
        elif source.suffix.lower() in ARCHIVE_EXTENSIONS:
            order, archive_meta = _safe_extract_zip(source, work)
            suffix = source.suffix.lower()
            output = _unique_output(out_dir, source.stem, suffix, scan_enabled)
            is_epub = suffix == ".epub"
            source_was_archive = True
        elif _is_direct_supported_image(source):
            order = _copy_images([source], work)
            suffix = ".cbz"
            output = _unique_output(out_dir, source.stem, suffix, scan_enabled)
            is_epub = False
            source_was_archive = False
        else:
            raise ValueError(f"暂不支持该输入：{source.name}。支持文件夹、JPG/JPEG/PNG、CBZ/ZIP/EPUB。")

        _check_cancel(cancel_cb)
        (
            seen, optimized, image_saved, used_oxipng, verified, trials,
            scan_processed, mismatches, tree_warnings,
        ) = optimize_tree(
            work,
            strip_metadata=options.strip_metadata,
            strategy=options.strategy,
            verify_pixels=options.verify_pixels,
            scan_options=options.scan,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )
        warnings.extend(tree_warnings)
        _check_cancel(cancel_cb)
        _repack_zip(work, output, is_epub=is_epub, order=order, metadata=archive_meta)

        copied_original = False
        if source_was_archive and not scan_enabled and output.stat().st_size >= source.stat().st_size:
            shutil.copy2(source, output)
            copied_original = True
            warnings.append("优化后容器没有变小，已自动保留原容器内容，避免文件增大。")

        return CompressionResult(
            source=os.fspath(source),
            output=os.fspath(output),
            original_size=original_size,
            output_size=output.stat().st_size,
            images_seen=seen,
            images_optimized=optimized,
            bytes_saved_in_images=image_saved,
            used_oxipng=used_oxipng,
            copied_original_container=copied_original,
            warnings=tuple(warnings),
            strategy=options.strategy,
            pixel_verified=verified,
            candidate_trials=trials,
            scan_processed=scan_processed,
            format_mismatch_count=mismatches,
        )


def _compress_image_group(
    sources: list[Path],
    out_dir: Path,
    *,
    options: CompressionOptions,
    progress_cb: ProgressCallback | None,
    cancel_cb: CancelCallback | None,
) -> CompressionResult:
    options = options.normalized()
    sources = [p.expanduser().resolve() for p in sources]
    original_size = sum(p.stat().st_size for p in sources)
    common_parent = sources[0].parent
    label = common_parent.name or "图片"
    scan_enabled = bool(options.scan and options.scan.enabled)

    with TemporaryDirectory(prefix="KCC-Optimize-") as td:
        work = Path(td) / "payload"
        work.mkdir(parents=True, exist_ok=True)
        order = _copy_images(sources, work)
        (
            seen, optimized, image_saved, used_oxipng, verified, trials,
            scan_processed, mismatches, warnings,
        ) = optimize_tree(
            work,
            strip_metadata=options.strip_metadata,
            strategy=options.strategy,
            verify_pixels=options.verify_pixels,
            scan_options=options.scan,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )
        _check_cancel(cancel_cb)
        output = _unique_output(out_dir, label, ".cbz", scan_enabled)
        _repack_zip(work, output, is_epub=False, order=order)
        return CompressionResult(
            source="; ".join(os.fspath(p) for p in sources),
            output=os.fspath(output),
            original_size=original_size,
            output_size=output.stat().st_size,
            images_seen=seen,
            images_optimized=optimized,
            bytes_saved_in_images=image_saved,
            used_oxipng=used_oxipng,
            warnings=tuple(warnings),
            strategy=options.strategy,
            pixel_verified=verified,
            candidate_trials=trials,
            scan_processed=scan_processed,
            format_mismatch_count=mismatches,
        )


def compress_sources(
    sources: Iterable[str | os.PathLike[str]],
    out_dir: str | os.PathLike[str],
    *,
    strip_metadata: bool = True,
    strategy: str = "smart",
    verify_pixels: bool = True,
    scan_options: ScanProcessOptions | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> list[CompressionResult]:
    """Compress one or more sources while keeping old callers compatible."""
    paths = [Path(p) for p in sources]
    paths = [p for p in paths if os.fspath(p).strip()]
    if not paths:
        raise ValueError("没有可压缩的输入。")
    options = CompressionOptions(
        strip_metadata=strip_metadata,
        strategy=strategy,
        verify_pixels=verify_pixels,
        scan=scan_options,
    ).normalized()
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    _check_cancel(cancel_cb)
    if len(paths) > 1 and all(_is_direct_supported_image(p) for p in paths):
        return [
            _compress_image_group(
                paths,
                out,
                options=options,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
        ]

    results: list[CompressionResult] = []
    total_sources = len(paths)
    for index, source in enumerate(paths, 1):
        _check_cancel(cancel_cb)

        def nested_progress(done: int, total: int, label: str) -> None:
            if progress_cb:
                progress_cb(done, total, f"[{index}/{total_sources}] {label}")

        results.append(
            _compress_one(
                source,
                out,
                options=options,
                progress_cb=nested_progress,
                cancel_cb=cancel_cb,
            )
        )
    return results


def summarize_results(results: Iterable[CompressionResult]) -> str:
    items = list(results)
    if not items:
        return "没有生成文件。"
    before = sum(item.original_size for item in items)
    after = sum(item.output_size for item in items)
    saved = max(0, before - after)
    ratio = (saved / before * 100.0) if before else 0.0
    optimized = sum(item.images_optimized for item in items)
    seen = sum(item.images_seen for item in items)
    verified = sum(item.pixel_verified for item in items)
    trials = sum(item.candidate_trials for item in items)
    scan_processed = sum(item.scan_processed for item in items)
    mismatches = sum(item.format_mismatch_count for item in items)
    engine = "OxiPNG + MozJPEG" if any(item.used_oxipng for item in items) else "MozJPEG + Pillow"
    strategy_map = {"standard": "快速", "smart": "智能择小", "maximum": "极限择小"}
    strategy = strategy_map.get(items[0].strategy, items[0].strategy)

    lines = [
        f"完成 {len(items)} 个输出",
        f"原始：{_format_bytes(before)}",
        f"生成：{_format_bytes(after)}",
        f"节省：{_format_bytes(saved)}（{ratio:.1f}%）",
        f"图片：{optimized}/{seen} 张实际变小或完成预处理",
        f"像素校验：{verified} 张无损候选通过",
        f"候选比较：{trials} 次 · 策略：{strategy}",
        f"引擎：{engine}",
    ]
    if scan_processed:
        lines.append(f"扫描件预处理：{scan_processed} 张（该模式会改变像素/几何）")
    if mismatches:
        lines.append(f"真实格式纠正：检测到 {mismatches} 个扩展名与内容不一致的图片")
    lines.extend(["", "输出："])
    lines.extend(f"• {Path(item.output).name}" for item in items)
    warnings = [warning for item in items for warning in item.warnings]
    if warnings:
        unique: list[str] = []
        seen_warning: set[str] = set()
        for warning in warnings:
            if warning not in seen_warning:
                seen_warning.add(warning)
                unique.append(warning)
            if len(unique) >= 8:
                break
        lines.extend(["", "提示：", *[f"• {warning}" for warning in unique]])
        if len(warnings) > len(unique):
            lines.append(f"• 另有 {len(warnings) - len(unique)} 条同类提示未展开")
    return "\n".join(lines)
