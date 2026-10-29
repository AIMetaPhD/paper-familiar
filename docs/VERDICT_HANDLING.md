# Muse verdict ingestion protocol (implementer side)

This document describes what happens after Muse posts a verdict in its queue result.

## Automatic ingestion (via `scripts/muse_poll.py`)

1. Poller sees task state = `finished` and fetches the full task with its `result` object.
2. Extracts `evidence.verdict` from the result, validates:
   - `gate` matches the task's gate
   - `commit_sha` matches the handoff file's `commit_sha`
   - `run_id` matches the handoff's `run_id`
   - `tester_identity` contains "muse" and `tester_origin` == "independent_muse"
   - `verdict_sha256` matches canonical JSON of the verdict object
3. If all pass, calls `scripts/muse_ingest.py` which:
   - Writes `qa/muse-verdict-Gn.json` (exact bytes from Muse)
   - Writes `qa/muse-report-Gn.md` (from `report_markdown` or fallback)
   - Writes `qa/muse-verdict-Gn.provenance.json` with transport metadata
   - Persists the exact bytes; never edits or reformats
3. Poller logs success/failure and continues polling remaining tasks.

## Manual fallback (if queue result loses the verdict)

Muse can paste the full verdict JSON in a second queue result with:
```
evidence.verdict_in_result = true
evidence.verdict_sha256 = "<sha256>"
```
The ingest script accepts this fallback, computes the hash, and proceeds identically.

## Post-ingestion (implementer side)

After all five gates have Muse verdicts:
1. `python scripts/check_gates.py --root .` returns 0
2. Run `scripts/final_gate_run.py` to re-run selftests on the final SHA and rebuild handoffs
3. Owner runs blind evaluation (USER-01) and signs `qa/user-acceptance.json`
4. Only then: owner creates empty private GitHub repo, gives URL + push authorization
5. Only with explicit second authorization: flip repo to Public, create Release, update `AIMetaPhD/AIMetaPhD`

## Failure modes

| Scenario | Action |
|---|---|
| Muse verdict JSON fails schema | Poller logs "invalid", task stays done; manual intervention needed |
| SHA mismatch | Poller rejects; Muse must re-result with correct hash |
| Gate/commit/run_id mismatch | Verdict rejected; wrong gate or wrong commit |
| Muse identity missing/fake | Rejected; only `muse-*` with `independent_muse` origin accepted |
| No verdict in result | Task marked "no verdict object"; continue polling |

The implementer never edits or composes a verdict — only transport, validation, and persistence.