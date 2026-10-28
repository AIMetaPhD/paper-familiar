# ADR-0002: Immutable source, half-open spans, three independent classification axes

- Status: accepted
- Date: 2026-10-28

## Context

The product must never show a finding that cannot be traced to the author's exact bytes. A finding may be mechanically provable, metadata-corroborated, heuristic, or semantic, and these are not interchangeable. The user may accept or dismiss a finding, but that decision must not silently upgrade the evidence level.

## Decision

- Every ingested file gets a SHA-256 over its raw bytes. A run binds to a document revision id derived from all file hashes.
- A `SourceSpan` is `file_path` (POSIX relative), 1-based `start_line`/`start_col`/`end_line`/`end_col`, an `exact_quote`, and `file_sha256`. The range is half-open; columns count Unicode code points, not UTF-16 units. A separate explicit conversion is used only when the editor needs UTF-16 ranges.
- A finding is admitted to the user ledger only if:
  1. the file hash matches the revision,
  2. the byte range contains the quote verbatim (no normalization), and
  3. the quote is non-empty and the range is inside the file.
- Three independent fields are stored: `finding_class` (mechanical | metadata | heuristic | semantic), `evidence_status` (verified_error | source_corroborated | candidate | insufficient_evidence | unavailable_offline | needs_expert_review | rejected_source_target_invalid), and `human_decision` (unreviewed | accepted | dismissed | needs_review).
- `human_decision=accepted` never changes `evidence_status`.
- Rejected AI findings go to an internal rejection log with the reason, never to the user-facing ledger.
- The source files are opened read-only. Accept, dismiss and export never write to the manuscript; the UI verifies the revision hash after every export.

## Consequences

- The quote gate is a hard precondition for every produced finding, including future model-generated ones.
- Line/column bugs become test failures rather than cosmetic issues, which is why the parser has explicit CRLF, Unicode and multi-file coverage.
- The report and the writing-agent export can state precisely what was mechanically verified and what was not.
