"""Command line entry point for the local web app."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, metadata as metadata_module, providers
from .ingest import path_workspace
from .service import Store, data_dir, export_run, summary
from .storage import StorageError
from .workspace import WorkspaceError


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    app = create_app()
    app.state.port = args.port
    url = f"http://127.0.0.1:{args.port}"
    import socket as _socket

    with _socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            print(f"error: port {args.port} is already in use by another process.\n"
                  f"       Close it, or start with a different port: "
                  f"paperfamiliar serve --port {args.port + 1}\n"
                  f"       PaperFamiliar will not silently bind elsewhere or a public "
                  f"interface.", file=sys.stderr)
            return 7
    print(f"PaperFamiliar {__version__}")
    print(f"  open:      {url}")
    print(f"  data:      {data_dir()}")
    print("  network:   loopback only, no telemetry, same-origin UI")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level=args.log_level,
                    access_log=args.access_log)
    except OSError as exc:
        if getattr(exc, "winerror", None) in (10048,) or "10048" in str(exc):
            print(f"error: port {args.port} is already in use. "
                  f"Pass --port 8421 or close the other process.", file=sys.stderr)
            return 7
        raise
    return 0


def _audit(args: argparse.Namespace) -> int:
    store = Store(data_dir())
    try:
        workspace = path_workspace(store, Path(args.path).expanduser(), label=args.label,
                                   kind="manuscript")
    except (StorageError, WorkspaceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    run = store.run_for_workspace(workspace.id)
    data = summary(store, run)
    print(f"workspace: {workspace.id}")
    print(f"run:       {run.id}")
    print(f"revision:  {run.revision_id}")
    print(f"findings:  {len(data['findings'])}")
    for finding in data["findings"]:
        span = finding["source_span"]
        print(f"  [{finding['evidence_status']}] {finding['rule_id']} "
              f"{span['file_path']}:{span['start_line']}:{span['start_col']}")
    if args.export:
        result = export_run(store, run)
        print(f"exports:   {result['directory']}")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def _providers(args: argparse.Namespace) -> int:
    print(json.dumps(providers.status(), indent=2, ensure_ascii=False))
    return 0


def _metadata(args: argparse.Namespace) -> int:
    result = metadata_module.lookup_doi(args.doi, allow_network=args.allow_network,
                                        cache_dir=data_dir())
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    return 0 if result.status in {"source_corroborated", "unavailable_offline"} else 1


def _ask(args: argparse.Namespace) -> int:
    text = Path(args.text_file).read_text(encoding="utf-8")
    config = providers.cloud_provider() if args.cloud else providers.local_provider()
    if config is None:
        print("error: cloud provider is not configured via environment variables",
              file=sys.stderr)
        return 2
    store = providers.ConsentStore()
    preview = store.preview(args.task, text, config)
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    if not args.confirm:
        print("\nNot sent. Re-run with --confirm to authorize exactly this payload.",
              file=sys.stderr)
        return 0
    store.confirm(preview["consent_id"])
    result = providers.send(store, preview["consent_id"], args.task, text, config)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "candidate" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="paperfamiliar",
        description="Local-first LaTeX manuscript verification in your browser.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="start the local web app and open the browser")
    serve.add_argument("--port", type=int, default=8420)
    serve.add_argument("--host", default="127.0.0.1",
                       help="only 127.0.0.1/localhost is supported in v0.1")
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.add_argument("--access-log", action="store_true")
    serve.set_defaults(func=_serve)

    audit = sub.add_parser("audit", help="headless audit of a folder, .zip or .tex")
    audit.add_argument("path")
    audit.add_argument("--label", default=None)
    audit.add_argument("--export", action="store_true")
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(func=_audit)

    prov = sub.add_parser("providers", help="show local and cloud model availability")
    prov.set_defaults(func=_providers)

    meta = sub.add_parser("metadata", help="look up DOI metadata (offline unless allowed)")
    meta.add_argument("--doi", required=True)
    meta.add_argument("--allow-network", action="store_true")
    meta.set_defaults(func=_metadata)

    ask = sub.add_parser("ask", help="preview, then optionally send, a model request")
    ask.add_argument("--text-file", required=True)
    ask.add_argument("--task", default="List candidate writing issues. Quote exact spans.")
    ask.add_argument("--cloud", action="store_true")
    ask.add_argument("--confirm", action="store_true")
    ask.set_defaults(func=_ask)

    args = parser.parse_args(argv)
    if getattr(args, "host", "127.0.0.1") not in ("127.0.0.1", "localhost"):
        print("error: v0.1 binds loopback only. LAN/public serving is deliberately "
              "unsupported.", file=sys.stderr)
        return 8
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
