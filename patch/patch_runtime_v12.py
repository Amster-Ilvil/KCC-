#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Post-patch hardening for KCC Kindle CN v1.2.

Runs after patch_kcc.py against the pinned official KCC 11.0.1 source.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys


def fail(msg: str):
    raise SystemExit(f"[错误] {msg}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"{label}：期望 1 处，实际 {count} 处")
    return text.replace(old, new, 1)


def patch_gui(path: Path):
    text = path.read_text(encoding="utf-8")
    if "refresh_kindlegen" not in text:
        text = replace_once(
            text,
            "from .kindle_cn_enhancements import install_enhancements, enhance_meta_editor, translate_more\n",
            "from .kindle_cn_enhancements import install_enhancements, enhance_meta_editor, translate_more\n"
            "from .kindlegen_runtime import refresh_kindlegen, diagnostic_text\n",
            "加入 KindleGen 运行时检测",
        )

    # User-facing cleanup: retain the useful identity text, remove the redundant
    # advertising claim from the bottom status bar.
    text = text.replace(
        'statusBarLabel = QLabel("Kindle 专用 · 简体中文 · 无广告/推广")',
        'statusBarLabel = QLabel("Kindle 专用 · 简体中文")',
    )

    # Replace upstream PATH-only KindleGen detection. Missing KindleGen is an
    # optional-feature state, not a startup-fatal dialog.
    pattern = re.compile(
        r"    def detectKindleGen\(self, startup=False\):\n.*?\n    def __init__\(self, kccapp, kccwindow\):",
        re.S,
    )
    replacement = '''    def detectKindleGen(self, startup=False):
        status = refresh_kindlegen()
        self.kindleGen = status.usable
        self.kindleGenPath = status.path if status.usable else ''
        if status.usable and status.version:
            try:
                if Version(status.version) < Version('2.9'):
                    self.addMessage('KindleGen 版本较旧，MOBI/AZW3 转换可能失败。', 'warning')
            except Exception:
                pass
        # Do not interrupt startup for an optional converter. The user gets a
        # precise diagnostic only if MOBI/AZW3 is actually selected.
        return status

    def __init__(self, kccapp, kccwindow):'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        fail(f"替换 detectKindleGen 失败（{count}）")

    missing_pattern = re.compile(
        r"    def display_kindlegen_missing\(self\):\n.*?\n    def saveSettings\(self, event\):",
        re.S,
    )
    missing_replacement = '''    def display_kindlegen_missing(self):
        status = refresh_kindlegen()
        self.addMessage(
            '<b>MOBI/AZW3 暂不可用。</b> ' + diagnostic_text(status) +
            '。请使用兼容现代 macOS 的 64 位 KindleGen，或安装 Kindle Previewer 3。',
            'error'
        )

    def saveSettings(self, event):'''
    text, count = missing_pattern.subn(missing_replacement, text, count=1)
    if count != 1:
        fail(f"替换 KindleGen 缺失提示失败（{count}）")

    # WorkerThread used to reset self.errors for each source and therefore
    # could report "All jobs completed" when an earlier item failed but the
    # final item succeeded. Keep per-item errors and an aggregate flag.
    worker_start = text.find("class WorkerThread(QThread):")
    worker_end = text.find("\nclass SystemTrayIcon", worker_start)
    if worker_start < 0 or worker_end < 0:
        fail("无法定位 WorkerThread")
    worker = text[worker_start:worker_end]
    if "self.anyErrors" not in worker:
        worker = replace_once(
            worker,
            "        self.errors = False\n        self.kindlegenErrorCode = [0]\n",
            "        self.errors = False\n        self.anyErrors = False\n        self.kindlegenErrorCode = [0]\n",
            "加入聚合错误状态",
        )
        worker = re.sub(
            r"(?m)^(\s*)self\.errors = True$",
            lambda m: m.group(0) + "\n" + m.group(1) + "self.anyErrors = True",
            worker,
        )
        # Only the final completion gate should use the aggregate flag.
        final_gate = worker.rfind("        if not self.errors:\n            MW.addMessage.emit('<b>All jobs completed.</b>'")
        if final_gate >= 0:
            worker = worker[:final_gate] + worker[final_gate:].replace(
                "        if not self.errors:\n            MW.addMessage.emit('<b>All jobs completed.</b>'",
                "        if not self.anyErrors:\n            MW.addMessage.emit('<b>All jobs completed.</b>'",
                1,
            )
        else:
            fail("无法定位最终完成状态")
        text = text[:worker_start] + worker + text[worker_end:]

    path.write_text(text, encoding="utf-8")
    print("[完成] GUI KindleGen/错误状态加固")


def patch_core(path: Path):
    text = path.read_text(encoding="utf-8")
    if "from .kindlegen_runtime import get_kindlegen_path" not in text:
        anchor = "from . import __version__\n"
        text = replace_once(
            text,
            anchor,
            anchor + "from .kindlegen_runtime import get_kindlegen_path\n",
            "core 导入 KindleGen resolver",
        )

    # Both the initial option check and the actual MOBI worker must resolve the
    # same executable. This prevents GUI/CLI disagreement and stale PATH bugs.
    text = text.replace("subprocess_run(['kindlegen',", "subprocess_run([get_kindlegen_path(),")
    if text.count("subprocess_run(['kindlegen',"):
        fail("仍存在硬编码 kindlegen 调用")

    # A missing/incompatible executable in a multiprocessing worker previously
    # escaped as OSError and could kill the worker pool. Convert it to a normal
    # KCC error result so cleanup/UI handling remains intact.
    marker = "    except CalledProcessError as err:\n        warnings = []\n"
    if "KindleGen unavailable:" not in text:
        text = replace_once(
            text,
            marker,
            "    except OSError as err:\n"
            "        return [-2, 'KindleGen unavailable: ' + (getattr(err, 'strerror', None) or str(err)), item, []]\n"
            + marker,
            "MOBI worker OSError 防护",
        )

    path.write_text(text, encoding="utf-8")
    print("[完成] comic2ebook KindleGen 调用加固")


def main():
    if len(sys.argv) != 2:
        fail("用法：patch_runtime_v12.py /path/to/kcc-v11.0.1")
    root = Path(sys.argv[1]).expanduser().resolve()
    gui = root / "kindlecomicconverter" / "KCC_gui.py"
    core = root / "kindlecomicconverter" / "comic2ebook.py"
    runtime_src = Path(__file__).with_name("kindlegen_runtime.py")
    runtime_dst = root / "kindlecomicconverter" / "kindlegen_runtime.py"
    if not gui.is_file() or not core.is_file():
        fail("目标源码不完整")
    if not runtime_src.is_file():
        fail("缺少 kindlegen_runtime.py")
    shutil.copy2(runtime_src, runtime_dst)
    patch_gui(gui)
    patch_core(core)
    print("[完成] v1.2 运行时加固补丁")


if __name__ == "__main__":
    main()
