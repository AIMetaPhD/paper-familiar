"""Optional adapters for third-party tools.

Each adapter probes for the real executable and reports `unavailable` instead of
pretending. Nothing here is required by the core product.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_executable(name: str) -> str | None:
    """Look on PATH, then next to the running interpreter (the project venv)."""
    found = shutil.which(name)
    if found:
        return found
    bindir = Path(sys.executable).parent
    for candidate in (bindir / name, bindir / f"{name}.exe", bindir / f"{name}.cmd"):
        if candidate.is_file():
            return str(candidate)
    return None


def papercheck_status() -> dict:
    exe = _find_executable("papercheck")
    if not exe:
        return {"status": "unavailable", "detail": "papercheck is not on PATH"}
    try:
        proc = subprocess.run([exe, "--help"], capture_output=True, text=True,
                              timeout=20, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}
    return {"status": "available" if proc.returncode == 0 else "error",
            "executable": exe, "detail": f"exit {proc.returncode}"}


def papercheck_verify_quote(file: Path, quote: str, line: int | None = None,
                            timeout: float = 30.0) -> dict:
    """Cross-check a quote with papercheck's own verifier. Never authoritative."""
    exe = _find_executable("papercheck")
    if not exe:
        return {"status": "unavailable", "detail": "papercheck is not on PATH"}
    if not quote.strip():
        return {"status": "rejected", "detail": "empty quote"}
    args = [exe, "verify-quote", str(file), quote]
    if line is not None:
        args += ["--line-start", str(line)]
    env = {k: os.environ[k] for k in
           ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "LC_ALL")
           if k in os.environ}
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              shell=False, env=env, cwd=str(file.parent))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0 and "QUOTE FOUND" in output.upper():
        return {"status": "cross_check_confirmed", "exit_code": proc.returncode,
                "detail": "papercheck located the quote; this only confirms presence, not meaning."}
    if "QUOTE NOT FOUND" in output.upper() or proc.returncode != 0:
        return {"status": "cross_check_rejected", "exit_code": proc.returncode,
                "detail": output.strip()[:400]}
    return {"status": "unavailable", "detail": output.strip()[:400]}
