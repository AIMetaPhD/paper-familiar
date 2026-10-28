from pathlib import Path

from paperfamiliar.evidence import verify_span
from paperfamiliar.model import SourceFile, sha256_bytes
from paperfamiliar.scanner import scan_file
from paperfamiliar.workspace import load_workspace

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "fixtures" / "draft_submission_论文 项目"


def test_multifile_order_and_crlf_positions():
    ws = load_workspace(DRAFT)
    scan = ws.scan()
    assert scan.order == ["main.tex", "sections/intro.tex", "sections/problem.tex",
                          "sections/method.tex", "sections/eval.tex"]
    main = ws.files["main.tex"]
    assert b"\r\n" in main.raw
    missing = [c for c in scan.files["main.tex"].citations if c.key == "missing2026"][0]
    assert missing.arg_span.exact_quote == "missing2026"
    assert verify_span(main, missing.arg_span).ok


def test_unicode_columns_are_code_points():
    text = "中文 é🙂 \\cite{key}\n第二行 \\ref{eq:one}\n"
    raw = text.encode("utf-8")
    sf = SourceFile(path="x.tex", raw=raw, text=text, sha256=sha256_bytes(raw))
    scan = scan_file(sf)
    cite = scan.citations[0]
    assert cite.arg_span.exact_quote == "key"
    line, col = cite.arg_span.start_line, cite.arg_span.start_col
    prefix = text.split("\n")[line - 1][: col - 1]
    assert prefix.endswith("\\cite{")
    assert len(prefix) == len("中文 é🙂 \\cite{")
    assert verify_span(sf, cite.arg_span).ok


def test_comment_verbatim_and_math_are_not_commands():
    text = (
        "% \\cite{in_comment}\n"
        "\\begin{verbatim}\n\\ref{in_verbatim}\n\\end{verbatim}\n"
        "$x + \\label{in_math}$\n"
        "\\label{real}\n"
    )
    raw = text.encode()
    sf = SourceFile(path="x.tex", raw=raw, text=text, sha256=sha256_bytes(raw))
    scan = scan_file(sf)
    assert [c.key for c in scan.citations] == []
    assert [r.key for r in scan.refs] == []
    assert [l.key for l in scan.labels] == ["real"]


def test_malicious_tex_is_scanned_never_executed(tmp_path):
    marker = tmp_path / "pwned.txt"
    text = (
        "\\write18{echo pwned > " + str(marker).replace("\\", "/") + "}\n"
        "\\input{/etc/passwd}\n"
        "\\input{../../secret.tex}\n"
        "\\def\\bomb{\\bomb\\bomb}\\bomb\n"
    )
    raw = text.encode()
    sf = SourceFile(path="evil.tex", raw=raw, text=text, sha256=sha256_bytes(raw))
    scan = scan_file(sf)
    assert scan.command_count >= 5
    assert not marker.exists()
    assert any("etc/passwd" in i.target for i in scan.includes)
