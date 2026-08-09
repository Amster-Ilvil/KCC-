#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime hardening for KCC Kindle CN.

Runs after patch_kcc.py against the pinned official KCC 11.0.1 source.
On GitHub's macOS build runner it also builds the pinned OxiPNG binary and adds
it to the PyInstaller bundle so end users do not need Homebrew or Rust.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import urllib.request

OXIPNG_VERSION = "10.1.1"


def fail(msg: str):
    raise SystemExit(f"[错误] {msg}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"{label}：期望 1 处，实际 {count} 处")
    return text.replace(old, new, 1)


def prepare_oxipng(root: Path) -> bool:
    """Build pinned OxiPNG on GitHub macOS arm64 and stage binary/license."""
    tools = root / "tools"
    licenses = root / "licenses"
    binary = tools / "oxipng"
    license_file = licenses / "OXIPNG-LICENSE.txt"

    if binary.is_file() and license_file.is_file():
        return True

    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true" or sys.platform != "darwin":
        print("[提示] 本地源码构建未发现 OxiPNG，将使用 Pillow 无损 PNG 优化后备。")
        return False

    cargo = shutil.which("cargo")
    if not cargo:
        fail("GitHub macOS Runner 缺少 cargo，无法构建固定版本 OxiPNG")

    install_root = root / ".kcc-oxipng-build"
    shutil.rmtree(install_root, ignore_errors=True)
    print(f"[构建] OxiPNG v{OXIPNG_VERSION} Apple Silicon")
    subprocess.run(
        [cargo, "install", "oxipng", "--version", OXIPNG_VERSION, "--locked", "--root", os.fspath(install_root)],
        check=True,
    )

    built = install_root / "bin" / "oxipng"
    if not built.is_file():
        fail("OxiPNG 构建完成但未找到可执行文件")
    tools.mkdir(parents=True, exist_ok=True)
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, binary)
    binary.chmod(binary.stat().st_mode | 0o111)

    license_url = f"https://raw.githubusercontent.com/oxipng/oxipng/v{OXIPNG_VERSION}/LICENSE"
    try:
        with urllib.request.urlopen(license_url, timeout=30) as response:
            license_bytes = response.read()
    except Exception as exc:
        fail(f"下载 OxiPNG MIT License 失败：{exc}")
    if len(license_bytes) < 100:
        fail("OxiPNG License 内容异常")
    license_file.write_bytes(license_bytes)

    probe = subprocess.run(
        [os.fspath(binary), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    print(probe.stdout.strip())
    if probe.returncode != 0 or OXIPNG_VERSION not in probe.stdout:
        fail("OxiPNG 版本/可执行性验证失败")
    return True


def patch_macos_spec(path: Path, bundle_oxipng: bool) -> None:
    if not bundle_oxipng:
        return
    text = path.read_text(encoding="utf-8")
    if "tools/oxipng" in text:
        return
    text = replace_once(
        text,
        "    datas=[],\n",
        "    datas=[\n"
        "        ('tools/oxipng', 'tools'),\n"
        "        ('licenses/OXIPNG-LICENSE.txt', 'licenses'),\n"
        "    ],\n",
        "PyInstaller 内置 OxiPNG",
    )
    path.write_text(text, encoding="utf-8")
    print("[完成] PyInstaller 已配置内置 OxiPNG 与 MIT License")


def patch_gui(path: Path):
    text = path.read_text(encoding="utf-8")

    if "QFontDatabase" not in text:
        text = replace_once(
            text,
            "from PySide6.QtGui import (QColor, QIcon, QImage, QKeyEvent, QPixmap, QDesktopServices)\n",
            "from PySide6.QtGui import (QColor, QIcon, QImage, QKeyEvent, QPixmap, QDesktopServices, QFontDatabase)\n",
            "加入 Qt 系统字体数据库",
        )
        text = replace_once(
            text,
            "        QApplication.__init__(self, argv)\n        self._key = 'KCC'\n",
            "        QApplication.__init__(self, argv)\n"
            "        if sys.platform == 'darwin':\n"
            "            self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))\n"
            "        self._key = 'KCC'\n",
            "应用 macOS Qt 系统字体",
        )

    if "refresh_kindlegen" not in text:
        text = replace_once(
            text,
            "from .kindle_cn_enhancements import install_enhancements, enhance_meta_editor, translate_more\n",
            "from .kindle_cn_enhancements import install_enhancements, enhance_meta_editor, translate_more\n"
            "from .kindlegen_runtime import refresh_kindlegen, diagnostic_text\n",
            "加入 MOBI/AZW3 引擎运行时检测",
        )

    if "install_compression_ui" not in text:
        text = replace_once(
            text,
            "from .kindlegen_runtime import refresh_kindlegen, diagnostic_text\n",
            "from .kindlegen_runtime import refresh_kindlegen, diagnostic_text\n"
            "from .kindle_cn_compression_ui import install_compression_ui\n",
            "加入智能压缩 UI",
        )
        text = replace_once(
            text,
            "        install_enhancements(self, MW)\n        self.editor = KCCGUI_MetaEditor()\n",
            "        install_enhancements(self, MW)\n        install_compression_ui(self, MW)\n        self.editor = KCCGUI_MetaEditor()\n",
            "启用智能压缩 UI",
        )

    text = text.replace(
        'statusBarLabel = QLabel("Kindle 专用 · 简体中文 · 无广告/推广")',
        'statusBarLabel = QLabel("Kindle 专用 · 简体中文")',
    )

    pattern = re.compile(
        r"    def detectKindleGen\(self, startup=False\):\n.*?\n    def __init__\(self, kccapp, kccwindow\):",
        re.S,
    )
    replacement = '''    def detectKindleGen(self, startup=False):
        status = refresh_kindlegen()
        self.kindleGen = status.usable
        self.kindleGenPath = status.path if status.usable else ''
        if status.usable and status.engine == 'kindlegen' and status.version:
            try:
                if Version(status.version) < Version('2.9'):
                    self.addMessage('KindleGen 版本较旧，MOBI/AZW3 转换可能失败。', 'warning')
            except Exception:
                pass
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
            '。当前版本正常情况下应自带 Apple Silicon Kindling；也可回退使用 Kindle Previewer 3。',
            'error'
        )

    def saveSettings(self, event):'''
    text, count = missing_pattern.subn(missing_replacement, text, count=1)
    if count != 1:
        fail(f"替换 MOBI/AZW3 引擎缺失提示失败（{count}）")

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
    print("[完成] GUI MOBI/AZW3 引擎、错误状态与智能压缩入口加固")


def patch_core(path: Path):
    text = path.read_text(encoding="utf-8")
    if "from .kindlegen_runtime import get_kindlegen_path" not in text:
        anchor = "from . import __version__\n"
        text = replace_once(
            text,
            anchor,
            anchor + "from .kindlegen_runtime import get_kindlegen_path, build_mobi_command\n",
            "core 导入 MOBI/AZW3 引擎 resolver",
        )

    preflight_pattern = re.compile(
        r"    if options\.format == 'MOBI':\n"
        r"        try:\n"
        r"            subprocess_run\(\['kindlegen', '-locale', 'en'\], stdout=PIPE, stderr=STDOUT, check=True\)\n"
        r"        except \(FileNotFoundError, CalledProcessError\):\n"
        r"            print\('ERROR: KindleGen is missing!'\)\n"
        r"            sys\.exit\(1\)\n"
        r"        except OSError as e:\n"
        r"            print\(f\"kindlegen: \{e\.strerror\}\"\)\n"
        r"            print\('Re-install Rosetta/Kindle Previewer/other Intel app\?'\)\n"
        r"            print\('Please email Amazon to make Kindle Previewer Apple silicon native at amazon\.com/kindle-help'\)\n"
        r"            sys\.exit\(1\)\n"
    )
    preflight_replacement = '''    if options.format == 'MOBI':
        try:
            get_kindlegen_path()
        except OSError as e:
            print('ERROR: MOBI/AZW3 engine unavailable: ' + (getattr(e, 'strerror', None) or str(e)))
            sys.exit(1)
'''
    text, preflight_count = preflight_pattern.subn(preflight_replacement, text, count=1)
    if preflight_count != 1:
        fail(f"替换 MOBI/AZW3 预检查失败（{preflight_count}）")

    worker_call = "subprocess_run(['kindlegen', '-dont_append_source', '-locale', 'en', item],"
    if text.count(worker_call) != 1:
        fail(f"定位 MOBI worker KindleGen 调用失败（{text.count(worker_call)}）")
    text = text.replace(worker_call, "subprocess_run(build_mobi_command(item),", 1)

    if "subprocess_run(['kindlegen'" in text:
        fail("仍存在硬编码 kindlegen 调用")

    marker = "    except CalledProcessError as err:\n        warnings = []\n"
    if "MOBI engine unavailable:" not in text and "KindleGen unavailable:" not in text:
        text = replace_once(
            text,
            marker,
            "    except OSError as err:\n"
            "        return [-2, 'MOBI engine unavailable: ' + (getattr(err, 'strerror', None) or str(err)), item, []]\n"
            + marker,
            "MOBI worker OSError 防护",
        )

    path.write_text(text, encoding="utf-8")
    print("[完成] comic2ebook MOBI/AZW3 引擎调用加固")


def main():
    if len(sys.argv) != 2:
        fail("用法：patch_runtime_v12.py /path/to/kcc-v11.0.1")
    root = Path(sys.argv[1]).expanduser().resolve()
    gui = root / "kindlecomicconverter" / "KCC_gui.py"
    core = root / "kindlecomicconverter" / "comic2ebook.py"
    spec = root / "kcc-macos.spec"
    patch_dir = Path(__file__).parent
    runtime_src = patch_dir / "kindlegen_runtime.py"
    runtime_dst = root / "kindlecomicconverter" / "kindlegen_runtime.py"
    compression_src = patch_dir / "kindle_cn_compress.py"
    compression_dst = root / "kindlecomicconverter" / "kindle_cn_compress.py"
    scan_src = patch_dir / "kindle_cn_scan_processing.py"
    scan_dst = root / "kindlecomicconverter" / "kindle_cn_scan_processing.py"
    compression_ui_src = patch_dir / "kindle_cn_compression_ui.py"
    compression_ui_dst = root / "kindlecomicconverter" / "kindle_cn_compression_ui.py"
    if not gui.is_file() or not core.is_file() or not spec.is_file():
        fail("目标源码不完整")
    for source, label in (
        (runtime_src, "kindlegen_runtime.py"),
        (compression_src, "kindle_cn_compress.py"),
        (scan_src, "kindle_cn_scan_processing.py"),
        (compression_ui_src, "kindle_cn_compression_ui.py"),
    ):
        if not source.is_file():
            fail(f"缺少 {label}")

    shutil.copy2(runtime_src, runtime_dst)
    shutil.copy2(scan_src, scan_dst)
    shutil.copy2(compression_src, compression_dst)
    shutil.copy2(compression_ui_src, compression_ui_dst)
    bundle_oxipng = prepare_oxipng(root)
    patch_macos_spec(spec, bundle_oxipng)
    patch_gui(gui)
    patch_core(core)
    print("[完成] Kindle 中文版运行时加固、智能压缩/扫描处理与 OxiPNG 打包配置")


if __name__ == "__main__":
    main()
