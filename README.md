# PaperFamiliar

**Verify the research. Preserve the author's voice.**

PaperFamiliar is a local-first, LaTeX-first manuscript workbench. It shows only what it can
point to: mechanically decidable citation errors, honest reference metadata, and a descriptive
picture of how you write. It never edits your manuscript, never compiles your TeX, and does not
use the network unless you explicitly ask it to.

- No account, no API key, no telemetry, no CDN.
- Every finding must reproduce an exact quote from your immutable source bytes.
- Style differences are described, not scored, and are never called academic errors.

## Status (2026-10-28)

This is a **v0.1 technical candidate**, not an accepted release.

| Item | State |
|---|---|
| Windows 11 x64 self-test | passing locally (native launcher, demo, audit, export) |
| macOS Apple Silicon | **not run** — no Mac is reachable from the development session; `BLOCKED_PLATFORM_UNTESTED` |
| Independent Muse QA (G1–G5) | **not completed** — transport verified, verdicts pending |
| User blind acceptance (G5) | not requested yet |
| Network/push | nothing pushed; the repository is local only |

Do not read this file as a claim that the product has passed acceptance. Gate evidence lives
under `qa/` when it exists.

## Requirements

- Python 3.11, 3.12 or 3.13 on the PATH.
- Windows 11 x64 or macOS on Apple Silicon (arm64). Linux is not an acceptance platform.
- End users do **not** need Node, Docker, WSL, or a TeX distribution. The frontend is prebuilt.

## Run

Windows PowerShell:

```powershell
.\scripts\start-windows.ps1
```

macOS:

```bash
./scripts/start-macos.sh
```

Both create `.venv`, install pinned dependencies, check port 8420, and open
`http://127.0.0.1:8420`. First run needs network access; afterwards build `wheelhouse/` with
`python scripts/build_wheelhouse.py` for an offline install.

Manual start:

```bash
.venv/bin/python -m paperfamiliar serve      # macOS
.venv\Scripts\python.exe -m paperfamiliar serve   # Windows
```

Headless audit:

```bash
paperfamiliar audit path/to/paper --export
paperfamiliar demo
```

## First experience

1. Click **Load the offline demo**. The demo is synthetic and contains deliberate defects.
2. Click any finding in the right-hand ledger. The source pane jumps to the exact file, line
   and column, and the quote is highlighted.
3. Ask the navigator `where is the optimization problem?`. It returns *Problem Formulation* or
   says it cannot find a match; it never invents a location.
4. Open **Style** to see aggregate prose habits from four approved synthetic papers and drift
   cards with sample sizes and confidence.
5. Accept or dismiss findings, then **Export**. The source hash is re-checked and reported.

## What v0.1 does

- Parses multi-file `.tex` and `.bib` using a position-aware static scanner; never compiles.
- Detects undefined citation keys, undefined references, duplicate labels, malformed or
  incomplete bibliography entries.
- Flags one conservative notation heuristic as a **candidate**, with its limits stated.
- Builds a section tree, environment sequence, label topology and symbol index without a model.
- Computes transparent style features (sentence length, function words, transitions,
  math-lead, passive rate) from approved primary-author prose only.
- Exports `report.json`, `report.md`, `agent-feedback.json`, `author-style-guide.md` and
  `cognitive-structure-profile.json` without the full manuscript by default.

## What v0.1 does not do

- No claim verification, plagiarism detection, AI-text detection, or Turnitin-style service.
- No docx, OCR, arbitrary PDF editing, full-text RAG, or theorem proving.
- No automatic rewriting and no automatic submission.
- No TeX compilation, including `\write18` or shell escape.
- No guarantee that metadata matching a real publication supports the paper's claim.

## Security posture

- Binds `127.0.0.1` only; rejects unexpected `Host` headers, cross-origin mutations and missing
  CSRF tokens.
- ZIP import rejects absolute paths, parent traversal, symlinks, special files, bombs, deep
  nesting and oversized archives.
- Includes (`\input`, `\include`) resolve only inside the workspace; escapes fail closed.
- API keys are never part of this version's default flow; optional integrations read them from
  the environment and never write them to logs or exports.

See `docs/threat-model.md`, `docs/adr/`, and `SECURITY.md`.

## Development

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,latex]"      # Windows
.venv/bin/python -m pip install -e ".[dev,latex]"          # macOS
python -m pytest
npm --prefix web install && npm --prefix web run build
```

The canonical synthetic corpus is `fixtures/`. `python fixtures/build_fixtures.py` regenerates
the adversarial archives; `python scripts/sync_demo.py` copies the corpus into the bundled demo.

## License

MIT. Third-party notices are in `THIRD_PARTY_NOTICES.md`. Optional integrations have their own
licenses; notably `academic-refchecker` pulls GPL dependencies and is therefore not distributed
with this project.
