#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail CI if repository text contains likely private/local-only data."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
SKIP_DIRS = {".git", "upstream", "dist", "package", "__pycache__", ".venv", "venv"}
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg",
    ".sh", ".command", ".ps1", ".plist", ".xml", ".html", ".css", ".js",
}
SELF = Path(__file__).resolve()
_PERSONAL_OWNER = "amster" + "-" + "ilvil"

PATTERNS = [
    ("macOS 本机用户路径", re.compile(r"/Users/(?!runner(?:/|$))[^/\s'\"]+", re.I)),
    ("Windows 本机用户路径", re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\s'\"]+", re.I)),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub Token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("GitHub Fine-grained Token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Bearer Token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.I)),
    ("个人 GitHub 标识", re.compile(rf"\b{re.escape(_PERSONAL_OWNER)}\b", re.I)),
]

EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z][A-Z0-9-]*(?:\.[A-Z0-9-]+)*\.[A-Z]{2,})(?![\w.-])",
    re.I,
)
ALLOWED_EMAIL_DOMAINS = {"users.noreply.github.com"}


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == SELF:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"LICENSE", "Dockerfile"}:
            yield path


def main() -> int:
    findings: list[str] = []
    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(ROOT)
        lines = text.splitlines()
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                line_text = lines[line - 1] if 0 < line <= len(lines) else ""
                if label == "个人 GitHub 标识" and "grep -qi" in line_text and "PLIST" in line_text:
                    continue
                findings.append(f"{rel}:{line}: {label}: {match.group(0)[:120]}")
        for match in EMAIL_RE.finditer(text):
            email = match.group(1)
            domain = email.rsplit("@", 1)[-1].lower()
            if domain not in ALLOWED_EMAIL_DOMAINS:
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line}: 邮箱地址: {email}")

    if findings:
        print("PRIVACY SCAN: FAIL")
        for item in findings:
            print(" -", item)
        return 1

    print("PRIVACY SCAN: PASS — 未发现本机用户路径、个人邮箱、私钥、常见 Token 或个人 GitHub 标识。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
