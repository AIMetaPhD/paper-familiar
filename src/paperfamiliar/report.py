"""Human and agent reports. Exports never contain the full manuscript by default."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

STATUS_LABEL = {
    "verified_error": "Verified error",
    "source_corroborated": "Source corroborated (metadata only)",
    "candidate": "Candidate — needs your review",
    "insufficient_evidence": "Insufficient evidence",
    "unavailable_offline": "Unavailable offline",
    "needs_expert_review": "Needs expert review",
    "rejected_source_target_invalid": "Rejected by quote gate",
}
DECISION_LABEL = {
    "unreviewed": "Not reviewed",
    "accepted": "Accepted",
    "dismissed": "Dismissed",
    "needs_review": "Marked for review",
}


def _integrity_warning(integrity: dict[str, Any] | None) -> str | None:
    if not integrity or integrity.get("status") == "unchanged":
        return None
    if integrity.get("status") == "unavailable":
        return ("> **Source unavailable.** The original source folder is no longer readable; this "
                "report describes the stored analysis snapshot.")
    paths = sorted({row["path"] for row in integrity.get("files", [])
                    if row["state"] != "unchanged"})
    listed = ", ".join(f"`{p}`" for p in paths[:5])
    if len(paths) > 5:
        listed += f" (+{len(paths) - 5} more)"
    return ("> **Source changed after analysis.** " + listed +
            " no longer match the analyzed snapshot, so line/column coordinates and quotes may be "
            "stale. Re-run the audit before acting on this report.")


def build_markdown_report(summary: dict[str, Any]) -> str:
    findings = summary["findings"]
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["evidence_status"]] = counts.get(finding["evidence_status"], 0) + 1
    lines = [
        "# PaperFamiliar report",
        "",
        f"- Run: `{summary['id']}`",
        f"- Source: {summary['label']}",
        f"- Main file: `{summary['main_path']}`",
        f"- Document revision: `{summary['revision_id']}`",
        f"- Created: {summary['created_at']}",
        f"- Mode: {summary.get('mode', 'workspace')}",
        "",
        "## Summary",
        "",
        f"- Files scanned: {summary['stats']['files_scanned']}",
        f"- Bibliography entries: {summary['stats']['bib_entries']}",
        f"- Findings: {len(findings)}",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"  - {STATUS_LABEL.get(status, status)}: {count}")
    warning = _integrity_warning(summary.get("source_integrity"))
    if warning:
        lines += ["", warning]
    if summary.get("assumptions"):
        lines += ["", "## Demo assumptions", ""]
        lines += [f"- {item}" for item in summary["assumptions"]]

    lines += ["", "## Findings", ""]
    if not findings:
        lines.append("No findings were produced. That is not a statement that the paper is correct.")
    for finding in findings:
        span = finding["source_span"]
        lines += [
            f"### {finding['id']} — {finding['claim']}",
            "",
            f"- Status: **{STATUS_LABEL.get(finding['evidence_status'], finding['evidence_status'])}**",
            f"- Class: {finding['finding_class']}",
            f"- Severity: {finding['severity']}",
            f"- Your decision: {DECISION_LABEL.get(finding['human_decision'], finding['human_decision'])}",
            f"- Location: `{span['file_path']}:{span['start_line']}:{span['start_col']}`",
            f"- Exact quote: `{span['exact_quote'][:300].replace('`', 'ˋ')}`",
            f"- Detail: {finding['detail']}",
        ]
        if finding.get("rule_scope"):
            lines.append(f"- Rule scope: {finding['rule_scope']}")
        lines.append("")

    if summary.get("security_events"):
        lines += ["## Security events", ""]
        for event in summary["security_events"]:
            where = ""
            if event.get("source_span"):
                span = event["source_span"]
                where = f" at `{span['file_path']}:{span['start_line']}`"
            lines.append(f"- **{event['kind']}**{where}: {event['detail']}")
        lines.append("")

    style = summary.get("style", {})
    baseline = style.get("baseline", {})
    lines += ["## Author style (descriptive, not a score)", "",
              f"- Baseline status: {baseline.get('status')}",
              f"- Papers used: {baseline.get('papers_used')}",
              f"- Sentences in baseline: {baseline.get('sentences')}",
              f"- {baseline.get('reason', '')}"]
    if baseline.get("profile"):
        prof = baseline["profile"]
        lines += [
            f"- Mean sentence length: {prof['mean_sentence_len']} words "
            f"(spread {prof['std_sentence_len']})",
            f"- Transition-opening rate: {prof['transition_rate']}",
            f"- Math-lead rate: {prof['math_lead_rate']}",
            f"- Passive-construction rate: {prof['passive_rate']}",
        ]
        if prof.get("top_transitions"):
            lines.append("- Frequent opening transitions: " + ", ".join(
                f"'{name}' ×{count}" for name, count in prof["top_transitions"]))
    drift = style.get("drift", [])
    if isinstance(drift, list) and drift and drift[0].get("status") == "insufficient_evidence":
        lines += ["", f"Drift cards withheld: {drift[0].get('reason')}"]
    elif isinstance(drift, list):
        for card in drift:
            if card.get("status") != "observed":
                continue
            lines.append("")
            lines.append(f"### {card['title']} ({card['section_id']})")
            lines.append("")
            lines.append("| Axis | This section | Baseline | Difference (baseline spread) |")
            lines.append("|---|---|---|---|")
            for axis, values in card["axes"].items():
                lines.append(f"| {axis} | {values['value']} | {values['baseline']} | "
                             f"{values['difference_in_baseline_spread']} |")
            lines.append(f"\nSample: {card['sample']['sentences']} sentences, "
                         f"{card['sample']['words']} words. {card['note']}")

    lines += ["", "## Limitations", "",
              "- `verified_error` means a mechanically decidable rule failed; it does not "
              "mean the paper is wrong.",
              "- Metadata that matches a real publication does not show that the paper "
              "supports a claim.",
              "- Symbol findings are heuristic candidates, not proofs.",
              "- This report never modifies the manuscript.",
              ""]
    return "\n".join(lines)


def build_agent_feedback(summary: dict[str, Any]) -> dict:
    approved = [f for f in summary["findings"] if f["human_decision"] == "accepted"]
    dismissed = [f for f in summary["findings"] if f["human_decision"] == "dismissed"]
    baseline = summary.get("style", {}).get("baseline", {})
    integrity = summary.get("source_integrity")
    constraints = [
        "Edit only the text covered by an approved finding.",
        "Do not change technical meaning, variable names, equations, or conclusions.",
        "Return a unified diff first; write to disk only after explicit user approval.",
        "Do not use metadata corroboration as evidence that a claim is supported.",
        "Do not rewrite passages merely because they differ from the author's baseline.",
        "Do not add citations that are not present in the supplied bibliography.",
    ]
    if integrity and integrity.get("status") != "unchanged":
        constraints.append(
            "The source changed after analysis; re-run the audit before applying these findings.")
    return {
        "schema": "paperfamiliar.agent-feedback/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_revision_id": summary["revision_id"],
        "constraints": constraints,
        "source_integrity": integrity,
        "approved_findings": [
            {"id": f["id"], "rule_id": f["rule_id"], "status": f["evidence_status"],
             "claim": f["claim"], "source_span": f["source_span"]}
            for f in approved
        ],
        "dismissed_findings": [
            {"id": f["id"], "rule_id": f["rule_id"]} for f in dismissed
        ],
        "style_profile": baseline.get("profile") if baseline.get("status") == "ok" else None,
        "style_status": baseline.get("status"),
        "cognitive_profile_file": "cognitive-structure-profile.json",
        "excluded_by_default": ["full manuscript text", "API keys", "unapproved quotations"],
    }


def build_style_guide(summary: dict[str, Any]) -> str:
    baseline = summary.get("style", {}).get("baseline", {})
    lines = ["# Author style guide", "",
             "This guide describes measured habits in the approved reference papers. "
             "It is not a rulebook and not a quality score.", ""]
    if baseline.get("status") != "ok":
        lines.append(f"Status: {baseline.get('status')}. {baseline.get('reason', '')}")
        lines.append("")
        return "\n".join(lines)
    prof = baseline["profile"]
    lines += [
        f"Reference sample: {baseline['papers_used']} paper(s), {baseline['sentences']} sentences.",
        "",
        "## Measured habits",
        "",
        f"- Sentences average **{prof['mean_sentence_len']} words** "
        f"(spread {prof['std_sentence_len']}).",
        f"- About **{round(prof['transition_rate'] * 100)}%** of sentences open with an explicit "
        "transition.",
        f"- About **{round(prof['math_lead_rate'] * 100)}%** of sentences introduce or carry "
        "mathematical content.",
        f"- Passive constructions occur at **{prof['passive_rate']} per sentence**.",
    ]
    if prof.get("top_transitions"):
        lines.append("- Recurring opening transitions: " + ", ".join(
            f"`{name}`" for name, _ in prof["top_transitions"]))
    lines += ["", "## How to use this with a writing agent", "",
              "1. Keep technical content and claims unchanged.",
              "2. Prefer the author's own transitions where a sentence opens a new step.",
              "3. Match sentence-length rhythm rather than copying phrases.",
              "4. Treat drift cards as questions, not instructions.",
              ""]
    return "\n".join(lines)
