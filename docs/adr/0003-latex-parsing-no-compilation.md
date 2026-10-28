# ADR-0003: Static LaTeX scanning, never compilation of user source

- Status: accepted
- Date: 2026-10-28

## Context

Uploaded `.tex` is untrusted input. TeX is Turing-complete and `\write18`, file inclusion and macro recursion can reach outside the workspace. The spec forbids automatic compilation in v0.1. At the same time, the product's core value is an exact file/line/column jump to the author's source, so a scanner that guesses positions is worse than no scanner.

## Decision

- v0.1 never invokes a TeX engine, shell escape, BibTeX or any external command on user input.
- A custom structural scanner tokenizes LaTeX while tracking file, line and column. It understands comments, escapes, brace groups, `\input`/`\include` (workspace-relative only), `\cite`/`\ref`/`\label`, and environment boundaries.
- `pylatexenc` may be used as a supplementary Unicode/LaTeX decoder, but its output is never the source of a span.
- When a macro makes a location genuinely ambiguous, the scanner emits `unsupported`/`needs_review` rather than a guessed coordinate.
- `\input`/`\include` targets are resolved inside a canonical workspace root; absolute paths, `..` escapes, symlinks leaving the root, and remote references fail closed and are reported as security events.
- Archives are extracted with limits on entry count, total uncompressed size, compression ratio, nesting depth, and entry type; symlinks, device files and absolute or parent paths are rejected before extraction.

## Consequences

- Some legitimate custom macros will produce fewer findings. This is acceptable: the product promises evidence, not coverage.
- PDF preview is optional and read-only; no SyncTeX reverse mapping is promised.
- Any future compile sandbox is a separate, explicitly authorized feature, not a flag on this scanner.
