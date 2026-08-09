#!/usr/bin/env python3
from pathlib import Path

path = Path('patch/kindle_cn_compress.py')
text = path.read_text(encoding='utf-8')
old = '''def _oxipng_plans(path: Path, strategy: str) -> list[tuple[str, bool]]:
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
'''
new = '''def _oxipng_plans(path: Path, strategy: str) -> list[tuple[str, bool]]:
    if strategy == "standard":
        return [("4", False)]
    if strategy == "maximum":
        # Zopfli is deliberately reserved for the explicit maximum mode. It
        # can save the final few bytes, but scales poorly across hundreds of
        # manga pages and therefore does not belong in the default workflow.
        return [("4", False), ("6", False), ("max", True)]

    # Smart/balanced mode compares the two practical OxiPNG levels only.
    # -o6 is worthwhile mainly for non-trivial PNGs; tiny pages stay on -o4.
    size = path.stat().st_size
    plans: list[tuple[str, bool]] = [("4", False)]
    if size >= 192 * 1024:
        plans.append(("6", False))
    return plans
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one _oxipng_plans block, got {count}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('smart strategy: o4/o6; maximum strategy: o4/o6/max+zopfli')
