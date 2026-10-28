from pathlib import Path

from paperfamiliar.rules import audit
from paperfamiliar.workspace import load_workspace

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"
CONTROL = ROOT / "fixtures" / "corpus" / "control_clean_paper.tex"


def test_draft_has_the_intended_defects():
    ws = load_workspace(DRAFT)
    result = audit(ws)
    rules = {(f.rule_id, f.evidence_status) for f in result.findings}
    assert ("cite.undefined_key", "verified_error") in rules
    assert ("label.duplicate", "verified_error") in rules
    assert ("ref.undefined_label", "verified_error") in rules
    assert ("bib.missing_required_field", "verified_error") in rules
    assert ("notation.possibly_undefined", "candidate") in rules
    # The control paper does not exist in this workspace.
    assert all(f.finding_class != "semantic" for f in result.findings)


def test_clean_control_produces_no_verified_errors():
    ws = load_workspace(CONTROL)
    result = audit(ws)
    verified = [f for f in result.findings if f.evidence_status == "verified_error"]
    assert verified == []


def test_duplicate_label_points_at_the_second_definition():
    ws = load_workspace(DRAFT)
    result = audit(ws)
    dup = [f for f in result.findings if f.rule_id == "label.duplicate"][0]
    assert dup.span.file_path == "sections/method.tex"
    assert "first appears at main.tex" in dup.detail
    assert dup.span.exact_quote == "\\label{sec:method}"


def test_findings_carry_scope_not_just_claim():
    ws = load_workspace(DRAFT)
    result = audit(ws)
    for finding in result.findings:
        assert finding.rule_scope, finding.rule_id
        assert finding.finding_class in {"mechanical", "metadata", "heuristic", "semantic"}
