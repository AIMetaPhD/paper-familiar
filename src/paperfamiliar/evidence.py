"""The quote gate.

Nothing reaches the user's ledger unless the span can be reproduced byte for byte
from the immutable source file at the stated line and column.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import SourceFile, SourceSpan


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str


def span_from_offsets(sf: SourceFile, start: int, end: int) -> SourceSpan:
    from .scanner import _span  # local import: one shared position convention

    return _span(sf, start, end)


def verify_span(sf: SourceFile, span: SourceSpan) -> GateResult:
    if not span.exact_quote:
        return GateResult(False, "empty_quote")
    if span.file_sha256 != sf.sha256:
        return GateResult(False, "file_hash_mismatch")
    if span.file_path != sf.path:
        return GateResult(False, "file_path_mismatch")
    try:
        start = sf.offset(span.start_line, span.start_col)
        end = sf.offset(span.end_line, span.end_col)
    except ValueError as exc:
        return GateResult(False, f"span_out_of_bounds: {exc}")
    if end <= start:
        return GateResult(False, "empty_range")
    actual = sf.text[start:end]
    if actual != span.exact_quote:
        return GateResult(False, "quote_mismatch")
    return GateResult(True, "verified")


def check_fabricated_finding(sf: SourceFile, item: dict) -> GateResult:
    """Validate an externally proposed finding before it may enter the ledger."""
    claimed_hash = item.get("file_sha256")
    if claimed_hash and claimed_hash != sf.sha256:
        return GateResult(False, "file_hash_mismatch")
    span = SourceSpan(
        file_path=item.get("file_path", sf.path),
        start_line=int(item["start_line"]),
        start_col=int(item["start_col"]),
        end_line=int(item["end_line"]),
        end_col=int(item["end_col"]),
        exact_quote=str(item.get("exact_quote", "")),
        file_sha256=sf.sha256,
    )
    return verify_span(sf, span)
