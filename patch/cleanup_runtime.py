#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small post-patch cleanup for runtime-only warnings."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: cleanup_runtime.py /path/to/kcc")
    root = Path(sys.argv[1]).resolve()
    gui = root / "kindlecomicconverter" / "KCC_gui.py"
    text = gui.read_text(encoding="utf-8")

    old = "        self.tray.show()\n"
    new = (
        "        # Only show the tray icon when the current Qt platform actually supports it.\n"
        "        # This avoids warnings in headless/offscreen sessions while preserving normal macOS behavior.\n"
        "        if self.tray.isSystemTrayAvailable() and not self.tray.icon().isNull():\n"
        "            self.tray.show()\n"
    )
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"tray cleanup target count mismatch: {count}")
    gui.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("[完成] runtime cleanup")


if __name__ == "__main__":
    main()
