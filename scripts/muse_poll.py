#!/usr/bin/env python3
"""Poll Muse queue tasks for the dispatched gates and validate verdicts.

Read-only against the queue (GET only). For each qa/muse-dispatch-G*.json it
tracks the task state; when a task finishes it fetches the Muse result and
checks whether the promised verdict/report files appeared in qa/ and validate
against schemas/qa-verdict.schema.json.

    python scripts/muse_poll.py            # loop until all settle or timeout
    python scripts/muse_poll.py --once     # single pass
Exit codes: 0 all tasks returned AND all verdict files valid; 1 some returned
result but evidence missing/invalid; 2 still waiting (timeout).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = Path(r"F:\Applications\Documents\Workspace\projects\muse-queue")
CLIENT = "queue_client.py"
ENV = {**os.environ, "MSYS_NO_PATHCONV": "1", "PYTHONUTF8": "1"}


def queue_get(path: str, timeout: int = 200) -> dict | None:
    cmd = [sys.executable, CLIENT, "--role", "producer", "--producer", "claude",
           "--method", "GET", "--path", path]
    try:
        proc = subprocess.run(cmd, capture_output=True, cwd=QUEUE, env=ENV,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    text = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not text.startswith("{"):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def queue_results() -> dict[str, dict]:
    """One /tasks listing (slow on a single-threaded queue) -> id -> result."""
    listing = queue_get("/tasks", timeout=360)
    out = {}
    for row in (listing or {}).get("tasks", []):
        task = row.get("task") or {}
        if row.get("state") == "finished" and row.get("result") is not None:
            out[task.get("id")] = {"result": row["result"],
                                   "claimed_by": row.get("claimed_by")}
    return out


def ingest_if_present(gate: str, task_id: str, claimed_by: str,
                      result: dict) -> tuple[str, str]:
    """Persist verdict-in-result via muse_ingest; never invent one."""
    evidence = (result or {}).get("evidence") or {}
    if not isinstance(evidence.get("verdict"), dict):
        return "missing", "no verdict object in the queue result"
    tmp = ROOT / "qa" / "evidence" / f"muse-result-{gate}-{task_id[:8]}.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, "scripts/muse_ingest.py", "--gate", gate,
                           "--task-id", task_id, "--result-file", str(tmp),
                           "--claimed-by", claimed_by or ""],
                          cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, "PYTHONUTF8": "1"})
    if proc.returncode == 0:
        return "persisted", proc.stdout.strip().splitlines()[0]
    return "invalid", (proc.stderr or proc.stdout).strip()[:300]


def validate_verdict(gate: str) -> tuple[str, str]:
    vp = ROOT / "qa" / f"muse-verdict-{gate}.json"
    rp = ROOT / "qa" / f"muse-report-{gate}.md"
    if not vp.is_file():
        return "missing", f"{vp.name} not created by Muse yet"
    try:
        doc = json.loads(vp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "invalid", f"JSON error: {exc}"
    schema = json.loads((ROOT / "schemas" / "qa-verdict.schema.json").read_text(
        encoding="utf-8"))
    try:
        import jsonschema

        jsonschema.validate(doc, schema)
    except Exception as exc:  # noqa: BLE001
        return "invalid", f"schema error: {exc}"
    handoff = ROOT / "qa" / f"handoff-{gate}.json"
    if handoff.is_file():
        h = json.loads(handoff.read_text(encoding="utf-8"))
        if doc.get("commit_sha") != h.get("commit_sha"):
            return "invalid", ("commit mismatch: verdict "
                               f"{doc.get('commit_sha')[:12]} != handoff "
                               f"{h.get('commit_sha')[:12]}")
        if doc.get("run_id") != h.get("run_id"):
            return "invalid", "run_id mismatch with handoff"
    status = doc.get("status")
    extra = "" if rp.is_file() else " (report md missing)"
    return "valid", f"status={status}{extra}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=240)
    ap.add_argument("--hours", type=float, default=10)
    args = ap.parse_args()

    dispatches = {}
    for path in sorted(ROOT.glob("qa/muse-dispatch-G*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for task in doc["tasks"]:
            dispatches[task["task_id"]] = {
                "gate": doc["gate"], "recipient": task["recipient"],
                "done": False, "note": "",
            }
    if not dispatches:
        print("nothing dispatched yet")
        return 2

    deadline = time.time() + args.hours * 3600
    log = ROOT / "qa" / "muse-poll.log"

    def line(message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{stamp}] {message}", flush=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")

    while True:
        pending = {tid: info for tid, info in dispatches.items() if not info["done"]}
        if not pending:
            break
        for tid, info in list(pending.items()):
            status = queue_get(f"/tasks/{tid}/status")
            if status is None:
                line(f"{info['gate']}/{info['recipient']} task {tid[:8]}: no response "
                     "(queue busy), will retry")
                continue
            state = status.get("state")
            if state != "finished":
                line(f"{info['gate']}/{info['recipient']} task {tid[:8]}: {state}")
                continue
            results = queue_results()
            fetched = results.get(tid)
            if fetched is not None:
                ingested = ingest_if_present(info["gate"], tid,
                                             fetched.get("claimed_by") or "", fetched["result"])
                if ingested[0] == "persisted":
                    line(f"{info['gate']}/{info['recipient']}: verdict persisted "
                         f"from queue result ({ingested[1]})")
                elif ingested[0] == "invalid":
                    line(f"{info['gate']}/{info['recipient']}: verdict rejected: "
                         f"{ingested[1]}")
                else:
                    line(f"{info['gate']}/{info['recipient']}: {ingested[1]}")
            verdict = validate_verdict(info["gate"])
            info["done"] = True
            info["note"] = f"task finished ({status.get('result_status')}); " \
                           f"verdict {verdict[0]}: {verdict[1]}"
            line(f"{info['gate']}/{info['recipient']}: {info['note']}")
        if args.once:
            break
        if all(info["done"] for info in dispatches.values()):
            break
        if time.time() > deadline:
            line("poll deadline reached; unfinished tasks remain pending")
            break
        time.sleep(args.interval)

    valid = sum(1 for i in dispatches.values() if "verdict valid" in i["note"])
    returned = sum(1 for i in dispatches.values() if i["done"])
    line(f"summary: {returned}/{len(dispatches)} tasks returned, {valid} verdicts valid")
    if all(i["done"] for i in dispatches.values()) and valid == len(dispatches):
        return 0
    if returned and returned == len(dispatches):
        return 1
    return 2 if not args.once else 1


if __name__ == "__main__":
    raise SystemExit(main())
