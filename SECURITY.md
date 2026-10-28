# Security policy

PaperFamiliar parses untrusted manuscripts and runs on a researcher's laptop. The security
model is in `docs/threat-model.md`.

## Reporting

Open a private security advisory in the repository once one exists, or contact the maintainer
directly. Do not include a real unpublished manuscript in a report; use a synthetic reproduction
that preserves the structure of the problem.

## Supported versions

Only the latest `0.1.x` line receives security fixes.

## Design commitments

- The HTTP server binds loopback and validates the `Host` header. State-changing requests need a
  per-process CSRF token; cross-origin requests are refused.
- No TeX is compiled. No shell command is executed from manuscript content.
- Archives are extracted with entry, size, ratio and depth limits; symlinks and special files are
  rejected.
- Includes cannot leave the workspace.
- Every finding passes an exact quote gate before it reaches the ledger.
- Strict offline mode is the default; cloud features require a per-request payload preview and
  explicit consent.
- Credentials are never written to logs, exports, the database or the repository.

## Known limitations

- The local API is protected by same-origin and CSRF checks, not by authentication; another
  process running as the same OS user can read the same files.
- A PDF preview is read-only and not sandboxed beyond the browser.
- Optional third-party integrations are outside this security boundary; review their licenses and
  network behavior before enabling them.
