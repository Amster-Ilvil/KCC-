# -*- coding: utf-8 -*-
"""Lossless comic image/container optimizer for the Kindle-only KCC edition.

Design goals:
- never resize, recolor, sharpen or re-encode JPEG DCT coefficients;
- only replace an image when the optimized payload is actually smaller;
- preserve a valid EPUB mimetype layout when repacking EPUB files;
- prefer the bundled OxiPNG binary for PNG and fall back to Pillow safely;
- run independently from KCC's normal conversion pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
import io
import os
import shutil
import subprocess
import sys

import mozjpeg_lossless_optimization
from PIL import Image, PngImagePlugin

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ARCHIVE_EXTENSIONS = {".cbz", ".zip", ".epub"}
COMPRESSED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".jxl",
    ".mp3", ".mp4", ".m4a", ".woff", ".woff2",
}
ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


class CompressionCancelled(RuntimeError):
    pass


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

    @property
    def saved_bytes(self) -> int:
        return max(0, self.original_size - self.output_size)

    @property
    def ratio(self) -> float:
        if self.original_size <= 0:
            return 0.0
        return self.saved_bytes / self.original_size


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


def _safe_target(root: Path, member_name: str) -> Path:
    member = member_name.replace("\\", "/").lstrip("/")
    target = (root / member).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"压缩包包含不安全路径：{member_name}") from exc
    return target


def _safe_extract_zip(source: Path, destination: Path) -> list[str]:
    order: list[str] = []
    with ZipFile(source, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if not name:
                continue
            target = _safe_target(destination, name)
            order.append(name)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    return order


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
        suffix = source.suffix.lower() or ".img"
        name = f"{index:04d}{suffix}"
        shutil.copy2(source, destination / name)
        order.append(name)
    return order


def _jpeg_exif_orientation(data: bytes) -> int:
    try:
        with Image.open(io.BytesIO(data)) as image:
            return int(image.getexif().get(274, 1) or 1)
    except Exception:
        return 1


def _optimize_jpeg(path: Path, strip_metadata: bool) -> tuple[bool, int]:
    original = path.read_bytes()
    if not original:
        return False, 0

    preserve_markers = (not strip_metadata) or _jpeg_exif_orientation(original) not in (0, 1)
    if preserve_markers:
        optimized = mozjpeg_lossless_optimization.optimize(
            original,
            copy=mozjpeg_lossless_optimization.COPY_MARKERS.ALL,
        )
    else:
        optimized = mozjpeg_lossless_optimization.optimize(original)

    if not optimized or len(optimized) >= len(original):
        return False, 0

    try:
        with Image.open(io.BytesIO(original)) as before, Image.open(io.BytesIO(optimized)) as after:
            if before.size != after.size:
                return False, 0
            after.verify()
    except Exception:
        return False, 0

    temp = path.with_name(path.name + ".kcc-opt")
    temp.write_bytes(optimized)
    os.replace(temp, path)
    return True, len(original) - len(optimized)


def _png_save_kwargs(image: Image.Image, strip_metadata: bool) -> dict:
    kwargs: dict = {"optimize": True, "compress_level": 9}
    if strip_metadata:
        if "transparency" in image.info:
            kwargs["transparency"] = image.info["transparency"]
        if "icc_profile" in image.info:
            kwargs["icc_profile"] = image.info["icc_profile"]
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
    for key in ("icc_profile", "dpi", "transparency", "exif"):
        if key in image.info:
            kwargs[key] = image.info[key]
    return kwargs


def _optimize_png_with_pillow(path: Path, strip_metadata: bool) -> tuple[bool, int]:
    original = path.read_bytes()
    if not original:
        return False, 0
    try:
        with Image.open(io.BytesIO(original)) as image:
            image.load()
            mode = image.mode
            size = image.size
            pixels = image.tobytes()
            out = io.BytesIO()
            image.save(out, format="PNG", **_png_save_kwargs(image, strip_metadata))
            optimized = out.getvalue()
        if not optimized or len(optimized) >= len(original):
            return False, 0
        with Image.open(io.BytesIO(optimized)) as check:
            check.load()
            if check.mode != mode or check.size != size or check.tobytes() != pixels:
                return False, 0
    except Exception:
        return False, 0

    temp = path.with_name(path.name + ".kcc-opt")
    temp.write_bytes(optimized)
    os.replace(temp, path)
    return True, len(original) - len(optimized)


def _optimize_png_with_oxipng(path: Path, oxipng: Path, strip_metadata: bool) -> tuple[bool, int]:
    before = path.stat().st_size
    if before <= 0:
        return False, 0

    cmd = [
        os.fspath(oxipng),
        "-o", "4",
        "--quiet",
        "--preserve",
    ]
    if strip_metadata:
        cmd.extend(["--strip", "safe"])
    cmd.append(os.fspath(path))

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        return _optimize_png_with_pillow(path, strip_metadata)

    after = path.stat().st_size
    if after >= before:
        return False, 0
    return True, before - after


def optimize_image(path: Path, *, strip_metadata: bool = True, oxipng: Path | None = None) -> tuple[bool, int, bool]:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        changed, saved = _optimize_jpeg(path, strip_metadata)
        return changed, saved, False
    if ext == ".png":
        if oxipng is not None:
            changed, saved = _optimize_png_with_oxipng(path, oxipng, strip_metadata)
            return changed, saved, True
        changed, saved = _optimize_png_with_pillow(path, strip_metadata)
        return changed, saved, False
    return False, 0, False


def optimize_tree(
    root: Path,
    *,
    strip_metadata: bool = True,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> tuple[int, int, int, bool]:
    images = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    images.sort(key=lambda p: p.as_posix().casefold())
    total = len(images)
    optimized_count = 0
    saved = 0
    used_oxipng = False
    oxipng = find_oxipng()

    for index, path in enumerate(images, 1):
        _check_cancel(cancel_cb)
        if progress_cb:
            progress_cb(index - 1, total, f"正在优化：{path.name}")
        changed, delta, used = optimize_image(path, strip_metadata=strip_metadata, oxipng=oxipng)
        used_oxipng = used_oxipng or used
        if changed:
            optimized_count += 1
            saved += delta
        if progress_cb:
            progress_cb(index, total, f"已处理 {index}/{total}：{path.name}")

    return total, optimized_count, saved, used_oxipng


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


def _repack_zip(root: Path, output: Path, *, is_epub: bool, order: Iterable[str]) -> None:
    names = _iter_repack_names(root, order)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(output.name + ".partial")
    if temp_output.exists():
        temp_output.unlink()

    with ZipFile(temp_output, "w") as zf:
        if is_epub:
            mimetype = root / "mimetype"
            if not mimetype.is_file():
                raise ValueError("EPUB 缺少 mimetype 文件。")
            zf.writestr(ZipInfo("mimetype"), mimetype.read_bytes(), compress_type=ZIP_STORED)
            names = [name for name in names if name != "mimetype"]

        for name in names:
            path = root / name
            if not path.is_file():
                continue
            compression = ZIP_STORED if path.suffix.lower() in COMPRESSED_EXTENSIONS else ZIP_DEFLATED
            if compression == ZIP_DEFLATED:
                zf.write(path, arcname=name, compress_type=compression, compresslevel=9)
            else:
                zf.write(path, arcname=name, compress_type=compression)
    os.replace(temp_output, output)


def _unique_output(out_dir: Path, base_name: str, suffix: str) -> Path:
    candidate = out_dir / f"{base_name}_无损压缩{suffix}"
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{base_name}_无损压缩_{counter}{suffix}"
        counter += 1
    return candidate


def _compress_one(
    source: Path,
    out_dir: Path,
    *,
    strip_metadata: bool,
    progress_cb: ProgressCallback | None,
    cancel_cb: CancelCallback | None,
) -> CompressionResult:
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"源文件不存在：{source}")

    original_size = _directory_size(source) if source.is_dir() else source.stat().st_size
    warnings: list[str] = []

    with TemporaryDirectory(prefix="KCC-Lossless-") as td:
        work = Path(td) / "payload"
        work.mkdir(parents=True, exist_ok=True)

        if source.is_dir():
            order = _copy_tree(source, work)
            suffix = ".cbz"
            output = _unique_output(out_dir, source.name, suffix)
            is_epub = False
        elif source.suffix.lower() in ARCHIVE_EXTENSIONS:
            order = _safe_extract_zip(source, work)
            suffix = source.suffix.lower()
            output = _unique_output(out_dir, source.stem, suffix)
            is_epub = suffix == ".epub"
        elif source.suffix.lower() in IMAGE_EXTENSIONS:
            order = _copy_images([source], work)
            suffix = ".cbz"
            output = _unique_output(out_dir, source.stem, suffix)
            is_epub = False
        else:
            raise ValueError(f"暂不支持该输入：{source.name}。支持文件夹、JPG/JPEG/PNG、CBZ/ZIP/EPUB。")

        _check_cancel(cancel_cb)
        seen, optimized, image_saved, used_oxipng = optimize_tree(
            work,
            strip_metadata=strip_metadata,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )
        _check_cancel(cancel_cb)
        _repack_zip(work, output, is_epub=is_epub, order=order)

        copied_original = False
        if source.is_file() and source.suffix.lower() in ARCHIVE_EXTENSIONS:
            if output.stat().st_size >= source.stat().st_size:
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
        )


def _compress_image_group(
    sources: list[Path],
    out_dir: Path,
    *,
    strip_metadata: bool,
    progress_cb: ProgressCallback | None,
    cancel_cb: CancelCallback | None,
) -> CompressionResult:
    sources = [p.expanduser().resolve() for p in sources]
    original_size = sum(p.stat().st_size for p in sources)
    common_parent = sources[0].parent
    label = common_parent.name or "图片"

    with TemporaryDirectory(prefix="KCC-Lossless-") as td:
        work = Path(td) / "payload"
        work.mkdir(parents=True, exist_ok=True)
        order = _copy_images(sources, work)
        seen, optimized, image_saved, used_oxipng = optimize_tree(
            work,
            strip_metadata=strip_metadata,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )
        _check_cancel(cancel_cb)
        output = _unique_output(out_dir, label, ".cbz")
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
        )


def compress_sources(
    sources: Iterable[str | os.PathLike[str]],
    out_dir: str | os.PathLike[str],
    *,
    strip_metadata: bool = True,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> list[CompressionResult]:
    paths = [Path(p) for p in sources]
    paths = [p for p in paths if os.fspath(p).strip()]
    if not paths:
        raise ValueError("没有可压缩的输入。")

    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    _check_cancel(cancel_cb)
    if len(paths) > 1 and all(p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS for p in paths):
        return [
            _compress_image_group(
                paths,
                out,
                strip_metadata=strip_metadata,
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
                strip_metadata=strip_metadata,
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
    engine = "OxiPNG + MozJPEG" if any(item.used_oxipng for item in items) else "MozJPEG + Pillow"

    lines = [
        f"完成 {len(items)} 个输出",
        f"原始：{_format_bytes(before)}",
        f"生成：{_format_bytes(after)}",
        f"节省：{_format_bytes(saved)}（{ratio:.1f}%）",
        f"图片：{optimized}/{seen} 张实际变小",
        f"引擎：{engine}",
        "",
        "输出：",
    ]
    lines.extend(f"• {Path(item.output).name}" for item in items)
    warnings = [warning for item in items for warning in item.warnings]
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)
