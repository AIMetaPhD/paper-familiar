"""Deterministic audit rules (V0) plus one clearly-labelled V2 heuristic.

Every finding carries its own scope statement. Nothing here predicts whether a
claim is true or whether a paper is any good.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .bibfile import BibEntry, parse_bib
from .evidence import span_from_offsets
from .model import Finding, SourceSpan
from .scanner import DocumentScan, Occurrence
from .workspace import Workspace

MATH_FUNCTIONS = {
    "sin", "cos", "tan", "log", "ln", "exp", "max", "min", "arg", "sup", "inf",
    "lim", "det", "dim", "rank", "trace", "softmax", "sigmoid", "relu", "argmax",
    "argmin", "mod", "gcd", "Pr", "mathbb", "mathcal", "mathrm", "text", "frac",
    "sqrt", "sum", "prod", "int", "partial", "nabla", "cdot", "times", "le", "ge",
    "leq", "geq", "in", "notin", "subset", "cup", "cap", "forall", "exists",
    "rightarrow", "leftarrow", "to", "mapsto", "infty", "alpha", "beta", "gamma",
    "delta", "epsilon", "lambda", "mu", "sigma", "theta", "phi", "psi", "omega",
}


@dataclass
class AuditResult:
    findings: list[Finding] = field(default_factory=list)
    security_events: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    bib_entries: list[BibEntry] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "findings": [f.as_dict() for f in self.findings],
            "security_events": self.security_events,
            "stats": self.stats,
        }


class _Ids:
    """Content-addressed finding ids.

    The id is derived from the rule, the file and the exact quoted text, so a
    review decision survives edits that only move a finding (line shifts) but is
    *not* inherited when the quoted source changes. Ordinal ids used to leak a
    decision onto a different problem of the same rule after a re-audit.
    """

    def __init__(self) -> None:
        self.occurrences: dict[tuple[str, str, str], int] = {}

    def next(self, rule: str, span: SourceSpan) -> str:
        key = (rule, span.file_path, span.exact_quote)
        self.occurrences[key] = self.occurrences.get(key, 0) + 1
        digest = hashlib.sha256("\x00".join(key).encode("utf-8")).hexdigest()[:10]
        n = self.occurrences[key]
        return f"F-{rule}-{digest}" + (f"-{n:02d}" if n > 1 else "")


def _finding(ids: _Ids, rule: str, *, finding_class: str, status: str, severity: str,
             claim: str, detail: str, span: SourceSpan, refs: list[dict] | None = None,
             scope: str | None = None, model_id: str | None = None) -> Finding:
    return Finding(
        id=ids.next(rule, span),
        rule_id=rule,
        finding_class=finding_class,
        evidence_status=status,
        severity=severity,
        claim=claim,
        detail=detail,
        span=span,
        evidence_refs=refs or [],
        rule_scope=scope,
        model_id=model_id,
    )


def audit(workspace: Workspace, scan: DocumentScan | None = None) -> AuditResult:
    scan = scan or workspace.scan()
    ids = _Ids()
    result = AuditResult()

    for event in workspace.security_events:
        result.security_events.append({
            "kind": event.kind, "detail": event.detail, "path": event.path,
            "source_span": event.source_span,
        })
    for path in scan.order:
        for event in scan.files[path].security_events:
            result.security_events.append(event)

    bib_entries: list[BibEntry] = []
    for path in sorted(workspace.bib_files):
        entries, problems = parse_bib(workspace.bib_files[path])
        bib_entries.extend(entries)
        for problem in problems:
            result.findings.append(_finding(
                ids, problem.kind, finding_class="mechanical", status="verified_error",
                severity="major", claim="The bibliography entry cannot be parsed.",
                detail=problem.detail, span=problem.span,
                scope="Static BibTeX structure only; no macro expansion.",
            ))
    known_keys = {entry.key for entry in bib_entries}
    result.bib_entries = bib_entries

    # cite.undefined_key
    for occ in scan.all_citations():
        if occ.key not in known_keys:
            result.findings.append(_finding(
                ids, "cite.undefined_key", finding_class="mechanical", status="verified_error",
                severity="major",
                claim="This citation key does not occur in any bibliography file in the workspace.",
                detail=f"Key '{occ.key}' is cited by \\{occ.command} but is absent from "
                       f"{len(workspace.bib_files)} .bib file(s).",
                span=occ.arg_span or occ.span,
                scope="Compares literal keys against parsed .bib entries; it does not "
                      "expand \\bibliography or external .bib paths.",
            ))

    # ref.undefined_label
    labels = list(scan.all_labels())
    label_map: dict[str, Occurrence] = {}
    for label in labels:
        if label.key in label_map:
            first = label_map[label.key]
            result.findings.append(_finding(
                ids, "label.duplicate", finding_class="mechanical", status="verified_error",
                severity="major",
                claim="This label is defined more than once.",
                detail=f"Label '{label.key}' first appears at "
                       f"{first.span.file_path}:{first.span.start_line}:{first.span.start_col}.",
                span=label.span,
                scope="Exact duplicate key comparison across included files.",
            ))
        else:
            label_map[label.key] = label

    for ref in scan.all_refs():
        if ref.key not in label_map:
            result.findings.append(_finding(
                ids, "ref.undefined_label", finding_class="mechanical", status="verified_error",
                severity="major",
                claim="This reference points to a label that is not defined in the document.",
                detail=f"\\{ref.command}{{{ref.key}}} has no matching \\label in the scanned files.",
                span=ref.arg_span or ref.span,
                scope="Included files only; labels generated by packages or external files "
                      "are out of scope.",
            ))

    # bib required fields
    for entry in bib_entries:
        required = {
            "article": ("author", "title", "journal", "year"),
            "inproceedings": ("author", "title", "booktitle", "year"),
            "conference": ("author", "title", "booktitle", "year"),
            "book": ("title", "publisher", "year"),
            "incollection": ("author", "title", "booktitle", "year"),
            "phdthesis": ("author", "title", "school", "year"),
            "mastersthesis": ("author", "title", "school", "year"),
            "techreport": ("author", "title", "institution", "year"),
        }.get(entry.entry_type)
        if not required or entry.span is None:
            continue
        missing = [name for name in required if name not in entry.fields]
        if missing:
            result.findings.append(_finding(
                ids, "bib.missing_required_field", finding_class="mechanical",
                status="verified_error", severity="minor",
                claim="This bibliography entry is missing a field required for its type.",
                detail=f"@{entry.entry_type}{{{entry.key}}} is missing: {', '.join(missing)}.",
                span=entry.span,
                scope="Required-field check only; it does not judge citation style.",
            ))

    # include resolution
    for path in scan.order:
        for inc in scan.files[path].includes:
            if _include_escapes(inc.target):
                result.security_events.append({
                    "kind": "include.path_escape",
                    "detail": f"include target escapes the workspace: {inc.target}",
                    "path": path, "source_span": inc.span.as_dict(),
                })
                result.findings.append(_finding(
                    ids, "security.include_escape", finding_class="mechanical",
                    status="verified_error", severity="critical",
                    claim="This include tries to reach outside the workspace.",
                    detail=f"\\input/\\include target '{inc.target}' is absolute or contains '..' "
                           "that leaves the workspace root. It was not followed.",
                    span=inc.span,
                    scope="Literal target inspection; no TeX expansion is performed.",
                ))

    # V2 heuristic: a math identifier used exactly once and never introduced in prose.
    prose_words = _prose_words(scan, workspace)
    occurrences = _math_identifiers(scan, workspace)
    for name, meta in occurrences.items():
        if meta["count"] != 1:
            continue
        if name in MATH_FUNCTIONS or name in prose_words:
            continue
        span = meta["span"]
        result.findings.append(_finding(
            ids, "notation.possibly_undefined", finding_class="heuristic", status="candidate",
            severity="info",
            claim="This math identifier appears only once and is never introduced in prose.",
            detail=f"'{name}' occurs once in math and not in the surrounding prose. This is a "
                   "heuristic reminder, not proof that the symbol is undefined.",
            span=span,
            scope="Single-occurrence heuristic. It cannot see macro definitions, scopes, or "
                  "notation introduced in another paper.",
        ))

    result.stats = {
        "files_scanned": len(scan.order),
        "bibliography_files": len(workspace.bib_files),
        "bib_entries": len(bib_entries),
        "citations": sum(len(f.citations) for f in scan.files.values()),
        "references": sum(len(f.refs) for f in scan.files.values()),
        "labels": len(labels),
        "sections": sum(len(f.sections) for f in scan.files.values()),
        "math_regions": sum(len(f.math_spans) for f in scan.files.values()),
        "findings": len(result.findings),
    }
    return result


def _include_escapes(target: str) -> bool:
    cleaned = target.replace("\\", "/").strip()
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        return True
    depth = 0
    for part in cleaned.split("/"):
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
        elif part not in ("", "."):
            depth += 1
    return False


def _prose_words(scan: DocumentScan, workspace: Workspace) -> set[str]:
    words: set[str] = set()
    for path in scan.order:
        sf = workspace.files[path]
        for start, end in scan.files[path].text_segments:
            words.update(re.findall(r"[A-Za-z][A-Za-z0-9]*", sf.text[start:end]))
    return words


IDENT = re.compile(r"(?<![\\A-Za-z])([A-Za-z][A-Za-z0-9]{1,24})(?![A-Za-z])")


def _math_identifiers(scan: DocumentScan, workspace: Workspace) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in scan.order:
        sf = workspace.files[path]
        for start, end in scan.files[path].math_spans:
            chunk = sf.text[start:end]
            # Mask commands and their braced arguments with spaces of the same
            # length so match offsets still index the original file.
            masked = re.sub(r"\\(?:begin|end|label|ref|eqref|cite)\s*\{[^}]*\}",
                            lambda m: " " * len(m.group(0)), chunk)
            masked = re.sub(r"\\[A-Za-z]+", lambda m: " " * len(m.group(0)), masked)
            for match in IDENT.finditer(masked):
                name = match.group(1)
                entry = found.setdefault(name, {"count": 0, "span": None})
                entry["count"] += 1
                if entry["span"] is None:
                    entry["span"] = span_from_offsets(sf, start + match.start(1), start + match.end(1))
    return found
