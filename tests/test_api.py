import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from paperfamiliar.api import create_app
from paperfamiliar.service import Store

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8420"


def make_client(tmp_path):
    app = create_app(Store(tmp_path / "test.sqlite3"))
    client = TestClient(app, base_url=BASE)
    return app, client


def test_host_and_csrf_guards(tmp_path):
    app, client = make_client(tmp_path)
    assert client.get("/api/health").status_code == 200
    bad = client.post("/api/demo", json={})
    assert bad.status_code == 403
    headers = {"X-PF-CSRF": app.state.csrf}
    foreign = client.post("/api/demo", json={}, headers={**headers, "Origin": "http://evil.example"})
    assert foreign.status_code == 403
    ok = client.post("/api/demo", json={}, headers=headers)
    assert ok.status_code == 200


def test_demo_decisions_export_and_source_immutability(tmp_path):
    app, client = make_client(tmp_path)
    headers = {"X-PF-CSRF": app.state.csrf}
    run = client.post("/api/demo", json={}, headers=headers).json()
    run_id = run["id"]
    assert len(run["findings"]) >= 4

    main_path = run["main_path"]
    original = client.get(f"/api/run/{run_id}/file", params={"path": main_path}).json()
    digest = hashlib.sha256(original["text"].encode("utf-8")).hexdigest()
    assert original["unchanged"] is True

    finding = run["findings"][0]
    decided = client.post(f"/api/run/{run_id}/decision",
                          json={"finding_id": finding["id"], "decision": "accepted"},
                          headers=headers)
    assert decided.status_code == 200

    exported = client.post(f"/api/run/{run_id}/export", json={}, headers=headers)
    assert exported.status_code == 200
    names = exported.json()["files"]
    assert "report.json" in names and "agent-feedback.json" in names

    again = client.get(f"/api/run/{run_id}/file", params={"path": main_path}).json()
    assert again["unchanged"] is True
    assert hashlib.sha256(again["text"].encode("utf-8")).hexdigest() == digest

    refreshed = client.get(f"/api/run/{run_id}").json()
    updated = [f for f in refreshed["findings"] if f["id"] == finding["id"]][0]
    assert updated["human_decision"] == "accepted"
    assert updated["evidence_status"] == finding["evidence_status"]


def test_path_escape_is_refused(tmp_path):
    app, client = make_client(tmp_path)
    headers = {"X-PF-CSRF": app.state.csrf}
    run = client.post("/api/demo", json={}, headers=headers).json()
    for path in ("../secret.tex", "C:/Windows/win.ini", "/etc/passwd"):
        response = client.get(f"/api/run/{run['id']}/file", params={"path": path})
        assert response.status_code in (403, 404)


def test_navigator_returns_not_found_explicitly(tmp_path):
    app, client = make_client(tmp_path)
    headers = {"X-PF-CSRF": app.state.csrf}
    run = client.post("/api/demo", json={}, headers=headers).json()
    found = client.post(f"/api/run/{run['id']}/navigate",
                        json={"query": "where is the optimization problem?"},
                        headers=headers).json()
    assert found["status"] == "found"
    missing = client.post(f"/api/run/{run['id']}/navigate",
                          json={"query": "zebra protocol appendix"},
                          headers=headers).json()
    assert missing["status"] == "not_found"
