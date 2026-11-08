"""Application service: analyze, persist, compare, export.

Layout of responsibilities:

- `analyze()` turns a loaded workspace into a self-describing payload. Prose per
  section is stored so style and navigation keep working after a restart.
- Reference papers (the author's own earlier work) are separate workspaces of
  kind `reference`; the style baseline is computed only from sections the author
  marked as their own primary writing.
- Review state (accept/dismiss, contribution labels) lives in SQLite keyed by
  workspace, never in the browser.
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import verify_span
from .fingerprint import (SectionText, build_baseline, build_sections, cognitive_skeleton,
                          drift_cards, navigate)
from .model import SourceSpan
from .report import build_agent_feedback, build_markdown_report, build_style_guide
from .rules import audit
from .storage import RunRecord, Store, Workspace
from .workspace import load_workspace


def data_dir() -> Path:
    override = os.environ.get("PAPERFAMILIAR_DATA")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PaperFamiliar"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "PaperFamiliar"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME",
                                   str(Path.home() / ".local/share"))) / "paperfamiliar"
    path.mkdir(parents=True, exist_ok=True)
    return path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "fixtures" / "corpus").is_dir():
            return parent
    return here.parent


def demo_root() -> Path:
    candidates = [
        Path(os.environ.get("PAPERFAMILIAR_DEMO", "")) if os.environ.get("PAPERFAMILIAR_DEMO") else None,
        Path(__file__).resolve().parent / "demo",          # installed / src tree
        repo_root() / "demo",                              # development machine
    ]
    for path in candidates:
        if path is not None and (path / "manifest.json").is_file():
            return path
    return Path(__file__).resolve().parent / "demo"


def _section_meta(section: SectionText) -> dict:
    return {
        "id": section.id,
        "title": section.title,
        "level": section.level,
        "role": section.role,
        "file_path": section.file_path,
        "heading_span": section.heading_span.as_dict(),
        "contribution": section.contribution,
        "author_approved": section.author_approved,
        "word_count": section.word_count,
        "sentence_count": len(section.sentences),
        "prose": section.prose,
    }


def _sections_from_payload(payload: dict, *, contribution_overrides: dict[str, str] | None = None,
                           blanket: str | None = None) -> list[SectionText]:
    rows = []
    for meta in payload.get("sections", []):
        contribution = (contribution_overrides or {}).get(
            meta["id"], blanket or meta["contribution"])
        rows.append(SectionText(
            id=meta["id"], title=meta["title"], level=meta["level"], role=meta["role"],
            file_path=meta["file_path"],
            heading_span=SourceSpan(**meta["heading_span"]),
            prose=meta.get("prose", ""), contribution=contribution,
            author_approved=contribution == "sole_or_primary",
            sentences=[],
        ))
        rows[-1].sentences = _split(rows[-1].prose)
    return rows


def _split(text: str) -> list[str]:
    from .fingerprint import split_sentences

    return split_sentences(text)


def analyze(workspace, scan, *, assumptions: list[str] | None = None,
            mode: str = "workspace") -> dict[str, Any]:
    """Audit a workspace and gate every finding against the immutable source."""
    result = audit(workspace, scan)
    admitted: list = []
    rejected: list[dict] = []
    for finding in result.findings:
        span = finding.span
        source = workspace.files.get(span.file_path) or workspace.bib_files.get(span.file_path)
        gate = verify_span(source, span) if source is not None else None
        if gate is not None and gate.ok:
            admitted.append(finding)
        else:
            rejected.append({
                "finding_id": finding.id, "rule_id": finding.rule_id,
                "reason": gate.reason if gate else "file_not_found",
                "claimed_span": span.as_dict(),
                "note": "Rejected findings stay in this log, never in the user's ledger.",
            })
    result.findings = admitted
    sections = build_sections(workspace, scan)
    files = [
        {"path": path, "sha256": sf.sha256, "bytes": len(sf.raw),
         "lines": len(sf.line_starts), "kind": kind}
        for kind, mapping in (("tex", workspace.files), ("bib", workspace.bib_files))
        for path, sf in sorted(mapping.items())
    ]
    return {
        "findings": [f.as_dict() for f in result.findings],
        "rejections": rejected,
        "security_events": result.security_events,
        "stats": result.stats,
        "sections": [_section_meta(s) for s in sections],
        "style": {
            "baseline": build_baseline([]).as_dict(),
            "drift": [],
            "reference_ids": [],
            "note": "Style differences are descriptive suggestions, not academic errors. "
                    "No similarity percentage is produced.",
        },
        "cognitive": cognitive_skeleton(workspace, scan, sections),
        "files": files,
        "bibliography_files": sorted(workspace.bib_files),
        "source_path": str(workspace.root),
        "assumptions": assumptions or [],
        "mode": mode,
    }


def refresh_style(store: Store, run: RunRecord, reference_ids: list[str],
                  *, topic_control: bool = True) -> dict:
    """Recompute the baseline from the author's approved sections and re-issue cards."""
    texts: list[str] = []
    used: list[dict] = []
    for wid in reference_ids:
        workspace = store.get_workspace(wid)
        if workspace is None or workspace.kind != "reference":
            used.append({"id": wid, "status": "missing"})
            continue
        try:
            ref_run = store.run_for_workspace(wid)
        except KeyError:
            used.append({"id": wid, "status": "no_run"})
            continue
        labels = store.labels(wid)
        blanket = labels.get("ALL")  # set by the demo bundler; real users label sections
        chunks = 0
        paper_sections: list[str] = []
        for section in ref_run.payload.get("sections", []):
            contribution = labels.get(section["id"], blanket or section["contribution"])
            if contribution == "sole_or_primary" and section.get("prose"):
                paper_sections.append(section["prose"])
                chunks += 1
        if paper_sections:
            # one text per paper: the abstention thresholds count papers, not sections
            texts.append("\n\n".join(paper_sections))
        used.append({"id": wid, "label": workspace.label, "sections_used": chunks,
                     "status": "ok" if chunks else "no_approved_sections"})
    baseline = build_baseline(texts)
    own_labels = store.labels(run.workspace_id or "")
    own_blanket = own_labels.get("ALL")
    sections = _sections_from_payload(run.payload, contribution_overrides=own_labels,
                                      blanket=own_blanket)
    cards = drift_cards(sections, baseline)
    style = {
        "baseline": baseline.as_dict(),
        "drift": cards,
        "reference_ids": reference_ids,
        "references": used,
        "topic_control": topic_control,
        "note": ("Differences are measured against the sections you marked as your own "
                 "primary writing. This is a description, not a score and not an error."),
    }
    run.payload["style"] = style
    store.save_run(run)
    return style


def summary(store: Store, run: RunRecord) -> dict:
    """Attach the durable human review state to a run payload."""
    data = run.summary()
    workspace_id = run.workspace_id or ""
    decisions = store.decisions(workspace_id)
    labels = store.labels(workspace_id)
    blanket = labels.get("ALL")  # only the demo bundler sets this; real users label sections
    for finding in data["findings"]:
        finding["human_decision"] = decisions.get(finding["id"], "unreviewed")
    for section in data["sections"]:
        contribution = labels.get(section["id"], blanket or section["contribution"])
        section["contribution"] = contribution
        section["author_approved"] = contribution == "sole_or_primary"
    return data


def file_text(store: Store, run: RunRecord, rel_path: str) -> dict:
    allowed = {row["path"] for row in run.payload["files"]}
    allowed |= set(run.payload.get("bibliography_files", []))
    if rel_path not in allowed:
        raise PermissionError("path is not part of this workspace")
    full = (run.root / rel_path).resolve()
    root = run.root.resolve()
    if full != root and not str(full).startswith(str(root) + os.sep):
        raise PermissionError("path escapes workspace")

    raw = full.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = next((row["sha256"] for row in run.payload["files"] if row["path"] == rel_path),
                    None)
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
    else:  # pragma: no cover - cp1252 replacement never raises
        text = raw.decode("latin-1")
    return {"path": rel_path, "text": text, "sha256": digest,
            "unchanged": expected is None or digest == expected}


def source_integrity(run: RunRecord) -> dict:
    """Compare the analyzed snapshot with the files on disk at export time.

    The run payload is immutable evidence of what was analyzed; this check makes
    a later source edit visible instead of silently exporting stale coordinates.
    """
    root = run.root.resolve()
    rows: list[dict] = []
    for expected in run.payload.get("files", []):
        rel = expected["path"]
        full = (root / rel).resolve()
        if full != root and not str(full).startswith(str(root) + os.sep):
            rows.append({"path": rel, "state": "unavailable", "expected_sha256": expected["sha256"],
                         "actual_sha256": None})
            continue
        try:
            digest = hashlib.sha256(full.read_bytes()).hexdigest()
        except OSError:
            rows.append({"path": rel, "state": "missing", "expected_sha256": expected["sha256"],
                         "actual_sha256": None})
            continue
        rows.append({"path": rel, "state": "unchanged" if digest == expected["sha256"] else "changed",
                     "expected_sha256": expected["sha256"], "actual_sha256": digest})
    states = {row["state"] for row in rows}
    if not rows:
        status = "unavailable"
    elif states == {"unchanged"}:
        status = "unchanged"
    else:
        status = "changed"
    return {"status": status, "checked_at": datetime.now(timezone.utc).isoformat(),
            "files": rows}


def export_run(store: Store, run: RunRecord) -> dict:
    data = summary(store, run)
    integrity = source_integrity(run)
    data["source_integrity"] = integrity
    out = store.exports_dir / run.id
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in (
        ("report.json", __import__("json").dumps(data, indent=2, ensure_ascii=False)),
        ("report.md", build_markdown_report(data)),
        ("agent-feedback.json", __import__("json").dumps(build_agent_feedback(data),
                                                         indent=2, ensure_ascii=False)),
        ("author-style-guide.md", build_style_guide(data)),
        ("cognitive-structure-profile.json",
         __import__("json").dumps(data["cognitive"], indent=2, ensure_ascii=False)),
    ):
        path = out / name
        path.write_text(content, encoding="utf-8")
        written.append(name)
    return {"directory": str(out), "files": written, "source_integrity": integrity}


def run_navigator(store: Store, run: RunRecord, query: str) -> dict:
    return navigate(query, _sections_from_payload(run.payload))


def workspace_row(workspace: Workspace) -> dict:
    return {
        "id": workspace.id, "label": workspace.label, "kind": workspace.kind,
        "stored": workspace.stored, "created_at": workspace.created_at, "revision_id": workspace.revision_id,
        "main_path": workspace.main_path, "run_id": workspace.run_id,
        "root": str(workspace.root), "stats": workspace.stats,
    }
