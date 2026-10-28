import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from paperfamiliar import metadata, providers


class _Recorder(BaseHTTPRequestHandler):
    requests: list[dict] = []
    response: dict = {}

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps(self.response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        type(self).requests.append({"path": self.path, "body": body})
        payload = {"choices": [{"message": {"content": "candidate text"}}]}
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@pytest.fixture()
def server():
    _Recorder.requests = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_metadata_offline_never_reaches_network(server):
    result = metadata.lookup_doi("10.1000/xyz123", allow_network=False,
                                 endpoint=server + "/")
    assert result.status == "unavailable_offline"
    assert result.claim_support == "unknown"
    assert result.as_dict()["claim_support"] == "unknown"


def test_metadata_requires_a_valid_doi():
    result = metadata.lookup_doi("not-a-doi", allow_network=True)
    assert result.status == "invalid_identifier"


def test_metadata_corroborates_but_never_supports_a_claim(server, tmp_path):
    _Recorder.response = {"message": {
        "title": ["Attention Is All You Need"],
        "author": [{"given": "Ashish", "family": "Vaswani"}],
        "issued": {"date-parts": [[2017]]},
        "container-title": ["NeurIPS"],
    }}
    result = metadata.lookup_doi("10.48550/arXiv.1706.03762", allow_network=True,
                                 cache_dir=tmp_path, endpoint=server + "/")
    assert result.status == "source_corroborated"
    assert result.title.startswith("Attention")
    assert result.claim_support == "unknown"
    assert "supported" not in json.dumps(result.as_dict()).lower().replace(
        "never means the cited paper supports the claim", "")


def _config(base_url):
    return providers.ProviderConfig("local", "test", "ollama", base_url, "test-model")


def test_no_request_before_consent(server):
    store = providers.ConsentStore()
    config = _config(server + "/v1")
    preview = store.preview("find issues", "Some manuscript text.", config)
    assert _Recorder.requests == []
    with pytest.raises(PermissionError):
        providers.send(store, preview["consent_id"], "find issues", "Some manuscript text.", config)
    assert _Recorder.requests == []


def test_consent_sends_exactly_the_previewed_payload(server):
    store = providers.ConsentStore()
    config = _config(server + "/v1")
    preview = store.preview("find issues", "Some manuscript text.", config)
    assert preview["payload_bytes"] > 0
    store.confirm(preview["consent_id"])
    result = providers.send(store, preview["consent_id"], "find issues",
                            "Some manuscript text.", config)
    assert result["status"] == "candidate"
    assert result["candidate_only"] is True
    assert len(_Recorder.requests) == 1
    sent = json.loads(_Recorder.requests[0]["body"])
    assert sent == preview["payload"]


def test_payload_change_after_preview_is_refused(server):
    store = providers.ConsentStore()
    config = _config(server + "/v1")
    preview = store.preview("find issues", "Original text.", config)
    store.confirm(preview["consent_id"])
    with pytest.raises(PermissionError):
        providers.send(store, preview["consent_id"], "find issues", "Changed text.", config)
    assert _Recorder.requests == []


def test_consent_is_single_use(server):
    store = providers.ConsentStore()
    config = _config(server + "/v1")
    preview = store.preview("find issues", "Text.", config)
    store.confirm(preview["consent_id"])
    providers.send(store, preview["consent_id"], "find issues", "Text.", config)
    with pytest.raises(PermissionError):
        providers.send(store, preview["consent_id"], "find issues", "Text.", config)


def test_secrets_are_redacted_before_the_preview(server):
    store = providers.ConsentStore()
    config = _config(server + "/v1")
    preview = store.preview("find issues", "key sk-" + "a" * 32, config)
    assert "sk-" + "a" * 32 not in json.dumps(preview)
    assert preview["redactions"] >= 1


def test_api_key_is_not_in_the_preview(monkeypatch, server):
    monkeypatch.setenv("PAPERFAMILIAR_CLOUD_ENDPOINT", server + "/v1")
    monkeypatch.setenv("PAPERFAMILIAR_CLOUD_MODEL", "test-model")
    monkeypatch.setenv("PAPERFAMILIAR_CLOUD_KEY_ENV", "PAPERFAMILIAR_TEST_KEY")
    monkeypatch.setenv("PAPERFAMILIAR_TEST_KEY", "secret-value-1234567890")
    config = providers.cloud_provider()
    store = providers.ConsentStore()
    preview = store.preview("task", "text", config)
    assert "secret-value" not in json.dumps(preview)
    assert providers.status()["cloud"]["key_present"] is True


def test_core_product_is_complete_without_any_model(tmp_path, monkeypatch):
    """AI-01 fallback: with no local model and no cloud config, the full golden
    path (demo -> audit -> decision -> style -> navigator -> export) works and
    the UI is told the model is unavailable rather than silently broken."""
    monkeypatch.setattr(providers, "probe_local",
                        lambda timeout=0.8: {"status": "unavailable", "models": [],
                                             "endpoint": "http://127.0.0.1:1",
                                             "detail": "UnitTest"})
    from fastapi.testclient import TestClient

    from paperfamiliar.api import create_app
    from paperfamiliar.storage import Store

    app = create_app(Store(tmp_path / "data"))
    client = TestClient(app, base_url="http://127.0.0.1:8420")
    headers = {"X-PF-CSRF": app.state.csrf}

    status = client.get("/api/providers").json()
    assert status["local"]["status"] == "unavailable"
    assert status["cloud"]["configured"] is False

    run = client.post("/api/demo", json={}, headers=headers).json()
    ws = run["workspace_id"]
    assert len(run["findings"]) >= 4 and run["style"]["baseline"]["status"] == "ok"
    client.post(f"/api/workspace/{ws}/decision",
                json={"finding_id": run["findings"][0]["id"], "decision": "dismissed"},
                headers=headers)
    nav = client.post(f"/api/workspace/{ws}/navigate",
                      json={"query": "evaluation"}, headers=headers).json()
    assert nav["status"] == "found"
    exported = client.post(f"/api/workspace/{ws}/export", json={}, headers=headers).json()
    assert "report.json" in exported["files"]

    preview = client.post("/api/providers/preview",
                          json={"task": "t", "text": "some excerpt", "provider": "local"},
                          headers=headers).json()
    sent = client.post("/api/providers/send",
                       json={"consent_id": preview["consent_id"], "task": "t",
                             "text": "some excerpt", "provider": "local", "confirm": True},
                       headers=headers).json()
    assert sent["status"] == "unavailable"
    assert sent.get("candidate_only") in (True, None)
