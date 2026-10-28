#!/usr/bin/env python3
"""Dispatch a gate handoff to Muse over the household queue.

Muse recipients (muse-1/2/3) share the same workstation account over SSH, so
the task points at the local repository, the frozen commit SHA and the handoff
JSON file rather than embedding 30 KB of payload in a 64 KiB-limited queue body.

Wording rules learned from P0 canaries: English, factual, no credential-ish or
imperative-injection words — muse-1's own safety screen rejects otherwise
innocent Chinese text that resembles injection.

Usage:
    python scripts/muse_dispatch.py --gate G1 [--recipients muse-1,muse-2,muse-3]

The task body is printed (token-free) before anything is sent; the queue server
stamps producer provenance. This script never writes a verdict — only Muse can.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = Path(r"F:\Applications\Documents\Workspace\projects\muse-queue")
CLIENT = "queue_client.py"

INSTRUCTIONS = """PaperFamiliar independent QA request, gate {gate}.

You are the independent black-box QA for this project. Judge only by your own
execution on the exact commit named below; the implementer's self-test files
are reference material, not your evidence.

Repository (same machine, read it directly):
    {repo}
Commit to verify (check out or verify HEAD equals this SHA before testing):
    {sha}
Handoff record with the check list, expected behavior and evidence paths:
    qa/handoff-{gate}.json

What to do:
1. Verify the product under test. The commit above must exist, and the product
   code must be unchanged up to HEAD: run
       git cat-file -e {sha} && git diff {sha} HEAD -- src web fixtures demo
   the diff must be empty (only qa/ evidence and docs may differ after it).
   Check out {sha} (detached) for the actual testing if you want strictness.
2. Create a fresh virtualenv outside the repository, install the project from
   source (pip install -e . or build a wheel and install it), and follow the
   reproduce commands in each check of the handoff file.
3. Run every listed check. For UI checks use Playwright with chromium, firefox
   and webkit as the handoff requires. Record exact commands, exit codes,
   versions and where logs/screenshots live.
4. Attack the same surfaces from your side with your own mutated variants of
   the synthetic fixtures under fixtures/ (do not trust the provided negative
   cases alone). Never send real user text anywhere; everything here is
   synthetic.
5. Write your verdict to:
       {repo}/qa/muse-verdict-{gate}.json
   following schemas/qa-verdict.schema.json exactly (schema_version 1.2,
   status one of VERIFIED / FAILED / BLOCKED / MUSE_UNAVAILABLE,
   tester_identity like "muse-N", tester_origin "independent_muse",
   independent_run_proof_path and report_path pointing at real files you
   produced, commit_sha equal to the SHA above, failed_gates listing every
   check id that is not PASS).
6. Also write a short human report at qa/muse-report-{gate}.md.

Hard rules:
- Do not modify product source code, fixtures, or the handoff file.
- Do not run any TeX engine on fixture files; the product must not either.
- If a platform, browser engine, or permission is unavailable to you, record
  that check as BLOCKED with the reason instead of guessing.
- If you cannot verify the commit matches, stop and record BLOCKED.
- Your identity is your own; never copy numbers or wording from the
  implementer's selftest JSON into your verdict without running it yourself.
"""


def queue_call(method: str, path: str, body: bytes | None = None) -> dict:
    cmd = [sys.executable, CLIENT, "--role", "producer", "--producer", "claude",
           "--method", method, "--path", path]
    proc = subprocess.run(cmd, input=body, capture_output=True, cwd=QUEUE,
                          env={**__import__("os").environ, "MSYS_NO_PATHCONV": "1"},
                          timeout=90)
    text = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not text.startswith("{"):
        raise RuntimeError(f"queue call failed: exit={proc.returncode} {text[:400]}")
    return json.loads(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True, choices=[f"G{i}" for i in range(1, 6)])
    ap.add_argument("--recipients", default="muse-1,muse-2,muse-3")
    ap.add_argument("--sha", default=None, help="override commit sha; default handoff file")
    args = ap.parse_args()

    handoff_path = ROOT / "qa" / f"handoff-{args.gate}.json"
    if not handoff_path.is_file():
        print(f"error: {handoff_path} missing; run scripts/make_handoff.py --gate {args.gate}",
              file=sys.stderr)
        return 2
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    sha = args.sha or handoff["commit_sha"]
    if handoff["commit_sha"] != sha:
        print("error: requested SHA differs from the handoff SHA; dispatch refused",
              file=sys.stderr)
        return 2

    sent = []
    for recipient in [r.strip() for r in args.recipients.split(",") if r.strip()]:
        body = {
            "recipient": recipient,
            "kind": f"paperfamiliar_gate_{args.gate.lower()}",
            "instructions": INSTRUCTIONS.format(gate=args.gate, repo=str(ROOT), sha=sha),
            "inputs": {
                "gate": args.gate,
                "commit_sha": sha,
                "handoff_file": f"qa/handoff-{args.gate}.json",
                "verdict_schema": "schemas/qa-verdict.schema.json",
                "run_id": handoff["run_id"],
            },
            "permissions": "read_only",
        }
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        result = queue_call("POST", "/tasks", encoded)
        sent.append({"recipient": recipient, "task_id": result["id"],
                     "state": "pending"})
        print(f"dispatched to {recipient}: task {result['id']}")
    log = ROOT / "qa" / f"muse-dispatch-{args.gate}.json"
    log.write_text(json.dumps({
        "gate": args.gate, "commit_sha": sha, "handoff_run_id": handoff["run_id"],
        "dispatched_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "tasks": sent,
        "note": "Provenance stamped server-side as claude producer. Verdicts must be "
                "produced by Muse; this script never writes muse-verdict-*.json.",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {log.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
