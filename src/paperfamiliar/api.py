"""Local HTTP API for the PaperFamiliar web app.

Loopback only. Same-origin only. Mutations require the CSRF token. Every
response that shows the manuscript is bound to a persisted workspace whose
original bytes are hashed and never written to.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, providers
from . import metadata as metadata_module
from .ingest import demo_workspace, list_workspaces, path_workspace, upload_workspace
from .service import (Store, analyze, data_dir, export_run, file_text, refresh_style,
                      run_navigator, summary)
from .storage import StorageError
from .workspace import WorkspaceError, load_workspace

ALLOWED_CONTRIBUTIONS = {"sole_or_primary", "coauthored", "not_primary", "unknown"}
ALLOWED_DECISIONS = {"unreviewed", "accepted", "dismissed", "needs_review"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def web_dist() -> Path:
    return Path(__file__).resolve().parent / "web" / "dist"


class WorkspacePathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    label: str | None = None
    kind: str = "manuscript"


class ReferenceRequest(BaseModel):
    workspace_id: str
    section_id: str
    contribution: str


class StyleRequest(BaseModel):
    reference_ids: list[str] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    finding_id: str
    decision: str


class NavigateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class ModelPreviewRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    text: str = Field(min_length=1, max_length=200_000)
    provider: str = "local"


class ModelSendRequest(ModelPreviewRequest):
    consent_id: str
    confirm: bool = False


class MetadataRequest(BaseModel):
    doi: str = Field(min_length=5, max_length=300)
    allow_network: bool = False


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="PaperFamiliar", version=__version__, docs_url=None, redoc_url=None)
    app.state.store = store or Store(data_dir())
    app.state.csrf = secrets.token_urlsafe(24)
    app.state.port = 8420
    app.state.consents = providers.ConsentStore()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").strip().lower()
        allowed = {f"127.0.0.1:{app.state.port}", f"localhost:{app.state.port}",
                   "127.0.0.1", "localhost"}
        if host not in allowed:
            return JSONResponse({"detail": "unexpected Host header"}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = (request.headers.get("origin") or "").strip().lower()
            if origin and origin not in {f"http://{h}" for h in allowed if ":" in h}:
                return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
            if request.headers.get("x-pf-csrf") != app.state.csrf:
                return JSONResponse({"detail": "missing CSRF token"}, status_code=403)
        return await call_next(request)

    def run_for(workspace_id: str):
        store: Store = app.state.store
        try:
            return store.run_for_workspace(workspace_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ---------- health / meta ----------

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "mode": "offline",
                "bound": f"127.0.0.1:{app.state.port}", "csrf": True}

    @app.get("/api/session")
    def session() -> dict:
        return {"csrf": app.state.csrf, "version": __version__,
                "data_dir": str(app.state.store.data_dir)}

    # ---------- workspaces ----------

    @app.get("/api/workspaces")
    def workspaces() -> dict:
        return {"workspaces": list_workspaces(app.state.store)}

    @app.post("/api/demo")
    def demo() -> dict:
        try:
            workspace = demo_workspace(app.state.store)
        except (StorageError, WorkspaceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return summary(app.state.store, run_for(workspace.id))

    @app.post("/api/workspace/upload")
    async def upload(files: list[UploadFile] = File(...),
                     label: str | None = Form(None),
                     kind: str = Form("manuscript")) -> dict:
        if kind not in {"manuscript", "reference"}:
            raise HTTPException(status_code=400, detail="kind must be manuscript or reference")
        payload: list[tuple[str, bytes]] = []
        for item in files:
            data = await item.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413,
                                    detail=f"{item.filename} is larger than "
                                           f"{MAX_UPLOAD_BYTES} bytes")
            payload.append((item.filename or "unnamed", data))
        try:
            workspace = upload_workspace(app.state.store, payload, label=label, kind=kind)
        except (StorageError, WorkspaceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if kind == "reference":
            run = run_for(workspace.id)
            return {"workspace_id": workspace.id, "kind": kind, "label": workspace.label,
                    "sections": [{"id": row["id"], "title": row["title"],
                                  "contribution": row["contribution"],
                                  "sentences": row["sentence_count"]}
                                 for row in run.payload["sections"]]}
        return summary(app.state.store, run_for(workspace.id))

    @app.post("/api/workspace/path")
    def open_path(body: WorkspacePathRequest) -> dict:
        if body.kind not in {"manuscript", "reference"}:
            raise HTTPException(status_code=400, detail="kind must be manuscript or reference")
        try:
            workspace = path_workspace(app.state.store, Path(body.path), label=body.label,
                                       kind=body.kind)
        except (StorageError, WorkspaceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if body.kind == "reference":
            run = run_for(workspace.id)
            return {"workspace_id": workspace.id, "kind": body.kind,
                    "label": workspace.label,
                    "sections": [{"id": row["id"], "title": row["title"],
                                  "contribution": row["contribution"],
                                  "sentences": row["sentence_count"]}
                                 for row in run.payload["sections"]]}
        return summary(app.state.store, run_for(workspace.id))

    @app.delete("/api/workspace/{workspace_id}")
    def delete_workspace(workspace_id: str) -> dict:
        try:
            return app.state.store.delete_workspace(workspace_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/workspace/{workspace_id}")
    def get_workspace(workspace_id: str) -> dict:
        workspace = app.state.store.get_workspace(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        return summary(app.state.store, run_for(workspace_id))

    @app.post("/api/workspace/{workspace_id}/audit")
    def reaudit(workspace_id: str) -> dict:
        """Re-run the audit. Review state is keyed by the content-addressed
        finding id, so it survives line shifts and resets when the quoted text
        changes."""
        run = run_for(workspace_id)
        try:
            loaded = load_workspace(Path(run.payload["source_path"]))
        except (WorkspaceError, FileNotFoundError) as exc:
            raise HTTPException(status_code=410,
                                detail=f"the source folder is no longer available: {exc}") from exc
        payload = analyze(loaded, loaded.scan(),
                          assumptions=run.payload.get("assumptions", []),
                          mode=run.payload.get("mode", "workspace"))
        run.payload = {**run.payload, **payload}
        app.state.store.save_run(run)
        style = run.payload["style"]
        if style.get("reference_ids"):
            refresh_style(app.state.store, run, style["reference_ids"])
        return summary(app.state.store, run)

    @app.get("/api/workspace/{workspace_id}/file")
    def get_file(workspace_id: str, path: str) -> dict:
        try:
            return file_text(app.state.store, run_for(workspace_id), path)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=410, detail="file no longer exists") from exc

    @app.post("/api/workspace/{workspace_id}/decision")
    def decide(workspace_id: str, body: DecisionRequest) -> dict:
        if body.decision not in ALLOWED_DECISIONS:
            raise HTTPException(status_code=400, detail="unknown decision")
        run = run_for(workspace_id)
        known = {f["id"] for f in run.payload["findings"]}
        if body.finding_id not in known:
            raise HTTPException(status_code=404, detail="unknown finding")
        app.state.store.set_decision(workspace_id, body.finding_id, body.decision)
        return {"ok": True, "finding_id": body.finding_id, "decision": body.decision}

    @app.post("/api/workspace/{workspace_id}/label")
    def label_section(workspace_id: str, body: ReferenceRequest) -> dict:
        if body.contribution not in ALLOWED_CONTRIBUTIONS:
            raise HTTPException(status_code=400, detail="unknown contribution label")
        run = run_for(workspace_id)
        if body.section_id != "ALL" and body.section_id not in {
                s["id"] for s in run.payload["sections"]}:
            raise HTTPException(status_code=404, detail="unknown section")
        app.state.store.set_label(workspace_id, body.section_id, body.contribution)
        return {"ok": True}

    @app.post("/api/workspace/{workspace_id}/style")
    def style(workspace_id: str, body: StyleRequest) -> dict:
        run = run_for(workspace_id)
        try:
            refresh_style(app.state.store, run, body.reference_ids)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return summary(app.state.store, run)

    @app.post("/api/workspace/{workspace_id}/navigate")
    def navigator(workspace_id: str, body: NavigateRequest) -> dict:
        return run_navigator(app.state.store, run_for(workspace_id), body.query)

    @app.post("/api/workspace/{workspace_id}/export")
    def export(workspace_id: str) -> dict:
        return export_run(app.state.store, run_for(workspace_id))

    @app.get("/api/workspace/{workspace_id}/export/{name}")
    def export_file(workspace_id: str, name: str):
        allowed = {"report.json", "report.md", "agent-feedback.json",
                   "author-style-guide.md", "cognitive-structure-profile.json"}
        if name not in allowed:
            raise HTTPException(status_code=404, detail="unknown export")
        run = run_for(workspace_id)
        path = app.state.store.exports_dir / run.id / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="export not generated yet")
        return FileResponse(path, filename=f"paperfamiliar-{run.id[:8]}-{name}")

    # ---------- settings / data lifecycle ----------

    @app.get("/api/settings")
    def settings() -> dict:
        return {"usage": app.state.store.usage(),
                "references": [row for row in list_workspaces(app.state.store)
                               if row["kind"] == "reference"],
                "providers": providers.status()}

    @app.post("/api/settings/clear")
    def clear() -> dict:
        return app.state.store.clear_all()

    # ---------- providers / metadata ----------

    @app.get("/api/providers")
    def provider_status() -> dict:
        return providers.status()

    def _provider(name: str):
        if name == "cloud":
            config = providers.cloud_provider()
            if config is None:
                raise HTTPException(status_code=400,
                                    detail="cloud provider is not configured (endpoint/model env)")
            return config
        return providers.local_provider()

    @app.post("/api/providers/preview")
    def provider_preview(body: ModelPreviewRequest) -> dict:
        return app.state.consents.preview(body.task, body.text, _provider(body.provider))

    @app.post("/api/providers/send")
    def provider_send(body: ModelSendRequest) -> dict:
        config = _provider(body.provider)
        if not body.confirm:
            raise HTTPException(status_code=403, detail="explicit confirmation is required")
        try:
            app.state.consents.confirm(body.consent_id)
            return providers.send(app.state.consents, body.consent_id, body.task,
                                  body.text, config)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/metadata")
    def metadata_lookup(body: MetadataRequest) -> dict:
        return metadata_module.lookup_doi(body.doi, allow_network=body.allow_network,
                                          cache_dir=data_dir()).as_dict()

    # ---------- static frontend ----------

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
