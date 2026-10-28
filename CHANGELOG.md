# Changelog

## 0.1.0 — unreleased technical candidate (2026-10-28/29)

### Architecture

- v1.2 Local-first Web App: one local FastAPI process serves the built React UI
  and the API at `http://127.0.0.1:8420`; native Windows/macOS clients,
  Electron/Tauri and per-OS launchers were dropped (ADR-0007).

### Added

- Position-aware multi-file LaTeX scanner; half-open spans with 1-based Unicode
  code-point columns; CRLF/LF; comment/verbatim/math-aware.
- V0 deterministic rules: undefined citation keys, undefined references,
  duplicate labels, malformed/incomplete BibTeX entries, includes escaping the
  workspace; each finding carries its rule scope.
- V2 notation candidate clearly labelled heuristic with stated limits.
- Hard quote gate before any finding enters the ledger; rejected findings are
  logged, never shown as issues.
- Safe ZIP and folder ingestion from the browser (multipart upload) or a local
  path, with fail-closed limits (zip-slip, absolute paths, symlinks, bombs,
  depth, counts, sizes).
- SQLite persistence of workspaces/runs/decisions/labels under a visible data
  directory; delete clears derived data; path-imported originals are never
  removed; v1.1 databases migrate aside without deletion.
- Deterministic author style profile with honest abstention (≥3 papers /
  ≥60 sentences), per-section contribution labels, drift cards with sample
  size and confidence; no similarity scores anywhere.
- Model-free cognitive skeleton (section tree, environment sequence, label
  topology, symbol index) and the deterministic familiarity navigator with
  explicit `not_found`.
- Three-pane React/Vite workbench: evidence ledger, style panel with reference
  paper management, structure panel, browser upload + folder upload, resume
  list, data lifecycle modal, export modal with post-export hash verification.
- Providers: local Ollama/OpenAI-compatible probe, per-payload cloud consent
  (preview + confirm + single-use + hash-pinned + TTL), secret redaction.
- Opt-in DOI metadata lookup (`source_corroborated`, never claim-supported);
  loopback-only outbound policy for local probes.
- CLI: `paperfamiliar serve|audit|providers|metadata|ask`; busy port exits 7
  with guidance; `--host` refuses non-loopback.
- Optional `papercheck` cross-check adapter (capability-probed, never assumed).
- Evidence tooling: `g1_check.py` runtime probes, per-gate `selftest.py`,
  `make_handoff.py`, `secret_scan.py`, `dependency_smoke.py`,
  `check_gates.py` (v1.2), v1.2 matrix/schemas.
- Synthetic corpus and adversarial fixtures (ADV-01…ADV-06, archive attacks,
  fabricated findings, prompt injection, control paper).

### Tests (self-tested on Windows 11 x64)

- 55 unit/API/offline tests; 33 Playwright E2E across Chromium, Firefox and
  WebKit; visual baselines per engine; strict-offline socket guard suite.

### Not claimed

- Muse independent verdicts, the author's blind sign-off, macOS/Linux host
  runs, real cloud API behavior. Nothing pushed; no remote created.
