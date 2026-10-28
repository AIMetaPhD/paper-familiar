# ADR-0001: Single-process FastAPI + prebuilt React/Vite + SQLite

- Status: accepted, **partially superseded by ADR-0007 (v1.2 Local-first Web
  App)** — the stack decision stands; the native per-OS launcher scripts and
  the two-OS native-client acceptance framing were dropped. `paperfamiliar
  serve` is now the single entry point on every OS.
- Date: 2026-10-28

## Context

PaperFamiliar must run on a researcher's Windows 11 or Apple Silicon macOS laptop without Docker, WSL, Node, or an account. The first experience is one native command that opens `http://127.0.0.1:8420`. The UI is a three-pane workbench (Paper Map, LaTeX source, Evidence Ledger). Data stays local.

## Decision

- One Python process serves both the JSON API and the built frontend from `127.0.0.1:8420`.
- Frontend is React + TypeScript built with Vite. The built assets are committed under `web/dist` and shipped in the Python package, so end users never need Node.
- State that must survive a restart (workspaces, runs, findings, human decisions, style profiles) lives in a SQLite database under the per-user data directory.
- The CLI (`paperfamiliar serve`, `paperfamiliar audit`) is a thin wrapper over the same application service.
- The HTTP server binds loopback by default. Binding another interface requires an explicit flag and prints a warning.

## Consequences

- One command is enough for the demo; no separate backend/frontend processes in production.
- Node is a development-only dependency, pinned in `web/package-lock.json`.
- Windows and macOS are equal first-class targets; no platform-specific backend code paths beyond the launcher scripts.
- A single process is easier to reason about for CSRF, DNS-rebinding and CORS policy: the server only accepts same-origin requests with an explicit host check.

## Alternatives rejected

- Electron: larger download, duplicate browser engine, harder to keep a pure-Python audit CLI.
- Docker-only: excluded by the product contract.
- Server-rendered templates: weaker fit for an interactive three-pane editor with source jumping.
