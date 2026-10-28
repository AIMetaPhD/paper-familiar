from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
DEMO = ROOT / "demo"


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_demo_draft_matches_fixture():
    assert _tree(DEMO / "draft") == _tree(FIXTURES / "draft_submission_论文 项目")


def test_demo_history_matches_fixture():
    demo_history = _tree(DEMO / "history")
    for name, data in demo_history.items():
        assert (FIXTURES / "corpus" / name).read_bytes() == data
