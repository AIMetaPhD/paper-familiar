# qa/ — acceptance evidence

Governance: `04_ACCEPTANCE_MATRIX.csv` (47 checks), `schemas/` (v1.2),
`scripts/check_gates.py` (contract shape only). Protocol: the v1.2 handoff pack
`03_MUSE_QA_PROTOCOL.md`, summarized here for this repository.

## Files

- `muse-transport.json` — the real discovered Muse channel (household task
  queue via `queue_client.py --role producer --producer claude`), including the
  canary history: two rejections by muse-1's own safety screen (Chinese task
  wording) and one **successful** round trip (`PF-ACK-20261028`,
  `qa/evidence/p0/muse-canary-success.json`). The channel exists and works.
- `handoff-G1..G5.json` — implementer submissions, built by
  `scripts/make_handoff.py` from the gate selftest at a frozen commit. They
  carry `status: SUBMITTED`, never a pass claim; `failed_gates` lists what is
  not PASS.
- `muse-verdict-G1..G5.json` + `muse-report-G1..G5.md` — **only Muse may write
  these**. They do not exist yet; that is the honest current state, not an
  oversight to fill in.
- `evidence/G<n>/host-local/selftest.json` + per-check logs — implementer
  self-test evidence (commands, exit codes, environment). `g1_check-*.json`
  are the live-server runtime probes. `evidence/G1/windows11_x64|macos_*`
  directories from the v1.1 layout are retired.
- `evidence/G4/visual/<engine>/demo-workbench.png` — per-engine visual
  baselines; an E2E run that differs writes `*.diff.png` and reports xfail for
  human review instead of silently updating.
- `templates/*.template.json` — field references only. A template is never
  proof.
- `muse-dispatch-G<n>.json` — what was sent to which recipient, task ids,
  commit SHA; written by `scripts/muse_dispatch.py`.
- `offline-proof.log` — referenced by every handoff as
  `network_isolation_proof`; the socket-guard test suite is the substance.

## Rules this repo follows

1. Claude self-tests are always labelled `IMPLEMENTER_SELF_TEST` inside the
   JSON and cannot unlock gates.
2. QA-01/QA-02 are recorded `BLOCKED` by the implementer by design; USER-01 is
   `UNTESTED` until the product owner signs. No empty PASS defaults.
3. A FAIL or a new commit invalidates prior verdicts for that gate; Muse
   re-runs the full critical set on the new SHA.
4. Every handoff dispatch is English and safety-neutral (Chinese task text
   tripped muse-1's injection screen twice) and states its own non-authority:
   Muse must re-execute, not copy.
5. Evidence committed here contains only synthetic content. Before any
   publication of this repository, `qa/` is reviewed again for machine paths
   and log hygiene (SEC-PUBLISH).

## Current gate state (2026-10-29)

| Gate | Selftest (this host) | Muse verdict |
|---|---|---|
| G1 | 9/9 PASS | not requested yet |
| G2 | 12/12 PASS | not requested yet |
| G3 | running | pending |
| G4 | running | pending |
| G5 | partial by design (QA-01/02 BLOCKED, USER-01 UNTESTED) | pending |

`python scripts/check_gates.py --root .` currently exits **2** (no Muse
verdicts). That is the correct state.
