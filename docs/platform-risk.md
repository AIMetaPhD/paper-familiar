# P0 Platform & Compatibility Risk (v1.2 Local-first Web App)

- Date: 2026-10-28 (rewritten for the v1.2 architecture; supersedes the v1.1
  two-native-client framing)
- Execution host for all evidence in this repo: **Windows 11 x64 (real machine)**
- Browser engines executed for E2E: **Chromium, Firefox, WebKit** via Playwright
  on that host.

## 1. What v1.2 requires vs what was measured

| Contract | Requirement | Actual status |
|---|---|---|
| One local Python service + one browser UI | real host, full golden path | PASS on Windows 11 x64 (self-test; Muse pending) |
| Three browser engines | Playwright chromium/firefox/webkit | PASS on Windows 11 x64; Safari-on-macOS itself untested |
| macOS / Linux hosts | honest README matrix, CI smoke recommended | **UNTESTED_PLATFORM** — no host has run the suite |
| Wheel contains prebuilt frontend + demo | zip inspection | PASS (38 entries incl. `web/dist` and demo) |
| No Node/Electron/Docker at runtime | import & process inspection | PASS |
| Strict offline | socket-level guard test + runtime probes | PASS on this host |

macOS note: the user's Apple Silicon machine exists on the network but this
session has no SSH credential; per v1.2 that is a README honesty item
(`UNTESTED_PLATFORM`), not a release blocker. If you want real-Mac evidence
later, run the repo's `tests/e2e` there or grant access.

## 2. Python toolchain (measured on this host)

| Component | Observed | Decision |
|---|---|---|
| Python | 3.13.9 (Anaconda base) | `pyproject` pins `>=3.11,<3.14`; venv per project |
| uv | absent | Not required; README documents the venv+pip path; `uv run` mentioned as alternative only |
| Node.js | 24.12.0 / npm 11.6.2 | build-time only, frontend rebuild |
| Git | 2.55 | local repository only; no remote operations |
| TeX Live 2025 present | — | deliberately unused: v0.1 never compiles user source |
| Ollama 0.32.14 installed, service stopped | probe → `unavailable` | exactly the fallback path the UI must show |
| Port 8420 | free at check time | busy-port precheck + clear exit code 7 (tested) |
| Windows LongPaths | disabled | product paths are kept short; deep archives are rejected by policy anyway |

## 3. Dependency / packaging risks

1. Optional integrations (`papercheck`, `academic-refchecker`) are not runtime
   dependencies; refchecker's transitive GPL packages are excluded (see
   dependency-audit §3). Wheel install must therefore work with the five runtime
   deps only. **Verified**: wheel installs and serves with `--no-deps` over a
   base env that already has FastAPI/uvicorn/pydantic.
2. macOS/Linux wheels: proven *downloadable* for the full optional set
   (`pip download --platform macosx_11_0_arm64` exit 0, native arm64 wheels for
   cffi/cryptography/numpy/pandas/pydantic-core/…); runtime behavior on those
   OS is UNTESTED, as stated.
3. FastAPI 0.162 pulls Starlette 1.10; behavior verified locally for
   middleware, UploadFile and StaticFiles. A downgrade pin is possible if a
   future minor breaks the loopback guard pattern — guard is plain middleware
   over `request.headers`, which is stable API.
4. Playwright webkit on Windows ships its own browser binaries; user machines do
   NOT need Safari/WebKit installed — E2E is a developer/CI concern only.

## 4. Runtime behavior risks

- Single-threaded SQLite access from uvicorn workers: safe today because we run
  one process with `check_same_thread=False` + WAL + short transactions. A
  `--workers` flag would need per-process connections; deliberately not offered.
- Loopback-only Host allowlist blocks DNS-rebinding (tested) but means users
  behind unusual local proxies get a clear 400, not a silent bypass.
- Browser download of exports uses the same session token page context; no
  credentials involved.
- Windows Defender/SmartScreen may flag a first-run python.exe listening on a
  port: documented; we do not tamper with either.

## 5. Decisions

1. All acceptance evidence in this repo is stamped with the *actual* host:
   `windows11_x64` + which engine ran. Nothing is pre-filled for other hosts.
2. CI OS matrix smoke (install wheel → `paperfamiliar serve` → `/api/health`)
   is the recommended future expansion; it is not present yet and the README
   says so.
3. Python 3.11–3.13 supported; 3.13.9 is the version actually exercised.
