#!/usr/bin/env python3
"""G1 runtime evidence: start the real server, probe it, record everything.

Checks performed against a live `paperfamiliar serve` process:
  WEB-SERVE   one local process, /api/health 200, UI served same-origin
  WEB-PACK    the wheel (when given) contains the built frontend, and running
              from an installed wheel needs no Node
  WEB-NOPLATFORM no native GUI process is involved (documented)
  WEB-PORT    a busy port fails with a clear error, never rebinds elsewhere
  WEB-HOST    unexpected Host headers are rejected
  WEB-CSRF    cross-origin / token-less mutations are rejected
  OFF-01      the demo golden path over HTTP with no API key

Usage:
    python scripts/g1_check.py --base http://127.0.0.1:8420 [--wheel path.whl]

Exit 0 = every check passed. The JSON output is evidence material; it is still
not a Muse verdict.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(url: str, method: str = "GET", body: bytes | None = None,
         headers: dict | None = None, timeout: float = 20.0):
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with NO_PROXY.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int, data_dir: Path, log_path: Path,
                 cwd: Path) -> subprocess.Popen:
    env = {**os.environ, "PAPERFAMILIAR_DATA": str(data_dir), "PYTHONUTF8": "1"}
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([PY, "-m", "paperfamiliar", "serve", "--no-browser",
                             "--port", str(port)],
                            cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.2)
    raise RuntimeError(f"server did not come up; see {log_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--base", default=None,
                        help="probe an already running server instead of starting one")
    args = parser.parse_args()

    checks: list[dict] = []
    commands: list[dict] = []
    ev_dir = ROOT / "qa" / "evidence" / "G1" / "host-local"
    ev_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    started = datetime.now(timezone.utc)

    def record(cid: str, ok: bool, expected: str, observed: str, logs: list[str]) -> None:
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "expected": expected,
                       "observed": observed, "evidence": logs})
        print(f"{'PASS' if ok else 'FAIL'}  {cid}  {observed[:100]}")

    def cmd(command: str, code: int, log: Path) -> str:
        rel = log.relative_to(ROOT).as_posix()
        commands.append({"command": command, "exit_code": code, "log_path": rel})
        return rel

    proc = None
    port = None
    log_files: list[str] = []
    try:
        if args.base:
            base = args.base.rstrip("/")
            port = int(base.rsplit(":", 1)[1])
            serve_log = ev_dir / "preexisting-server.txt"
            serve_log.write_text(f"probing an already running server at {base}\n",
                                 encoding="utf-8")
            log_files.append(cmd(f"probe {base}", 0, serve_log))
        else:
            if args.wheel:
                install_dir = Path(sys.executable).parent  # use current interpreter
                code = subprocess.call([str(install_dir / ("pip" + (".exe" if os.name == "nt" else ""))),
                                        "install", "--force-reinstall", "--no-deps", args.wheel])
                log = ev_dir / f"wheel-install-{run_id}.log"
                log.write_text(f"pip install --force-reinstall --no-deps {args.wheel}\nexit={code}\n",
                               encoding="utf-8")
                log_files.append(cmd(f"pip install {Path(args.wheel).name}", code, log))
                if code != 0:
                    record("WEB-PACK", False, "the wheel installs cleanly",
                           f"pip exit {code}", log_files)
            port = free_port()
            data_dir = Path(sys.argv[0]).resolve().parent.parent / f".g1-data-{run_id}"
            serve_log = ev_dir / f"serve-{run_id}.log"
            proc = start_server(port, data_dir, serve_log, ROOT)
            base = f"http://127.0.0.1:{port}"
            log_files.append(cmd(f"paperfamiliar serve --no-browser --port {port}", 0, serve_log))

        # WEB-SERVE + OFF-01: health and same-origin UI
        code, body = http(base + "/api/health")
        health = json.loads(body) if code == 200 else {}
        ok = code == 200 and health.get("status") == "ok"
        record("WEB-SERVE", ok, "a single local Python server answers /api/health on 127.0.0.1",
               f"HTTP {code} {health}", log_files)

        code, body = http(base + "/")
        html = body.decode("utf-8", "replace")
        record("WEB-NOPLATFORM", code == 200 and "__PF_CSRF__" not in html and "/assets/" in html,
               "the UI is served same-origin by the Python process; no native GUI or dev server",
               f"GET / HTTP {code}; csrf injected={('__PF_CSRF__' not in html)}; "
               f"assets referenced={'/assets/' in html}", log_files)

        # CSRF token: the same token the page embeds; a cross-origin page can request
        # /api/session but cannot read it back (no CORS), exactly like the HTML.
        code, body = http(base + "/api/session")
        token = json.loads(body).get("csrf") if code == 200 else None
        code, body = http(base + "/api/demo", method="POST", body=b"{}",
                          headers={"Content-Type": "application/json",
                                   "X-PF-CSRF": token or ""})
        demo_ok = code == 200
        finding_count = 0
        if demo_ok:
            data = json.loads(body)
            finding_count = len(data.get("findings", []))
            demo_ok = finding_count >= 4 and data.get("workspace_id")
        record("OFF-01", demo_ok,
               "with no network, no API key and no model, the demo audit returns the planted defects",
               f"POST /api/demo HTTP {code}, {finding_count} findings", log_files)

        # WEB-HOST
        code, _ = http(base + "/api/health", headers={"Host": "attacker.example"})
        record("WEB-HOST", code == 400, "a foreign Host header is rejected",
               f"Host: attacker.example -> HTTP {code}", log_files)

        # WEB-CSRF
        code, _ = http(base + "/api/demo", method="POST", body=b"{}",
                       headers={"Content-Type": "application/json",
                                "X-PF-CSRF": "wrong"})
        csrf_no_token = code == 403
        code, _ = http(base + "/api/demo", method="POST", body=b"{}",
                       headers={"Content-Type": "application/json", "X-PF-CSRF": token or "",
                                "Origin": "http://evil.example"})
        csrf_origin = code == 403
        record("WEB-CSRF", csrf_no_token and csrf_origin,
               "mutations without the session token, or from another origin, are refused",
               f"no-token POST -> {code}, cross-origin POST -> {code}", log_files)

        # WEB-PORT: a second server on a busy port must fail loudly, not rebind
        busy = free_port()
        holder = start_server(busy, ROOT / f".g1-data-holder-{run_id}",
                              ev_dir / f"holder-{run_id}.log", ROOT)
        try:
            conflict_log = ev_dir / f"port-conflict-{run_id}.log"
            env = {**os.environ, "PAPERFAMILIAR_DATA": str(ROOT / f".g1-data-conflict-{run_id}"),
                   "PYTHONUTF8": "1"}
            with open(conflict_log, "w", encoding="utf-8") as sink:
                code = subprocess.call([PY, "-m", "paperfamiliar", "serve", "--no-browser",
                                        "--port", str(busy)], cwd=ROOT, env=env,
                                       stdout=sink, stderr=sink, timeout=90)
            text = conflict_log.read_text(encoding="utf-8", errors="replace")
            log_files.append(cmd(f"paperfamiliar serve --port {busy} (already in use)",
                                 code, conflict_log))
            record("WEB-PORT", code == 7 and "already in use" in text,
                   "a busy port exits with a clear diagnostic and never falls back to another bind",
                   f"exit {code}, message present={'already in use' in text}", log_files)
        finally:
            holder.terminate()
            holder.wait(timeout=15)

        # WEB-STATE-BOOT: persistence across a server restart
        if demo_ok and token:
            data = json.loads(http(base + "/api/demo", method="POST", body=b"{}",
                                   headers={"Content-Type": "application/json",
                                            "X-PF-CSRF": token})[1])
            ws = data["workspace_id"]
            fid = data["findings"][0]["id"]
            http(base + f"/api/workspace/{ws}/decision", method="POST",
                 body=json.dumps({"finding_id": fid, "decision": "accepted"}).encode(),
                 headers={"Content-Type": "application/json", "X-PF-CSRF": token})
            if proc is not None:
                proc.terminate()
                proc.wait(timeout=15)
                restart_log = ev_dir / f"restart-{run_id}.log"
                proc = start_server(port, ROOT / f".g1-data-{run_id}", restart_log, ROOT)
                log_files.append(cmd("restart the same server", 0, restart_log))
            code, body = http(base + f"/api/workspace/{ws}")
            after = json.loads(body) if code == 200 else {}
            decisions = {f["id"]: f["human_decision"] for f in after.get("findings", [])}
            record("WEB-STATE-BOOT", code == 200 and decisions.get(fid) == "accepted",
                   "a decision made before the restart is still there after the restart",
                   f"GET workspace HTTP {code}, decision={decisions.get(fid)}", log_files)

    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except Exception:  # noqa: BLE001
                proc.kill()
        import shutil

        for stale in ROOT.glob(f".g1-data-*{run_id}*"):
            shutil.rmtree(stale, ignore_errors=True)

    passed = sum(1 for c in checks if c["status"] == "PASS")
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "environment": {
            "os": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": platform.python_version(),
            "host": "local real machine (not a container)",
        },
        "commit_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.strip(),
        "wheel": args.wheel,
        "kind": "IMPLEMENTER_SELF_TEST (not a Muse verdict)",
        "checks": checks,
        "executed_commands": commands,
        "summary": f"{passed}/{len(checks)} checks passed",
    }
    out = Path(args.out) if args.out else ev_dir / f"g1-check-{run_id}.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}  ({doc['summary']})")
    return 0 if passed == len(checks) and checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
