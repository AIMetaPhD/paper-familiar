"""Strict-offline proof.

While this test runs, any socket connection to a non-loopback address raises.
The whole product path (demo -> audit -> decisions -> style -> export) must
complete. This file's log is the `network_isolation_proof` artifact referenced
by QA handoffs; it is also run inside the ordinary pytest suite.
"""
from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from paperfamiliar.api import create_app
from paperfamiliar.storage import Store

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
attempts: list[str] = []


@pytest.fixture(autouse=True, scope="module")
def block_external_network():
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args):
        host = address[0] if isinstance(address, tuple) and address else address
        if isinstance(host, str) and host not in LOOPBACK:
            attempts.append(str(host))
            raise AssertionError(f"strict offline violated: connect to {host!r}")
        return real_connect(self, address, *args)

    socket.socket.connect = guarded_connect
    try:
        yield
    finally:
        socket.socket.connect = real_connect


def test_full_demo_path_works_without_any_egress(tmp_path):
    app = create_app(Store(tmp_path / "data"))
    client = TestClient(app, base_url="http://127.0.0.1:8420")
    headers = {"X-PF-CSRF": app.state.csrf}

    run = client.post("/api/demo", json={}, headers=headers).json()
    ws = run["workspace_id"]
    assert len(run["findings"]) >= 4
    assert run["style"]["baseline"]["status"] == "ok"

    client.post(f"/api/workspace/{ws}/decision",
                json={"finding_id": run["findings"][0]["id"], "decision": "accepted"},
                headers=headers)
    client.post(f"/api/workspace/{ws}/navigate",
                json={"query": "where is the optimization problem?"}, headers=headers)
    exported = client.post(f"/api/workspace/{ws}/export", json={}, headers=headers).json()
    assert "report.json" in exported["files"]
    assert attempts == []


def test_offline_metadata_lookup_never_opens_a_socket(tmp_path):
    from paperfamiliar import metadata

    result = metadata.lookup_doi("10.48550/arXiv.1706.03762", allow_network=False,
                                 cache_dir=tmp_path)
    assert result.status == "unavailable_offline"
    assert attempts == []


def test_provider_probe_is_loopback_only():
    from paperfamiliar import providers

    status = providers.status()
    assert status["local"]["endpoint"].startswith("http://127.0.0.1")
    assert status["cloud"]["configured"] is False
    assert attempts == []
