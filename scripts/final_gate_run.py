#!/usr/bin/env python3
"""One-command final evidence pass: freeze a SHA, run G1-G5 selftests, rebuild
all five handoffs on that SHA, run the contract checker, and write
docs/G1-G5_SUMMARY.md — all without touching the product tree.

Refuses to start when the working tree has product changes (src/web/fixtures/
demo), because a gate pass must bind to what is actually committed.

    python scripts/final_gate_run.py [--skip-e2e]

Exit codes: 0 all selftests done (checker verdict is reported, not enforced —
exit 0 requires Muse verdicts + user signature); 2 precondition failure.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
GATES = [f"G{i}" for i in range(1, 6)]
PRODUCT_PATHS = ["src", "web", "fixtures", "demo"]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-selftest", action="store_true",
                    help="only rebuild handoffs from existing evidence")
    args = ap.parse_args()

    dirty = git("status", "--porcelain", "--", *PRODUCT_PATHS)
    if dirty:
        print("refusing: product tree has uncommitted changes:\n" + dirty, file=sys.stderr)
        return 2
    sha = git("rev-parse", "HEAD")
    print(f"freezing at {sha}")

    summary = {"commit_sha": sha, "started_at": datetime.now(timezone.utc).isoformat(),
               "gates": {}}
    failed_gates = []
    for gate in GATES:
        if not args.skip_selftest:
            proc = subprocess.run([PY, "scripts/selftest.py", "--gate", gate],
                                  cwd=ROOT, capture_output=True, text=True,
                                  env={**__import__("os").environ, "PYTHONUTF8": "1"})
            tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
            print(f"{gate}: exit {proc.returncode} — {tail[0]}")
            if proc.returncode not in (0, 1):
                failed_gates.append(gate)
        handoff = subprocess.run([PY, "scripts/make_handoff.py", "--gate", gate],
                                 cwd=ROOT, capture_output=True, text=True)
        print("  " + (handoff.stdout.strip().splitlines() or [""])[-1])
        if handoff.returncode != 0:
            failed_gates.append(gate)
            continue
        doc = json.loads((ROOT / "qa" / f"handoff-{gate}.json").read_text(encoding="utf-8"))
        summary["gates"][gate] = {
            "run_id": doc["run_id"],
            "checks": {c["id"]: c["status"] for c in doc["checks"]},
            "failed_gates": doc["failed_gates"],
            "browsers": doc["browsers_tested"],
        }

    checker = subprocess.run([PY, "scripts/check_gates.py", "--root", "."],
                             cwd=ROOT, capture_output=True, text=True)
    print(f"check_gates exit {checker.returncode}: "
          f"{(checker.stderr or checker.stdout).strip().splitlines()[0]}")
    summary["check_gates_exit"] = checker.returncode
    summary["check_gates_message"] = (checker.stderr or checker.stdout).strip().splitlines()[:3]
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()

    out = ROOT / "qa" / "final-gate-run.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0 if not failed_gates else 2


if __name__ == "__main__":
    raise SystemExit(main())
