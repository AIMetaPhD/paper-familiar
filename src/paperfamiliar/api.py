"""Local HTTP API. Loopback only, same-origin only, no CORS, no telemetry."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .service import (Store, apply_decisions, build_run, export_run, file_text,
                      load_demo, run_navigator, data_dir)
from .workspace import WorkspaceError

ALLOWED_CONTRIBUTIONS = {"sole_or_primary", "coauthored", "not_primary", "unknown"}
ALLOWED_DECISIONS = {"unreviewed", "accepted", "dismissed", "needs_review"}


def web_dist() -> Path:
    return Path(__file__).resolve().parent / "web" / "dist"


class WorkspaceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    label: str | None = None


class DecisionRequest(BaseModel):
    finding_id: str
    decision: str


class LabelRequest(BaseModel):
    section_id: str
    contribution: str


class NavigateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="PaperFamiliar", version=__version__, docs_url=None, redoc_url=None)
    app.state.store = store or Store()
    app.state.csrf = secrets.token_urlsafe(24)
    app.state.port = 8420

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host", "")
        allowed = {f"127.0.0.1:{app.state.port}", f"localhost:{app.state.port}",
                   "127.0.0.1", "localhost"}
        if host not in allowed:
            return JSONResponse({"detail": "unexpected Host header"}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin:
                ok = any(origin == f"http://{h}" for h in allowed if ":" in h)
                if not ok:
                    return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
            if request.headers.get("x-pf-csrf") != app.state.csrf:
                return JSONResponse({"detail": "missing CSRF token"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "mode": "offline",
                "data_dir": str(data_dir())}

    def summary_for(run_id: str) -> dict:
        run = app.state.store.load_run(run_id)
        return apply_decisions(app.state.store, run.summary(), run_id)

    @app.post("/api/demo")
    def demo() -> dict:
        try:
            run = load_demo(app.state.store)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return summary_for(run.id)

    @app.post("/api/workspace")
    def open_workspace(body: WorkspaceRequest) -> dict:
        try:
            run = build_run(app.state.store, Path(body.path).expanduser(), label=body.label)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return summary_for(run.id)

    @app.get("/api/run/{run_id}")
    def get_run(run_id: str) -> dict:
        try:
            return summary_for(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/run/{run_id}/file")
    def get_file(run_id: str, path: str) -> dict:
        try:
            return file_text(app.state.store, run_id, path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=410, detail="file no longer exists") from exc

    @app.post("/api/run/{run_id}/decision")
    def decide(run_id: str, body: DecisionRequest) -> dict:
        if body.decision not in ALLOWED_DECISIONS:
            raise HTTPException(status_code=400, detail="unknown decision")
        try:
            run = app.state.store.load_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        known = {f["id"] for f in run.payload["findings"]}
        if body.finding_id not in known:
            raise HTTPException(status_code=404, detail="unknown finding")
        app.state.store.set_decision(run_id, body.finding_id, body.decision)
        return {"ok": True, "finding_id": body.finding_id, "decision": body.decision}

    @app.post("/api/run/{run_id}/label")
    def label(run_id: str, body: LabelRequest) -> dict:
        if body.contribution not in ALLOWED_CONTRIBUTIONS:
            raise HTTPException(status_code=400, detail="unknown contribution label")
        try:
            app.state.store.set_label(run_id, body.section_id, body.contribution)
        except Exception as exc:  # noqa: BLE001 - database errors surface to the UI
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/run/{run_id}/navigate")
    def navigator(run_id: str, body: NavigateRequest) -> dict:
        try:
            return run_navigator(app.state.store, run_id, body.query)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/run/{run_id}/export")
    def export(run_id: str) -> dict:
        try:
            return export_run(app.state.store, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/run/{run_id}/export/{name}")
    def export_file(run_id: str, name: str):
        allowed = {"report.json", "report.md", "agent-feedback.json",
                   "author-style-guide.md", "cognitive-structure-profile.json"}
        if name not in allowed:
            raise HTTPException(status_code=404, detail="unknown export")
        path = data_dir() / "exports" / run_id / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="export not generated yet")
        return FileResponse(path)

    dist = web_dist()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        page = dist / "index.html"
        if not page.is_file():
            return HTMLResponse(
                "<html><body style='font-family:system-ui;padding:2rem'>"
                "<h1>PaperFamiliar</h1><p>The web build is missing. Run "
                "<code>npm --prefix web install &amp;&amp; npm --prefix web run build</code>, "
                "then reload.</p></body></html>",
                status_code=503,
            )
        html = page.read_text(encoding="utf-8")
        html = html.replace("__PF_CSRF__", app.state.csrf)
        return HTMLResponse(html)

    return app
