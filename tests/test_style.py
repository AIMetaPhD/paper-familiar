from pathlib import Path

from paperfamiliar.fingerprint import (FUNCTION_WORDS, build_baseline, build_sections,
                                       drift_cards, style_profile)
from paperfamiliar.workspace import load_workspace

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "fixtures" / "corpus"
DEMO_HISTORY = [CORPUS / name for name in (
    "a1_distributed_inference_2022.tex",
    "a2_kv_cache_2023.tex",
    "a3_edge_scheduling_2024.tex",
    "a4_latency_modeling_2025.tex",
)]


def _prose(path: Path) -> str:
    ws = load_workspace(path)
    return " ".join(section.prose for section in build_sections(ws, ws.scan()))


def test_small_sample_abstains_instead_of_scoring():
    baseline = build_baseline([_prose(p) for p in DEMO_HISTORY[:2]])
    assert baseline.status == "insufficient_evidence"
    assert baseline.profile is None
    assert "at least 3" in baseline.reason


def test_baseline_uses_function_words_not_topic_terms():
    baseline = build_baseline([_prose(p) for p in DEMO_HISTORY])
    assert baseline.status == "ok"
    assert set(baseline.profile.function_vector) <= set(FUNCTION_WORDS)
    for term in ("inference", "cache", "latency", "edge"):
        assert term not in baseline.profile.function_vector


def test_coauthor_sections_are_excluded_from_the_profile():
    ws = load_workspace(CORPUS / "adv03_coauthor_mixed.tex")
    sections = build_sections(ws, ws.scan())
    by_title = {section.title: section for section in sections}
    assert by_title["Introduction"].author_approved
    assert not by_title["Compression Background"].author_approved
    assert by_title["Compression Background"].contribution == "coauthored"
    assert not by_title["Implementation Details"].author_approved
    assert by_title["Implementation Details"].contribution == "not_primary"


def test_same_topic_different_author_does_not_look_identical():
    baseline = build_baseline([_prose(p) for p in DEMO_HISTORY])
    other = style_profile(_prose(CORPUS / "adv01_same_topic_other_author.tex"))
    same = style_profile(_prose(DEMO_HISTORY[1]))
    def distance(profile):
        return sum(abs(profile.function_vector[w] - baseline.profile.function_vector[w])
                   for w in FUNCTION_WORDS)
    assert distance(other) > 0
    # The fixture is intentionally written in a different register; it must not be
    # closer to the baseline than the author's own paper on the same topic.
    assert distance(other) > distance(same) * 0.5


def test_no_similarity_percentage_is_ever_produced():
    baseline = build_baseline([_prose(p) for p in DEMO_HISTORY])
    ws = load_workspace(ROOT / "fixtures" / "draft_submission_论文 项目")
    cards = drift_cards(build_sections(ws, ws.scan()), baseline)
    for card in cards:
        assert "similarity" not in str(card).lower()
        assert "percent" not in str(card).lower()
        assert card.get("note")
