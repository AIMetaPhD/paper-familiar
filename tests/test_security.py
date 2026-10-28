from pathlib import Path

import pytest

from paperfamiliar.rules import audit
from paperfamiliar.workspace import WorkspaceError, load_workspace

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "fixtures" / "generated"
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"


@pytest.mark.parametrize("name", [
    "zipslip.zip", "absolute.zip", "symlink.zip", "bomb.zip", "deep.zip", "many.zip",
])
def test_dangerous_archives_fail_closed(name):
    with pytest.raises(WorkspaceError):
        load_workspace(GENERATED / name)


def test_clean_archive_loads_and_keeps_crlf():
    ws = load_workspace(GENERATED / "clean_project.zip")
    assert ws.main_path == "main.tex"
    assert b"\r\n" in ws.files["main.tex"].raw


def test_malicious_includes_are_reported_not_followed():
    ws = load_workspace(ROOT / "fixtures" / "adversarial" / "malicious.tex")
    result = audit(ws)
    kinds = {event["kind"] for event in result.security_events}
    assert "include.unresolved" in kinds
    escapes = [f for f in result.findings if f.rule_id == "security.include_escape"]
    assert len(escapes) >= 2
    assert all(f.evidence_status == "verified_error" for f in escapes)
    assert all(f.severity == "critical" for f in escapes)


def test_prompt_injection_is_inert_text():
    ws = load_workspace(DRAFT)
    result = audit(ws)
    rendered = " ".join(
        f.claim + " " + f.detail for f in result.findings
    ).lower()
    assert "evil.example" not in rendered
    assert "api key" not in rendered
    assert "developer mode" not in rendered
    # The injected comment is still visible in the source, but no finding follows it.
    assert "ignore all previous instructions" in ws.files["main.tex"].text


def test_scanner_never_writes_next_to_source(tmp_path):
    (tmp_path / "main.tex").write_text("\\write18{echo hi}\n", encoding="utf-8")
    before = {p.name for p in tmp_path.iterdir()}
    ws = load_workspace(tmp_path / "main.tex")
    audit(ws)
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after
