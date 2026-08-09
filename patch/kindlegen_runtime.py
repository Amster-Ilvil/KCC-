# -*- coding: utf-8 -*-
"""MOBI/AZW3 engine discovery for KCC Kindle CN.

The KCC conversion core still speaks the historical kindlegen command line.
This module resolves a compatible executable in a deterministic order.  It
supports both Amazon KindleGen and Kindling's documented kindlegen-compat mode,
and rejects legacy 32-bit Mach-O programs that modern macOS cannot execute.
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
    engine: str = ""  # "kindling" | "kindlegen" | ""


class KindleGenUnavailable(OSError):
    pass


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
        pass
    return None


def candidate_paths() -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []

    env = os.environ.get("KCC_KINDLEGEN", "").strip()
    if env:
        candidates.append((Path(env).expanduser(), "环境变量 KCC_KINDLEGEN"))

    contents = _app_contents()
    if contents is not None:
        # v1.3 release places Kindling here under the historical executable
        # name so the mature KCC MOBI worker can keep its proven CLI flow.
        candidates.extend([
            (contents / "Resources" / "tools" / "kindlegen", "App 内置 MOBI 引擎"),
            (contents / "Resources" / "kindlegen", "App 内置 MOBI 引擎"),
        ])

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


def _kindlegen_version(output: str) -> str:
    match = re.search(r"Amazon\s+kindlegen.*?\bV([0-9]+(?:\.[0-9]+)+)", output, re.I | re.S)
    return match.group(1) if match else ""


def _kindling_version(output: str) -> str:
    # clap normally prints "kindling 0.31.0"; tolerate kindling-cli and v-prefix.
    match = re.search(r"\bkindling(?:-cli)?\b[^0-9]{0,16}v?([0-9]+(?:\.[0-9]+){1,3})", output, re.I)
    return match.group(1) if match else ""


def _run(path: Path, args: list[str], timeout: int = 12) -> subprocess.CompletedProcess:
    return subprocess.run(
        [os.fspath(path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="ignore",
        timeout=timeout,
        check=False,
    )


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
                usable=False,
                path=os.fspath(path),
                source=source,
                architecture=arch,
                reason="这是 32 位 i386/PowerPC KindleGen，现代 macOS 与 Apple Silicon 无法运行",
            )

        # Kindling has a normal --version path. Probe it first so its own version
        # is not confused with Amazon KindleGen's unrelated 2.9 numbering.
        version_probe = _run(path, ["--version"], timeout=8)
        version_output = version_probe.stdout or ""
        if "kindling" in version_output.lower():
            version = _kindling_version(version_output)
            if version_probe.returncode == 0:
                return KindleGenStatus(
                    usable=True,
                    path=os.fspath(path),
                    source=source,
                    version=version,
                    architecture=arch,
                    engine="kindling",
                )
            return KindleGenStatus(
                usable=False,
                path=os.fspath(path),
                source=source,
                version=version,
                architecture=arch,
                reason=f"Kindling 版本探测失败（退出码 {version_probe.returncode}）",
                engine="kindling",
            )

        # Real KindleGen has no reliable --version switch. Its historical
        # `-locale en` probe emits the Amazon kindlegen banner even if the
        # process returns non-zero, which is why identity is based on output.
        legacy_probe = _run(path, ["-locale", "en"])
        legacy_output = legacy_probe.stdout or ""
        if "kindlegen" in legacy_output.lower() or "kindlegen" in version_output.lower():
            combined = version_output + "\n" + legacy_output
            return KindleGenStatus(
                usable=True,
                path=os.fspath(path),
                source=source,
                version=_kindlegen_version(combined),
                architecture=arch,
                engine="kindlegen",
            )

        return KindleGenStatus(
            usable=False,
            path=os.fspath(path),
            source=source,
            architecture=arch,
            reason=f"无法确认 MOBI 引擎兼容 KindleGen CLI（退出码 {legacy_probe.returncode}）",
        )
    except subprocess.TimeoutExpired:
        return KindleGenStatus(
            False,
            os.fspath(path),
            source,
            architecture=_arch_from_description(_file_description(path)),
            reason="MOBI 引擎启动超时",
        )
    except OSError as exc:
        return KindleGenStatus(
            False,
            os.fspath(path),
            source,
            architecture=_arch_from_description(_file_description(path)),
            reason=exc.strerror or str(exc),
        )
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
        return KindleGenStatus(
            False,
            first.path,
            first.source,
            first.version,
            first.architecture,
            first.reason or "检测失败",
            first.engine,
        )
    return KindleGenStatus(False, reason="未找到可用的 MOBI/AZW3 引擎")


def refresh_kindlegen() -> KindleGenStatus:
    find_kindlegen.cache_clear()
    return find_kindlegen()


def get_kindlegen_path() -> str:
    status = find_kindlegen()
    if status.usable and status.path:
        return status.path
    raise KindleGenUnavailable(status.reason or "未找到可运行的 MOBI/AZW3 引擎")


def diagnostic_text(status: KindleGenStatus | None = None) -> str:
    status = status or find_kindlegen()
    arch = ""
    if status.architecture and status.architecture != "unknown":
        arch = f" · {status.architecture}"

    if status.usable:
        version = f" v{status.version}" if status.version else ""
        if status.engine == "kindling":
            return f"Kindling{version}：可用（{status.source}{arch} · KindleGen 兼容模式）"
        return f"KindleGen{version}：可用（{status.source}{arch}）"

    if status.path:
        prefix = "Kindling" if status.engine == "kindling" else "MOBI 引擎"
        return f"{prefix}不可用：{status.reason}{arch}"
    return "MOBI/AZW3 引擎不可用"
