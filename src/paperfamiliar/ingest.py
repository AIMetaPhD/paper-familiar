"""Create workspaces from browser uploads, local paths, or the bundled demo."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from .service import analyze, demo_root, refresh_style
from .storage import (MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_UPLOAD_FILES, RunRecord,
                      StorageError, Store, Workspace, utcnow)
from .workspace import WorkspaceError, load_workspace, safe_extract_zip


def _safe_rel(name: str) -> str:
    cleaned = (name or "").replace("\\", "/").strip()
    if not cleaned:
        raise StorageError("empty file name")
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        raise StorageError(f"absolute path is not allowed: {name}")
    parts = Path(cleaned).parts
    if any(part in ("", "..", ".") for part in parts):
        raise StorageError(f"unsafe path: {name}")
    if len(parts) > 8:
        raise StorageError(f"path too deep: {name}")
    suffix = Path(cleaned).suffix.lower()
    if suffix not in {".tex", ".bib"}:
        raise StorageError(f"unsupported file type: {suffix or name}")
    return Path(*parts).as_posix()


def _extract_upload_zip(data: bytes, dest: Path) -> None:
    archive = dest / "upload.zip"
    archive.write_bytes(data)
    safe_extract_zip(archive, dest / "project")
    archive.unlink()


def _import_directory(store: Store, source: Path, *, label: str, kind: str,
                      assumptions: list[str] | None = None,
                      mode: str = "workspace", stored: bool = False) -> Workspace:
    workspace = load_workspace(source)
    scan = workspace.scan()
    payload = analyze(workspace, scan, assumptions=assumptions, mode=mode)
    run_id = uuid.uuid4().hex
    row = RunRecord(id=run_id, workspace_id=None, created_at=utcnow(), label=label,
                    root=workspace.root, main_path=workspace.main_path,
                    revision_id=workspace.revision_id, payload=payload)
    return store.create_workspace(label=label, kind=kind, root=workspace.root,
                                    revision_id=workspace.revision_id,
                                    main_path=workspace.main_path,
                                    source_path=str(source.resolve()),
                                    stats=payload["stats"], run=row, stored=stored)


def upload_workspace(store: Store, files: list[tuple[str, bytes]], *,
                     label: str | None = None, kind: str = "manuscript") -> Workspace:
    if not files:
        raise StorageError("no files were uploaded")
    if len(files) > MAX_UPLOAD_FILES:
        raise StorageError(f"{len(files)} files is over the limit of {MAX_UPLOAD_FILES}")
    total = sum(len(data) for _n, data in files)
    if total > MAX_TOTAL_BYTES:
        raise StorageError(f"upload is {total} bytes, over the {MAX_TOTAL_BYTES} limit")

    wid = uuid.uuid4().hex
    dest = store.workspaces_dir / wid
    dest.mkdir(parents=True, exist_ok=True)
    try:
        zips = [(n, d) for n, d in files if n.lower().endswith(".zip")]
        others = [(n, d) for n, d in files if not n.lower().endswith(".zip")]
        if len(zips) > 1:
            raise StorageError("upload one .zip at a time")
        if zips and others:
            raise StorageError("upload a .zip or a set of .tex/.bib files, not both")
        if zips:
            _extract_upload_zip(zips[0][1], dest)
            project = dest / "project"
        else:
            project = dest / "project"
            project.mkdir(parents=True, exist_ok=True)
            seen: set[str] = set()
            for name, data in others:
                if len(data) > MAX_FILE_BYTES:
                    raise StorageError(f"{name} is larger than {MAX_FILE_BYTES} bytes")
                rel = _safe_rel(name)
                if rel in seen:
                    raise StorageError(f"duplicate file name: {rel}")
                seen.add(rel)
                target = (project / rel).resolve()
                if not str(target).startswith(str(project.resolve()) + os.sep):
                    raise StorageError(f"upload escapes its directory: {name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        return _import_directory(store, project, label=label or "browser upload",
                                 kind=kind, stored=True)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def path_workspace(store: Store, source: Path, *, label: str | None = None,
                   kind: str = "manuscript") -> Workspace:
    """Import a folder, .zip or .tex file that already lives on this machine."""
    source = Path(source).expanduser()
    if not source.exists():
        raise StorageError(f"path does not exist: {source}")
    if source.is_file() and source.suffix.lower() == ".zip":
        wid = uuid.uuid4().hex
        dest = store.workspaces_dir / wid
        dest.mkdir(parents=True, exist_ok=True)
        try:
            safe_extract_zip(source, dest / "project")
            return _import_directory(store, dest / "project",
                                     label=label or source.name, kind=kind, stored=True)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise
    return _import_directory(store, source, label=label or source.name, kind=kind)


def demo_workspace(store: Store) -> Workspace:
    """Load the bundled demo, reusing an existing demo bundle when unchanged.

    Keyed by the demo's content revision id, so pressing "Reload demo" ten times
    returns the same workspace instead of accumulating copies.
    """
    root = demo_root()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise StorageError("demo data is not installed; run scripts/sync_demo.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    loaded = load_workspace(root / manifest["draft"])
    for existing in store.list_workspaces():
        if (existing.kind == "demo" and existing.revision_id == loaded.revision_id
                and existing.root.is_dir()):
            return existing
    record = _import_directory(store, root / manifest["draft"],
                               label=manifest.get("name", "PaperFamiliar demo"),
                               kind="demo",
                               assumptions=manifest.get("assumptions", []),
                               mode="demo")
    references: list[str] = []
    for item in manifest.get("history", []):
        ref = _import_directory(store, root / item["path"],
                                label=Path(item["path"]).name, kind="reference")
        # Demo fixtures carry no explicit section comments, so the manifest owns
        # the claim. This is stated in the run's assumptions, never implied.
        store.set_label(ref.id, "ALL", item.get("contribution", "unknown"))
        references.append(ref.id)
    if bool(manifest.get("draft_assume_primary", True)):
        # demo-only: the manifest (not a scanner feature) asserts authorship, and
        # the assumption is spelled out in run.assumptions below.
        store.set_label(record.id, "ALL", "sole_or_primary")
    run = store.load_run(record.run_id)
    assumptions = list(run.payload.get("assumptions", []))
    assumptions.append(
        "The demo's four reference papers are synthetic and are labelled as the demo "
        "author's own writing only to make the comparison visible. In a real workspace you "
        "mark each section yourself.")
    run.payload["assumptions"] = assumptions
    run.payload["style"]["reference_ids"] = references
    store.save_run(run)
    refresh_style(store, run, references)
    return store.get_workspace(record.id)  # type: ignore[return-value]


def list_workspaces(store: Store) -> list[dict]:
    from .service import workspace_row

    return [workspace_row(row) for row in store.list_workspaces()]
