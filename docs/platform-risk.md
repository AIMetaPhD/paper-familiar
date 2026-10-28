# P0 Platform Risk Assessment

- Date: 2026-10-28
- Scope: Windows 11 x64 (primary, present) and macOS Apple Silicon arm64 (primary, **not reachable from this session**)
- Evidence: commands below were run in this session; machine fingerprint recorded in `qa/muse-transport.json` and `docs/dependency-audit.md`.

## 1. Machines actually available

| Platform | Present | Fingerprint | Consequence |
|---|---|---|---|
| Windows 11 x64 | yes | Windows 11 Pro 10.0.26200 build 26200, Intel i5-12600KF (10C/16T), 31.8 GB RAM, 64-bit | all Windows evidence can be produced locally |
| macOS Apple Silicon arm64 | no | `ssh 100.113.5.29` failed with `Permission denied (publickey,password,keyboard-interactive)`; no SSH host alias or key configured | macOS G1/G5 evidence is `BLOCKED_PLATFORM_UNTESTED` until the user runs the acceptance script on the Mac or grants key-based SSH |

The MacBook is online in Tailscale (`macbook 100.113.5.29`), but this session has no credential. This is a hard blocker for macOS acceptance, not a reason to lower the gate.

## 2. Windows 11 toolchain

| Component | Observed | Risk / decision |
|---|---|---|
| Python | 3.13.9 (Anaconda, `F:\Applications\Anaconda\python.exe`), pip 25.3 | Locked as build interpreter. `papercheck 0.3.4` only classifies 3.10–3.12, so its adapter is capability-probed and optional. Final user install should use a dedicated 3.12/3.13 venv, not Anaconda base. |
| venv | created at `.venv` (Python 3.13.9) | Works; no admin rights needed |
| uv | not installed | Not required; launcher uses `python -m venv`. If added later, it must not become mandatory. |
| Node.js | 24.12.0, npm 11.6.2 | Development-only. Built assets are committed; end users do not need Node. |
| Git | 2.55.0.windows.4 | available; repository is local only |
| GitHub CLI | 2.89.0 | authenticated state is not inspected or printed; no push in P0 |
| TeX | TeX Live 2025 on PATH | **Not used**: v0.1 never compiles user source |
| Ollama | 0.32.14 installed, service not running | Local model path is optional; absence must degrade cleanly |
| Browsers | Chrome and Edge installed | Both need a smoke test; Safari is macOS-only |
| Port 8420 | free at time of check | Launcher must detect conflicts and exit non-zero with a clear message |
| Long paths | `LongPathsEnabled = 0` | Keep generated paths short; do not depend on >260 char paths. Test spaces and Unicode, not extreme depth. |
| Display | not yet measured; 125%/150% DPI must be tested in G1 | UI must use scalable layout, no fixed pixel assumptions |

## 3. macOS Apple Silicon risks (unverified here)

- Native `arm64` wheels are required for any compiled dependency (`lxml`, `cryptography`, `python-Levenshtein`). The wheelhouse audit (`pip download --platform macosx_11_0_arm64`) records whether each pinned version publishes one.
- Gatekeeper may quarantine downloaded launchers; the supported path is a checked-out repository plus `python3 -m venv`, not a signed .app in v0.1.
- Rosetta must not be used. The acceptance script must assert `uname -m == arm64` and `platform.machine() == arm64`.
- Unicode normalization (NFC/NFD) differs from Windows; paths with Chinese characters must be tested on the Mac.
- Safari is the second browser and must be smoke-tested; Chromium-only testing is insufficient.

## 4. Offline install risk

- First install requires network to populate the wheel cache. Acceptance runs must then work with `pip install --no-index --find-links wheelhouse`.
- `academic-refchecker` pulls `pdfminer.six`, `pdfplumber`, `cryptography`, `pybtex`, `lxml`, `python-Levenshtein`. That is a large surface for a metadata-only feature. It is optional at runtime; failure degrades to `unavailable`.
- A clean-machine README must state the real prerequisite (Python 3.11+), because v0.1 does not ship a signed standalone installer.

## 5. Decisions

1. The Windows machine is the only source of native evidence in this session. macOS remains blocked until the user provides access or runs the script.
2. Python is locked per-venv, not global. `pyproject.toml` requires `>=3.11,<3.14`.
3. The launcher scripts must work without admin rights, without Node, without Docker, and with spaces/Chinese characters in the project path.
4. Cross-platform binary availability is proven by `pip download --platform ... --only-binary=:all:` evidence, not by assumption.
