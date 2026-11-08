# Implicit state machines in PaperFamiliar v1.2

This document inventories every **implicit state machine** in the product: places
where behavior depends on a value that is not modeled as an explicit workflow
object, but that still has a finite set of states, legal transitions, guards and
persistence. It covers the Python service, the React UI, the SQLite store, the
on-disk data directory, and the QA toolchain under `scripts/` and `qa/`.

"Implicit" here means: no state-machine library, no `state` column that drives a
workflow engine, no transition table in code. The states exist as string enums,
booleans, nullable fields, exception paths, or "row present / row absent".

Method: every enum literal, status field, boolean flag, migration table,
`HTTPException` code, CLI exit code and UI `useState` flag was traced to its
writers and readers. Where a transition can fail, the failure state is listed
too, because in this product **honest failure is a state** (abstention, offline,
quote-gate rejection, `MUSE_UNAVAILABLE`).

Legend for risk: **L** low (local, recoverable), **M** medium (user-visible
inconsistency), **H** high (silent wrong result).

---

## Inventory

| # | Machine | Where | States | Persistence | Risk |
|---|---|---|---|---|---|
| 1 | Workspace identity | `storage.py`, `ingest.py` | kind × stored × revision | SQLite `workspaces` | M |
| 2 | Demo reuse | `ingest.py:demo_workspace` | new / reused | SQLite | L |
| 3 | Legacy schema migration | `storage.py:_migrate_legacy` | pre-v1.2 / migrated | SQLite `legacy_migrations` | L |
| 4 | Workspace deletion | `storage.py:delete_workspace` | stored / path / missing | filesystem + SQLite | M |
| 5 | Run lifecycle | `service.analyze`, `/audit` | created / re-audited / stale-source / deleted | SQLite `runs` | M |
| 6 | Finding admission | `evidence.verify_span` | produced → admitted / rejected | run payload JSON | H |
| 7 | Human decision ledger | `decisions` table, `App.decide` | unreviewed ↔ accepted ↔ dismissed ↔ needs_review | SQLite `decisions` | H |
| 8 | Contribution labels | `labels` table, `refresh_style` | per-section + blanket `ALL` | SQLite `labels` | M |
| 9 | Baseline / drift | `fingerprint.build_baseline` | insufficient_evidence / ok; card observed / insufficient | run payload | M |
| 10 | Navigator lookup | `fingerprint.navigate` | found / not_found | none (response) | L |
| 11 | File read integrity | `service.file_text` | unchanged / changed / gone / forbidden | computed per read | M |
| 12 | Export generation | `service.export_run` | not generated / generated / missing | `exports/` files | M |
| 13 | Consent transaction | `providers.ConsentStore` | preview → confirmed → used / expired / hash-mismatch | SQLite `consents` | M |
| 14 | Provider probe | `providers.probe/status` | available / no_models / unavailable | none (response) | L |
| 15 | Metadata lookup | `metadata.lookup_doi` | invalid / offline / not_found / network_error / corroborated | cache JSON, 30 d | L |
| 16 | HTTP request gate | `api.py` middleware | accepted / 400 / 403 | none | L |
| 17 | App shell | `App.tsx` | landing / workbench / restoring | `localStorage` | M |
| 18 | Tab selection | `App.tsx` | evidence / style / structure | component state | L |
| 19 | Overlays | `App.tsx` | closed / import(kind) / settings / models / reference | component state | L |
| 20 | Focus & jump | `App.tsx` | no target / pending jump / rendered | component state | M |
| 21 | Decision toggle | `App.tsx:decide` | same → unreviewed; different → new | server | M |
| 22 | Label write + refresh | `App.tsx:labelSection` | saved / style-refresh-failed / write-failed | server | M |
| 23 | Provider panel | `ModelsPanel.tsx` | idle / probing / preview / sending / candidate / error | component state | M |
| 24 | Source-intact banner | `App.tsx` `sourceIntact` | unknown / intact / changed | component state | L |
| 25 | Ingest validation | `ingest.upload_workspace` | accepted / rejected(reason) | filesystem | L |
| 26 | Include resolution | `workspace.include_order` | resolved / unresolved / visited | computed per load | L |
| 27 | Scanner mode | `scanner.py` | text / comment / verbatim / math (env depth) | per scan | L |
| 28 | Gate contract | `check_gates.py` | SUBMITTED + verdict → PASS/BLOCKED/ERROR/APPROVAL | `qa/*.json` | M |
| 29 | Self-test status | `selftest.py` | PASS / FAIL / BLOCKED / UNTESTED | `qa/evidence/*` | L |
| 30 | Muse queue task | `muse_poll.py` | pending / claimed / finished(+result) / stale | remote queue | M |
| 31 | Handoff/verdict binding | `muse_ingest.py` | valid / rejected(identity, sha, schema) | `qa/*.json` | H |
| 32 | CLI process | `cli.py` | exit 0/1/2/7/8 | exit code | L |
| 33 | Bulk erasure | `/api/settings/clear`, UI typed DELETE | intact / erasing / erased | data dir | H |

---

## 1. Workspace identity and lifecycle

`Workspace` (`storage.py`) is the root object. Its "state" is the tuple
`(kind, stored, revision_id, root exists)`.

| State | Meaning | Entered by |
|---|---|---|
| `manuscript`, stored | user-uploaded draft | `upload_workspace` / `path_workspace(kind="manuscript")` |
| `reference`, stored | user-uploaded prior paper | same, `kind="reference"` |
| `demo`, stored | bundled synthetic workspace | `demo_workspace` |
| `*`, not stored | path import; files stay where they are | `path_workspace` |
| missing root | path import whose folder moved/deleted | filesystem change |

Transitions:

- upload/path/demo → row inserted with `revision_id` (aggregate hash of paths +
  bytes) and one run row.
- `stored` is set at creation and never changes; it is the only guard that
  decides whether deletion may touch files.
- `revision_id` changes only when a **new** workspace is created. Re-auditing
  the same workspace does not rewrite it even if files changed on disk (see #5).
- deletion → row, run, decisions, labels and exports removed.

Guards and invariants:

- `kind` is restricted to `manuscript|reference|demo` at the API boundary
  (`api.py` rejects anything else with 400).
- `delete_workspace` resolves `root` and refuses anything outside the data
  directory; for a stored child named `project` it removes `root.parent`.
- A path workspace is never deleted from disk.

Risks: **M** — a path workspace is a live pointer. Its content can change
between sessions without any row update, so `revision_id` can silently describe
bytes that no longer exist. The next re-audit detects the new bytes but the
stored revision is not compared; see #5.

## 2. Demo reuse

`demo_workspace()` is a deduplicating state machine keyed on
`(kind == "demo", revision_id == loaded.revision_id, root.is_dir())`.

- **new**: no matching row → create workspace + import draft and four references,
  set blanket label `ALL`, refresh style.
- **reused**: match → return existing row unchanged (no duplicate rows, no
  duplicate runs).
- **recreated**: row matches but root is gone → falls through to new.

Risk: **L**. The guard is revision-based, so editing the bundled demo changes
`revision_id` and intentionally creates a second workspace; the old one remains
until deleted. `usage()` reports both.

## 3. Legacy schema migration

One-way, self-disarming machine in `Store._migrate_legacy()`:

`pre-v1.2 schema` → detect tables `runs`/`decisions`/`labels` lacking
`workspace_id` → rename to `*_v11` → insert marker into `legacy_migrations` →
`v1.2 schema`.

- Never deletes or rewrites legacy rows; they stay queryable under `_v11`.
- The marker makes the transition idempotent; a second boot is a no-op.
- There is no downgrade path. A v1.2 database opened by v1.1 code is undefined.

Risk: **L** (data preserved by design), but worth stating: the old data is
**not** visible in the UI after migration.

## 4. Workspace deletion

States: `present` → `deleting` (synchronous, no intermediate persisted state) →
`gone`. Outcomes:

| Condition | Files | Rows | Exports |
|---|---|---|---|
| `stored=true`, inside data dir | removed (`root.parent` if `project`) | deleted | directory removed |
| `stored=false` (path import) | untouched | deleted | directory removed |
| root escapes data dir | refused (raise) | kept | kept |
| unknown id | 404 | — | — |

Risk: **M** — no `deleting` state exists, so a crash mid-`rmtree` can leave a
partially removed directory with no row, which no later code cleans up. Not
observed in tests; low likelihood, but the machine has no recovery edge.

## 5. Run / revision lifecycle

Each workspace owns exactly one `RunRecord` (`runs` table), reused across
re-audits.

```
created ──audit──> analyzed ──re-audit──> analyzed' (payload replaced, same run id)
   │                    │
   │                    ├─ source path missing ──> 410, payload unchanged
   │                    └─ source unreadable  ──> 410
   └─ workspace deleted ──> gone
```

Transitions and guards (`POST /api/workspace/{id}/audit`):

1. Load workspace from `run.payload["source_path"]`; failure → HTTP 410, state
   unchanged.
2. `analyze()` re-runs scan + rules + quote gate; every finding re-admitted or
   re-rejected.
3. `run.payload` is merged with the new payload and saved; `revision_id` on the
   run row is **not** recomputed from the new bytes.
4. If a style baseline exists (`reference_ids`), style is refreshed.

Risk: **M** — "re-audit" is not a new revision. Any external consumer reading
`run.revision_id` after an edit sees the old revision even though the findings
describe new bytes. The UI does not surface a "source changed since analysis"
state except per-file `unchanged` (#11).

## 6. Finding admission (quote gate)

The most important safety machine. Every candidate finding is produced by a
rule and must pass an ordered gate before it reaches the ledger.

```
rule produces finding
        │
        ▼
verify_span(source, span)
  empty_quote ─────────────┐
  file_hash_mismatch ──────┤
  file_path_mismatch ──────┤──> rejected (logged, never shown)
  span_out_of_bounds ──────┤
  empty_range ─────────────┤
  quote_mismatch ──────────┘
        │ all pass
        ▼
     admitted → human_decision = unreviewed
```

- Failure reasons are ordered and mutually exclusive; the first failing guard
  wins, so the reason is deterministic.
- Rejected findings are written to `run.payload["rejections"]` with the claimed
  span and reason; they are never mixed into `findings`.
- `file_not_found` is a synthetic reason used when no source mapping exists
  (`service.analyze`).

Risk: **H** if this machine were bypassed anywhere; today the only writer of
`findings` is `analyze()` after the gate. Tests cover fabricated quotes and
out-of-bounds spans (`test_quote_gate.py`).

## 7. Human decision ledger

`decisions` rows key on `(workspace_id, finding_id)`; the in-memory default is
`unreviewed`.

States: `unreviewed`, `accepted`, `dismissed`, `needs_review`. The API accepts
all four (`ALLOWED_DECISIONS`); the UI toggle sends `unreviewed` when the user
clicks the already-active button.

```
unreviewed --accept--> accepted --accept--> unreviewed
unreviewed --dismiss-> dismissed --dismiss-> unreviewed
any --mark for review--> needs_review
```

Two representations of the same state exist: **no row** and **a row whose value
is `unreviewed`**. `summary()` treats both as `unreviewed`, so behavior is
correct, but the table accumulates terminal rows that mean "never decided".

Risk: **H** — finding IDs are **ordinal per rule**, not content-addressed
(`rules._Ids`: `F-<rule>-0001`). Re-audit preserves decisions by ID, and the
endpoint docstring says so. Consequence: if the user fixes finding `0001` of a
rule and a *different* problem of the same rule becomes `0001`, the new finding
silently inherits the old decision (e.g. `dismissed`, or `accepted`). The
current tests do not exercise that sequence. This is the single most
consequential implicit transition in the product.

## 8. Contribution labels and baseline admission

Two-level label machine:

- Per-section label (`sole_or_primary | coauthored | not_primary | unknown`) in
  `labels`, keyed by section id.
- A blanket `ALL` row set only by the demo bundler; `summary()` and
  `refresh_style()` resolve `labels.get(section_id, ALL or section_default)`.

The baseline only consumes sentences from sections resolving to
`sole_or_primary`. Guard: at least 3 papers and 60 sentences
(`fingerprint.build_baseline`). State:

```
insufficient_evidence (reason: too_few_papers / too_few_sentences)
        │ condition met
        ▼
       ok (profile present)
```

`refresh_style` also has a terminal `no_approved_sections` state when labeled
references yield no usable text.

Risk: **M** — the blanket label is invisible in the UI except as column
defaults. If a user labels one section and leaves others, the others still
inherit `ALL`; that is correct per demo design but easy to misread as
"unlabeled ⇒ excluded".

## 9. Baseline and drift cards

Drift evaluation is a three-valued machine per card:

| Card state | Meaning | Renderer behavior |
|---|---|---|
| `observed` | metric computed with sample size | shown with confidence tier |
| `insufficient_evidence` | not enough prose in baseline or target | shown as abstention, no score |
| card list empty | no baseline | style tab shows baseline state only |

Confidence is a derived label (not a stored state) from sample counts. There is
no transition from `insufficient_evidence` to `observed` except by adding text
or labels and refreshing; refreshing is idempotent.

Risk: **M** — `confidence` values are computed at refresh time and stored in
the payload; they do not update when the user later changes labels without a
refresh. The UI calls `refreshStyle` after label changes, so the normal path is
consistent; direct API label writes are not.

## 10. Navigator

`navigate()` returns exactly one of:

- `{"status": "found", ...}` with section, span, confidence;
- `{"status": "not_found", ...}` with the query and no location.

There is no "partial" or "maybe". The UI renders `nav` as null (idle) before
the first query, then the response. No persistence.

Risk: **L** — the response is deterministic for a fixed workspace; nothing to
desynchronize.

## 11. File read integrity

`GET /file` is a per-request machine:

| Condition | Result |
|---|---|
| path not in run file list | 403 |
| path escapes root | 403 (PermissionError) |
| file missing | 410 |
| readable | text + `sha256` + `unchanged` |

`unchanged` is `true` when the file has no recorded hash (e.g. bibliography
files) or the current digest equals the recorded one. The UI sets
`sourceIntact` from this field.

Risk: **M** — `unchanged` is computed only when a file is opened in the centre
pane. No global "workspace drifted" state exists; exports (#12) do not consult
it.

## 12. Export generation

States: `not generated` (files absent) → `generated` (five files written) →
`missing` (user or cleanup removed them).

- `POST /export` always overwrites the five files; writes are not transactional.
- `GET /export/{name}` returns 404 for a name outside the fixed set, 410 when
  the file does not exist.
- Exports are removed with the workspace.

Risk: **M** — `export_run()` does **not** re-hash source files. It writes the
snapshot from the last run. If files changed on disk after analysis, the
exported report is labeled with the old revision and no drift warning. The
README's claim that the hash is "re-checked and reported unchanged" refers to
the `/file` endpoint, not to export. This gap should be closed or documented as
a known limitation.

## 13. Consent transaction

`ConsentStore` is the only path to any model call.

```
preview(payload) ──> consent record (confirmed=false, used=false, hash pinned)
        │ confirm()                       │ TTL 300 s at every check
        ▼                                 ▼
   confirmed=true                 expired → PermissionError
        │ send()
        ▼
   used=true  (set in `finally`, even on transport failure)
        │
        └─ any later check() → "consent already used"
```

Guards in `check()`: consent exists → not used → not expired → payload digest
matches the pinned hash. Cloud also requires `confirmed`; local does not.

Risk: **M** — `used` conflates **attempted** with **delivered**. A network
timeout consumes the consent, so a retry requires a fresh preview. That is a
conservative design (no silent duplicate send), but it is an implicit terminal
state the UI only reveals through a generic error. There is no `failed` state
recorded.

## 14. Provider probe

`probe()` returns `available` (models non-empty), `no_models`, or `unavailable`
(any exception). `status()` adds config and redaction policy, and always reports
the core product as usable without a model. Local endpoints are loopback-only.

Risk: **L** — stateless probe; the UI shows whatever the last probe said until
the user re-probes.

## 15. Metadata lookup

State table (`metadata.lookup_doi`):

| State | Cause | Exit code (`paperfamiliar metadata`) |
|---|---|---|
| `invalid_identifier` | malformed DOI | 1 |
| `unavailable_offline` | network not allowed | 0 |
| `not_found` | Crossref has no record | 1 |
| `network_error` | HTTP/transport failure | 1 |
| `source_corroborated` | record fetched | 0 |

Only `source_corroborated` is cached (30-day TTL, keyed by DOI digest); negative
results are deliberately not cached, so a transient outage is retried.

Risk: **L** — no partial state; `claim_support` is always `unknown` and is not
a state at all.

## 16. HTTP request gate

Per-request middleware (`api.py`):

```
request ──> Host allowlisted? ──no──> 400
             │ yes
             └─> Origin same-origin (if present)? ──no──> 403
                   │ yes
                   └─> X-PF-CSRF matches session token? ──no──> 403
                         │ yes
                         └─> route
```

Risk: **L** — stateless. The CSRF token is per-process, so restarting the
server invalidates open tabs' mutating requests (the UI reloads and obtains a
new session).

## 17. App shell and last-workspace restore

`App` has three top-level states:

```
landing (run == null)
   │ open workspace / demo / restore
   ▼
workbench (run != null)  ──error──> workbench + error banner
   │
   └─ delete current workspace ──> landing
```

Restore edge: on mount, `localStorage["paperfamiliar.workspace"]` is read and
the workspace fetched. If the fetch fails (deleted, server data wiped), the UI
must fall back to landing. `sourceIntact` resets with each file load.

Risk: **M** — last-workspace ID is a cached pointer in a different store
(browser) than the authority (SQLite). The fallback exists, but if the server
is temporarily unreachable the app shows an error rather than distinguishing
"workspace gone" from "server down".

## 18. Tab selection

`tab ∈ {evidence, style, structure}`. Pure UI state, no guards. Switching tabs
does not clear `activeFinding` or `nav`; a finding selected in Evidence remains
active if the user returns. Risk: **L** (stale highlight only).

## 19. Overlays

`showImport: null | "manuscript" | "reference"`, plus independent booleans
`showSettings`, `showModels`, and `manageReference: string | null`.

- `showImport` is a single-valued enum (one import dialog at a time).
- The others are independent booleans, so in principle Settings and Models can
  both be open; in practice each modal is rendered last-wins and covers the
  other.

Risk: **L** — inconsistent modeling (enum vs booleans) but no data corruption.

## 20. Focus and jump state

Three fields cooperate: `activeFinding` (which ledger row is selected),
`jumpTarget` (`{file, line} | null`), and `filePath`/`fileText` (what the centre
pane shows).

```
click finding / map / navigator result
   → set activeFinding + jumpTarget
   → fetch file text
   → render highlight at line
```

There is no explicit "jump consumed" transition; `jumpTarget` remains set until
another jump. Risk: **M** — if the target file changed on disk, the highlight
line may no longer correspond to the quote; `fileUnchanged` is shown but the
jump is not blocked.

## 21. Decision toggle

`decide()` computes `next = (decision === current) ? "unreviewed" : decision`,
then POSTs and refreshes the run from the response. Server state is the
authority; the UI does not apply the change optimistically.

Risk: **M** — two clicks race: both read the same `current`, both send the same
`next`, and the second overwrites the first rather than toggling back. The
window is small and the result is still a legal state.

## 22. Label write and style refresh

`labelSection()` is a two-step transition: (1) `POST /label` persists the
contribution; (2) local state is updated; (3) `refreshStyle` recomputes the
baseline. Steps 1–2 are atomic from the UI's point of view; step 3 is a second
request that can fail independently.

States:

```
old label --POST ok--> label saved + local update --style ok--> baseline current
                                        │
                                        └─ style fails --> label saved, baseline stale,
                                                           error banner, no rollback
old label --POST fails--> unchanged + error banner
```

Risk: **M** — the interesting failure is the middle one: the persisted label
and the displayed contribution are correct, but the baseline still reflects the
previous labels until the user reopens or reloads. A `refreshStyle` retry on
error would close this.

## 23. Provider panel

`ModelsPanel` local states: `idle → probing → (available|no_models|unavailable)`,
then `preview → sending → (candidate|error|unavailable)`. Each preview is
single-use; sending consumes it (#13).

Risk: **M** — after a failed send the panel shows the error but the preview is
already spent; the user must re-preview. No distinct "expired" message.

## 24. Source-intact banner

`sourceIntact: boolean | null` — `null` before the first file load, `true` when
`unchanged`, `false` when the digest differs. It is per-file, reset on each
open.

Risk: **L** — no persistent workspace-level drift indicator.

## 25. Ingest validation pipeline

Fail-closed sequence in `upload_workspace()`:

```
zip XOR files
  → per-name safe relative path (no absolute, no traversal, no depth, known suffix)
  → count limit / total bytes / per-file bytes
  → zip-slip / absolute / symlink / bomb / depth checks during extraction
  → duplicate-name detection
  → write to a fresh directory
  → load workspace (must contain a .tex)
```

Any failure is a terminal `StorageError` (HTTP 400/413 for uploads); no partial
workspace row is created. Risk: **L** — extraction writes before all checks in
some paths, but into a temporary directory that is discarded.

## 26. Include resolution

`Workspace.include_order()` is a graph traversal with a `seen` set:

- resolved include → enqueue target (once);
- missing or outside workspace → record `include.unresolved` security event and
  do not enqueue;
- cycle → stopped by `seen`;
- order is deterministic.

Risk: **L** — unresolved includes are surfaced, not fatal.

## 27. Scanner mode automaton

The static scanner is a character-level state machine over
`text | comment | verbatim | math`, with environment nesting:

- `%` enters `comment` until newline (unless escaped);
- `\begin{verbatim|lstlisting|minted|comment}` enters `verbatim` until the
  matching `\end`;
- math environments and `$...$` enter `math`, where citations/labels are not
  interpreted;
- every occurrence carries a 1-based code-point line/column.

Risk: **L** — unmatched environments at EOF are tolerated as text; no explicit
"unterminated" state is reported. This matches the documented conservative
behavior but is an implicit decision.

## 28. Gate contract (release QA)

`scripts/check_gates.py` reads a pair of files per gate: handoff (`SUBMITTED`)
and Muse verdict (`VERIFIED` required). The checker itself has four terminal
states:

| Exit | Meaning |
|---|---|
| 0 | contract complete (not proof of identity) |
| 2 | blocked: missing files, non-VERIFIED verdict, missing PASS, platform/browser gap |
| 3 | schema/evidence error: bad shape, unknown host, SHA mismatch, wrong schema |
| 4 | user approval missing or not APPROVED |

Additional derived states: optional checks may be `UNTESTED` but never silently
`FAIL`/`BLOCKED`; all gates must share one `commit_sha`.

Risk: **M** — the checker validates **shape**, not truth; its own output says
so. `MUSE_UNAVAILABLE` is not a pass state: the file is absent, so exit is 2.

## 29. Self-test statuses

Each check in `scripts/selftest.py` is `PASS | FAIL | BLOCKED | UNTESTED`.
`MUSE_ONLY` checks (QA-01/02) are emitted as `BLOCKED`; `MANUAL` (USER-01) as
`UNTESTED`. Evidence is written per gate and pinned to the product SHA.

Risk: **L** — statuses are declarations written by this host; the gate checker
separates them from Muse verdicts by file name and identity.

## 30. Muse queue task lifecycle

Remote task states observed by `scripts/muse_poll.py`:

```
pending ──claim──> claimed ──finish──> finished (result_status success|failure)
   │                  │
   │                  └─ 30 min without finish ──> stale (claim expires, task
   │                                                returns to pending)
   └─ rejected by platform screen ──> finished (result_status rejected)
```

The poller treats only `state == "finished"` with a non-null `result` as
ingestible; anything else stays pending until the poll deadline, then the
poller exits leaving tasks pending. `muse_ingest.py` then validates the
result's identity, schema, SHA and handoff binding before writing a verdict.

Risk: **M** — "claimed" is not "running" and "finished" is not "passed";
`result_status` must be interpreted, not assumed.

## 31. Handoff/verdict binding

Validation states in `muse_ingest.py` / `check_gates.py`:

- reject on producer identity mismatch (`issuer`, `key_id`);
- reject on canonical-hash mismatch of the submitted text;
- reject on schema version;
- reject on `commit_sha`/`run_id` mismatch between handoff and verdict;
- accept only `tester_origin == independent_muse` and `status == VERIFIED`.

Risk: **H** — if binding were relaxed, a stale or foreign verdict could unlock
a gate. It is currently strict and covered by tests.

## 32. CLI process states

| Command | Exit states |
|---|---|
| `serve` | 0 normal; 7 port in use; 8 non-loopback host |
| `audit` | 0 success; 2 workspace/parse error |
| `providers` | 0 always (status is data) |
| `metadata` | 0 corroborated/offline; 1 not found/network/invalid |
| `ask` | 0 candidate; 1 otherwise; 2 cloud not configured |

Risk: **L** — documented and stable; exit 7/8 are deliberate refusals, not
crashes.

## 33. Bulk erasure

`/api/settings/clear` (UI: Settings → type `DELETE`) moves the data directory
from `intact` to `erased` in one step. There is no persisted `erasing` state and
no undo.

Risk: **H** — irreversible by design. The guard is a typed confirmation, not a
transaction; a crash mid-delete leaves an unknown mixture.

---

## Cross-cutting observations

1. **Three independent axes, one row.** Each finding simultaneously carries
   `finding_class` (mechanical/metadata/heuristic/semantic), `evidence_status`
   (verified_error/candidate/etc.) and `human_decision`
   (unreviewed/accepted/...). They change independently; no transition couples
   them. This is intentional (the product never marks a human decision as
   evidence), but any UI that collapses them into one "status" chip loses
   information.
2. **Persistence is layered.** SQLite holds identity, runs, decisions, labels,
   consents; the run payload JSON holds derived analysis; `localStorage` holds
   only a last-workspace pointer; export files are derived. The most fragile
   layer is the run payload: it is rewritten wholesale on re-audit.
3. **Terminal states are honest.** `insufficient_evidence`, `not_found`,
   `unavailable_offline`, `MUSE_UNAVAILABLE` and quote-gate `rejected` are all
   explicit refusing states rather than missing values. This is the product's
   core invariant and should be preserved in any refactor.
4. **Highest-risk transition:** re-audit with ordinal finding IDs (#7). If
   review state is meant to survive edits, IDs must become content-addressed
   (rule + file + quote/excerpt hash) or decisions must be invalidated when the
   finding's span or quote changes. Until then, "review state is preserved by
   finding id" is true mechanically but not semantically.
5. **Second gap:** export (#12) does not re-verify source hashes, so an export
   can silently describe a stale snapshot.
6. **Minor asymmetries worth a follow-up:** `unreviewed` stored as a row; a
   successful label write can leave the baseline stale if the follow-up style
   refresh fails (#22); metadata negative results not cached (deliberate);
   consent `used` set on transport failure (conservative but indistinguishable
   from success in the UI).
