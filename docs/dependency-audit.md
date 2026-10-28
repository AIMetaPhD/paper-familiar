# P0 Dependency Audit

- Date: 2026-10-28
- Machine: Windows 11 Pro 26200, x64, Python 3.13.9 (venv), pip 25.3/26.2
- Evidence:
  - `docs/evidence/p0/pip-install-win11.log` — full Windows install log
  - `docs/evidence/p0/dependency-smoke.json` — imports, versions, public names
  - `docs/evidence/p0/pip-download-macos-arm64.log` — macOS arm64 resolution
  - `docs/evidence/p0/papercheck-scan.json` / `.err` — real CLI scan of the synthetic draft
- Method: install in an isolated venv, import, call a minimal API, run each CLI, and inspect
  `importlib.metadata` (entry points, requires, license expression). No version or API in the
  project plan was accepted without this test.

## 1. Result table

| Package | Version | License | Declared role | Test result | Decision |
|---|---|---|---|---|---|
| fastapi | 0.162.0 | MIT | runtime HTTP API | imports; app served on 127.0.0.1:8420 | **ADOPT** (pinned range) |
| uvicorn | 0.54.0 | BSD-3-Clause | runtime server | serves the app | **ADOPT** |
| pydantic | 2.14.1 | MIT | request models | imports via FastAPI | **ADOPT** |
| pylatexenc | 2.11 | MIT | supplementary LaTeX decode | `LatexWalker` parsed a sample into 3 nodes | **ADOPT as optional extra**; spans come from our scanner |
| bibtexparser | 2.1.0 | MIT | optional cross-check | parsed a sample entry `k/article` | **OPTIONAL**; runtime uses the position-aware internal parser |
| papercheck | 0.3.4 | MIT | reuse candidate | CLI works; `scan` produced JSON; `verify-quote` accepted a real quote (exit 0) and rejected a fabricated one (exit 1) | **OPTIONAL ADAPTER, default off** |
| academic-refchecker | 3.1.11 | MIT (package) | metadata lookup candidate | module `refchecker` imports (`ArxivReferenceChecker`, `checkers`, ...); CLI prints help | **EXCLUDE from default install** (see GPL below); optional, user-installed |
| pystylometry | 1.4.3 | MIT | style experiment candidate | imports (`analyze`, `tokenize`, `stylistic`, ...); pulls pandas/numpy | **EXPERIMENT ONLY**, not shipped |
| faststylometry | 1.0.15 | MIT | style experiment candidate | not installed (`Requires-Python <=3.13.3`) | **NOT EVALUATED**; no claim |
| fuzzywuzzy | 0.18.0 | **GPLv2** | transitive of academic-refchecker | installed as a transitive dependency | **GPL — must not be bundled** |
| python-Levenshtein | 0.27.5 | **GPL-2.0-or-later** | transitive of academic-refchecker | installed as a transitive dependency | **GPL — must not be bundled** |

## 2. papercheck: what actually exists

- Distribution: `papercheck 0.3.4`, MIT, `Requires-Python >=3.10`, dependencies `jsonschema`,
  `mcp>=1.0`, `pylatexenc`, `pyyaml`, `typer`.
- Console scripts: `papercheck` and `papercheck-mcp`.
- Python package `__init__.py` exposes **no public API** (`dir(papercheck)` is empty of public
  names). Any reuse must go through the CLI or private modules, so the stable interface is the
  CLI.
- Commands observed: `init`, `scan`, `segments`, `gate`, `render`, `verify-quote`, `prompts`,
  `report`, `compare`, `profile`, `packs`, `serve`, `mcp`.
- Real smoke test on the synthetic draft:
  - `papercheck scan .tmpdata/pcpaper --json` → exit 0, JSON listing 4 `.tex`, 1 `.bib`, main
    candidate `main.tex` with score 13.
  - `papercheck verify-quote sections/eval.tex "Tail latency improves by 7"` → `QUOTE FOUND`,
    exit 0.
  - Same command with `"…by 40"` → `QUOTE NOT FOUND`, exit 1.
- Decision: keep it as an **optional cross-check adapter** (`paperfamiliar.adapters.papercheck`),
  invoked only when the executable is present, never required by the core product. Do not copy
  its code or claim its checks as ours.

## 3. academic-refchecker: why it is not a default dependency

- Its own package is MIT, but it hard-depends on `fuzzywuzzy` (**GPLv2**) and
  `python-Levenshtein` (**GPL-2.0-or-later**), plus `pdfplumber`/`pdfminer.six`, `pybtex`,
  `cryptography`, `lxml`, `pandas`, `numpy`.
- It also ships AI-text detection features (local model, LLM judge, external detectors). Those
  are explicitly out of scope for this product and must never be invoked.
- Shipping it inside the default distribution would drag GPL code into a MIT-licensed product
  and imply capabilities we do not support.
- Decision: metadata verification in v0.1 uses a small, opt-in HTTP adapter against
  Crossref/OpenAlex (JSON only), disabled offline and never used to claim claim-support.
  `academic-refchecker` remains a documented, user-installed alternative with its own license
  notice. This is a deliberate deviation from "integrate academic-refchecker"; the reason is
  the license and scope, both established by inspection rather than assumption.

## 4. macOS Apple Silicon availability

`pip download --only-binary=:all: --platform macosx_11_0_arm64 --python-version 3.13 --implementation cp --abi cp313`
resolved and downloaded the full candidate set (72 wheels, exit 0), including native wheels:

- `cffi`, `cryptography`, `Levenshtein`, `numpy`, `pandas`, `pillow`, `pydantic_core`,
  `pyyaml`, `rapidfuzz`, `rpds_py` — `macosx_11_0_arm64`
- `lxml`, `charset_normalizer` — `macosx_10_13_universal2`
- 59 pure-Python wheels

This proves wheels exist for the pinned versions. It **does not** prove runtime behavior on
Apple Silicon, which remains `BLOCKED_PLATFORM_UNTESTED` until a real Mac runs the acceptance
script. No Rosetta fallback is assumed.

## 5. Windows availability

All packages installed from wheels or pure Python on Windows x64 with CPython 3.13; the install
log shows no source build, no compiler, and no admin elevation.

## 6. Residual risks

1. Python 3.13 is newer than papercheck's declared classifier range (3.10–3.12). The CLI worked,
   but this remains an unsupported combination for that project; the adapter treats failure as
   `unavailable`.
2. `pystylometry` pulls pandas/numpy and is not needed for the shipped transparent features;
   it is excluded from runtime dependencies to keep the offline wheelhouse small.
3. Optional integrations must be installed by the user with their own license review; the
   project's MIT license does not cover them.
4. A macOS runtime test is mandatory before G1; wheel availability is not evidence of behavior.
