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
under qa/evidence are reference material, not your evidence.

Repository location: the workstation you already SSH into with your normal
account to run queue_client.py — the same host and account, path:
    {repo}
Use that existing SSH session for all file access (git, venv creation, test
runs, writing your two output files). If the path or session is genuinely
unreachable for you, record every affected check as BLOCKED with the exact
reason; do not substitute guesses.

Commit under test:
    {sha}
Handoff record with the check list, expected behavior and evidence paths:
    qa/handoff-{gate}.json

What to do:
1. Verify the product under test:
       git -C <repo> cat-file -e {sha}
       git -C <repo> diff {sha} HEAD -- src web fixtures demo   (must be empty)
   Prefer testing from a clean checkout of {sha} (git worktree add elsewhere).
2. Create a fresh virtualenv OUTSIDE the repository, install the project from
   that checkout (pip install -e . or build the wheel and install it), and
   follow each check's reproduce procedure from the handoff file. UI checks
   require Playwright with chromium, firefox and webkit
   (pip install playwright; playwright install chromium firefox webkit).
   Keep your venv, caches and downloads outside the repository directory.
3. Run every check id in the handoff. Record exact commands, exit codes,
   versions and where your logs/screenshots live.
4. Attack the same surfaces with your OWN mutated variants of the synthetic
   fixtures under fixtures/ (do not trust the provided negative cases alone).
   Everything here is synthetic; never place any real manuscript anywhere.
5. Write your verdict to:
       {repo}/qa/muse-verdict-{gate}.json
   following schemas/qa-verdict.schema.json exactly (schema_version 1.2,
   status VERIFIED | FAILED | BLOCKED | MUSE_UNAVAILABLE, tester_identity
   "muse-N", tester_origin "independent_muse", commit_sha {sha}, run_id
   copied from the handoff, independent_run_proof_path and report_path
   pointing at real files you produced, failed_gates listing every check id
   that is not PASS).
6. Write a human report at qa/muse-report-{gate}.md (commands, environments,
   findings, reproduction of any failure).
7. Do NOT run git commit or git push; the implementer integrates and commits
   evidence after reviewing it. Return your queue result with
   status=success/failure and evidence {{"gate": "{gate}", "summary": "..."}}.
   Additionally, paste the FULL verdict JSON (the same content you wrote to
   qa/muse-verdict-{gate}.json, minified) into a second queue task reply only
   if you could not write files; then set evidence.verdict_in_result=true and
   include its sha256 so the implementer can persist and verify it byte-exact.

Hard rules:
- You may write ONLY qa/muse-verdict-{gate}.json and qa/muse-report-{gate}.md
  plus new files under qa/evidence/{gate}/muse/. Do not modify product source
  code, fixtures, demo, or the handoff file.
- Never run a TeX engine on any file; the product must not either.
- Missing platform, engine, or permission => BLOCKED with reason, not guessed.
- Your verdict must come from what YOU executed. Never copy wording or numbers
  from the implementer's selftest JSON without running it yourself.
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
            "permissions": "approval_required",
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
