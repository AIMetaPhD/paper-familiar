"""Small, position-aware BibTeX reader.

It is deliberately not a full BibTeX implementation. It extracts entry keys,
types, top-level fields and exact spans so that a "missing required field"
finding can point at the insecure entry. Values inside braces are kept as raw
BibTeX text; no macro expansion or string concatenation is attempted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import SourceFile, SourceSpan
from .scanner import _span

REQUIRED_FIELDS = {
    "article": ("author", "title", "journal", "year"),
    "inproceedings": ("author", "title", "booktitle", "year"),
    "conference": ("author", "title", "booktitle", "year"),
    "book": ("title", "publisher", "year"),
    "incollection": ("author", "title", "booktitle", "year"),
    "phdthesis": ("author", "title", "school", "year"),
    "mastersthesis": ("author", "title", "school", "year"),
    "techreport": ("author", "title", "institution", "year"),
}


@dataclass
class BibEntry:
    key: str
    entry_type: str
    fields: dict[str, str] = field(default_factory=dict)
    span: SourceSpan | None = None
    field_spans: dict[str, SourceSpan] = field(default_factory=dict)
    file_path: str = ""


@dataclass
class BibProblem:
    kind: str
    detail: str
    span: SourceSpan


def _read_braced_value(text: str, i: int) -> tuple[str, int] | None:
    if text[i] != "{":
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
                return text[i + 1 : j], j + 1
        j += 1
    return None


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def parse_bib(sf: SourceFile) -> tuple[list[BibEntry], list[BibProblem]]:
    text = sf.text
    entries: list[BibEntry] = []
    problems: list[BibProblem] = []
    i = 0
    n = len(text)
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        start = at
        j = at + 1
        while j < n and (text[j].isalnum() or text[j] in "_-"):
            j += 1
        entry_type = text[at + 1 : j].lower()
        j = _skip_ws(text, j)
        if j >= n or text[j] not in "{(":
            problems.append(BibProblem("bib.malformed", f"@{entry_type} has no body",
                                       _span(sf, start, min(j + 1, n))))
            i = j + 1
            continue
        opener = text[j]
        closer = "}" if opener == "{" else ")"
        body_start = j + 1
        # find the matching closer, respecting nested braces and quotes
        depth = 1
        k = body_start
        in_quote = False
        end = n
        while k < n:
            ch = text[k]
            if ch == "\\":
                k += 2
                continue
            if ch == '"' and not in_quote:
                in_quote = True
            elif ch == '"' and in_quote:
                in_quote = False
            elif not in_quote:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and closer == "}":
                        end = k
                        break
                elif ch == ")" and closer == ")":
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            k += 1
        if end >= n:
            problems.append(BibProblem("bib.unbalanced", f"@{entry_type} is not closed",
                                       _span(sf, start, n)))
            break
        entry_end = end + 1
        if entry_type in {"string", "preamble", "comment"}:
            i = entry_end
            continue
        body = text[body_start:end]
        comma = body.find(",")
        if comma < 0:
            problems.append(BibProblem("bib.malformed", "entry has no key/field separator",
                                       _span(sf, start, entry_end)))
            i = entry_end
            continue
        key = body[:comma].strip()
        if not key:
            problems.append(BibProblem("bib.malformed", "entry has an empty key",
                                       _span(sf, start, entry_end)))
            i = entry_end
            continue
        entry = BibEntry(key=key, entry_type=entry_type,
                         span=_span(sf, start, entry_end), file_path=sf.path)
        pos = body_start + comma + 1
        while pos < end:
            pos = _skip_ws(text, pos)
            while pos < end and text[pos] == ",":
                pos = _skip_ws(text, pos + 1)
            if pos >= end:
                break
            name_start = pos
            while pos < end and (text[pos].isalnum() or text[pos] in "_-"):
                pos += 1
            name = text[name_start:pos].strip().lower()
            pos = _skip_ws(text, pos)
            if not name or pos >= end or text[pos] != "=":
                # skip this malformed fragment to the next top-level comma
                nxt = text.find(",", pos)
                pos = end if nxt < 0 or nxt > end else nxt + 1
                continue
            pos = _skip_ws(text, pos + 1)
            value_start = pos
            if pos < end and text[pos] == "{":
                braced = _read_braced_value(text, pos)
                if braced is None:
                    break
                value, pos = braced
            elif pos < end and text[pos] == '"':
                close_q = text.find('"', pos + 1)
                if close_q < 0 or close_q > end:
                    break
                value = text[pos + 1 : close_q]
                pos = close_q + 1
            else:
                while pos < end and text[pos] != ",":
                    pos += 1
                value = text[value_start:pos].strip()
            entry.fields[name] = value.strip()
            entry.field_spans[name] = _span(sf, value_start, max(value_start + 1, pos))
            nxt = text.find(",", pos)
            pos = end if nxt < 0 or nxt > end else nxt + 1
        entries.append(entry)
        i = entry_end
    return entries, problems
