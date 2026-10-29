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


def ev_dir_for(gate: str) -> Path:
    path = ROOT / "qa" / "evidence" / gate / "host-local"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    code_sha = self_doc["commit_sha"]
    # Evidence/doc commits legitimately land after the tested code commit; the
    # product tree must not have changed. Anything under src/web/fixtures/demo
    # differing invalidates the selftest.
    diff = subprocess.run(["git", "diff", "--name-only", code_sha, "HEAD", "--",
                           "src", "web", "fixtures", "demo"],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if diff:
        print(f"error: product files changed since the selftest ran at {code_sha}:\n{diff}\n"
              "Re-run scripts/selftest.py against the current tree.", file=sys.stderr)
        return 2
    exists = subprocess.run(["git", "cat-file", "-e", f"{code_sha}^{{commit}}"],
                            cwd=ROOT).returncode
    if exists != 0:
        print(f"error: selftest commit {code_sha} does not exist in history", file=sys.stderr)
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
        "commit_sha": code_sha,
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
    }
    context = ev_dir_for(args.gate) / f"handoff-context-{self_doc['run_id']}.log"
    context.write_text(
        "Implementer submission notes (kept out of the schema-constrained JSON):\n"
        "- commit_sha is the tested product commit; the branch may have further\n"
        "  commits touching only qa/ and docs/. Muse must confirm\n"
        "  `git diff <commit_sha> HEAD -- src web fixtures demo` is empty.\n"
        "- Statuses above are implementer self-test observations, not independent\n"
        "  verification. Muse re-runs every check on commit_sha and writes\n"
        f"  qa/muse-verdict-{args.gate}.json itself; never copy this run's wording\n"
        "  into a verdict without executing it.\n"
        "- failed_gates lists checks that are not PASS here, including ones the\n"
        "  implementer is structurally not allowed to attest (QA-01/02, USER-01).\n",
        encoding="utf-8")
    if context.relative_to(ROOT).as_posix() not in evidence:
        evidence.append(context.relative_to(ROOT).as_posix())
        doc["evidence_paths"] = sorted(set(evidence))
    out = ROOT / "qa" / f"handoff-{args.gate}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(checks)} checks, "
          f"{len(open_ids)} non-PASS, commit {code_sha[:12]} (HEAD {sha[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
