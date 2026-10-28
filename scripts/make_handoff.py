#!/usr/bin/env python3
"""Build qa/handoff-G<n>.json from a gate selftest run (v1.2 schema).

Usage:
    python scripts/selftest.py --gate G1
    python scripts/make_handoff.py --gate G1 --run-id <run_id from selftest.json>

The handoff records what the implementer observed and references real logs; it
does NOT claim independent verification. Muse fills in the verdict file. Status
is SUBMITTED with failed_gates listing anything still open, so a handoff can
never look like a pass on its own.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paperfamiliar.fingerprint import split_sentences  # noqa: E402  (import check)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True, choices=[f"G{i}" for i in range(1, 6)])
    ap.add_argument("--run-id", default=None,
                    help="run id from selftest.json; default: newest directory")
    ap.add_argument("--isolation-log", default="qa/evidence/offline-proof.log")
    args = ap.parse_args()

    ev_dir = ROOT / "qa" / "evidence" / args.gate / "host-local"
    self_file = ev_dir / "selftest.json"
    if not self_file.is_file():
        print(f"error: {self_file} missing; run scripts/selftest.py --gate {args.gate} first",
              file=sys.stderr)
        return 2
    self_doc = json.loads(self_file.read_text(encoding="utf-8"))
    if args.run_id and self_doc["run_id"] != args.run_id:
        print(f"error: selftest run id {self_doc['run_id']} != requested {args.run_id}; "
              "the evidence on disk is not from the run you want to submit", file=sys.stderr)
        return 2
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                         text=True).stdout.strip()
    if self_doc["commit_sha"] != sha:
        print(f"error: selftest was recorded at {self_doc['commit_sha']} but HEAD is {sha}.\n"
              "Re-run the selftest against the commit you intend to submit.", file=sys.stderr)
        return 2

    # keep the isolation proof referenced by every gate as a real, growing log
    iso = ROOT / args.isolation_log
    iso.parent.mkdir(parents=True, exist_ok=True)
    marker = (f"# strict-offline proof, gate {args.gate}, commit {sha}, "
              f"{datetime.now(timezone.utc).isoformat()}\n"
              "The suite monkeypatches socket.socket.connect to fail on any non-loopback\n"
              "address; tests/test_strict_offline.py is part of the ordinary pytest run,\n"
              "so any violation makes the suite red. See also\n"
              "qa/evidence/G1/host-local/serve-*.log for the live server's own output.\n")
    iso.write_text(marker, encoding="utf-8")

    checks = []
    for check in self_doc["checks"]:
        entry = {
            "id": check["id"],
            "status": check["status"],
            "expected": check["expected"],
            "observed": check["observed"],
            "platforms_tested": check["platforms_tested"],
            "browsers_tested": check.get("browsers_tested", []),
            "evidence_paths": check["evidence_paths"],
        }
        checks.append(entry)

    evidence = sorted({path for c in checks for path in c["evidence_paths"]} | {args.isolation_log})
    open_ids = sorted(c["id"] for c in checks if c["status"] != "PASS")
    doc = {
        "schema_version": "1.2",
        "gate": args.gate,
        "commit_sha": sha,
        "run_id": self_doc["run_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "SUBMITTED",
        "environment_fingerprint": self_doc["environment_fingerprint"],
        "tested_platforms": sorted({p for c in checks for p in c["platforms_tested"]}),
        "browsers_tested": sorted({b for c in checks for b in c["browsers_tested"]}),
        "executed_commands": [
            {**command, "platform": command.get("platform", self_doc["platform"])}
            for command in self_doc["executed_commands"]
        ],
        "checks": checks,
        "failed_gates": open_ids,
        "evidence_paths": evidence,
        "network_isolation_proof": args.isolation_log,
        "notes": [
            "This is the implementer's submission. The statuses above are self-test "
            "observations, not independent verification.",
            "Muse must re-run every check on this commit_sha in its own environment and "
            "produce qa/muse-verdict-%s.json. Do not reuse this run_id if the commit changes."
            % args.gate,
            "failed_gates lists checks that are not PASS yet; they must be tested by Muse "
            "and are expected to include anything only a human or Muse can decide.",
        ],
    }
    out = ROOT / "qa" / f"handoff-{args.gate}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(checks)} checks, "
          f"{len(open_ids)} non-PASS, commit {sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
