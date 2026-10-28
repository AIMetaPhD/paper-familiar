#!/usr/bin/env python3
"""Start the workbench for the browser preview tool, from any working directory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

from paperfamiliar.cli import main  # noqa: E402

raise SystemExit(main(["serve", "--no-browser"]))
