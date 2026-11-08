# Known issues backlog (implementer observations, 2026-10-29)

Recorded while the product tree is frozen for Muse round-2 execution
(`d01b27f`). None of these blocks a gate as far as our own tests show; each
gets fixed in one batch after the verdicts return, then re-verified, and the
gates are re-run and handoffs rebuilt on the final consolidated SHA. If Muse
reports them, they merge into this list.

1. **Demo workspace accumulation** — FIXED (9dc84f9): `demo_workspace` now
   reuses the existing bundle keyed by content revision; tests cover reload
   identity and decision persistence.
2. **"sources 0 B" without context** — FIXED (9dc84f9): usage now reports
   "stored copies · exports · cache · N path-imported folder(s) stay where
   they are".
3. **Reference modal opened from landing upload** shows, but there is no
   in-workbench affordance to *re-open* the section-labeling dialog for a
   reference once you left it; the checkbox list is there but the "label
   sections" button only appears per row in the Style tab (works) — verify a
   Muse pass covers discoverability, not just presence.
4. **Metadata UI absent** — the DOI lookup endpoint exists with full offline
   semantics and tests, but no panel exposes it yet. v1.2 P2 lists
   "quote gate + auditable structured report" as the required UI, and the
   matrix has no metadata-UI check (EVD-02 passes at API level), so this is a
   planned enhancement, not a gap against the matrix; flag it so Muse does not
   have to guess why the settings mention network lookups that the UI never
   triggers.
5. **Re-audit on a path-imported workspace whose folder changed** returns 410
   with the workspace's own error string — good — but the UI surfaces it only
   as a dismissable banner. Acceptable; noted for polish.

Fix-order after verdicts: 1 → 2 → 3 (verify) → commit → full pytest + g1 +
e2e rerun → regenerate selftests/handoffs on the final SHA → G5 dispatch →
then, and only then, the user-acceptance step.

## Post-freeze fixes (2026-11-09)

Found by the state-machine inventory (`docs/state-machines.md`), fixed after the
technical candidate was delivered:

6. **Review decisions inherited by different findings** — FIXED: finding IDs are
   now content-addressed (`rule + file + exact quote`), so a line shift keeps the
   decision and a changed quote resets it to `unreviewed`. Regression test
   `test_finding_ids_are_content_addressed_across_reaudits`.
7. **Export did not re-check source hashes** — FIXED: `source_integrity` is
   computed at export time and declared in `report.json`, `report.md`,
   `agent-feedback.json` and the export modal. Regression test
   `test_export_declares_source_drift`.

Both are product changes after the 6b07e4b freeze. Gate handoffs and
`qa/user-acceptance.json` remain pinned to `6b07e4b` as historical evidence;
the owner should evaluate the current HEAD.
