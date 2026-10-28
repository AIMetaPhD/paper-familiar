# PaperFamiliar Architecture (v1.2 — Local-first Web App)

- Date: 2026-10-28, supersedes the v1.1 native-client sections.
- Authoritative sources: `00_MASTER_PROJECT_PLAN.md` and ADR-0007
  (`docs/adr/0007-local-web-app-v1.2.md`).

## 1. Shape of the system

```
Browser (Chromium / Firefox / WebKit)
   └── http://127.0.0.1:8420   (same origin; UI assets served by Python)
         ▲
         │ one process
FastAPI (uvicorn, loopback only)
 ├── api.py          routes, Host/Origin/CSRF guard, workspace lifecycle
 ├── ingest.py       browser uploads / local paths / demo → workspaces
 ├── service.py      analyze → gate → persist; style refresh; exports
 ├── storage.py      SQLite + data-dir lifecycle (workspaces/runs/decisions/labels)
 ├── workspace.py    safe loading: dirs, single .tex, ZIP with fail-closed limits
 ├── scanner.py      position-aware LaTeX scanner (never compiles)
 ├── bibfile.py      position-aware BibTeX reader
 ├── rules.py        V0 deterministic rules + V2 notation candidate
 ├── evidence.py     quote gate: byte-exact span verification
 ├── fingerprint.py  style profile, drift cards, cognitive skeleton, navigator
 ├── metadata.py     V1 DOI lookup, opt-in, never claim-supporting
 ├── providers.py    local/cloud AI with per-payload consent, redaction
 ├── adapters.py     optional papercheck cross-check (probed, never assumed)
 ├── report.py       report.md / agent-feedback.json / style guide exports
 └── cli.py          paperfamiliar serve | audit | providers | metadata | ask
```

Runtime dependencies: FastAPI, uvicorn, pydantic, python-multipart. Node/Vite are
build-time only; the built `web/dist` ships inside the wheel and the Python
package. There is no second server, no dev-server requirement, no Electron, no
native GUI, no browser extension, and no PWA service worker.

## 2. Frontend

React 18 + TypeScript + Vite, one SPA:

- **Left pane** — Paper Map (sections with role + contribution labels),
  Familiarity Navigator (deterministic, honest `not_found`), finding counts.
- **Center** — read-only LaTeX source with per-file tabs, line gutter,
  code-point column highlighting of spans, jump/sync from every evidence card.
- **Right** — Evidence Ledger (status chips, rule scope, Accept/Dismiss),
  Style panel (reference selection, baseline metrics, drift cards with
  confidence), Structure panel (section tree, environment sequence, label
  topology, symbol index).
- **Import modal** — browser file/folder/ZIP upload (`FormData`, relative
  paths preserved) *or* a local path handled server-side; reference papers get
  a per-section contribution dialog.
- **Models modal** — provider probe, payload preview, explicit consent per
  cloud request.
- **Data modal** — data directory, sizes, workspace list with delete, and an
  erase-all gate.

No CDN, no web fonts, no analytics; the page sets a per-process CSRF token that
the HTML embeds (`__PF_CSRF__` replaced server-side).

State that matters is server-side. The browser keeps only one key in
`localStorage`: the last opened workspace id, so a refresh or browser restart
reopens the same review. Manuscript text is never persisted in the browser.

## 3. Persistence and lifecycle

`app_data_dir` (Windows `%LOCALAPPDATA%\PaperFamiliar`, macOS
`~/Library/Application Support/PaperFamiliar`, Linux `$XDG_DATA_HOME/paperfamiliar`,
override `PAPERFAMILIAR_DATA`):

```text
paperfamiliar.sqlite3     workspaces · runs · decisions · labels
workspaces/<id>/project/  stored copies of browser uploads (deleted with the row)
exports/<run_id>/         report.json · report.md · agent-feedback.json · …
cache/metadata/           opt-in DOI responses (TTL 30 days)
```

- A workspace is `manuscript`, `reference` or `demo`.
- **Stored** workspaces (uploads, ZIP imports) live under the data dir and are
  removed on delete. **Path** workspaces reference the user's folder; delete
  unlinks the record only and never touches user files (tested).
- Original bytes are immutable: every file gets SHA-256 at load; `file_text()`
  re-hashes on read and reports `unchanged`; exports re-check after writing.
- Deleting clears decisions, labels, runs and exports for that workspace.
  Erase-all clears tables, export and cache directories.

## 4. Evidence chain

finding intake (rules or adapters) → `evidence.verify_span()` → only byte-exact,
hash-matched, in-bounds spans enter the ledger → everything else goes to
`payload["rejections"]` with a reason. `finding_class`, `evidence_status` and
`human_decision` stay independent; accepting never upgrades evidence.

## 5. Networking policy

- Server binds `127.0.0.1` only; `--host` exists but rejects non-loopback values
  (exit 8). DNS-rebinding-style `Host` headers and cross-origin mutations are
  rejected by middleware; the CSRF token is required for all non-GET requests.
- Outbound requests exist only in `metadata.lookup_doi` (opt-in `allow_network`)
  and `providers.send` (per-payload consent, TTL 300 s, single-use, hash-pinned).
  Strict offline is the default; nothing else opens a socket.
- Local provider probe (`Ollama /api/tags`) is loopback-only, 0.8 s timeout, and
  only runs when a client asks for provider status.

## 6. Security model

See `docs/threat-model.md` (T1–T10) plus the v1.2 web-specific items:
WEB-HOST, WEB-CSRF, WEB-FILE, WEB-LAN. Fail-closed rules in §3 of that file
still apply. The ZIP extractor, include resolver and scanner are shared with the
v1.1 design and unchanged in their guarantees.

## 7. What is intentionally not here (v0.1)

LAN sharing, authentication, PWA/offline caching, TeX compilation, PDF preview,
docx/OCR, vector RAG, model-managed downloads, plugin system. These are ADR-0007
deferrals, not omissions by accident.

## 8. Compatibility honesty

Implemented and self-tested on Windows 11 x64 with Python 3.13 and Playwright
Chromium/Firefox/WebKit. The same code path is expected to work on macOS and
Linux (pure Python + SQLite + static assets; wheel availability for optional
integrations was verified for macOS arm64 in `docs/dependency-audit.md`), but no
macOS/Linux host has executed the suite yet — README lists those as
`UNTESTED_PLATFORM`. No claim of “works everywhere” is made anywhere.
