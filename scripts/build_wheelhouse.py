#!/usr/bin/env python3
"""Populate ./wheelhouse so a clean machine can install without a network.

Usage:  python scripts/build_wheelhouse.py
Then:   pip install --no-index --find-links wheelhouse -e .
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "wheelhouse"
PACKAGES = [
    "-r", str(ROOT / "requirements-lock.txt"),
    "setuptools", "wheel",
]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "download", "--dest", str(OUT),
           "--only-binary=:all:", *PACKAGES]
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
