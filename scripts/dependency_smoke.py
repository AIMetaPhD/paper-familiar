#!/usr/bin/env python3
"""P0 dependency audit: prove what actually imports and works on this machine.

This script records evidence; it does not install anything. Run it inside the
project virtual environment:

    .venv/Scripts/python scripts/dependency_smoke.py --out docs/evidence/p0/dependency-smoke.json

Every check reports ok/error and the observed API surface, so a later change in
a third-party package is visible rather than silently assumed.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import json
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

CANDIDATES = [
    "papercheck",
    "academic-refchecker",
    "pylatexenc",
    "bibtexparser",
    "pystylometry",
    "faststylometry",
]


def dist_info(name: str) -> dict:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return {"installed": False}
    meta = dist.metadata
    return {
        "installed": True,
        "version": dist.version,
        "license": (meta.get("License") or "")[:200],
        "requires_python": meta.get("Requires-Python"),
        "requires": sorted(dist.requires or []),
        "files_top_level": sorted({str(p).split("/")[0].split("\\")[0] for p in (dist.files or [])})[:20],
    }


def check_pylatexenc() -> dict:
    from pylatexenc.latexwalker import LatexWalker

    walker = LatexWalker("A \\emph{b} c")
    nodes, _, _ = walker.get_latex_nodes()
    return {"ok": True, "parsed_nodes": len(nodes), "first_node": type(nodes[0]).__name__}


def check_bibtexparser() -> dict:
    import bibtexparser

    bib = "@article{k, title={T}, author={A}, year={2020}, journal={J}}"
    try:
        from bibtexparser.bparser import BibTexParser

        db = BibTexParser(common_strings=True).parse(bib)
        entries = db.entries
    except Exception:
        library = bibtexparser.parse_string(bib)
        entries = [{"key": e.key, "type": e.entry_type} for e in library.entries]
    return {"ok": True, "entries": entries}


def check_papercheck() -> dict:
    mod = importlib.import_module("papercheck")
    public = [n for n in dir(mod) if not n.startswith("_")]
    return {"ok": True, "module_file": getattr(mod, "__file__", None), "public_names": public[:40]}


def check_refchecker() -> dict:
    last = None
    for name in ("academic_refchecker", "refchecker"):
        try:
            mod = importlib.import_module(name)
            public = [n for n in dir(mod) if not n.startswith("_")]
            return {"ok": True, "module": name, "module_file": getattr(mod, "__file__", None),
                    "public_names": public[:40]}
        except Exception as exc:  # noqa: BLE001 - recorded as evidence
            last = f"{type(exc).__name__}: {exc}"
    raise RuntimeError(f"No importable module found ({last})")


def check_pystylometry() -> dict:
    mod = importlib.import_module("pystylometry")
    public = [n for n in dir(mod) if not n.startswith("_")]
    return {"ok": True, "module_file": getattr(mod, "__file__", None), "public_names": public[:40]}


def check_faststylometry() -> dict:
    mod = importlib.import_module("faststylometry")
    public = [n for n in dir(mod) if not n.startswith("_")]
    return {"ok": True, "module_file": getattr(mod, "__file__", None), "public_names": public[:40]}


CHECKERS = {
    "papercheck": check_papercheck,
    "academic-refchecker": check_refchecker,
    "pylatexenc": check_pylatexenc,
    "bibtexparser": check_bibtexparser,
    "pystylometry": check_pystylometry,
    "faststylometry": check_faststylometry,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {},
    }
    failures = 0
    for name in CANDIDATES:
        entry = dist_info(name)
        checker = CHECKERS.get(name)
        if entry["installed"] and checker:
            try:
                entry["smoke"] = checker()
            except Exception as exc:  # noqa: BLE001
                failures += 1
                entry["smoke"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                                  "traceback": traceback.format_exc()[-1500:]}
        else:
            entry["smoke"] = {"ok": False, "error": "not installed"}
        report["packages"][name] = entry
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    for name, entry in report["packages"].items():
        status = "OK" if entry["smoke"].get("ok") else "FAIL"
        print(f"{status:4} {name:22} {entry.get('version', '-')}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
