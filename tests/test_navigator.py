from pathlib import Path

from paperfamiliar.fingerprint import build_sections, navigate
from paperfamiliar.workspace import load_workspace

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"


def _sections():
    ws = load_workspace(DRAFT)
    return build_sections(ws, ws.scan())


def test_finds_the_problem_formulation_offline():
    result = navigate("where is the optimization problem?", _sections())
    assert result["status"] == "found"
    assert result["matches"][0]["title"] == "Problem Formulation"
    assert result["matches"][0]["span"]["file_path"] == "main.tex"


def test_reports_not_found_instead_of_inventing_a_location():
    result = navigate("quantum chromodynamics lattice", _sections())
    assert result["status"] == "not_found"
    assert result["matches"] == []
    assert "No location is invented" in result["reason"]


def test_empty_query_is_not_a_match():
    assert navigate("   ?? ", _sections())["status"] == "not_found"
