#!/usr/bin/env python3
"""Generate deterministic adversarial archives from the committed synthetic corpus.

Run from the repository root:  python fixtures/build_fixtures.py

Nothing here contains a real manuscript. The archives exist so that the workspace
loader can be tested against zip-slip, absolute paths, symlinks, bombs and deep
nesting without shipping dangerous binaries in git.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated"
DRAFT = ROOT / "draft_submission_论文 项目"

# Keep main.tex CRLF (OS-PATH-01 fixture). Every other source stays LF.
CRLF_FILE = DRAFT / "main.tex"


def ensure_crlf() -> None:
    raw = CRLF_FILE.read_bytes().replace(b"\r\n", b"\n")
    CRLF_FILE.write_bytes(raw.replace(b"\n", b"\r\n"))


def add_bytes(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def add_symlink(zf: zipfile.ZipFile, name: str, target: str) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3  # Unix
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    zf.writestr(info, target.encode())


def clean_project() -> None:
    path = OUT / "clean_project.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(DRAFT.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(DRAFT).as_posix())


def zip_slip() -> None:
    path = OUT / "zipslip.zip"
    with zipfile.ZipFile(path, "w") as zf:
        add_bytes(zf, "../../evil.txt", b"escaped\n")
        add_bytes(zf, "pkg/../../../evil2.txt", b"escaped\n")


def absolute() -> None:
    path = OUT / "absolute.zip"
    with zipfile.ZipFile(path, "w") as zf:
        add_bytes(zf, "/abs/evil.txt", b"absolute\n")
        add_bytes(zf, "C:/Windows/evil.txt", b"drive\n")
        add_bytes(zf, "\\\\server\\share\\evil.txt", b"unc\n")


def symlinks() -> None:
    path = OUT / "symlink.zip"
    with zipfile.ZipFile(path, "w") as zf:
        add_bytes(zf, "main.tex", b"\\documentclass{article}\n")
        add_symlink(zf, "link_to_passwd", "/etc/passwd")
        add_symlink(zf, "link_up", "../../outside")


def bomb() -> None:
    path = OUT / "bomb.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        add_bytes(zf, "zeros.bin", b"\0" * (80 * 1024 * 1024))


def deep() -> None:
    path = OUT / "deep.zip"
    with zipfile.ZipFile(path, "w") as zf:
        name = "/".join(["d"] * 80) + "/deep.tex"
        add_bytes(zf, name, b"deep\n")


def many() -> None:
    path = OUT / "many.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(5000):
            add_bytes(zf, f"files/{i:05d}.tex", b"x")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ensure_crlf()
    for old in OUT.glob("*.zip"):
        old.unlink()
    clean_project()
    zip_slip()
    absolute()
    symlinks()
    bomb()
    deep()
    many()
    for path in sorted(OUT.glob("*.zip")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{digest}  {path.name}  {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
