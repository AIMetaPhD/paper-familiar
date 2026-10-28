from pathlib import Path

import pytest

from paperfamiliar.adapters import papercheck_status, papercheck_verify_quote

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "fixtures" / "draft_submission_论文 项目" / "sections" / "eval.tex"

pytestmark = pytest.mark.skipif(papercheck_status()["status"] != "available",
                                reason="papercheck is not installed")


def test_real_quote_is_confirmed():
    result = papercheck_verify_quote(TARGET, "Tail latency improves by 7")
    assert result["status"] == "cross_check_confirmed"


def test_fabricated_quote_is_rejected():
    result = papercheck_verify_quote(TARGET, "Tail latency improves by 40")
    assert result["status"] == "cross_check_rejected"


def test_wrong_line_window_is_rejected():
    result = papercheck_verify_quote(TARGET, "Tail latency improves by 7", line=40)
    assert result["status"] == "cross_check_rejected"
