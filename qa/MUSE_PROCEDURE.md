# PaperFamiliar gate QA — procedure for Muse (read-only, verdict in queue result)

You are the independent black-box QA. The implementer's own tests are reference
material only; your verdict must come from what you personally executed.
Authorization context: the product owner relayed approval for this project's
gate QA on 2026-10-29, and the queue server verifies the dispatch signature
(issuer=claude, key_id=claude-producer-v1).

## Fixed facts

- Repository on the workstation you already SSH into with your normal account:
  `E:\ClaudeCodeFiles\MyProducts\PaperFamiliar\paper-familiar`
- Product code commit under test: the exact `commit_sha` field of the handoff
  file named in your queue task (nothing else).
- Handoff file for your gate: `qa/handoff-G1.json` … `qa/handoff-G5.json`,
  each with per-check expected/observed/evidence paths.

## Steps

1. In the repo: `git cat-file -e <sha>` and
   `git diff <sha> HEAD -- src web fixtures demo` — the diff must be empty
   (qa/ and docs/ may differ). Then prefer `git worktree add <temp dir> <sha>`
   for testing.
2. Create a fresh virtualenv OUTSIDE the repository. `pip install -e <worktree>`
   (or build the wheel and install it). For UI checks:
   `pip install playwright; playwright install chromium firefox webkit`.
3. Work through every check id in your handoff, in order. The reproduce route
   for each id is its evidence log plus the mapped pytest file; a fast overall
   pass is `python -m pytest -q --ignore=tests/e2e` then `python -m pytest
   tests/e2e -q`. Runtime probes: `python scripts/g1_check.py`.
4. Time-box yourself to 25 minutes from claim. If time runs short, post what
   you have: unfinished checks become UNTESTED or BLOCKED in the verdict. A
   partial honest verdict beats a silent expiry.
5. Verdict object (validate against `schemas/qa-verdict.schema.json`,
   schema_version "1.2"): copy `gate`, `commit_sha`, `run_id` from the
   handoff; `tester_identity` = your own name (muse-1/muse-3);
   `tester_origin` = "independent_muse"; per-check `status` PASS/FAIL/
   UNTESTED/BLOCKED with your own `observed` strings; `evidence_paths` may
   point inside the repo at existing files, or be [] when you kept your logs
   outside; `independent_run_proof_path` and `report_path` likewise (use "" if
   nothing was written in-repo).
6. Return your queue result:
   `{"status": "success", "evidence": {"gate": "<Gn>",
   "verdict": <the verdict object>,
   "verdict_sha256": "<sha256 of json.dumps(verdict, sort_keys=True,
   separators=(',',':')) encoded UTF-8>", "summary": "<one line>"}}`
   The implementer persists those exact bytes unedited; hash mismatches are
   rejected loudly.

## Hard rules

- Read-only in the repository: no writes, no git commit/push, no edits to
  fixtures or handoffs. Keep venvs/downloads/temp files outside the repo.
- Never run a TeX engine on any file.
- All manuscripts in this project are synthetic; never put a real manuscript
  into this repo or any queue message.
- Environment you lack (engine, permission) → BLOCKED with the reason, not a
  guess. Your judgment is yours; do not copy wording from self-test logs.
