# Known issues backlog (implementer observations, 2026-10-29)

Recorded while the product tree is frozen for Muse round-2 execution
(`d01b27f`). None of these blocks a gate as far as our own tests show; each
gets fixed in one batch after the verdicts return, then re-verified, and the
gates are re-run and handoffs rebuilt on the final consolidated SHA. If Muse
reports them, they merge into this list.

1. **Demo workspace accumulation** — every `POST /api/demo` creates a fresh
   draft + 4 reference workspaces instead of reusing the bundle. Ten rows
   already sit in the Data list on this machine. Fix: key the demo bundle by
   its content revision id; return the existing workspace when it matches.
   Affects: nothing in the matrix directly, but wastes disk and confuses the
   user. Repro: click "Reload demo" three times, open Data, count rows.
2. **"sources 0 B" without context** — the usage line counts only stored upload
   copies (path/demo workspaces keep files in place, which is the design), but
   reads like "no data". Fix label: "stored copies X · exports Y · cache Z
   (path-imported folders are not duplicated)".
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
