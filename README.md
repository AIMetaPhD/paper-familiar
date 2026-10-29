# PaperFamiliar

**Verify the research. Preserve the author's voice.**

PaperFamiliar is a **local-first web app** for LaTeX manuscripts. One Python
process serves both the API and the browser UI on `http://127.0.0.1:8420`; your
papers, review state and author profile live on your own disk. It shows only
what it can point to: mechanically decidable citation errors, honest reference
metadata, and a measured picture of how you write.

- No account, no API key, no telemetry, no CDN, no second server.
- Upload `.tex`/`.bib`/`.zip` in the browser, or import a folder path.
- Every finding must reproduce an exact quote from your immutable source bytes.
- Style differences are described, never scored, and never called academic errors.
- Your manuscript is never modified — originals are read-only and hash-checked.

## Status (2026-10-28)

**v0.1 technical candidate.** Self-tested end to end on Windows 11 x64; the G1–G5
acceptance matrix is **not** passed yet: independent Muse QA verdicts and the
author's own blind sign-off are still outstanding. Nothing is published anywhere.

| Item | State |
|---|---|
| Local server + browser UI, offline demo, upload, persistence, exports | working, self-tested |
| Unit tests (parser, rules, quote gate, security, style, navigator, providers, offline proof) | 58 passing on this machine |
| Playwright E2E on Chromium / Firefox / WebKit | 36 passing on this machine (one host) |
| Wheel packaging (`web/dist` + demo inside the wheel) | verified; clean-venv install check pending |
| Independent Muse QA (G1–G5) | transport verified working; verdicts pending |
| Author blind evaluation (G5, `USER-01`) | reserved for you |
| macOS / Linux | `UNTESTED_PLATFORM` — same code path, no host has run it |
| Real cloud API | `UNTESTED_CLOUD_REAL` — consent flow proven against a mock endpoint |
| Private repository | pushed to `AIMetaPhD/paper-familiar` (PRIVATE) on 2026-10-29, commit `c391414` — public visibility, Release and the AIMetaPhD list remain unauthorized |

## Requirements

- Python 3.11, 3.12 or 3.13 on PATH (verified on 3.13).
- A modern browser: Chromium-family, Firefox or WebKit/Safari.
- No Node, no Docker, no TeX distribution at runtime. (Node is only needed to
  rebuild the frontend from source.)

## Run

From a source checkout (first run installs dependencies into `.venv`):

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e .        # Windows
.venv/bin/python -m pip install -e .            # macOS / Linux
.venv\Scripts\paperfamiliar serve               # opens http://127.0.0.1:8420
```

Once a wheel is built (`python -m build --wheel`), any Python environment can:

```bash
python -m pip install dist/paperfamiliar-0.1.0-py3-none-any.whl
paperfamiliar serve
```

Headless audit without a browser: `paperfamiliar audit path/to/paper --export`.
Port conflict? The CLI says so and exits; it never silently rebinds elsewhere or
to a public interface (`--port 8421`).

## The golden path in the browser

1. **Load the offline demo** — four synthetic "your earlier papers" plus a
   synthetic draft with planted defects.
2. Findings appear in the **Evidence ledger** with their exact status:
   *Verified error* (mechanically provable) vs *Candidate* (heuristic, needs you).
3. Click a finding → the centre pane jumps to the exact file/line/column and the
   quote is highlighted; the same jump works from Paper Map, navigator results
   and structure chips.
4. **Familiarity navigator**: ask `where is the optimization problem?` and it
   finds Problem Formulation — or answers `not_found`. It never invents a
   location.
5. **Style tab**: pick which reference papers are yours, mark per-section
   contribution (only "I wrote it" sections enter the baseline), get drift cards
   with sample sizes and confidence. Too few papers → honest abstention, no
   fake score.
6. Accept/Dismiss findings, then **Export**: `report.json`, `report.md`,
   `agent-feedback.json`, `author-style-guide.md`,
   `cognitive-structure-profile.json` — written to your data directory, source
   hash re-checked and reported unchanged. Exports contain findings,
   coordinates and aggregate style metrics, not your full text.
7. Close the tab, restart the server: your workspaces, decisions and profile
   come back (SQLite under your data dir; **Data** shows and deletes them).

## What v0.1 does

- Multi-file `.tex` + `.bib` + safe `.zip` parsing with a position-aware static
  scanner (comments/verbatim/math-aware; exact code-point line/column; CRLF or
  LF).
- V0 rules: undefined citation keys, undefined `\ref` targets, duplicate
  `\label`, malformed or incomplete BibTeX entries, includes escaping the
  workspace — each with its rule scope stated.
- One conservative notation heuristic, clearly labelled `candidate`.
- Model-free cognitive skeleton (section tree, environment sequence, label
  topology, symbol index) and the deterministic navigator.
- Transparent style measurements (sentence length, function words, transition
  openers, math-lead, passive rate) from approved primary-author prose only.
- Local/cloud AI behind consent: Ollama/OpenAI-compatible loopback probe; cloud
  disabled until configured; every send shows the exact payload, bytes, token
  estimate, redactions and destination before you confirm.
- Optional DOI metadata lookup (opt-in; results are `source_corroborated`,
  never "claim supported").
- Optional `papercheck` cross-check adapter when installed — capability-probed,
  never assumed.

## What v0.1 does not do

No plagiarism detection, AI-text detection, or Turnitin-style service; no claim
truth verification; no theorem proving; no docx/OCR/PDF editing; no automatic
rewriting; no TeX compilation (ever, in v0.1); no LAN/public serving; no browser
extension; no "98% authorship" numbers.

## Security model, briefly

Loopback bind + Host allowlist + same-origin + per-process CSRF token; ZIP
extraction fails closed on zip-slip/absolute/symlink/bomb/deep archives;
includes never escape the workspace; prompt-injection text inside manuscripts is
inert data; quote gate before any finding reaches you; no secrets in logs or
exports; strict offline by default with an import-blocking test proving zero
egress. Details: [docs/threat-model.md](docs/threat-model.md),
[SECURITY.md](SECURITY.md), [docs/architecture.md](docs/architecture.md).

## Development

```bash
python -m pytest -q                     # unit + API + offline-proof
python -m pytest tests/e2e -q           # needs: pip install playwright
                                        # and: playwright install chromium firefox webkit
python scripts/g1_check.py              # live-server runtime probes
python scripts/selftest.py --gate G1    # per-gate evidence (self-test only)
python scripts/make_handoff.py --gate G1
python scripts/check_gates.py --root .  # evidence-contract shape checker
```

Acceptance governance lives in `04_ACCEPTANCE_MATRIX.csv`, `schemas/`, `qa/` and
`docs/adr/0005-muse-qa-and-release-gates.md`. Muse's own verdicts are the only
path to a passed gate.

## License

MIT. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — notably,
`academic-refchecker` pulls GPL dependencies and is therefore **not** bundled.
