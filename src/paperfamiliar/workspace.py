"""Workspace loading: directories and untrusted ZIP archives, fail closed."""
from __future__ import annotations

import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .model import SourceFile, document_revision_id, sha256_bytes
from .scanner import DocumentScan, FileScan, scan_file

MAX_FILES = 2000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_RATIO = 200
MAX_DEPTH = 20
MAX_ENTRY_BYTES = 24 * 1024 * 1024
TEXT_SUFFIXES = {".tex", ".bib", ".sty", ".cls"}


class WorkspaceError(Exception):
    pass


@dataclass
class SecurityEvent:
    kind: str
    detail: str
    path: str | None = None
    source_span: dict | None = None


@dataclass
class Workspace:
    root: Path
    files: dict[str, SourceFile]
    bib_files: dict[str, SourceFile]
    main_path: str
    security_events: list[SecurityEvent] = field(default_factory=list)
    tempdir: tempfile.TemporaryDirectory | None = None
    strict_main: bool = False

    @property
    def bib_texts(self) -> dict[str, str]:
        return {path: sf.text for path, sf in self.bib_files.items()}

    @property
    def revision_id(self) -> str:
        return document_revision_id(self.files)

    def scan(self) -> DocumentScan:
        order = self.include_order()
        scans = {path: scan_file(self.files[path]) for path in order}
        return DocumentScan(files=scans, order=order)

    def include_order(self) -> list[str]:
        order: list[str] = []
        seen: set[str] = set()

        def visit(path: str) -> None:
            if path in seen:
                return
            seen.add(path)
            order.append(path)
            scan = scan_file(self.files[path])
            for inc in scan.includes:
                target = resolve_include(path, inc.target, self.files)
                if target is None:
                    self.security_events.append(
                        SecurityEvent(
                            kind="include.unresolved",
                            detail=f"include target is outside the workspace or missing: {inc.target}",
                            path=path,
                            source_span=inc.span.as_dict(),
                        )
                    )
                    continue
                visit(target)

        visit(self.main_path)
        # Files not reachable from main are still visible in the source browser,
        # except for a single-file workspace where sibling papers are unrelated.
        if not self.strict_main:
            for path in sorted(self.files):
                if path not in seen:
                    visit(path)
        return order


def _normalise_member(name: str) -> str:
    if "\\" in name:
        name = name.replace("\\", "/")
    if name.startswith("/") or name.startswith("//"):
        raise WorkspaceError(f"absolute path in archive: {name}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise WorkspaceError(f"parent traversal in archive: {name}")
    if len(pure.parts) > MAX_DEPTH:
        raise WorkspaceError(f"archive path too deep ({len(pure.parts)}): {name}")
    return pure.as_posix()


def _member_is_regular(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    if mode == 0:
        return not info.is_dir()
    return stat.S_ISREG(mode)


def safe_extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise WorkspaceError(f"archive has too many entries: {len(infos)}")
        total = sum(i.file_size for i in infos)
        if total > MAX_TOTAL_BYTES:
            raise WorkspaceError(f"archive expands to {total} bytes, over limit")
        for info in infos:
            if info.is_dir():
                continue
            name = _normalise_member(info.filename)
            if not _member_is_regular(info):
                raise WorkspaceError(f"archive entry is not a regular file: {name}")
            if info.file_size > MAX_ENTRY_BYTES:
                raise WorkspaceError(f"archive entry too large: {name}")
            ratio = info.file_size / max(info.compress_size, 1)
            if info.file_size > 1024 * 1024 and ratio > MAX_RATIO:
                raise WorkspaceError(f"suspicious compression ratio {ratio:.0f}: {name}")
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest.resolve()) + os.sep):
                raise WorkspaceError(f"entry escapes destination: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                written = 0
                while chunk := src.read(1 << 16):
                    written += len(chunk)
                    if written > MAX_ENTRY_BYTES:
                        raise WorkspaceError(f"entry exceeds size limit: {name}")
                    out.write(chunk)


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def _read_tree(root: Path) -> tuple[dict[str, SourceFile], dict[str, SourceFile], list[SecurityEvent]]:
    files: dict[str, SourceFile] = {}
    bib: dict[str, SourceFile] = {}
    events: list[SecurityEvent] = []
    root_resolved = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        resolved = path.resolve()
        if not str(resolved).startswith(str(root_resolved) + os.sep):
            events.append(SecurityEvent(kind="file.symlink_escape", detail=str(rel)))
            continue
        raw = resolved.read_bytes()
        text, _encoding = _decode(raw)
        sf = SourceFile(path=rel, raw=raw, text=text, sha256=sha256_bytes(raw))
        if path.suffix.lower() == ".bib":
            bib[rel] = sf
            continue
        files[rel] = sf
    return files, bib, events


def _pick_main(files: dict[str, SourceFile]) -> str:
    for candidate in ("main.tex", "paper.tex", "manuscript.tex"):
        if candidate in files:
            return candidate
    with_class = [
        path for path, sf in files.items()
        if "\\documentclass" in sf.text
    ]
    if with_class:
        return sorted(with_class)[0]
    if files:
        return sorted(files)[0]
    raise WorkspaceError("no .tex file found in the workspace")


def resolve_include(from_path: str, target: str, files: dict[str, SourceFile]) -> str | None:
    """Resolve a TeX include inside the workspace; never outside it."""
    cleaned = target.replace("\\", "/").strip()
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        return None
    base = PurePosixPath(from_path).parent
    for candidate in (cleaned, cleaned + ".tex"):
        rel = (base / candidate).as_posix()
        parts: list[str] = []
        escaped = False
        for part in PurePosixPath(rel).parts:
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    escaped = True
                    break
                parts.pop()
                continue
            parts.append(part)
        if escaped:
            return None
        normalised = "/".join(parts)
        if normalised in files:
            return normalised
    return None


def load_workspace(source: Path) -> Workspace:
    source = source.resolve()
    if not source.exists():
        raise WorkspaceError(f"path does not exist: {source}")
    if source.is_file() and source.suffix.lower() == ".tex":
        root = source.parent
        files, bib, events = _read_tree(root)
        if source.name not in files:
            raise WorkspaceError(f"cannot read {source.name}")
        return Workspace(root=root, files=files, bib_files=bib, main_path=source.name,
                         security_events=events, strict_main=True)
    if source.is_dir():
        root = source
        files, bib, events = _read_tree(root)
        if not files:
            raise WorkspaceError(f"no LaTeX sources found under {source}")
        return Workspace(root=root, files=files, bib_files=bib, main_path=_pick_main(files),
                         security_events=events)
    if source.suffix.lower() == ".zip":
        tmp = tempfile.TemporaryDirectory(prefix="paperfamiliar-")
        dest = Path(tmp.name)
        safe_extract_zip(source, dest)
        files, bib, events = _read_tree(dest)
        if not files:
            tmp.cleanup()
            raise WorkspaceError("archive contains no .tex file")
        return Workspace(root=dest, files=files, bib_files=bib, main_path=_pick_main(files),
                         security_events=events, tempdir=tmp)
    raise WorkspaceError("v0.1 accepts a directory, .tex/.bib bundle directory, or .zip")


def reload_file(workspace: Workspace, rel_path: str) -> SourceFile:
    """Re-read one file from disk and refuse if its hash changed."""
    path = (workspace.root / rel_path).resolve()
    if not str(path).startswith(str(workspace.root.resolve()) + os.sep):
        raise WorkspaceError("path escapes workspace")
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != workspace.files[rel_path].sha256:
        raise WorkspaceError(f"source changed on disk: {rel_path}")
    return workspace.files[rel_path]
