import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from paperfamiliar.api import create_app
from paperfamiliar.storage import Store

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8420"
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"


def make_client(tmp_path):
    app = create_app(Store(tmp_path / "data"))
    client = TestClient(app, base_url=BASE)
    return app, client


def headers(app):
    return {"X-PF-CSRF": app.state.csrf}


def test_host_and_csrf_guards(tmp_path):
    app, client = make_client(tmp_path)
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/demo", json={}).status_code == 403
    foreign = client.post("/api/demo", json={},
                          headers={**headers(app), "Origin": "http://evil.example"})
    assert foreign.status_code == 403
    evil_host = client.get("/api/health", headers={"Host": "attacker.example"})
    assert evil_host.status_code == 400
    assert client.post("/api/demo", json={}, headers=headers(app)).status_code == 200


def test_demo_persists_survives_restart_and_export_is_immutable(tmp_path):
    app, client = make_client(tmp_path)
    run = client.post("/api/demo", json={}, headers=headers(app)).json()
    ws_id = run["workspace_id"]
    assert ws_id and len(run["findings"]) >= 4

    main_path = run["main_path"]
    original = client.get(f"/api/workspace/{ws_id}/file", params={"path": main_path}).json()
    digest = hashlib.sha256(original["text"].encode("utf-8")).hexdigest()
    assert original["unchanged"] is True

    finding = run["findings"][0]
    decided = client.post(f"/api/workspace/{ws_id}/decision",
                          json={"finding_id": finding["id"], "decision": "accepted"},
                          headers=headers(app))
    assert decided.status_code == 200

    exported = client.post(f"/api/workspace/{ws_id}/export", json={}, headers=headers(app))
    assert exported.status_code == 200
    assert "report.json" in exported.json()["files"]

    again = client.get(f"/api/workspace/{ws_id}/file", params={"path": main_path}).json()
    assert again["unchanged"] is True
    assert hashlib.sha256(again["text"].encode("utf-8")).hexdigest() == digest

    # a brand-new app over the same on-disk database restores the workspace
    app2 = create_app(Store(tmp_path / "data"))
    client2 = TestClient(app2, base_url=BASE)
    restored = client2.get(f"/api/workspace/{ws_id}").json()
    updated = [f for f in restored["findings"] if f["id"] == finding["id"]][0]
    assert updated["human_decision"] == "accepted"
    assert updated["evidence_status"] == finding["evidence_status"]
    listing = client2.get("/api/workspaces").json()["workspaces"]
    assert any(row["id"] == ws_id for row in listing)


def test_upload_from_browser_multiples(tmp_path):
    app, client = make_client(tmp_path)
    files = [
        ("files", ("main.tex", (DRAFT / "main.tex").read_bytes(), "application/octet-stream")),
        ("files", ("sections/intro.tex", (DRAFT / "sections/intro.tex").read_bytes(),
                   "application/octet-stream")),
        ("files", ("sections/problem.tex", (DRAFT / "sections/problem.tex").read_bytes(),
                   "application/octet-stream")),
        ("files", ("sections/method.tex", (DRAFT / "sections/method.tex").read_bytes(),
                   "application/octet-stream")),
        ("files", ("sections/eval.tex", (DRAFT / "sections/eval.tex").read_bytes(),
                   "application/octet-stream")),
        ("files", ("refs.bib", (DRAFT / "refs.bib").read_bytes(), "application/octet-stream")),
    ]
    response = client.post("/api/workspace/upload", files=files,
                           data={"label": "browser upload test", "kind": "manuscript"},
                           headers=headers(app))
    assert response.status_code == 200
    run = response.json()
    rules = {f["rule_id"] for f in run["findings"]}
    assert {"cite.undefined_key", "label.duplicate", "ref.undefined_label"} <= rules
    paths = {f["path"] for f in run["files"]}
    assert "sections/eval.tex" in paths
    # the uploaded copy keeps CRLF in main.tex
    main = client.get(f"/api/workspace/{run['workspace_id']}/file",
                      params={"path": "main.tex"}).json()
    assert "\r\n" in main["text"]


def test_upload_rejects_traversal_and_bad_types(tmp_path):
    app, client = make_client(tmp_path)
    bad = client.post("/api/workspace/upload",
                      files=[("files", ("../evil.tex", b"x", "application/octet-stream"))],
                      headers=headers(app))
    assert bad.status_code == 400
    exe = client.post("/api/workspace/upload",
                      files=[("files", ("evil.exe", b"MZ", "application/octet-stream"))],
                      headers=headers(app))
    assert exe.status_code == 400


def test_path_workspace_and_reference_flow(tmp_path):
    app, client = make_client(tmp_path)
    ref = client.post("/api/workspace/path",
                      json={"path": str(ROOT / "fixtures" / "corpus" /
                                        "a1_distributed_inference_2022.tex"),
                            "kind": "reference"},
                      headers=headers(app)).json()
    assert ref["kind"] == "reference" and ref["sections"]
    target = ref["sections"][0]
    labeled = client.post(f"/api/workspace/{ref['workspace_id']}/label",
                          json={"workspace_id": ref["workspace_id"],
                                "section_id": target["id"], "contribution": "sole_or_primary"},
                          headers=headers(app))
    assert labeled.status_code == 200

    draft = client.post("/api/workspace/path",
                        json={"path": str(DRAFT), "kind": "manuscript"},
                        headers=headers(app)).json()
    assert draft["style"]["baseline"]["status"] == "insufficient_evidence"
    styled = client.post(f"/api/workspace/{draft['workspace_id']}/style",
                         json={"reference_ids": [ref["workspace_id"]]},
                         headers=headers(app)).json()
    # one paper alone must still abstain, not fabricate a comparison
    assert styled["style"]["baseline"]["status"] == "insufficient_evidence"


def test_delete_workspace_removes_copy_but_not_the_original(tmp_path):
    app, client = make_client(tmp_path)
    run = client.post("/api/workspace/path",
                      json={"path": str(DRAFT), "kind": "manuscript"},
                      headers=headers(app)).json()
    ws_id = run["workspace_id"]
    source_listed = sorted(p.name for p in DRAFT.iterdir())
    deleted = client.request("DELETE", f"/api/workspace/{ws_id}", headers=headers(app))
    assert deleted.status_code == 200
    assert sorted(p.name for p in DRAFT.iterdir()) == source_listed
    assert client.get(f"/api/workspace/{ws_id}").status_code == 404


def test_path_escape_is_refused(tmp_path):
    app, client = make_client(tmp_path)
    run = client.post("/api/demo", json={}, headers=headers(app)).json()
    ws_id = run["workspace_id"]
    for path in ("../secret.tex", "C:/Windows/win.ini", "/etc/passwd",
                 "draft/../../Windows/win.ini"):
        response = client.get(f"/api/workspace/{ws_id}/file", params={"path": path})
        assert response.status_code in (403, 404), path


def test_navigator_returns_not_found_explicitly(tmp_path):
    app, client = make_client(tmp_path)
    run = client.post("/api/demo", json={}, headers=headers(app)).json()
    ws_id = run["workspace_id"]
    found = client.post(f"/api/workspace/{ws_id}/navigate",
                        json={"query": "where is the optimization problem?"},
                        headers=headers(app)).json()
    assert found["status"] == "found"
    missing = client.post(f"/api/workspace/{ws_id}/navigate",
                          json={"query": "zebra protocol appendix"},
                          headers=headers(app)).json()
    assert missing["status"] == "not_found"


def test_clear_all_empties_the_store(tmp_path):
    app, client = make_client(tmp_path)
    client.post("/api/demo", json={}, headers=headers(app))
    cleared = client.post("/api/settings/clear", json={}, headers=headers(app))
    assert cleared.status_code == 200
    assert client.get("/api/workspaces").json()["workspaces"] == []


def test_legacy_v11_database_migrates_without_data_loss(tmp_path):
    import sqlite3

    legacy = tmp_path / "paperfamiliar.sqlite3"
    db = sqlite3.connect(legacy)
    db.execute("""CREATE TABLE runs (id TEXT PRIMARY KEY, created_at TEXT, label TEXT,
                  root TEXT, main_path TEXT, revision_id TEXT, payload TEXT)""")
    db.execute("""CREATE TABLE decisions (run_id TEXT, finding_id TEXT, decision TEXT,
                  updated_at TEXT, PRIMARY KEY (run_id, finding_id))""")
    db.execute("INSERT INTO runs VALUES ('old1','t','l','r','m','rev','{}')")
    db.execute("INSERT INTO decisions VALUES ('old1','F-1','accepted','t')")
    db.commit()
    db.close()

    store = Store(tmp_path)
    assert store.list_workspaces() == []
    row = store.db.execute("SELECT moved_tables FROM legacy_migrations").fetchone()
    assert row and "runs" in row[0]
    kept = store.db.execute("SELECT decision FROM decisions_v11 WHERE finding_id='F-1'").fetchone()
    assert kept and kept[0] == "accepted"


def test_demo_reload_reuses_the_same_workspace(tmp_path):
    app, client = make_client(tmp_path)
    first = client.post("/api/demo", json={}, headers=headers(app)).json()
    second = client.post("/api/demo", json={}, headers=headers(app)).json()
    assert first["workspace_id"] == second["workspace_id"]
    listing = client.get("/api/workspaces").json()["workspaces"]
    demo_rows = [row for row in listing if row["kind"] == "demo"]
    assert len(demo_rows) == 1
    # a decision made before the reload is still visible after it
    fid = first["findings"][0]["id"]
    client.post(f"/api/workspace/{first['workspace_id']}/decision",
                json={"finding_id": fid, "decision": "accepted"}, headers=headers(app))
    again = client.post("/api/demo", json={}, headers=headers(app)).json()
    row = [f for f in again["findings"] if f["id"] == fid][0]
    assert row["human_decision"] == "accepted"


def test_usage_reports_stored_and_path_workspaces_separately(tmp_path):
    app, client = make_client(tmp_path)
    client.post("/api/demo", json={}, headers=headers(app))
    usage = client.get("/api/settings").json()["usage"]
    assert usage["stored_workspaces"] == 0  # demo is path-based, nothing copied
    assert usage["path_workspaces"] >= 5
