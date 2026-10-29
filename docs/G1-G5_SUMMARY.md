# G1–G5 acceptance summary — PaperFamiliar v1.2

- Date: 2026-10-29
- Code SHA for all evidence below: rebuilt on the final frozen commit by
  `scripts/final_gate_run.py`; this document is regenerated from
  `qa/final-gate-run.json` after each run.
- **Status: NOT ACCEPTED.** Implementer self-tests pass on this host; the
  independent Muse verdicts and the product owner's own signature are missing.
  No gate is claimed as passed.

## What the matrix requires vs what exists

| Gate | Required | Implementer self-test | Muse verdict | User |
|---|---|---|---|---|
| G1 | local server + browser golden path, offline, persistence, 3 engines, packaging | see `qa/evidence/G1/host-local/selftest.json` | **none — blocked** | n/a |
| G2 | deterministic evidence, quote gate, security, web guards | see `qa/evidence/G2/host-local/selftest.json` | **none — blocked** | n/a |
| G3 | style/cognitive profiles, abstention, navigator, drift cards | see `qa/evidence/G3/host-local/selftest.json` | **none — blocked** | n/a |
| G4 | tri-engine E2E, persistence/delete, AI privacy, exports, layout | see `qa/evidence/G4/host-local/selftest.json` | **none — blocked** | n/a |
| G5 | Muse independence, final regression, release readiness | 3/6 (QA-01/02 BLOCKED, USER-01 UNTESTED) | **none — blocked** | **not signed** |

`python scripts/check_gates.py --root .` exits **2** — correct, because no
`qa/muse-verdict-*.json` exists. That file may only be produced by Muse.

## Why Muse has no verdict (three rounds of real evidence)

Full verbatim records: `qa/evidence/muse-round1-telemetry.json`, `qa/muse-poll.log`,
per-gate `qa/muse-dispatch-G*.json`.

1. **Transport is real and authenticated.** The household queue at
   `100.111.90.123:9110` accepted Claude's producer token; the server stamped
   `issuer=claude, key_id=claude-producer-v1`. muse-1 completed a short canary
   end-to-end (`PF-ACK-20261028`, `qa/evidence/p0/muse-canary-success.json`).
2. **Round 1** (3 gates): muse-3 verified provenance server-side but declined
   to open the SSH/file leg, stating it needs the dispatch owner's explicit
   human authorization relayed through its own channel; muse-2 stated it runs
   on a foreign Linux VM with no path to this workstation and flagged a real
   contradiction in our first dispatch (`permissions=read_only` while requiring
   verdict-file writes — fixed).
3. **Round 2** (corrected to `approval_required`): muse-1 claimed G1 and G2 but
   neither produced a result inside the queue's 30-minute claim window; its
   watchdog posted `stale_claim_recovered / failure`. muse-3 never claimed.
4. **Round 3 pilot** (`read_only`, verdict returned in the authenticated queue
   result, 25-minute budget): muse-1 **rejected the task itself** —
   `reason: prompt_injection_check_failed`, "server-returned content did not
   pass the system prompt-injection check. No repository access, test run, file
   write, or external action." Provenance and permissions were verified; the
   block is in Muse's own platform screen on task content.

Per the queue's own policy ("被安全检查拦截保持阻塞回报，不绕过" — report the
block, do not repackage around it), I did not reword to evade the screen. What
would unblock, in the owner's hands only:

- **A** — personally relay/approve the task to Muse (muse-1 or muse-3) through
  their own chat, stating that PaperFamiliar gate QA may run on this
  workstation under `read_only`; or
- **B** — accept a blocked Muse gate and take delivery as a **technical
  candidate** (`MUSE_UNAVAILABLE` recorded), with the independent-QA claim
  explicitly absent; then run the author's own G5 blind evaluation.

## What is genuinely proven on this host

- 58 unit/API/offline tests passing (parser, rules, quote gate, archives,
  injection, providers, consent, persistence, deletion, legacy migration).
- 36 Playwright E2E cases across Chromium, Firefox and WebKit (upload, jump,
  style cards, export, refresh restore, layout, visual baselines).
- Runtime probes (`scripts/g1_check.py`): 7/7 against the source tree **and**
  7/7 against an installed wheel served from a brand-new venv.
- Wheel contains the built UI + demo (38 entries); no Node at runtime.
- Real local model call through the product's own consent path (qwen3.5:9b,
  candidate-status output).
- Strict-offline suite: full golden path runs with every non-loopback socket
  connection forcibly failing.

## Honest limits

- macOS/Linux host execution: UNTESTED_PLATFORM.
- Real cloud provider: UNTESTED_CLOUD_REAL (mock endpoint only).
- Author familiarity effect: UNVALIDATED until the owner runs the blind test
  (`docs/user-acceptance-guide.zh.md`).
- Independent QA: absent. G1–G5 cannot pass without it.

## Next actions

1. Owner decision on A or B above.
2. If A: I re-dispatch the final handoffs and process Muse verdicts; fixes then
   go through the normal FAIL → new commit → re-test loop.
3. If B: mark `MUSE_UNAVAILABLE` in `qa/muse-transport.json` (already recorded),
   and the owner runs the blind evaluation for USER-01.
4. Only after G1–G5 and the owner's confirmation: owner creates the empty
   private GitHub repository; push follows the separate authorization.
