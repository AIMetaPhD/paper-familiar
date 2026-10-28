"""Core data types shared by the scanner, rules, API and reports.

The invariants here are the product contract: a span is half-open, columns are
1-based Unicode code points, and a finding is only usable when its quote matches
the immutable source bytes at the stated location.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceSpan:
    file_path: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    exact_quote: str
    file_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "exact_quote": self.exact_quote,
            "file_sha256": self.file_sha256,
        }


@dataclass
class SourceFile:
    path: str  # POSIX path relative to the workspace root
    raw: bytes
    text: str
    sha256: str
    line_starts: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.line_starts:
            self.line_starts = compute_line_starts(self.text)

    def offset(self, line: int, col: int) -> int:
        if line < 1 or line > len(self.line_starts):
            raise ValueError(f"line {line} outside {self.path}")
        start = self.line_starts[line - 1]
        line_text = self.text[start:].split("\n", 1)[0].rstrip("\r")
        if col < 1 or col > len(line_text) + 1:
            raise ValueError(f"column {col} outside line {line} of {self.path}")
        return start + col - 1

    def slice(self, start: int, end: int) -> str:
        return self.text[start:end]


@dataclass
class Finding:
    id: str
    rule_id: str
    finding_class: str  # mechanical | metadata | heuristic | semantic
    evidence_status: str
    severity: str
    claim: str
    detail: str
    span: SourceSpan
    human_decision: str = "unreviewed"
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    model_id: str | None = None
    rule_scope: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "finding_class": self.finding_class,
            "evidence_status": self.evidence_status,
            "human_decision": self.human_decision,
            "severity": self.severity,
            "claim": self.claim,
            "detail": self.detail,
            "source_span": self.span.as_dict(),
            "evidence_refs": self.evidence_refs,
            "model_id": self.model_id,
            "rule_scope": self.rule_scope,
        }


def compute_line_starts(text: str) -> list[int]:
    starts = [0]
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "\r":
            if i + 1 < length and text[i + 1] == "\n":
                i += 1
            starts.append(i + 1)
        elif ch == "\n":
            starts.append(i + 1)
        i += 1
    return starts


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_revision_id(files: dict[str, SourceFile]) -> str:
    """Stable aggregate hash over path and bytes, independent of dict order."""
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(files[path].raw)
        h.update(b"\0")
    return h.hexdigest()
