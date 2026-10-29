"""Local persistence: workspaces, runs, decisions, labels and lifecycle.

Everything the product remembers lives under one visible data directory. The
browser never stores manuscript text. Deleting a workspace removes its copies,
derived caches and review state.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAX_UPLOAD_FILES = 400
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
ALLOWED_SUFFIXES = {".tex", ".bib", ".zip"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageError(Exception):
    pass


@dataclass
class Workspace:
    id: str
    label: str
    kind: str  # manuscript | reference | demo
    stored: bool  # a copy lives under the data directory
    root: Path
    created_at: str
    revision_id: str
    main_path: str
    source_path: str | None
    run_id: str
    stats: dict


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.workspaces_dir = data_dir / "workspaces"
        self.exports_dir = data_dir / "exports"
        self.cache_dir = data_dir / "cache"
        for path in (self.workspaces_dir, self.exports_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "paperfamiliar.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._migrate_legacy()
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL,
                root TEXT NOT NULL, created_at TEXT NOT NULL, revision_id TEXT NOT NULL,
                main_path TEXT NOT NULL, source_path TEXT, run_id TEXT NOT NULL,
                stats TEXT NOT NULL DEFAULT '{}', stored INTEGER NOT NULL DEFAULT 0)"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, created_at TEXT NOT NULL,
                label TEXT NOT NULL, root TEXT NOT NULL, main_path TEXT NOT NULL,
                revision_id TEXT NOT NULL, payload TEXT NOT NULL)"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS decisions (
                workspace_id TEXT NOT NULL, finding_id TEXT NOT NULL, decision TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY (workspace_id, finding_id))"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS labels (
                workspace_id TEXT NOT NULL, section_id TEXT NOT NULL, contribution TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY (workspace_id, section_id))"""
        )
        if "stored" not in {row[1] for row in self.db.execute("PRAGMA table_info(workspaces)")}:
            self.db.execute("ALTER TABLE workspaces ADD COLUMN stored INTEGER NOT NULL DEFAULT 0")
        self.db.commit()

    def _migrate_legacy(self) -> None:
        """v1.1 keyed decisions/labels/runs differently; v1.2 needs workspace_id.

        Rather than guess a mapping, pre-1.2 tables are moved aside to *_v11
        (never deleted) and fresh v1.2 tables are created by the caller. Old
        review decisions stay inspectable but are not mixed into the new schema.
        """
        tables = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        needs_move = []
        for name in ("runs", "decisions", "labels"):
            if name in tables and "workspace_id" not in {
                    row[1] for row in self.db.execute(f"PRAGMA table_info({name})")}:
                needs_move.append(name)
        if not needs_move:
            return
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS legacy_migrations "
            "(id INTEGER PRIMARY KEY, moved_tables TEXT NOT NULL, moved_at TEXT NOT NULL)")
        with self.db:
            for name in needs_move:
                self.db.execute(f"ALTER TABLE {name} RENAME TO {name}_v11")
            self.db.execute("INSERT INTO legacy_migrations (moved_tables, moved_at) "
                            "VALUES (?, ?)", (",".join(needs_move), utcnow()))

    # ---------- workspaces ----------

    def create_workspace(self, *, label: str, kind: str, root: Path, revision_id: str,
                         main_path: str, source_path: str | None, stats: dict,
                         run: RunRecord, stored: bool = False) -> Workspace:
        """Insert the workspace row and its run in one transaction."""
        workspace = Workspace(id=uuid.uuid4().hex, label=label, kind=kind, stored=stored,
                              root=root, created_at=utcnow(), revision_id=revision_id,
                              main_path=main_path, source_path=source_path,
                              run_id=run.id, stats=stats)
        run.workspace_id = workspace.id
        with self.db:
            self.db.execute(
                "INSERT INTO workspaces (id,label,kind,root,created_at,revision_id,"
                "main_path,source_path,run_id,stats,stored) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (workspace.id, workspace.label, workspace.kind, str(workspace.root),
                 workspace.created_at, workspace.revision_id, workspace.main_path,
                 workspace.source_path, workspace.run_id, json.dumps(stats),
                 1 if stored else 0),
            )
            self.db.execute(
                "INSERT INTO runs (id,workspace_id,created_at,label,root,main_path,"
                "revision_id,payload) VALUES (?,?,?,?,?,?,?,?)",
                (run.id, workspace.id, run.created_at, run.label, str(run.root),
                 run.main_path, run.revision_id,
                 json.dumps(run.payload, ensure_ascii=False)),
            )
        return workspace

    def save_run(self, run: "RunRecord") -> None:
        with self.db:
            self.db.execute(
                "UPDATE runs SET payload=?, revision_id=?, root=?, main_path=?, label=? WHERE id=?",
                (json.dumps(run.payload, ensure_ascii=False), run.revision_id, str(run.root),
                 run.main_path, run.label, run.id),
            )

    def load_run(self, run_id: str) -> "RunRecord":
        row = self.db.execute(
            "SELECT id,workspace_id,created_at,label,root,main_path,revision_id,payload "
            "FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(f"run not found: {run_id}")
        return RunRecord(id=row[0], workspace_id=row[1] or None, created_at=row[2], label=row[3],
                         root=Path(row[4]), main_path=row[5], revision_id=row[6],
                         payload=json.loads(row[7]))

    def run_for_workspace(self, workspace_id: str) -> "RunRecord":
        row = self.db.execute("SELECT run_id FROM workspaces WHERE id=?",
                              (workspace_id,)).fetchone()
        if not row:
            raise KeyError(f"workspace not found: {workspace_id}")
        return self.load_run(row[0])

    _WS_COLUMNS = ("id,label,kind,root,created_at,revision_id,main_path,source_path,"
                   "run_id,stats,stored")

    def _row_to_workspace(self, row) -> Workspace:
        return Workspace(id=row[0], label=row[1], kind=row[2], root=Path(row[3]),
                         created_at=row[4], revision_id=row[5], main_path=row[6],
                         source_path=row[7], run_id=row[8], stats=json.loads(row[9] or "{}"),
                         stored=bool(row[10]))

    def list_workspaces(self) -> list[Workspace]:
        rows = self.db.execute(
            f"SELECT {self._WS_COLUMNS} FROM workspaces ORDER BY created_at DESC").fetchall()
        return [self._row_to_workspace(row) for row in rows]

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        row = self.db.execute(
            f"SELECT {self._WS_COLUMNS} FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        return self._row_to_workspace(row) if row else None

    def delete_workspace(self, workspace_id: str) -> dict:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            raise KeyError(f"workspace not found: {workspace_id}")
        removed = {"workspace": workspace_id, "root": str(workspace.root), "run_id": workspace.run_id}
        with self.db:
            self.db.execute("DELETE FROM decisions WHERE workspace_id=?", (workspace_id,))
            self.db.execute("DELETE FROM labels WHERE workspace_id=?", (workspace_id,))
            self.db.execute("DELETE FROM runs WHERE id=?", (workspace.run_id,))
            self.db.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
        # A stored copy lives under the data directory and is removed with the row.
        # A workspace imported from a user path is only unlinked; the user's own
        # files are never deleted.
        if workspace.stored and workspace.root.is_dir():
            target = workspace.root.parent if workspace.root.name == "project" else workspace.root
            base = str(self.workspaces_dir.resolve())
            resolved = str(target.resolve())
            if resolved == base or resolved.startswith(base + os.sep):
                shutil.rmtree(target, ignore_errors=True)
                removed["deleted_directory"] = str(target)
            else:
                removed["deleted_directory"] = "refused: outside data directory"
        export_dir = self.exports_dir / workspace.run_id
        if export_dir.is_dir():
            shutil.rmtree(export_dir, ignore_errors=True)
            removed["deleted_exports"] = str(export_dir)
        return removed

    # ---------- review state ----------

    def decisions(self, workspace_id: str) -> dict[str, str]:
        return {fid: value for fid, value in self.db.execute(
            "SELECT finding_id,decision FROM decisions WHERE workspace_id=?", (workspace_id,))}

    def set_decision(self, workspace_id: str, finding_id: str, decision: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO decisions (workspace_id,finding_id,decision,updated_at) "
                "VALUES (?,?,?,?)", (workspace_id, finding_id, decision, utcnow()))

    def labels(self, workspace_id: str) -> dict[str, str]:
        return {sid: value for sid, value in self.db.execute(
            "SELECT section_id,contribution FROM labels WHERE workspace_id=?", (workspace_id,))}

    def set_label(self, workspace_id: str, section_id: str, contribution: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO labels (workspace_id,section_id,contribution,updated_at) "
                "VALUES (?,?,?,?)", (workspace_id, section_id, contribution, utcnow()))

    def usage(self) -> dict:
        def size(path: Path) -> int:
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0

        return {
            "data_dir": str(self.data_dir),
            "workspaces": self.db.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0],
            "runs": self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
            "stored_workspaces": self.db.execute(
                "SELECT COUNT(*) FROM workspaces WHERE stored=1").fetchone()[0],
            "path_workspaces": self.db.execute(
                "SELECT COUNT(*) FROM workspaces WHERE stored=0").fetchone()[0],
            "database_bytes": (self.data_dir / "paperfamiliar.sqlite3").stat().st_size
            if (self.data_dir / "paperfamiliar.sqlite3").is_file() else 0,
            "workspaces_bytes": size(self.workspaces_dir),
            "exports_bytes": size(self.exports_dir),
            "cache_bytes": size(self.cache_dir),
        }

    def clear_all(self) -> dict:
        removed = self.usage()
        for workspace in self.list_workspaces():
            self.delete_workspace(workspace.id)
        with self.db:
            self.db.execute("DELETE FROM runs")
            self.db.execute("DELETE FROM decisions")
            self.db.execute("DELETE FROM labels")
            self.db.execute("DELETE FROM workspaces")
        for path in (self.exports_dir, self.cache_dir):
            shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True, exist_ok=True)
        return removed


@dataclass
class RunRecord:
    id: str
    workspace_id: str | None
    created_at: str
    label: str
    root: Path
    main_path: str
    revision_id: str
    payload: dict

    def summary(self) -> dict:
        data = dict(self.payload)
        data.update(id=self.id, workspace_id=self.workspace_id, created_at=self.created_at,
                    label=self.label, main_path=self.main_path, revision_id=self.revision_id)
        return data
