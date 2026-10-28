#!/usr/bin/env python3
"""SEC-PUBLISH / SEC-SECRET scan over the repository working tree.

Looks for credential-shaped strings, private manuscript-shaped files and
forbidden assets. Exit 0 = clean; 1 = findings (listed, never the matches
themselves in full). This complements — it does not replace — a human read of
the diff before any push.
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIR_NAMES = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
                  ".mypy_cache", ".ruff_cache", "dist", "build", "web", ".claude",
                  "wheelhouse", "ms-playwright", ".package"}


def _skip_part(part: str) -> bool:
    if part in SKIP_DIR_NAMES or part.endswith(".egg-info"):
        return True
    if part.startswith((".tmpdata", ".g1-data")):
        return True
    return False

PATTERNS = [
    ("openai-style key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("bearer literal", re.compile(r"[Bb]earer\s+[A-Za-z0-9._-]{32,}")),
    ("slack token", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
]
# producer tokens for the local QA queue are 32+ char hex/base64 near that word
QUEUE_HINT = re.compile(r"(?:producer_token|consumer_token)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}")

BINARY_HINTS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".zip"}
ALLOWED_ZIPS = {"fixtures/generated", "src/paperfamiliar/web/dist"}
FORBIDDEN_ASSETS = re.compile(r"(?:turnitin)", re.IGNORECASE)


def scan_text(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return [f"{path}: unreadable"]
    findings: list[str] = []
    if b"\0" in data[:4096]:
        return findings  # binary
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return findings
    if len(text) > 2_000_000:
        return [f"{path}: oversized file, review manually"]
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{path}:{line}: {name}")
    for match in QUEUE_HINT.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        findings.append(f"{path}:{line}: possible queue credential literal")
    if FORBIDDEN_ASSETS.search(text):
        # a mention in docs/tests is allowed; shipped brand assets are not
        lowered = str(path).lower()
        if "/web/dist/" in lowered.replace("\\", "/"):
            findings.append(f"{path}: turnitin reference inside built assets")
    return findings


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(_skip_part(part) for part in rel_parts):
            continue
        suffix = path.suffix.lower()
        if suffix in BINARY_HINTS:
            posix = "/".join(rel_parts)
            allowed = any(posix.startswith(allowed_dir) for allowed_dir in ALLOWED_ZIPS) or \
                posix.startswith("qa/evidence/") or "/web/dist/" in posix or posix.endswith(".png")
            if not allowed:
                findings.append(f"{path}: binary payload type {suffix} committed")
            continue
        if suffix in {".woff2", ".woff", ".ttf", ".otf", ".so", ".dll", ".dylib", ".exe"}:
            findings.append(f"{path}: unexpected binary artifact {suffix}")
            continue
        scanned += 1
        findings.extend(scan_text(path))

    # base64 blobs that decode to credential shapes (defense against split secrets)
    b64 = re.compile(r"[A-Za-z0-9+/]{48,}={0,2}")
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".py", ".md", ".txt"}:
            continue
        parts = path.relative_to(ROOT).parts
        if any(_skip_part(p) for p in parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in b64.finditer(text):
            try:
                decoded = base64.b64decode(match.group(0) + "==").decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                continue
            if any(pattern.search(decoded) for _n, pattern in PATTERNS):
                findings.append(f"{path}: base64-wrapped credential shape")

    print(f"scanned {scanned} text files under {ROOT}")
    if findings:
        print(f"FINDINGS ({len(findings)}):")
        for item in findings[:50]:
            print(f"  {item}")
        return 1
    print("clean: no credential shapes, no unexpected binaries, no shipped brand assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
