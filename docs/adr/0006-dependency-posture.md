# ADR-0006: Small dependency surface; third-party reuse only behind adapters

- Status: accepted
- Date: 2026-10-28

## Context

The plan names several third-party projects as candidates (`papercheck`, `academic-refchecker`, `pylatexenc`, `bibtexparser`, stylometry packages). Their presence on PyPI does not prove that their APIs, platform wheels or licenses fit. Heavy transitive trees also threaten offline installation.

## Decision

- Core runtime dependencies: FastAPI, uvicorn, pydantic, pylatexenc, bibtexparser. Each is pinned in `pyproject.toml` and locked with hashes.
- `papercheck` and `academic-refchecker` are integrated only through explicit adapters with a capability probe. If the import or the expected entry point fails, the adapter reports `unavailable` and the product continues with its own V0 rules.
- Stylometry libraries are optional experiment dependencies, not runtime requirements. The shipped fingerprint uses transparent, locally computed features.
- Any dependency without a permissive license, or without a working wheel for Windows x64 and macOS arm64, is not shipped.
- Every new dependency must pass `scripts/dependency_smoke.py` and be recorded in `docs/dependency-audit.md` with version, license and evidence.

## Consequences

- The shipped product stays installable offline from a wheel cache and has a small audit surface.
- Some capabilities are duplicated locally at low cost (e.g. citation scanning) rather than adopting an unstable interface.
- Optional integrations can be removed without breaking the core experience.
