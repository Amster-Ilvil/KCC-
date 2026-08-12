#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/workflows/release-v15-smart-compression.yml')
text = path.read_text(encoding='utf-8')
old = '          git config user.email github-actions@github.com\n'
new = '          git config user.email "github-actions$(printf \'\\100\')users.noreply.github.com"\n'
count = text.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one release identity line, got {count}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('release workflow no longer contains a literal email address')
