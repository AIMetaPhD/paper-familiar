"""Application service: load, audit, fingerprint, persist, export."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bibfile import parse_bib
from .fingerprint import (Baseline, SectionText, build_baseline, build_sections,
                          cognitive_skeleton, drift_cards, navigate)
from .evidence import verify_span
from .model import Finding
from .report import build_agent_feedback, build_markdown_report, build_style_guide
from .rules import audit
from .workspace import Workspace, WorkspaceError, load_workspace


def data_dir() -> Path:
    override = os.environ.get("PAPERFAMILIAR_DATA")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PaperFamiliar"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "PaperFamiliar"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "paperfamiliar"
    path.mkdir(parents=True, exist_ok=True)
    return path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "fixtures" / "corpus").is_dir():
            return parent
    return here.parent


def demo_root() -> Path:
    bundled = Path(__file__).resolve().parent / "demo"
    if (bundled / "manifest.json").is_file():
        return bundled
    return repo_root() / "demo"


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "paperfamiliar.sqlite3"
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, label TEXT NOT NULL,
            root TEXT NOT NULL, main_path TEXT NOT NULL, revision_id TEXT NOT NULL,
            payload TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS decisions (
            run_id TEXT NOT NULL, finding_id TEXT NOT NULL, decision TEXT NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY (run_id, finding_id))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS labels (
            run_id TEXT NOT NULL, section_id TEXT NOT NULL, contribution TEXT NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY (run_id, section_id))""")
        self.db.commit()

    def save_run(self, run: "Run") -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO runs (id,created_at,label,root,main_path,revision_id,payload) "
                "VALUES (?,?,?,?,?,?,?)",
                (run.id, run.created_at, run.label, str(run.root), run.main_path,
                 run.revision_id, json.dumps(run.payload, ensure_ascii=False)),
            )

    def load_run(self, run_id: str) -> "Run":
        row = self.db.execute(
            "SELECT id,created_at,label,root,main_path,revision_id,payload FROM runs WHERE id=?",
            (run_id,)).fetchone()
        if not row:
            raise KeyError(f"run not found: {run_id}")
        return Run(id=row[0], created_at=row[1], label=row[2], root=Path(row[3]),
                   main_path=row[4], revision_id=row[5],
                   payload=json.loads(row[6]))

    def decisions(self, run_id: str) -> dict[str, str]:
        return {fid: decision for fid, decision in self.db.execute(
            "SELECT finding_id,decision FROM decisions WHERE run_id=?", (run_id,))}

    def set_decision(self, run_id: str, finding_id: str, decision: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO decisions (run_id,finding_id,decision,updated_at) "
                "VALUES (?,?,?,?)",
                (run_id, finding_id, decision, datetime.now(timezone.utc).isoformat()))

    def labels(self, run_id: str) -> dict[str, str]:
        return {sid: value for sid, value in self.db.execute(
            "SELECT section_id,contribution FROM labels WHERE run_id=?", (run_id,))}

    def set_label(self, run_id: str, section_id: str, contribution: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO labels (run_id,section_id,contribution,updated_at) "
                "VALUES (?,?,?,?)",
                (run_id, section_id, contribution, datetime.now(timezone.utc).isoformat()))


@dataclass
class Run:
    id: str
    created_at: str
    label: str
    root: Path
    main_path: str
    revision_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict:
        data = dict(self.payload)
        data.update(id=self.id, created_at=self.created_at, label=self.label,
                    main_path=self.main_path, revision_id=self.revision_id)
        return data


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
    }


def build_run(store: Store, source: Path, *, label: str | None = None,
              history: list[tuple[Path, str]] | None = None,
              assume_draft_primary: bool = False,
              assumptions: list[str] | None = None,
              max_history_papers: int = 10) -> Run:
    workspace = load_workspace(source)
    scan = workspace.scan()
    result = audit(workspace, scan)
    # Hard gate: a finding may enter the ledger only if its quote is reproduced
    # byte for byte from the immutable file at the stated location.
    admitted = []
    rejected = []
    for finding in result.findings:
        span = finding.span
        sf = workspace.files.get(span.file_path) or workspace.bib_files.get(span.file_path)
        gate = verify_span(sf, span) if sf is not None else None
        if gate is not None and gate.ok:
            admitted.append(finding)
        else:
            rejected.append({"finding_id": finding.id, "rule_id": finding.rule_id,
                             "reason": gate.reason if gate else "file_not_found",
                             "claimed_span": span.as_dict()})
    result.findings = admitted
    sections = build_sections(workspace, scan)
    for section in sections:
        if assume_draft_primary and section.contribution == "unknown":
            section.contribution = "sole_or_primary"
            section.author_approved = True

    history_texts: list[str] = []
    history_meta: list[dict] = []
    for path, contribution in (history or [])[:max_history_papers]:
        try:
            hist_ws = load_workspace(path)
            hist_scan = hist_ws.scan()
            hist_sections = build_sections(hist_ws, hist_scan)
        except WorkspaceError as exc:
            history_meta.append({"path": str(path), "status": "unavailable", "detail": str(exc)})
            continue
        used = 0
        paper_chunks: list[str] = []
        for section in hist_sections:
            if contribution == "sole_or_primary" and section.contribution == "unknown":
                section.contribution = "sole_or_primary"
                section.author_approved = True
            if section.author_approved:
                paper_chunks.append(section.prose)
                used += 1
        if paper_chunks:
            history_texts.append("\n\n".join(paper_chunks))
        history_meta.append({"path": path.name, "contribution": contribution,
                             "sections_used": used})

    baseline = build_baseline(history_texts)
    cards = drift_cards(sections, baseline)
    cognitive = cognitive_skeleton(workspace, scan, sections)

    payload = {
        "findings": [f.as_dict() for f in result.findings],
        "security_events": result.security_events,
        "rejections": rejected,
        "stats": result.stats,
        "sections": [_section_meta(s) for s in sections],
        "style": {
            "baseline": baseline.as_dict(),
            "drift": cards,
            "history": history_meta,
            "note": "Style differences are descriptive suggestions, not academic errors. "
                    "No similarity percentage is produced.",
        },
        "cognitive": cognitive,
        "files": [
            {"path": path, "sha256": sf.sha256, "bytes": len(sf.raw),
             "lines": len(sf.line_starts), "kind": kind}
            for kind, mapping in (("tex", workspace.files), ("bib", workspace.bib_files))
            for path, sf in sorted(mapping.items())
        ],
        "bibliography_files": sorted(workspace.bib_files),
        "source_path": str(source.resolve()),
        "assumptions": assumptions or [],
        "mode": "demo" if assumptions else "workspace",
    }
    run = Run(id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
              label=label or source.name, root=workspace.root, main_path=workspace.main_path,
              revision_id=workspace.revision_id, payload=payload)
    store.save_run(run)
    return run


def load_demo(store: Store) -> Run:
    root = demo_root()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise WorkspaceError("demo data is not installed; run scripts/sync_demo.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    history: list[tuple[Path, str]] = []
    for item in manifest.get("history", []):
        history.append((root / item["path"], item.get("contribution", "unknown")))
    draft = root / manifest["draft"]
    return build_run(store, draft, label=manifest.get("name", "PaperFamiliar demo"),
                     history=history,
                     assume_draft_primary=bool(manifest.get("draft_assume_primary", True)),
                     assumptions=manifest.get("assumptions", []))


def file_text(store: Store, run_id: str, rel_path: str) -> dict:
    run = store.load_run(run_id)
    allowed = {row["path"] for row in run.payload["files"]}
    allowed |= set(run.payload.get("bibliography_files", []))
    if rel_path not in allowed:
        raise PermissionError("path is not part of this workspace")
    full = (run.root / rel_path).resolve()
    if not str(full).startswith(str(run.root.resolve()) + os.sep) and full != run.root.resolve():
        raise PermissionError("path escapes workspace")
    raw = full.read_bytes()
    import hashlib

    digest = hashlib.sha256(raw).hexdigest()
    expected = next((row["sha256"] for row in run.payload["files"] if row["path"] == rel_path), None)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return {"path": rel_path, "text": text, "sha256": digest,
            "unchanged": expected is None or digest == expected}


def apply_decisions(store: Store, summary: dict, run_id: str) -> dict:
    decisions = store.decisions(run_id)
    labels = store.labels(run_id)
    for finding in summary["findings"]:
        finding["human_decision"] = decisions.get(finding["id"], "unreviewed")
    for section in summary["sections"]:
        if section["id"] in labels:
            section["contribution"] = labels[section["id"]]
    return summary


def export_run(store: Store, run_id: str) -> dict:
    run = store.load_run(run_id)
    summary = apply_decisions(store, run.summary(), run_id)
    out = data_dir() / "exports" / run_id
    out.mkdir(parents=True, exist_ok=True)
    report_json = out / "report.json"
    report_md = out / "report.md"
    agent = out / "agent-feedback.json"
    guide = out / "author-style-guide.md"
    cognitive = out / "cognitive-structure-profile.json"
    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_md.write_text(build_markdown_report(summary), encoding="utf-8")
    agent.write_text(json.dumps(build_agent_feedback(summary), indent=2, ensure_ascii=False),
                     encoding="utf-8")
    guide.write_text(build_style_guide(summary), encoding="utf-8")
    cognitive.write_text(json.dumps(summary["cognitive"], indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return {"directory": str(out),
            "files": [p.name for p in (report_json, report_md, agent, guide, cognitive)]}


def run_navigator(store: Store, run_id: str, query: str) -> dict:
    run = store.load_run(run_id)
    rebuild = []
    for meta in run.payload["sections"]:
        rebuild.append(SectionText(
            id=meta["id"], title=meta["title"], level=meta["level"], role=meta["role"],
            file_path=meta["file_path"], heading_span=_span_from_dict(meta["heading_span"]),
            prose="", contribution=meta["contribution"],
            author_approved=meta["author_approved"],
        ))
    # Navigator body matching needs prose; read it back from the source files.
    workspace = load_workspace(Path(run.payload["source_path"]))
    scan = workspace.scan()
    fresh = {s.id: s for s in build_sections(workspace, scan)}
    for section in rebuild:
        if section.id in fresh:
            section.prose = fresh[section.id].prose
    return navigate(query, rebuild)


def _span_from_dict(data: dict):
    from .model import SourceSpan

    return SourceSpan(**data)
