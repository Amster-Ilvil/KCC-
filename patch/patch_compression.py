#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install the lossless compression module into a pristine KCC 11.0.1 tree."""
from __future__ import annotations

from pathlib import Path
import shutil
import sys


def fail(message: str) -> None:
    raise SystemExit(f"[错误] {message}")


def main() -> None:
    if len(sys.argv) != 2:
        fail("用法：patch_compression.py /path/to/kcc-v11.0.1")

    root = Path(sys.argv[1]).expanduser().resolve()
    package = root / "kindlecomicconverter"
    source = Path(__file__).with_name("kindle_cn_compress.py")
    target = package / "kindle_cn_compress.py"

    if not package.is_dir():
        fail("目标不是完整 KCC 源码目录")
    if not source.is_file():
        fail("缺少 kindle_cn_compress.py")

    shutil.copy2(source, target)
    print("[完成] 已加入 Kindle 中文版无损压缩引擎")


if __name__ == "__main__":
    main()
