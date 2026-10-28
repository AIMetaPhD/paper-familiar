"""Command line entry point."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .service import Store, build_run, export_run, load_demo, data_dir
from .workspace import WorkspaceError


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    app = create_app()
    app.state.port = args.port
    url = f"http://127.0.0.1:{args.port}"
    print(f"PaperFamiliar {__version__}")
    print(f"  local:     {url}")
    print(f"  data:      {data_dir()}")
    print("  network:   loopback only, no telemetry")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level=args.log_level,
                access_log=args.access_log)
    return 0


def _audit(args: argparse.Namespace) -> int:
    store = Store()
    try:
        run = build_run(store, Path(args.path).expanduser(), label=args.label)
    except WorkspaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = run.summary()
    print(f"run: {run.id}")
    print(f"revision: {run.revision_id}")
    print(f"findings: {len(summary['findings'])}")
    for finding in summary["findings"]:
        span = finding["source_span"]
        print(f"  [{finding['evidence_status']}] {finding['rule_id']} "
              f"{span['file_path']}:{span['start_line']}:{span['start_col']}")
    if args.export:
        result = export_run(store, run.id)
        print(f"exports: {result['directory']}")
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _demo(args: argparse.Namespace) -> int:
    store = Store()
    try:
        run = load_demo(store)
    except WorkspaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"run": run.id, "label": run.label, "findings": len(run.payload["findings"]),
                      "style_status": run.payload["style"]["baseline"]["status"]}, indent=2))
    if args.export:
        print(export_run(store, run.id)["directory"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paperfamiliar",
                                     description="Local-first LaTeX manuscript verification.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="start the local workbench")
    serve.add_argument("--port", type=int, default=8420)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.add_argument("--access-log", action="store_true")
    serve.set_defaults(func=_serve)

    audit = sub.add_parser("audit", help="run a headless audit on a directory or .zip")
    audit.add_argument("path")
    audit.add_argument("--label", default=None)
    audit.add_argument("--export", action="store_true")
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(func=_audit)

    demo = sub.add_parser("demo", help="run the bundled synthetic demo")
    demo.add_argument("--export", action="store_true")
    demo.set_defaults(func=_demo)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
