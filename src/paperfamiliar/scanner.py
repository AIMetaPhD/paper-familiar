"""Structural LaTeX scanner.

It never executes TeX. It walks the decoded source once, records exact code-point
offsets for citations, references, labels, includes, sectioning commands, math and
environments, and converts those offsets to 1-based line/column pairs.

Design rules:
- comments, verbatim-like environments and math are skipped for command parsing;
- an unbalanced group ends the scan of that command, not the file;
- unknown macros are ignored rather than guessed at.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from .model import SourceFile, SourceSpan

CITE_COMMANDS = {
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear",
    "citenum", "citeyearpar", "Cite", "Citep", "Citet", "parencite", "textcite",
    "autocite", "footcite",
}
REF_COMMANDS = {"ref", "eqref", "autoref", "cref", "Cref", "pageref", "nameref", "vref"}
SECTION_COMMANDS = {"part": 0, "chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4}
INCLUDE_COMMANDS = {"input", "include", "subfile"}
VERBATIM_ENVS = {"verbatim", "verbatim*", "lstlisting", "minted", "comment"}
MATH_ENVS = {
    "equation", "equation*", "align", "align*", "gather", "gather*", "multline",
    "multline*", "eqnarray", "eqnarray*", "displaymath", "math",
}


@dataclass(frozen=True)
class Occurrence:
    key: str
    command: str
    span: SourceSpan
    arg_span: SourceSpan | None = None


@dataclass(frozen=True)
class Section:
    level: int
    title: str
    heading_span: SourceSpan
    title_span: SourceSpan
    order: int


@dataclass(frozen=True)
class Environment:
    name: str
    span: SourceSpan
    order: int


@dataclass(frozen=True)
class Include:
    target: str
    span: SourceSpan


@dataclass
class FileScan:
    path: str
    citations: list[Occurrence] = field(default_factory=list)
    refs: list[Occurrence] = field(default_factory=list)
    labels: list[Occurrence] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    environments: list[Environment] = field(default_factory=list)
    includes: list[Include] = field(default_factory=list)
    math_spans: list[tuple[int, int]] = field(default_factory=list)
    text_segments: list[tuple[int, int]] = field(default_factory=list)
    security_events: list[dict] = field(default_factory=list)
    command_count: int = 0


def _pos(sf: SourceFile, offset: int) -> tuple[int, int]:
    idx = bisect.bisect_right(sf.line_starts, offset) - 1
    return idx + 1, offset - sf.line_starts[idx] + 1


def _span(sf: SourceFile, start: int, end: int) -> SourceSpan:
    line, col = _pos(sf, start)
    end_line, end_col = _pos(sf, max(start, end - 1))
    end_col += 1  # half-open: one past the last character
    return SourceSpan(
        file_path=sf.path,
        start_line=line,
        start_col=col,
        end_line=end_line,
        end_col=end_col,
        exact_quote=sf.text[start:end],
        file_sha256=sf.sha256,
    )


def _read_braced(text: str, i: int) -> tuple[str, int, int] | None:
    """text[i] == '{'. Return (content, content_start, index_after_closing)."""
    if i >= len(text) or text[i] != "{":
        return None
    depth = 0
    j = i
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j], i + 1, j + 1
        j += 1
    return None


def _read_bracket(text: str, i: int) -> tuple[str, int, int] | None:
    if i >= len(text) or text[i] != "[":
        return None
    depth = 0
    j = i
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j], i + 1, j + 1
        j += 1
    return None


def _skip_to(text: str, i: int, needle: str) -> int:
    found = text.find(needle, i)
    return len(text) if found < 0 else found + len(needle)


def _skip_inline_math(text: str, i: int, delim: str) -> int:
    j = i + len(delim)
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text.startswith(delim, j):
            return j + len(delim)
        j += 1
    return len(text)


def scan_file(sf: SourceFile) -> FileScan:
    text = sf.text
    out = FileScan(path=sf.path)
    i = 0
    n = len(text)
    order = 0
    text_start = 0

    def flush_text(end: int) -> None:
        if end > text_start:
            out.text_segments.append((text_start, end))

    while i < n:
        ch = text[i]
        if ch == "%":
            flush_text(i)
            i = _skip_to(text, i, "\n")
            text_start = i
            continue
        if ch == "$":
            flush_text(i)
            delim = "$$" if text.startswith("$$", i) else "$"
            end = _skip_inline_math(text, i, delim)
            out.math_spans.append((i, end))
            i = end
            text_start = i
            continue
        if ch == "\\":
            # \( ... \) and \[ ... \]
            if i + 1 < n and text[i + 1] in "([":
                close = "\\)" if text[i + 1] == "(" else "\\]"
                flush_text(i)
                end = _skip_to(text, i + 2, close)
                out.math_spans.append((i, end))
                i = end
                text_start = i
                continue
            # control word or symbol
            j = i + 1
            if j < n and text[j].isalpha():
                while j < n and text[j].isalpha():
                    j += 1
                name = text[i + 1 : j]
            elif j < n:
                name = text[j]
                j += 1
            else:
                j = n
                name = ""

            if name == "verb" and j < n:
                delim = text[j]
                if delim != "\n":
                    end = text.find(delim, j + 1)
                    i = n if end < 0 else end + 1
                    text_start = i
                    continue

            if name == "begin":
                flush_text(i)
                group = _read_braced(text, j)
                if group is None:
                    i = j
                    text_start = i
                    continue
                env_name, _, after = group
                out.environments.append(Environment(env_name, _span(sf, i, after), order))
                order += 1
                if env_name in VERBATIM_ENVS:
                    end = _skip_to(text, after, f"\\end{{{env_name}}}")
                    if env_name in MATH_ENVS:
                        out.math_spans.append((after, end))
                    i = end
                    text_start = i
                    continue
                if env_name in MATH_ENVS:
                    out.math_spans.append((after, _skip_to(text, after, f"\\end{{{env_name}}}")))
                i = after
                text_start = i
                continue

            if name == "end":
                group = _read_braced(text, j)
                i = group[2] if group else j
                text_start = i
                continue

            # optional star, optional [..], then {..}
            k = j
            if k < n and text[k] == "*":
                k += 1
            while k < n and text[k] in " \t":
                k += 1
            if k < n and text[k] == "[":
                bracket = _read_bracket(text, k)
                if bracket:
                    k = bracket[2]
            group = _read_braced(text, k) if k < n and text[k] == "{" else None
            full_end = group[2] if group else k

            flush_text(i)
            out.command_count += 1
            base = name.rstrip("*")

            if base in CITE_COMMANDS and group:
                content, content_start, _ = group
                cursor = 0
                for raw_key in content.split(","):
                    key = raw_key.strip()
                    if key:
                        rel = content.find(raw_key, cursor)
                        cursor = rel + len(raw_key)
                        key_start = content_start + rel + (len(raw_key) - len(raw_key.lstrip()))
                        key_end = key_start + len(key)
                        arg = _span(sf, key_start, key_end)
                        out.citations.append(
                            Occurrence(key, name, _span(sf, i, full_end), arg)
                        )
            elif base in REF_COMMANDS and group:
                content, content_start, _ = group
                key = content.strip()
                if key:
                    key_start = content_start + (len(content) - len(content.lstrip()))
                    out.refs.append(
                        Occurrence(key, name, _span(sf, i, full_end),
                                   _span(sf, key_start, key_start + len(key)))
                    )
            elif name == "label" and group:
                content, content_start, _ = group
                key = content.strip()
                if key:
                    key_start = content_start + (len(content) - len(content.lstrip()))
                    out.labels.append(
                        Occurrence(key, name, _span(sf, i, full_end),
                                   _span(sf, key_start, key_start + len(key)))
                    )
            elif base in SECTION_COMMANDS and group:
                content, _, _ = group
                out.sections.append(
                    Section(SECTION_COMMANDS[base], content.strip(),
                            _span(sf, i, full_end), _span(sf, group[1], group[1] + len(content)),
                            order)
                )
                order += 1
            elif base in INCLUDE_COMMANDS and group:
                content, _, _ = group
                out.includes.append(Include(content.strip(), _span(sf, i, full_end)))

            i = full_end
            text_start = i
            continue

        i += 1

    flush_text(n)
    return out


@dataclass
class DocumentScan:
    files: dict[str, FileScan]
    order: list[str]

    def all_citations(self):
        for path in self.order:
            yield from self.files[path].citations

    def all_refs(self):
        for path in self.order:
            yield from self.files[path].refs

    def all_labels(self):
        for path in self.order:
            yield from self.files[path].labels

    def all_sections(self):
        rows = []
        for path in self.order:
            rows.extend(self.files[path].sections)
        return rows
