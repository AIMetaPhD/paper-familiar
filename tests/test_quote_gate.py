import json
from pathlib import Path

from paperfamiliar.evidence import check_fabricated_finding, span_from_offsets, verify_span
from paperfamiliar.workspace import load_workspace

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"


def test_every_fabricated_finding_is_rejected():
    ws = load_workspace(DRAFT)
    sf = ws.files["sections/eval.tex"]
    fixture = json.loads((ROOT / "fixtures" / "adversarial" / "fabricated_findings.json")
                         .read_text(encoding="utf-8"))
    results = {item["id"]: check_fabricated_finding(sf, item) for item in fixture["findings"]}
    assert all(not result.ok for result in results.values())
    assert results["F-FAKE-001"].reason == "quote_mismatch"
    assert results["F-FAKE-002"].reason.startswith("span_out_of_bounds")
    assert results["F-FAKE-003"].reason == "file_hash_mismatch"
    assert results["F-FAKE-004"].reason == "quote_mismatch"


def test_exact_span_round_trips():
    ws = load_workspace(DRAFT)
    sf = ws.files["sections/eval.tex"]
    start = sf.text.index("Tail latency improves")
    span = span_from_offsets(sf, start, start + len("Tail latency improves"))
    assert verify_span(sf, span).ok
    shifted = type(span)(**{**span.__dict__, "start_line": span.start_line + 1})
    assert not verify_span(sf, shifted).ok
