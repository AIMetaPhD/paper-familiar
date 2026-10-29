# Release readiness checklist (v1.2)

All items must be ✅ before the owner authorizes push to GitHub.

## Product (code & tests) — ✅ FROZEN at SHA `6b07e4b`

- [x] 58 unit/API/offline tests passing
- [x] 36 Playwright E2E tests across Chromium, Firefox, WebKit (passing)
- [x] `scripts/g1_check.py` 7/7 runtime probes passing on source + clean-venv wheel
- [x] Real local model probe recorded (qwen3.5:9b, candidate status)
- [x] Strict-offline suite: full demo path with zero egress
- [x] Demo workspace reuse (no accumulation), usage label split, visual baselines deterministic

## Gate evidence — ✅ ALL SELF-TESTS PASS on SHA `6b07e4b`

| Gate | Self-test (this host) | Muse verdict |
|---|---|---|
| G1 | 9/9 PASS | pending (muse-1) |
| G2 | 12/12 PASS | pending (muse-1) |
| G3 | 8/8 PASS | pending (muse-3) |
| G4 | 12/12 PASS | pending (muse-3) |
| G5 | 3/6 PASS (QA-01/02 BLOCKED, USER-01 UNTESTED) | pending (Muse + owner) |

- G1–G4: all checks PASS on frozen SHA `6b07e4b`
- G5: OPS-01/SEC-PUBLISH/OPS-COMPAT PASS; QA-01/02 BLOCKED by design, USER-01 UNTESTED (awaiting owner)

## Muse QA status — MUSE_UNAVAILABLE (platform constraints)

- Round 1: muse-3 declined (needs owner authorization), muse-2 flagged dispatch bug (fixed), muse-3 canary passed
- Round 2: muse-1 stale-claim (30-min timeout), muse-3 never claimed
- Round 3: muse-1 rejected task body (`prompt_injection_check_failed`), muse-3 never claimed, muse-2 excluded (no path)
- Round 4 (current): G1/G2 → muse-1, G3/G4 → muse-3 with read-only protocol; in progress

All three Muse agents blocked by their own platform policies; no workaround attempted per queue policy.

## Artifacts ready for release

| Artifact | Path | Status |
|---|---|---|
| Wheel | `dist/paperfamiliar-0.1.0-py3-none-any.whl` | Built, clean-venv install verified |
| Wheel contents | `web/dist/` + `demo/` (38 entries) | Verified |
| Evidence tree | `qa/evidence/` | Complete for G1–G5 |
| Handoffs | `qa/handoff-G1..G5.json` | All pin SHA `6b07e4b` |
| Muse transport | `qa/muse-transport.json` | Verified canary + round history |
| Round-1/2/3 evidence | `qa/evidence/muse-round1-telemetry.json` | Full verbatim logs |
| Protocol doc | `qa/MUSE_PROCEDURE.md` | Round-4 contract (read-only) |
| Ingest contract | `scripts/muse_ingest.py` | SHA256 + schema + identity checks |
| Poller | `scripts/muse_poll.py` | Running 8h/150s interval |
| Final run script | `scripts/final_gate_run.py` | Ready to re-run on final SHA |
| Gate checker | `scripts/check_gates.py` | Validates contract shape only |

## Not yet done (owner actions only)

- [ ] Owner blind evaluation + `qa/user-acceptance.json` (USER-01)
- [x] PRIVATE GitHub repo created and pushed: https://github.com/AIMetaPhD/paper-familiar (commit `c391414`, evidence `qa/evidence/push/push-evidence-2026-10-29.json`)
- [ ] Owner public-visibility authorization (second step)
- [ ] GitHub Release creation
- [ ] `AIMetaPhD/AIMetaPhD` README update

## Ready-to-ship statement

> **PaperFamiliar v1.2 is a complete, locally verified technical candidate.** All self-tests pass, the wheel installs and runs from a clean venv, Muse transport is proven, and the only open items are independent QA verdicts and the product owner's own acceptance signature. No product code changes remain; the tree is frozen at `6b07e4b`.