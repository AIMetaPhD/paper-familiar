"""Deterministic author-style and cognitive-structure analysis.

No model is used. The output reports observed measurements, sample sizes and
explicit abstentions. It never prints a single "similarity" percentage and it
never treats a style difference as an academic error.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .model import SourceSpan
from .scanner import DocumentScan, _span
from .workspace import Workspace

TRANSITIONS = [
    "however", "moreover", "furthermore", "therefore", "thus", "hence",
    "in particular", "for example", "for instance", "in contrast", "by contrast",
    "on the other hand", "in addition", "as a result", "consequently",
    "specifically", "notably", "meanwhile", "finally", "first", "second", "third",
    "we therefore", "we thus", "in this paper", "to this end", "accordingly",
]
FUNCTION_WORDS = [
    "the", "a", "an", "of", "to", "in", "and", "or", "for", "on", "with", "by",
    "that", "this", "these", "those", "is", "are", "was", "were", "be", "been",
    "we", "our", "it", "its", "as", "at", "from", "which", "can", "may", "not",
    "when", "where", "while", "if", "than", "such", "each", "both", "also",
    "more", "most", "less", "least", "one", "two", "not", "only", "but", "so",
]
ROLE_KEYWORDS = {
    "abstract": ("abstract",),
    "introduction": ("introduction", "motivation"),
    "related_work": ("related work", "background", "preliminaries", "literature"),
    "problem": ("problem formulation", "problem statement", "system model",
                "formulation", "objective", "problem"),
    "method": ("method", "approach", "design", "algorithm", "proposed", "implementation"),
    "evaluation": ("evaluation", "experiment", "results", "performance", "empirical"),
    "conclusion": ("conclusion", "future work", "discussion", "summary"),
}
ABBREVIATIONS = {"al", "e.g", "i.e", "fig", "eq", "eqs", "sec", "ref", "vs", "cf", "no", "approx"}
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ed|shown|given|used|made|"
                     r"done|found|seen|known|built|kept|set|put|held)\b", re.IGNORECASE)
MATH_LEAD = re.compile(r"^\s*(?:let|we define|denote|define|where)\b", re.IGNORECASE)


@dataclass
class SectionText:
    id: str
    title: str
    level: int
    role: str
    file_path: str
    heading_span: SourceSpan
    prose: str
    contribution: str = "unknown"
    author_approved: bool = False
    sentences: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(re.findall(r"[A-Za-z][A-Za-z'-]*", self.prose))


def _section_offsets(sf, span: SourceSpan) -> int:
    return sf.offset(span.start_line, span.start_col)


def _contribution_before(text: str, heading_offset: int) -> str:
    window = text[max(0, heading_offset - 400):heading_offset]
    matches = re.findall(r"%\s*contribution:\s*([a-z_]+)", window)
    return matches[-1] if matches else "unknown"


def build_sections(workspace: Workspace, scan: DocumentScan) -> list[SectionText]:
    """Linearise the included document and attribute prose to the active section."""
    from .workspace import resolve_include

    rows: list[SectionText] = []
    current: dict | None = None
    front: list[str] = []
    index = 0

    def close() -> None:
        nonlocal current
        if current is None:
            return
        prose = re.sub(r"\s+", " ", " ".join(current["chunks"])).strip()
        if prose or current["has_heading"]:
            rows.append(SectionText(
                id=current["id"], title=current["title"], level=current["level"],
                role=current["role"], file_path=current["file"],
                heading_span=current["span"], prose=prose,
                contribution=current["contribution"],
                author_approved=current["contribution"] == "sole_or_primary",
                sentences=split_sentences(prose),
            ))
        current = None

    def walk(path: str, stack: tuple[str, ...]) -> None:
        nonlocal current, index
        if path in stack:
            return
        sf = workspace.files[path]
        fscan = scan.files.get(path)
        if fscan is None:
            return
        items: list[tuple[int, int, str, object]] = []
        for start, end in fscan.text_segments:
            items.append((start, 0, "text", (start, end)))
        for section in fscan.sections:
            items.append((_section_offsets(sf, section.heading_span), 1, "heading", section))
        for inc in fscan.includes:
            target = resolve_include(path, inc.target, workspace.files)
            if target:
                items.append((_section_offsets(sf, inc.span), 2, "include", (target, inc.target)))
        items.sort(key=lambda row: (row[0], row[1]))
        for offset, _rank, kind, payload in items:
            if kind == "text":
                start, end = payload  # type: ignore[misc]
                pieces = _subtract_math([(start, end)], fscan.math_spans)
                chunk = " ".join(sf.text[a:b] for a, b in pieces)
                if not chunk.strip():
                    continue
                if current is None:
                    front.append(chunk)
                else:
                    current["chunks"].append(chunk)
            elif kind == "heading":
                section = payload  # type: ignore[assignment]
                close()
                index += 1
                current = {
                    "id": f"S{index}",
                    "title": section.title,
                    "level": section.level,
                    "role": classify_role(section.title),
                    "file": path,
                    "span": section.heading_span,
                    "contribution": _contribution_before(sf.text, offset),
                    "chunks": [],
                    "has_heading": True,
                }
            else:
                target, _raw = payload  # type: ignore[misc]
                walk(target, stack + (path,))

    walk(workspace.main_path, ())
    close()
    if any(chunk.strip() for chunk in front):
        prose = re.sub(r"\s+", " ", " ".join(front)).strip()
        sf = workspace.files[workspace.main_path]
        first = scan.files[workspace.main_path].sections
        span = _span(sf, 0, min(1, len(sf.text))) if sf.text else None
        if span is not None:
            rows.insert(0, SectionText(
                id="S0", title="Abstract / front matter", level=0, role="abstract",
                file_path=workspace.main_path, heading_span=span, prose=prose,
                contribution="unknown", author_approved=False,
                sentences=split_sentences(prose),
            ))
            for number, row in enumerate(rows):
                row.id = f"S{number}"
    return rows


def _subtract_math(segments: list[tuple[int, int]], math_spans: list[tuple[int, int]]):
    result = []
    for start, end in segments:
        pieces = [(start, end)]
        for ms, me in math_spans:
            nxt = []
            for a, b in pieces:
                if me <= a or ms >= b:
                    nxt.append((a, b))
                    continue
                if ms > a:
                    nxt.append((a, min(ms, b)))
                if me < b:
                    nxt.append((max(me, a), b))
            pieces = nxt
        result.extend(p for p in pieces if p[1] > p[0])
    return result


def classify_role(title: str) -> str:
    lowered = title.lower()
    for role, keys in ROLE_KEYWORDS.items():
        if any(key in lowered for key in keys):
            return role
    return "unknown"


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentences: list[str] = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if sentences:
            last_word = re.sub(r"[^A-Za-z.]", "", sentences[-1].split()[-1]).lower().strip(".")
            if last_word in ABBREVIATIONS:
                sentences[-1] = sentences[-1] + " " + stripped
                continue
        sentences.append(stripped)
    return sentences


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text.lower())


@dataclass
class StyleProfile:
    sentence_count: int
    word_count: int
    mean_sentence_len: float
    std_sentence_len: float
    transition_rate: float
    math_lead_rate: float
    passive_rate: float
    function_vector: dict[str, float]
    top_transitions: list[tuple[str, int]]
    type_token_ratio: float
    paragraph_count: int

    def as_dict(self) -> dict:
        return {
            "sentence_count": self.sentence_count,
            "word_count": self.word_count,
            "mean_sentence_len": round(self.mean_sentence_len, 2),
            "std_sentence_len": round(self.std_sentence_len, 2),
            "transition_rate": round(self.transition_rate, 3),
            "math_lead_rate": round(self.math_lead_rate, 3),
            "passive_rate": round(self.passive_rate, 3),
            "function_word_profile": {k: round(v, 4) for k, v in self.function_vector.items()},
            "top_transitions": self.top_transitions,
            "type_token_ratio": round(self.type_token_ratio, 3),
            "paragraph_count": self.paragraph_count,
        }


def style_profile(text: str, sentences: list[str] | None = None) -> StyleProfile:
    sentences = sentences if sentences is not None else split_sentences(text)
    words = _words(text)
    lengths = [len(_words(s)) for s in sentences] or [0]
    mean = sum(lengths) / len(lengths)
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    transitions = []
    for sentence in sentences:
        lowered = sentence.lower()
        for phrase in TRANSITIONS:
            if lowered.startswith(phrase):
                transitions.append(phrase)
                break
    math_lead = 0
    for sentence in sentences:
        if "$" in sentence or MATH_LEAD.search(sentence):
            math_lead += 1
    passive = len(PASSIVE.findall(text))
    counts = {w: 0 for w in FUNCTION_WORDS}
    for word in words:
        if word in counts:
            counts[word] += 1
    total = max(len(words), 1)
    vector = {k: v / total for k, v in counts.items()}
    ttr = len(set(words)) / total
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    top = sorted({t: transitions.count(t) for t in transitions}.items(),
                 key=lambda kv: (-kv[1], kv[0]))[:6]
    return StyleProfile(
        sentence_count=len(sentences), word_count=len(words), mean_sentence_len=mean,
        std_sentence_len=math.sqrt(var), transition_rate=len(transitions) / max(len(sentences), 1),
        math_lead_rate=math_lead / max(len(sentences), 1), passive_rate=passive / max(len(sentences), 1),
        function_vector=vector, top_transitions=top, type_token_ratio=ttr,
        paragraph_count=len(paragraphs),
    )


@dataclass
class Baseline:
    status: str
    reason: str
    papers_used: int
    sentences: int
    profile: StyleProfile | None
    axes: dict[str, tuple[float, float]] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "papers_used": self.papers_used,
            "sentences": self.sentences,
            "profile": self.profile.as_dict() if self.profile else None,
            "axes": {k: [round(a, 4), round(b, 4)] for k, (a, b) in self.axes.items()},
        }


def build_baseline(approved_texts: list[str], min_papers: int = 3,
                   min_sentences: int = 60) -> Baseline:
    usable = [t for t in approved_texts if len(split_sentences(t)) >= 8]
    sentences = sum(len(split_sentences(t)) for t in usable)
    if len(usable) < min_papers:
        return Baseline("insufficient_evidence",
                        f"Only {len(usable)} approved paper(s) with usable prose; at least "
                        f"{min_papers} are required before any style comparison is shown.",
                        len(usable), sentences, None)
    if sentences < min_sentences:
        return Baseline("insufficient_evidence",
                        f"Only {sentences} usable sentences; at least {min_sentences} are "
                        "required to estimate a stable profile.", len(usable), sentences, None)
    profile = style_profile(" \n\n ".join(usable))
    axes = {
        "mean_sentence_len": (profile.mean_sentence_len, max(profile.std_sentence_len, 1.0)),
        "transition_rate": (profile.transition_rate, 0.08),
        "math_lead_rate": (profile.math_lead_rate, 0.10),
        "passive_rate": (profile.passive_rate, 0.06),
    }
    return Baseline("ok", "Computed from approved primary-author prose only.",
                    len(usable), sentences, profile, axes)


def drift_cards(sections: list[SectionText], baseline: Baseline,
                min_section_sentences: int = 6) -> list[dict]:
    cards = []
    if baseline.status != "ok" or baseline.profile is None:
        return []
    for section in sections:
        if not section.author_approved:
            continue
        if len(section.sentences) < min_section_sentences:
            cards.append({
                "section_id": section.id,
                "title": section.title,
                "status": "insufficient_evidence",
                "reason": f"{len(section.sentences)} sentence(s); at least "
                          f"{min_section_sentences} are needed.",
                "span": section.heading_span.as_dict(),
            })
            continue
        prof = style_profile(section.prose, section.sentences)
        axes = {}
        for name, (base, spread) in baseline.axes.items():
            value = getattr(prof, name)
            z = (value - base) / spread if spread else 0.0
            axes[name] = {"value": round(value, 3), "baseline": round(base, 3),
                          "difference_in_baseline_spread": round(z, 2)}
        total = math.sqrt(sum(v["difference_in_baseline_spread"] ** 2 for v in axes.values()))
        confidence = "low" if len(section.sentences) < 12 else (
            "moderate" if len(section.sentences) < 24 else "higher")
        cards.append({
            "section_id": section.id,
            "title": section.title,
            "status": "observed",
            "axes": axes,
            "combined_deviation": round(total, 2),
            "sample": {"sentences": len(section.sentences), "words": prof.word_count,
                       "confidence": confidence},
            "note": "A difference is a description of this section, not a quality judgement "
                    "and not evidence of authorship. Small samples produce unstable numbers.",
            "span": section.heading_span.as_dict(),
        })
    return cards


def cognitive_skeleton(workspace: Workspace, scan: DocumentScan,
                       sections: list[SectionText]) -> dict:
    tree: list[dict] = []
    stack: list[dict] = []
    for section in sections:
        node = {
            "id": section.id,
            "title": section.title,
            "role": section.role,
            "level": section.level,
            "file": section.file_path,
            "span": section.heading_span.as_dict(),
            "children": [],
        }
        while stack and stack[-1]["level"] >= section.level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            tree.append(node)
        stack.append(node)

    environments = []
    for path in scan.order:
        for env in scan.files[path].environments:
            environments.append({"name": env.name, "span": env.span.as_dict()})

    labels = []
    for label in scan.all_labels():
        labels.append({"key": label.key, "span": label.span.as_dict()})
    refs = {}
    for ref in scan.all_refs():
        refs[ref.key] = refs.get(ref.key, 0) + 1

    symbols: dict[str, dict] = {}
    for path in scan.order:
        sf = workspace.files[path]
        for start, end in scan.files[path].math_spans:
            chunk = sf.text[start:end]
            masked = re.sub(r"\\(?:begin|end|label|ref|eqref|cite)\s*\{[^}]*\}",
                            lambda m: " " * len(m.group(0)), chunk)
            masked = re.sub(r"\\[A-Za-z]+", lambda m: " " * len(m.group(0)), masked)
            for match in re.finditer(r"(?<![\\A-Za-z])[A-Za-z][A-Za-z0-9]{1,24}(?![A-Za-z])", masked):
                token = match.group(0)
                entry = symbols.setdefault(token, {"count": 0, "first": None})
                entry["count"] += 1
                if entry["first"] is None:
                    entry["first"] = _span(sf, start + match.start(), start + match.end()).as_dict()
    top_symbols = sorted(symbols.items(), key=lambda kv: (-kv[1]["count"], kv[0]))[:40]

    return {
        "section_tree": tree,
        "environment_sequence": environments,
        "label_topology": {"labels": labels, "reference_counts": refs},
        "symbol_index": [{"symbol": k, "count": v["count"], "first": v["first"]}
                         for k, v in top_symbols],
        "notes": {
            "model_used": None,
            "section_roles": "Dictionary-based; unknown titles stay 'unknown'.",
            "symbols": "Index only. Frequency does not imply a definition.",
        },
    }


SYNONYMS = {
    "problem": {"problem", "optimization", "objective", "formulation", "model", "assumption"},
    "method": {"method", "approach", "algorithm", "design", "solution"},
    "evaluation": {"evaluation", "experiment", "results", "performance", "benchmark"},
    "introduction": {"introduction", "motivation", "contribution", "overview"},
    "related_work": {"related", "background", "prior", "literature"},
    "conclusion": {"conclusion", "summary", "future"},
}


def navigate(query: str, sections: list[SectionText], max_results: int = 3) -> dict:
    normalized = re.sub(r"[^a-z0-9\s]", " ", query.lower())
    tokens = [t for t in normalized.split() if len(t) > 2 and t not in {"the", "where", "what", "is", "are", "of", "in", "and"}]
    if not tokens:
        return {"status": "not_found", "query": query,
                "reason": "The query contains no searchable terms.", "matches": []}
    wanted_roles = set()
    for token in tokens:
        for role, words in SYNONYMS.items():
            if token in words:
                wanted_roles.add(role)
    scored = []
    for section in sections:
        title_tokens = set(re.findall(r"[a-z0-9]+", section.title.lower()))
        overlap = len(title_tokens & set(tokens))
        score = 0.0
        reasons = []
        if overlap:
            score += 2.0 * overlap
            reasons.append(f"{overlap} title term(s) match")
        if section.role in wanted_roles:
            score += 4.0
            reasons.append(f"section role '{section.role}' matches the question")
        body_hits = sum(1 for t in tokens if re.search(rf"\b{re.escape(t)}\b", section.prose.lower()))
        if body_hits:
            score += min(body_hits * 0.5, 2.0)
            reasons.append(f"{body_hits} query term(s) occur in the section text")
        if score > 0:
            scored.append((score, section, reasons))
    scored.sort(key=lambda row: (-row[0], row[1].id))
    if not scored or scored[0][0] < 2.0:
        return {"status": "not_found", "query": query,
                "reason": "No section matched strongly enough. No location is invented.",
                "matches": []}
    return {
        "status": "found",
        "query": query,
        "matches": [
            {"section_id": s.id, "title": s.title, "role": s.role,
             "score": round(score, 2), "reasons": reasons, "span": s.heading_span.as_dict()}
            for score, s, reasons in scored[:max_results]
        ],
    }
