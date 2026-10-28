#!/usr/bin/env python3
"""CI helper: boot the installed wheel's server and prove the golden path API.

Runs with the .testenv interpreter in CI (or any environment on this machine):
    python scripts/ci_smoke.py
Starts `paperfamiliar serve` on a free loopback port with an isolated data dir,
waits for /api/health, loads the demo, makes one decision, exports, checks the
source hash, then shuts the server down. Writes a log under qa/ci-smoke/.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "qa" / "ci-smoke"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(url: str, method: str = "GET", body: bytes | None = None,
         headers: dict | None = None, timeout: float = 30.0):
    request = urllib.request.Request(url, data=body, method=method,
                                     headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return response.status, response.read()


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logfile = LOG_DIR / f"smoke-{stamp}.log"
    lines: list[str] = [f"python: {sys.version}", f"platform: {sys.platform}", ""]

    def log(message: str) -> None:
        print(message, flush=True)
        lines.append(message)

    port = free_port()
    data_dir = Path(tempfile.mkdtemp(prefix="paperfamiliar-ci-"))
    env = {**os.environ, "PAPERFAMILIAR_DATA": str(data_dir), "PYTHONUTF8": "1"}
    base = f"http://127.0.0.1:{port}"
    server_log = open(logfile.with_suffix(".server.log"), "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "paperfamiliar", "serve",
                             "--no-browser", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=server_log,
                            stderr=subprocess.STDOUT)
    failed = False
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                status, _ = http(base + "/api/health", timeout=2)
                if status == 200:
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
                continue
            time.sleep(0.5)
        else:
            raise RuntimeError("server never became healthy")

        status, body = http(base + "/api/health")
        health = json.loads(body)
        log(f"health: {health}")
        assert health["status"] == "ok"

        status, body = http(base + "/api/session")
        token = json.loads(body)["csrf"]
        headers = {"Content-Type": "application/json", "X-PF-CSRF": token}

        status, body = http(base + "/api/demo", method="POST", body=b"{}",
                            headers=headers)
        run = json.loads(body)
        ws = run["workspace_id"]
        log(f"demo: {len(run['findings'])} findings, baseline "
            f"{run['style']['baseline']['status']}, mode {run['mode']}")
        assert len(run["findings"]) >= 4
        assert run["style"]["baseline"]["status"] == "ok"

        finding = run["findings"][0]
        http(base + f"/api/workspace/{ws}/decision", method="POST",
             body=json.dumps({"finding_id": finding["id"],
                              "decision": "accepted"}).encode(), headers=headers)
        exported = json.loads(http(base + f"/api/workspace/{ws}/export",
                                  method="POST", body=b"{}", headers=headers)[1])
        log(f"export: {exported['files']}")
        assert "report.json" in exported["files"]

        source = json.loads(http(base + f"/api/workspace/{ws}/file?path="
                                 f"{run['main_path']}", headers=headers)[1])
        log(f"source unchanged after export: {source['unchanged']}")
        assert source["unchanged"]

        nav = json.loads(http(base + f"/api/workspace/{ws}/navigate", method="POST",
                              body=json.dumps({"query": "where is the optimization "
                                             "problem?"}).encode(), headers=headers)[1])
        log(f"navigator: {nav['status']} -> "
            f"{nav['matches'][0]['title'] if nav['status'] == 'found' else nav['reason']}")
        assert nav["status"] == "found"
    except Exception as exc:  # noqa: BLE001
        failed = True
        log(f"FAILED: {type(exc).__name__}: {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        server_log.close()
        shutil.rmtree(data_dir, ignore_errors=True)
        logfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"log: {logfile}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
