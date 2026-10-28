import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import { api } from "./api";
import type {
  DriftCard,
  Finding,
  NavigateResult,
  RunSummary,
  SectionMeta,
  SourceSpan,
} from "./types";

const STATUS_TEXT: Record<string, string> = {
  verified_error: "Verified error",
  source_corroborated: "Metadata only",
  candidate: "Candidate",
  insufficient_evidence: "Insufficient evidence",
  unavailable_offline: "Offline",
  needs_expert_review: "Needs expert",
  rejected_source_target_invalid: "Rejected",
};

const DECISION_TEXT: Record<string, string> = {
  unreviewed: "Unreviewed",
  accepted: "Accepted",
  dismissed: "Dismissed",
  needs_review: "Marked for review",
};

function StatusChip({ status }: { status: string }) {
  return (
    <span className={`chip chip-${status}`} title={STATUS_TEXT[status] ?? status}>
      {STATUS_TEXT[status] ?? status}
    </span>
  );
}

function shortSha(sha: string) {
  return sha.slice(0, 10);
}

interface Mark {
  start: number;
  end: number;
  findingId: string;
  status: string;
}

function marksForLine(
  findings: Finding[],
  lines: string[],
  file: string,
  lineNumber: number,
): Mark[] {
  const marks: Mark[] = [];
  for (const finding of findings) {
    const span = finding.source_span;
    if (span.file_path !== file) continue;
    if (lineNumber < span.start_line || lineNumber > span.end_line) continue;
    const text = Array.from(lines[lineNumber - 1] ?? "");
    let start = lineNumber === span.start_line ? span.start_col - 1 : 0;
    let end = lineNumber === span.end_line ? span.end_col - 1 : text.length;
    start = Math.max(0, Math.min(start, text.length));
    end = Math.max(start, Math.min(end, text.length));
    marks.push({ start, end, findingId: finding.id, status: finding.evidence_status });
  }
  return marks;
}

function renderLine(line: string, marks: Mark[]) {
  const chars = Array.from(line);
  if (!marks.length) return line || " ";
  const sorted = [...marks].sort((a, b) => a.start - b.start);
  const out: ReactElement[] = [];
  let cursor = 0;
  sorted.forEach((mark, index) => {
    if (mark.start > cursor) {
      out.push(<span key={`t${index}`}>{chars.slice(cursor, mark.start).join("")}</span>);
    }
    const from = Math.max(cursor, mark.start);
    out.push(
      <mark key={`m${index}`} className={`mark mark-${mark.status}`} data-finding={mark.findingId}>
        {chars.slice(from, mark.end).join("")}
      </mark>,
    );
    cursor = Math.max(cursor, mark.end);
  });
  if (cursor < chars.length) out.push(<span key="tail">{chars.slice(cursor).join("")}</span>);
  return out;
}

function roleLabel(role: string) {
  return role === "related_work" ? "related work" : role.replace("_", " ");
}

function SectionTree({
  sections,
  onSelect,
  onLabel,
}: {
  sections: SectionMeta[];
  onSelect: (section: SectionMeta) => void;
  onLabel: (section: SectionMeta, contribution: string) => void;
}) {
  return (
    <ul className="section-tree">
      {sections.map((section) => (
        <li key={section.id} style={{ marginLeft: `${Math.max(0, section.level - 2) * 12}px` }}>
          <button className="section-row" onClick={() => onSelect(section)}>
            <span className="section-title">{section.title}</span>
            <span className="role">{roleLabel(section.role)}</span>
          </button>
          <div className="section-meta">
            <span>
              {section.sentence_count} sent · {section.word_count} words
            </span>
            <select
              aria-label={`Contribution label for ${section.title}`}
              value={section.contribution}
              onChange={(event) => onLabel(section, event.target.value)}
            >
              <option value="sole_or_primary">I wrote it</option>
              <option value="coauthored">Coauthored</option>
              <option value="not_primary">Not mine</option>
              <option value="unknown">Unknown</option>
            </select>
          </div>
        </li>
      ))}
    </ul>
  );
}

function LedgerCard({
  finding,
  active,
  onSelect,
  onDecide,
}: {
  finding: Finding;
  active: boolean;
  onSelect: () => void;
  onDecide: (decision: string) => void;
}) {
  const span = finding.source_span;
  return (
    <article className={`ledger-card ${active ? "active" : ""}`} id={`card-${finding.id}`}>
      <header>
        <StatusChip status={finding.evidence_status} />
        <span className="class-tag">{finding.finding_class}</span>
        <span className={`severity severity-${finding.severity}`}>{finding.severity}</span>
      </header>
      <h3>{finding.claim}</h3>
      <p className="detail">{finding.detail}</p>
      <blockquote onClick={onSelect} title="Jump to the exact source location">
        <code>{span.exact_quote.length > 240 ? `${span.exact_quote.slice(0, 240)}…` : span.exact_quote}</code>
      </blockquote>
      <button className="location" onClick={onSelect}>
        {span.file_path}:{span.start_line}:{span.start_col}
      </button>
      {finding.rule_scope && (
        <details className="scope">
          <summary>What this rule can and cannot see</summary>
          <p>{finding.rule_scope}</p>
        </details>
      )}
      <footer>
        <button
          className={`decide ${finding.human_decision === "accepted" ? "on" : ""}`}
          onClick={() => onDecide("accepted")}
        >
          Accept
        </button>
        <button
          className={`decide ${finding.human_decision === "dismissed" ? "on" : ""}`}
          onClick={() => onDecide("dismissed")}
        >
          Dismiss
        </button>
        <span className="decision">{DECISION_TEXT[finding.human_decision]}</span>
      </footer>
    </article>
  );
}

function DriftCardView({ card }: { card: DriftCard }) {
  if (card.status !== "observed" || !card.axes) {
    return (
      <div className="drift-card muted">
        <strong>{card.title}</strong>
        <p>{card.reason}</p>
      </div>
    );
  }
  return (
    <div className="drift-card">
      <header>
        <strong>{card.title}</strong>
        <span className="sample">
          {card.sample?.sentences} sent · {card.sample?.confidence} confidence
        </span>
      </header>
      <table>
        <thead>
          <tr>
            <th>axis</th>
            <th>section</th>
            <th>your baseline</th>
            <th>Δ spread</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(card.axes).map(([axis, values]) => (
            <tr key={axis}>
              <td>{axis.replaceAll("_", " ")}</td>
              <td>{values.value}</td>
              <td>{values.baseline}</td>
              <td className={Math.abs(values.difference_in_baseline_spread) > 2 ? "far" : ""}>
                {values.difference_in_baseline_spread}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">{card.note}</p>
    </div>
  );
}

export default function App() {
  const [run, setRun] = useState<RunSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [filePath, setFilePath] = useState<string>("");
  const [fileText, setFileText] = useState<string>("");
  const [fileUnchanged, setFileUnchanged] = useState<boolean>(true);
  const [activeFinding, setActiveFinding] = useState<string | null>(null);
  const [tab, setTab] = useState<"evidence" | "style" | "structure">("evidence");
  const [query, setQuery] = useState("");
  const [nav, setNav] = useState<NavigateResult | null>(null);
  const [openPath, setOpenPath] = useState("");
  const [showOpen, setShowOpen] = useState(false);
  const [exportInfo, setExportInfo] = useState<{ directory: string; files: string[] } | null>(null);
  const [sourceIntact, setSourceIntact] = useState<boolean | null>(null);
  const sourceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.health().catch((err: Error) => setError(err.message));
  }, []);

  const lines = useMemo(() => fileText.split(/\r\n|\n|\r/), [fileText]);

  async function loadFile(runArg: RunSummary, path: string) {
    setFilePath(path);
    setFileText("loading…");
    try {
      const data = await api.file(runArg.id, path);
      setFileText(data.text);
      setFileUnchanged(data.unchanged);
    } catch (err) {
      setFileText("");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function adoptRun(next: RunSummary) {
    setRun(next);
    setNav(null);
    setActiveFinding(null);
    setExportInfo(null);
    setSourceIntact(null);
    setTab("evidence");
    await loadFile(next, next.main_path);
  }

  async function loadDemo() {
    setBusy("Loading the synthetic demo…");
    setError(null);
    try {
      await adoptRun(await api.demo());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function openWorkspace() {
    if (!openPath.trim()) return;
    setBusy("Scanning the workspace…");
    setError(null);
    try {
      await adoptRun(await api.openWorkspace(openPath.trim()));
      setShowOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function selectFinding(finding: Finding) {
    setActiveFinding(finding.id);
    setTab("evidence");
    if (finding.source_span.file_path !== filePath && run) {
      void loadFile(run, finding.source_span.file_path);
    }
  }

  useEffect(() => {
    if (!activeFinding || !run) return;
    const finding = run.findings.find((f) => f.id === activeFinding);
    if (!finding) return;
    const node = document.querySelector(`[data-line="${finding.source_span.start_line}"]`);
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeFinding, filePath, run]);

  async function decide(finding: Finding, decision: string) {
    if (!run) return;
    const next = decision === finding.human_decision ? "unreviewed" : decision;
    try {
      await api.decide(run.id, finding.id, next);
      setRun({
        ...run,
        findings: run.findings.map((f) =>
          f.id === finding.id ? { ...f, human_decision: next as Finding["human_decision"] } : f,
        ),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function labelSection(section: SectionMeta, contribution: string) {
    if (!run) return;
    try {
      await api.label(run.id, section.id, contribution);
      setRun({
        ...run,
        sections: run.sections.map((s) =>
          s.id === section.id
            ? { ...s, contribution, author_approved: contribution === "sole_or_primary" }
            : s,
        ),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function runNavigator() {
    if (!run || !query.trim()) return;
    try {
      setNav(await api.navigate(run.id, query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function doExport() {
    if (!run) return;
    setBusy("Writing exports…");
    try {
      const info = await api.exportRun(run.id);
      setExportInfo(info);
      const check = await api.file(run.id, run.main_path);
      setSourceIntact(check.unchanged);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function jumpToSpan(span: SourceSpan) {
    const finding = run?.findings.find(
      (f) =>
        f.source_span.file_path === span.file_path &&
        f.source_span.start_line === span.start_line,
    );
    if (finding) {
      selectFinding(finding);
    } else if (run) {
      void loadFile(run, span.file_path).then(() => {
        requestAnimationFrame(() => {
          document.querySelector(`[data-line="${span.start_line}"]`)?.scrollIntoView({
            block: "center",
            behavior: "smooth",
          });
        });
      });
    }
  }

  if (!run) {
    return (
      <div className="landing">
        <div className="landing-inner">
          <p className="eyebrow">PaperFamiliar · local-first manuscript instrument</p>
          <h1>Verify the research.<br />Preserve the author's voice.</h1>
          <p className="lede">
            A LaTeX-first workbench that shows only what it can point to: mechanical citation
            errors, honest metadata, and your own writing habits. No account. No cloud. No
            similarity percentage.
          </p>
          <div className="landing-actions">
            <button className="primary" onClick={loadDemo} disabled={!!busy}>
              Load the offline demo
            </button>
            <button className="ghost" onClick={() => setShowOpen(true)} disabled={!!busy}>
              Open a LaTeX workspace
            </button>
          </div>
          {busy && <p className="busy">{busy}</p>}
          {error && <p className="error">{error}</p>}
          <ul className="privacy">
            <li>Binds 127.0.0.1 only; no telemetry, fonts or CDN.</li>
            <li>Every finding must reproduce an exact quote from your bytes.</li>
            <li>Style differences are described, never scored or called errors.</li>
          </ul>
          <p className="fine">
            Demo data is synthetic. It includes deliberate defects (a missing citation, a
            duplicate label, a misattributed citation, and prompt-injection text in a comment).
          </p>
        </div>
        {showOpen && (
          <div className="modal-backdrop" onClick={() => setShowOpen(false)}>
            <div className="modal" onClick={(event) => event.stopPropagation()}>
              <h2>Open a workspace</h2>
              <p>
                Paste the absolute path to a folder containing .tex and .bib files, or to a .zip.
                PaperFamiliar reads it in place and never writes to it.
              </p>
              <input
                autoFocus
                value={openPath}
                placeholder="C:\Users\you\Documents\论文 项目"
                onChange={(event) => setOpenPath(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && openWorkspace()}
              />
              <div className="modal-actions">
                <button className="ghost" onClick={() => setShowOpen(false)}>Cancel</button>
                <button className="primary" onClick={openWorkspace} disabled={!!busy}>
                  Scan workspace
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  const drift = run.style.drift;
  const findingsByFile = run.files.map((file) => ({
    ...file,
    count: run.findings.filter((f) => f.source_span.file_path === file.path).length,
  }));
  const statusCounts = run.findings.reduce<Record<string, number>>((acc, finding) => {
    acc[finding.evidence_status] = (acc[finding.evidence_status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">PF</span>
          <div>
            <strong>PaperFamiliar</strong>
            <span className="run-label">{run.label}</span>
          </div>
        </div>
        <div className="run-meta">
          <span className="pill" title="No network, no telemetry">offline</span>
          <span className="mono" title={run.revision_id}>
            rev {shortSha(run.revision_id)}
          </span>
          <span>{run.files.length} files · {run.findings.length} findings</span>
          {!fileUnchanged && <span className="warn">source changed on disk</span>}
        </div>
        <div className="top-actions">
          <button className="ghost" onClick={loadDemo}>Reload demo</button>
          <button className="ghost" onClick={() => setShowOpen(true)}>Open workspace</button>
          <button className="primary" onClick={doExport}>Export</button>
        </div>
      </header>

      {error && (
        <div className="banner error" role="alert">
          {error}
          <button onClick={() => setError(null)}>dismiss</button>
        </div>
      )}
      {run.assumptions.length > 0 && (
        <div className="banner assumptions">
          <strong>Demo assumptions:</strong> {run.assumptions[0]}
          <details>
            <summary>all</summary>
            <ul>{run.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
          </details>
        </div>
      )}

      <main className="workbench">
        <aside className="pane left">
          <div className="pane-head">
            <h2>Paper map</h2>
            <span className="muted">{run.sections.length} sections</span>
          </div>
          <SectionTree sections={run.sections} onSelect={(s) => jumpToSpan(s.heading_span)}
                       onLabel={labelSection} />
          <div className="navigator">
            <h3>Familiarity navigator</h3>
            <p className="hint">Deterministic. If it cannot find a section, it says so.</p>
            <div className="nav-row">
              <input
                value={query}
                placeholder="where is the optimization problem?"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && runNavigator()}
              />
              <button onClick={runNavigator}>Find</button>
            </div>
            {nav && (
              <div className={`nav-result ${nav.status}`}>
                {nav.status === "found" ? (
                  nav.matches.map((match) => (
                    <button key={match.section_id} onClick={() => jumpToSpan(match.span)}>
                      <strong>{match.title}</strong>
                      <span>{match.reasons.join(" · ")}</span>
                    </button>
                  ))
                ) : (
                  <p>{nav.reason}</p>
                )}
              </div>
            )}
          </div>
          <div className="counts">
            {Object.entries(statusCounts).map(([status, count]) => (
              <div key={status}>
                <StatusChip status={status} />
                <span>{count}</span>
              </div>
            ))}
            {run.security_events.length > 0 && (
              <div className="security">
                <strong>{run.security_events.length} security event(s)</strong>
                <span>{run.security_events[0].kind}</span>
              </div>
            )}
          </div>
        </aside>

        <section className="pane center">
          <div className="file-tabs">
            {findingsByFile.map((file) => (
              <button
                key={file.path}
                className={file.path === filePath ? "active" : ""}
                onClick={() => run && loadFile(run, file.path)}
                title={file.path}
              >
                {file.path.split("/").pop()}
                {file.count > 0 && <span className="badge">{file.count}</span>}
              </button>
            ))}
          </div>
          <div className="source-head">
            <span className="mono">{filePath}</span>
            <span className="mono muted">sha {shortSha(run.files.find((f) => f.path === filePath)?.sha256 ?? "")}</span>
          </div>
          <div className="source" ref={sourceRef}>
            <pre>
              {lines.map((line, index) => {
                const number = index + 1;
                const marks = marksForLine(run.findings, lines, filePath, number);
                const activeLine = activeFinding
                  ? run.findings.find((f) => f.id === activeFinding)?.source_span.start_line === number
                  : false;
                return (
                  <div key={number} className={`src-line ${activeLine ? "active" : ""}`} data-line={number}>
                    <span className="gutter">{number}</span>
                    <code>{renderLine(line, marks)}</code>
                  </div>
                );
              })}
            </pre>
          </div>
          <div className="source-foot">
            <span>Read-only · the manuscript is never edited</span>
            <span className="mono">{fileText.length} chars</span>
          </div>
        </section>

        <aside className="pane right">
          <div className="right-tabs">
            <button className={tab === "evidence" ? "active" : ""} onClick={() => setTab("evidence")}>
              Evidence ({run.findings.length})
            </button>
            <button className={tab === "style" ? "active" : ""} onClick={() => setTab("style")}>
              Style
            </button>
            <button className={tab === "structure" ? "active" : ""} onClick={() => setTab("structure")}>
              Structure
            </button>
          </div>

          {tab === "evidence" && (
            <div className="ledger">
              {run.findings.length === 0 && (
                <p className="empty">
                  No findings. That is not proof the paper is correct — only that no
                  deterministic rule fired.
                </p>
              )}
              {run.findings.map((finding) => (
                <LedgerCard
                  key={finding.id}
                  finding={finding}
                  active={activeFinding === finding.id}
                  onSelect={() => selectFinding(finding)}
                  onDecide={(decision) => decide(finding, decision)}
                />
              ))}
              {run.rejections.length > 0 && (
                <details className="rejections">
                  <summary>{run.rejections.length} finding(s) rejected by the quote gate</summary>
                  <ul>
                    {run.rejections.map((row) => (
                      <li key={row.finding_id}>
                        <code>{row.finding_id}</code> — {row.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <p className="ledger-note">
                “Verified error” means a mechanical rule failed. It does not mean the paper's
                claims are wrong. Accepting a finding never upgrades its evidence level.
              </p>
            </div>
          )}

          {tab === "style" && (
            <div className="style-pane">
              <div className="baseline">
                <h3>Your reference profile</h3>
                <p className={`status-line ${run.style.baseline.status}`}>
                  {run.style.baseline.status === "ok"
                    ? `${run.style.baseline.papers_used} approved papers · ${run.style.baseline.sentences} sentences`
                    : "Insufficient reference data"}
                </p>
                {run.style.baseline.status !== "ok" && <p>{run.style.baseline.reason}</p>}
                {run.style.baseline.profile && (
                  <ul className="baseline-metrics">
                    <li><span>Sentence length</span><strong>{run.style.baseline.profile.mean_sentence_len} words</strong></li>
                    <li><span>Transition openings</span><strong>{Math.round(run.style.baseline.profile.transition_rate * 100)}%</strong></li>
                    <li><span>Math-led sentences</span><strong>{Math.round(run.style.baseline.profile.math_lead_rate * 100)}%</strong></li>
                    <li><span>Passive / sentence</span><strong>{run.style.baseline.profile.passive_rate}</strong></li>
                  </ul>
                )}
                {run.style.baseline.profile?.top_transitions?.length ? (
                  <p className="transitions">
                    {run.style.baseline.profile.top_transitions.map(([name, count]) => (
                      <span key={name}>{name} ×{count}</span>
                    ))}
                  </p>
                ) : null}
              </div>
              <h3 className="section-heading">Drift cards</h3>
              <p className="hint">
                A difference is a description of this section, not a quality judgement and not
                evidence of authorship. Small samples are marked low confidence.
              </p>
              {drift.length === 0 && (
                <p className="empty">
                  No drift cards: {run.style.baseline.reason}
                </p>
              )}
              {drift.map((card) => <DriftCardView key={card.section_id} card={card} />)}
              <p className="note">{run.style.note}</p>
            </div>
          )}

          {tab === "structure" && (
            <div className="structure">
              <h3>Section skeleton</h3>
              <ul className="skeleton">
                {run.sections.map((section) => (
                  <li key={section.id} style={{ marginLeft: `${Math.max(0, section.level - 2) * 14}px` }}>
                    <button onClick={() => jumpToSpan(section.heading_span)}>
                      <span>{section.title}</span>
                      <span className="role">{roleLabel(section.role)}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <h3>Environment sequence</h3>
              <div className="env-sequence">
                {run.cognitive.environment_sequence.map((env, index) => {
                  const counted = run.cognitive.environment_sequence
                    .slice(0, index)
                    .filter((other) => other.name === env.name).length;
                  return (
                    <button key={`${env.name}-${index}`} onClick={() => jumpToSpan(env.span)}>
                      {env.name}{counted ? ` ${counted + 1}` : ""}
                    </button>
                  );
                })}
              </div>
              <h3>Labels and references</h3>
              <p className="hint">
                {run.cognitive.label_topology.labels.length} labels ·{" "}
                {Object.values(run.cognitive.label_topology.reference_counts).reduce((a, b) => a + b, 0)} references
              </p>
              <h3>Symbols seen in math</h3>
              <div className="symbols">
                {run.cognitive.symbol_index.slice(0, 16).map((row) => (
                  <button key={row.symbol} onClick={() => jumpToSpan(row.first)}>
                    <code>{row.symbol}</code>
                    <span>×{row.count}</span>
                  </button>
                ))}
              </div>
              <p className="note">{run.cognitive.notes.symbols}</p>
            </div>
          )}
        </aside>
      </main>

      {showOpen && (
        <div className="modal-backdrop" onClick={() => setShowOpen(false)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h2>Open a workspace</h2>
            <p>
              Paste the absolute path to a folder containing .tex and .bib files, or to a .zip.
              PaperFamiliar reads it in place and never writes to it.
            </p>
            <input
              autoFocus
              value={openPath}
              placeholder="C:\Users\you\Documents\论文 项目"
              onChange={(event) => setOpenPath(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && openWorkspace()}
            />
            <div className="modal-actions">
              <button className="ghost" onClick={() => setShowOpen(false)}>Cancel</button>
              <button className="primary" onClick={openWorkspace} disabled={!!busy}>
                Scan workspace
              </button>
            </div>
          </div>
        </div>
      )}

      {exportInfo && (
        <div className="modal-backdrop" onClick={() => setExportInfo(null)}>
          <div className="modal wide" onClick={(event) => event.stopPropagation()}>
            <h2>Exports written</h2>
            <p className="mono small">{exportInfo.directory}</p>
            <ul className="export-list">
              {exportInfo.files.map((name) => (
                <li key={name}>
                  <a href={api.exportUrl(run.id, name)} download>{name}</a>
                </li>
              ))}
            </ul>
            <p className={sourceIntact === false ? "error" : "ok-line"}>
              {sourceIntact === null
                ? "Source verification pending."
                : sourceIntact
                  ? "Source hash unchanged after export."
                  : "Source changed on disk — exports refer to an earlier revision."}
            </p>
            <p className="fine">
              By default exports contain findings, coordinates and aggregate style metrics, not
              the full manuscript.
            </p>
            <div className="modal-actions">
              <button className="primary" onClick={() => setExportInfo(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {busy && <div className="busy-toast">{busy}</div>}
    </div>
  );
}
