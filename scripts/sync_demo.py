#!/usr/bin/env python3
"""Copy the canonical synthetic fixtures into the bundled demo directory.

The fixtures are the source of truth. The bundled copy makes the installed
package self-contained. `tests/test_demo_parity.py` fails if the two drift.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "fixtures" / "corpus"
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"
DEMO = ROOT / "demo"

HISTORY = [
    "a1_distributed_inference_2022.tex",
    "a2_kv_cache_2023.tex",
    "a3_edge_scheduling_2024.tex",
    "a4_latency_modeling_2025.tex",
]


def main() -> int:
    (DEMO / "history").mkdir(parents=True, exist_ok=True)
    if (DEMO / "draft").exists():
        shutil.rmtree(DEMO / "draft")
    shutil.copytree(DRAFT, DEMO / "draft")
    for name in HISTORY:
        shutil.copy2(CORPUS / name, DEMO / "history" / name)
    print(f"demo synced: {DEMO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
