#!/usr/bin/env python3
"""Persist a Muse verdict that came back inside an authenticated queue result.

This script is TRANSPORT, not authorship: it copies the verdict object exactly
as Muse submitted it, verifies the canonical sha256 Muse declared, validates
the schema, cross-checks gate/commit/run_id against the handoff, and writes the
bytes plus a provenance record. It refuses to alter any field.

    python scripts/muse_ingest.py --gate G1 --task-id <id> --result-file <json>

--result-file is the queue task row's `result` object ({"status": ...,
"evidence": {"verdict": {...}, "verdict_sha256": "..."}}), saved from the queue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True, choices=[f"G{i}" for i in range(1, 6)])
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--result-file", required=True)
    ap.add_argument("--claimed-by", required=True,
                    help="consumer identity the queue recorded for this task")
    args = ap.parse_args()

    result = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
    evidence = result.get("evidence") or {}
    if evidence.get("gate") != args.gate:
        print(f"error: result gate {evidence.get('gate')!r} != {args.gate}", file=sys.stderr)
        return 2
    verdict = evidence.get("verdict")
    if not isinstance(verdict, dict):
        print("error: result carries no verdict object; Muse did not produce one",
              file=sys.stderr)
        return 2

    declared = evidence.get("verdict_sha256")
    digest = hashlib.sha256(canonical(verdict).encode("utf-8")).hexdigest()
    if declared and declared != digest:
        print(f"error: declared sha {declared} != computed {digest}; refusing to persist",
              file=sys.stderr)
        return 2

    handoff_path = ROOT / "qa" / f"handoff-{args.gate}.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    for field in ("gate", "commit_sha", "run_id"):
        if verdict.get(field) != handoff.get(field):
            print(f"error: verdict {field} {verdict.get(field)!r} != handoff "
                  f"{handoff.get(field)!r}; the verdict is for a different run",
                  file=sys.stderr)
            return 2

    schema = json.loads((ROOT / "schemas" / "qa-verdict.schema.json")
                        .read_text(encoding="utf-8"))
    try:
        import jsonschema

        jsonschema.validate(verdict, schema)
    except Exception as exc:  # noqa: BLE001
        print(f"error: verdict fails schema: {exc}", file=sys.stderr)
        return 3

    identity = str(verdict.get("tester_identity", ""))
    if ("muse" not in identity.lower() or
            verdict.get("tester_origin") != "independent_muse"):
        print("error: verdict does not claim an independent Muse identity", file=sys.stderr)
        return 2
    if args.claimed_by and identity.lower() != args.claimed_by.lower():
        print(f"error: queue claimed_by={args.claimed_by} but verdict identity={identity}; "
              "refusing to conflate identities", file=sys.stderr)
        return 2

    out = ROOT / "qa" / f"muse-verdict-{args.gate}.json"
    out.write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    provenance = {
        "gate": args.gate,
        "task_id": args.task_id,
        "claimed_by": args.claimed_by,
        "persisted_at": datetime.now(timezone.utc).isoformat(),
        "transport": "household muse queue (authenticated producer claude token)",
        "queue_result_status": result.get("status"),
        "verdict_canonical_sha256": digest,
        "declared_sha256": declared,
        "verdict_status": verdict.get("status"),
        "note": ("Persisted byte-for-byte from Muse's queue result. The implementer did "
                 "not run, edit or re-author any field; schema and SHA checks above are "
                 "the only transformations (indentation only)."),
    }
    prov = ROOT / "qa" / f"muse-verdict-{args.gate}.provenance.json"
    prov.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"persisted {out.relative_to(ROOT)} (status {verdict.get('status')})")
    print(f"provenance {prov.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
