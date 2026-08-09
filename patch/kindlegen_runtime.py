# -*- coding: utf-8 -*-
"""KindleGen discovery and compatibility guard for KCC Kindle CN.

The upstream KCC invokes ``kindlegen`` by name.  This layer adds a deterministic
search order suitable for a self-contained macOS app while refusing legacy
32-bit Mach-O builds that modern macOS cannot execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
import platform
import re
import shutil
import subprocess
import sys


@dataclass(frozen=True)
class KindleGenStatus:
    usable: bool
    path: str = ""
    source: str = ""
    version: str = ""
    architecture: str = ""
    reason: str = ""


class KindleGenUnavailable(OSError):
    pass


def _app_contents() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    try:
        exe = Path(sys.executable).resolve()
        # .../Foo.app/Contents/MacOS/Foo -> .../Foo.app/Contents
        if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
            return exe.parent.parent
        for parent in exe.parents:
            if parent.name == "Contents" and parent.parent.suffix == ".app":
                return parent
    except Exception:
        pass
    return None


def candidate_paths() -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []

    env = os.environ.get("KCC_KINDLEGEN", "").strip()
    if env:
        candidates.append((Path(env).expanduser(), "环境变量 KCC_KINDLEGEN"))

    contents = _app_contents()
    if contents is not None:
        candidates.extend([
            (contents / "Resources" / "tools" / "kindlegen", "App 内置 KindleGen"),
            (contents / "Resources" / "kindlegen", "App 内置 KindleGen"),
        ])

    # Development/source-build location. This also makes CI tests deterministic.
    package_root = Path(__file__).resolve().parent.parent
    candidates.extend([
        (package_root / "tools" / "kindlegen", "源码 tools 目录"),
        (Path.home() / "Library" / "Application Support" / "KCC-Kindle-CN" / "tools" / "kindlegen",
         "用户工具目录"),
    ])

    if platform.system() == "Darwin":
        candidates.extend([
            (Path("/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen"), "Kindle Previewer 3"),
            (Path("/Applications/Kindle Comic Creator/Kindle Comic Creator.app/Contents/MacOS/kindlegen"),
             "Kindle Comic Creator"),
        ])

    found = shutil.which("kindlegen")
    if found:
        candidates.append((Path(found), "PATH"))

    # Deduplicate while preserving priority.
    seen: set[str] = set()
    result: list[tuple[Path, str]] = []
    for path, source in candidates:
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        if key not in seen:
            seen.add(key)
            result.append((path, source))
    return result


def _file_description(path: Path) -> str:
    if platform.system() == "Darwin" and Path("/usr/bin/file").exists():
        try:
            proc = subprocess.run(
                ["/usr/bin/file", "-b", os.fspath(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
                check=False,
            )
            return (proc.stdout or "").strip()
        except Exception:
            return ""
    return ""


def _arch_from_description(desc: str) -> str:
    parts: list[str] = []
    lower = desc.lower()
    if "arm64" in lower or "aarch64" in lower:
        parts.append("arm64")
    if "x86_64" in lower:
        parts.append("x86_64")
    if re.search(r"\bi386\b|80386", lower):
        parts.append("i386")
    if "ppc" in lower or "powerpc" in lower:
        parts.append("ppc")
    return "+".join(parts) or "unknown"


def _legacy_32bit_macos(desc: str) -> bool:
    lower = desc.lower()
    has_modern = "x86_64" in lower or "arm64" in lower or "aarch64" in lower
    has_legacy = bool(re.search(r"\bi386\b|80386|powerpc|\bppc\b", lower))
    return platform.system() == "Darwin" and has_legacy and not has_modern


def _version_from_output(output: str) -> str:
    # Typical output includes "Amazon kindlegen(MAC OSX) V2.9 build ..."
    match = re.search(r"Amazon\s+kindlegen.*?\bV([0-9]+(?:\.[0-9]+)+)", output, re.I | re.S)
    return match.group(1) if match else ""


def _probe(path: Path, source: str) -> KindleGenStatus:
    try:
        if not path.is_file():
            return KindleGenStatus(False, os.fspath(path), source, reason="文件不存在")
        if not os.access(path, os.X_OK):
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except Exception:
                return KindleGenStatus(False, os.fspath(path), source, reason="文件不可执行")

        desc = _file_description(path)
        arch = _arch_from_description(desc)
        if _legacy_32bit_macos(desc):
            return KindleGenStatus(
                False,
                os.fspath(path),
                source,
                architecture=arch,
                reason="这是 32 位 i386/PowerPC KindleGen，现代 macOS 与 Apple Silicon 无法运行",
            )

        proc = subprocess.run(
            [os.fspath(path), "-locale", "en"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="ignore",
            timeout=12,
            check=False,
        )
        output = proc.stdout or ""
        version = _version_from_output(output)

        # KindleGen commonly returns a non-zero code for version/help probes, so
        # identify it by output rather than requiring rc==0.
        if "kindlegen" not in output.lower():
            return KindleGenStatus(
                False, os.fspath(path), source, version, arch,
                f"无法确认 KindleGen 可用（退出码 {proc.returncode}）",
            )
        return KindleGenStatus(True, os.fspath(path), source, version, arch, "")
    except subprocess.TimeoutExpired:
        return KindleGenStatus(False, os.fspath(path), source, architecture=_arch_from_description(_file_description(path)),
                               reason="KindleGen 启动超时")
    except OSError as exc:
        reason = exc.strerror or str(exc)
        return KindleGenStatus(False, os.fspath(path), source, architecture=_arch_from_description(_file_description(path)),
                               reason=reason)
    except Exception as exc:
        return KindleGenStatus(False, os.fspath(path), source, reason=str(exc))


@lru_cache(maxsize=1)
def find_kindlegen() -> KindleGenStatus:
    failures: list[KindleGenStatus] = []
    for path, source in candidate_paths():
        if not path.exists():
            continue
        status = _probe(path, source)
        if status.usable:
            return status
        failures.append(status)

    if failures:
        first = failures[0]
        detail = first.reason or "检测失败"
        return KindleGenStatus(False, first.path, first.source, first.version, first.architecture, detail)
    return KindleGenStatus(False, reason="未找到 KindleGen")


def refresh_kindlegen() -> KindleGenStatus:
    find_kindlegen.cache_clear()
    return find_kindlegen()


def get_kindlegen_path() -> str:
    status = find_kindlegen()
    if status.usable and status.path:
        return status.path
    raise KindleGenUnavailable(status.reason or "未找到可运行的 KindleGen")


def diagnostic_text(status: KindleGenStatus | None = None) -> str:
    status = status or find_kindlegen()
    if status.usable:
        version = f" v{status.version}" if status.version else ""
        arch = f" · {status.architecture}" if status.architecture and status.architecture != "unknown" else ""
        return f"KindleGen{version}：可用（{status.source}{arch}）"
    if status.path:
        arch = f"（{status.architecture}）" if status.architecture and status.architecture != "unknown" else ""
        return f"KindleGen 不可用：{status.reason}{arch}"
    return "KindleGen 未安装：MOBI/AZW3 输出不可用"
