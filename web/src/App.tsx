import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import { api } from "./api";
import ModelsPanel from "./ModelsPanel";
import type {
  DriftCard,
  ExportInfo,
  Finding,
  NavigateResult,
  RunSummary,
  SectionMeta,
  SourceSpan,
  WorkspaceRow,
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

const CONTRIBUTION_OPTIONS: [string, string][] = [
  ["sole_or_primary", "I wrote it"],
  ["coauthored", "Coauthored"],
  ["not_primary", "Not mine"],
  ["unknown", "Unknown"],
];

const LAST_WORKSPACE_KEY = "paperfamiliar.workspace";

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

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
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

function ContributionSelect({
  value,
  onChange,
  ariaLabel,
}: {
  value: string;
  onChange: (next: string) => void;
  ariaLabel: string;
}) {
  return (
    <select aria-label={ariaLabel} value={value} onChange={(event) => onChange(event.target.value)}>
      {CONTRIBUTION_OPTIONS.map(([code, text]) => (
        <option key={code} value={code}>{text}</option>
      ))}
    </select>
  );
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
            <ContributionSelect
              ariaLabel={`Contribution label for ${section.title}`}
              value={section.contribution}
              onChange={(next) => onLabel(section, next)}
            />
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

function DriftCardView({ card, onJump }: { card: DriftCard; onJump: (span: SourceSpan) => void }) {
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
      <button className="location" onClick={() => onJump(card.span)}
              title="Jump to this section's heading in the source">
        {card.span.file_path}:{card.span.start_line}:{card.span.start_col}
      </button>
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

type ImportKind = "manuscript" | "reference";

function ImportModal({
  presetKind,
  onClose,
  onManuscript,
  onReference,
  setError,
}: {
  presetKind: ImportKind;
  onClose: () => void;
  onManuscript: (summary: RunSummary) => void;
  onReference: (workspaceId: string, label: string) => void;
  setError: (message: string | null) => void;
}) {
  const [kind, setKind] = useState<ImportKind>(presetKind);
  const [files, setFiles] = useState<File[] | null>(null);
  const [label, setLabel] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  async function uploadSelected() {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.upload(Array.from(files), label || null, kind);
      if ("kind" in result && "sections" in result) {
        onReference(result.workspace_id, result.label);
      } else {
        onManuscript(result as RunSummary);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function openPath() {
    if (!path.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.openPath(path.trim(), label || null, kind);
      if ("kind" in result && "sections" in result) {
        onReference(result.workspace_id, result.label);
      } else {
        onManuscript(result as RunSummary);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const showDrop = kind === "manuscript" || kind === "reference";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(event) => event.stopPropagation()}>
        <h2>{kind === "reference" ? "Add reference papers (your own earlier work)" : "Open a paper"}</h2>
        <div className="segmented">
          <button className={kind === "manuscript" ? "active" : ""} onClick={() => setKind("manuscript")}>
            Paper to audit
          </button>
          <button className={kind === "reference" ? "active" : ""} onClick={() => setKind("reference")}>
            My earlier papers
          </button>
        </div>
        {kind === "reference" && (
          <p>
            Reference papers build your style baseline. Nothing is compared unless you mark
            sections as your own primary writing.
          </p>
        )}

        {showDrop && (
          <div
            className="drop-zone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (event.dataTransfer.files.length) setFiles(Array.from(event.dataTransfer.files));
            }}
          >
            <p>
              {files
                ? `${files.length} file(s) selected (${formatBytes(files.reduce((a, f) => a + f.size, 0))})`
                : "Drop .tex / .bib files, a .zip, or choose below"}
            </p>
            <div className="drop-actions">
              <button onClick={() => fileRef.current?.click()}>Choose files</button>
              <button onClick={() => folderRef.current?.click()}>Choose folder</button>
            </div>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".tex,.bib,.zip"
              hidden
              onChange={(event) => setFiles(event.target.files ? Array.from(event.target.files) : null)}
            />
            <input
              ref={folderRef}
              type="file"
              hidden
              onChange={(event) => setFiles(event.target.files ? Array.from(event.target.files) : null)}
              {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
            />
          </div>
        )}

        <label className="wide-label">
          Label (optional)
          <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. ICASSP 2026 submission" />
        </label>

        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary" onClick={uploadSelected} disabled={busy || !files?.length}>
            {kind === "reference" ? "Add as reference" : "Audit this paper"}
          </button>
        </div>

        {kind === "manuscript" && (
          <>
            <h3 className="section-heading">…or a folder already on this machine</h3>
            <p className="hint">
              The server reads it in place and never writes to it. Only .tex/.bib/.zip under the
              given path are visible.
            </p>
            <div className="nav-row">
              <input
                value={path}
                placeholder="E:/papers/my_submission or …/paper.zip"
                onChange={(event) => setPath(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && openPath()}
              />
              <button onClick={openPath} disabled={busy || !path.trim()}>Open</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ReferenceModal({
  workspaceId,
  onClose,
  setError,
}: {
  workspaceId: string;
  onClose: () => void;
  setError: (message: string | null) => void;
}) {
  const [sections, setSections] = useState<SectionMeta[] | null>(null);
  const [label, setLabel] = useState("");

  useEffect(() => {
    api.workspace(workspaceId)
      .then((summary) => {
        setSections(summary.sections);
        setLabel(summary.label);
      })
      .catch((err: Error) => setError(err.message));
  }, [workspaceId, setError]);

  async function relabel(section: SectionMeta, contribution: string) {
    try {
      await api.label(workspaceId, section.id, contribution);
      setSections((prev) => prev?.map((s) => (s.id === section.id ? { ...s, contribution } : s)) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(event) => event.stopPropagation()}>
        <h2>Mark your own writing — {label || "reference paper"}</h2>
        <p>
          Only sections you mark <em>“I wrote it”</em> enter your style baseline. Unknown and
          coauthored sections are excluded by default.
        </p>
        {!sections && <p className="busy">Loading sections…</p>}
        <ul className="ref-sections">
          {(sections ?? []).map((section) => (
            <li key={section.id}>
              <span>{section.title}</span>
              <span className="muted small">{section.sentence_count} sentences</span>
              <ContributionSelect
                ariaLabel={`Contribution for ${section.title}`}
                value={section.contribution}
                onChange={(next) => relabel(section, next)}
              />
            </li>
          ))}
        </ul>
        <div className="modal-actions">
          <button className="primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

function SettingsModal({
  onClose,
  onChanged,
  setError,
}: {
  onClose: () => void;
  onChanged: (remaining: WorkspaceRow[]) => void;
  setError: (message: string | null) => void;
}) {
  const [settings, setSettings] = useState<Awaited<ReturnType<typeof api.settings>> | null>(null);
  const [rows, setRows] = useState<WorkspaceRow[]>([]);
  const [confirmWord, setConfirmWord] = useState("");

  async function reload() {
    const [nextSettings, nextList] = await Promise.all([api.settings(), api.workspaces()]);
    setSettings(nextSettings);
    setRows(nextList.workspaces);
    return nextList.workspaces;
  }

  useEffect(() => {
    reload().catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function removeWorkspace(row: WorkspaceRow) {
    if (!window.confirm(`Delete “${row.label}” and its stored copies? Your original folder is never touched.`)) return;
    try {
      await api.deleteWorkspace(row.id);
      if (localStorage.getItem(LAST_WORKSPACE_KEY) === row.id) localStorage.removeItem(LAST_WORKSPACE_KEY);
      onChanged(await reload());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function clearAll() {
    try {
      await api.clearAll();
      localStorage.removeItem(LAST_WORKSPACE_KEY);
      onChanged(await reload());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(event) => event.stopPropagation()}>
        <h2>Local data</h2>
        {!settings && <p className="busy">Loading…</p>}
        {settings && (
          <>
            <p className="mono small">{settings.usage.data_dir}</p>
            <ul className="privacy">
              <li>{settings.usage.workspaces} workspace(s) · {settings.usage.runs} run(s)</li>
              <li>
                stored copies {formatBytes(settings.usage.workspaces_bytes)} ({settings.usage.stored_workspaces} uploaded)
                · exports {formatBytes(settings.usage.exports_bytes)} · cache {formatBytes(settings.usage.cache_bytes)}
                · {settings.usage.path_workspaces} path-imported folder(s) stay where they are
              </li>
              <li>local model: <strong>{settings.providers.local.status}</strong> · cloud: <strong>{settings.providers.cloud.configured ? "configured" : "not configured"}</strong></li>
            </ul>
            <h3 className="section-heading">Workspaces</h3>
            <table className="ws-table">
              <thead>
                <tr><th>label</th><th>kind</th><th>created</th><th></th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.label}</td>
                    <td>{row.kind}</td>
                    <td className="mono small">{row.created_at.slice(0, 19)}</td>
                    <td><button onClick={() => removeWorkspace(row)}>Delete</button></td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={4} className="muted">Nothing stored on this machine.</td></tr>
                )}
              </tbody>
            </table>
            <h3 className="section-heading">Danger zone</h3>
            <p className="hint">
              Removes every workspace record, upload copy, export and cache from this machine.
              Folders imported by path are only unlinked, never deleted.
            </p>
            <div className="nav-row">
              <input
                value={confirmWord}
                placeholder="type DELETE to confirm"
                onChange={(event) => setConfirmWord(event.target.value)}
              />
              <button className="danger" disabled={confirmWord !== "DELETE"} onClick={clearAll}>
                Erase all local data
              </button>
            </div>
          </>
        )}
        <div className="modal-actions">
          <button className="primary" onClick={onClose}>Close</button>
        </div>
      </div>
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
  const [jumpTarget, setJumpTarget] = useState<{ file: string; line: number } | null>(null);
  const [tab, setTab] = useState<"evidence" | "style" | "structure">("evidence");
  const [query, setQuery] = useState("");
  const [nav, setNav] = useState<NavigateResult | null>(null);
  const [showImport, setShowImport] = useState<null | ImportKind>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showModels, setShowModels] = useState(false);
  const [selectedText, setSelectedText] = useState("");
  const [manageReference, setManageReference] = useState<string | null>(null);
  const [referenceRows, setReferenceRows] = useState<WorkspaceRow[]>([]);
  const [exportInfo, setExportInfo] = useState<ExportInfo | null>(null);
  const [recent, setRecent] = useState<WorkspaceRow[]>([]);

  const wsId = run?.workspace_id ?? "";
  const manuscripts = recent.filter((row) => row.kind !== "reference");

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        const list = await api.workspaces();
        setRecent(list.workspaces);
        const saved = localStorage.getItem(LAST_WORKSPACE_KEY);
        if (saved) {
          const hit = list.workspaces.find((row) => row.id === saved && row.kind !== "reference");
          if (hit) {
            adopt(await api.workspace(hit.id));
            return;
          }
        }
        setReferenceRows(list.workspaces.filter((row) => row.kind === "reference"));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lines = useMemo(() => fileText.split(/\r\n|\n|\r/), [fileText]);

  async function loadFile(id: string, path: string) {
    setFilePath(path);
    setFileText("loading…");
    try {
      const data = await api.file(id, path);
      setFileText(data.text);
      setFileUnchanged(data.unchanged);
    } catch (err) {
      setFileText("");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function adopt(next: RunSummary) {
    setRun(next);
    setNav(null);
    setActiveFinding(null);
    setExportInfo(null);
    setTab("evidence");
    if (next.workspace_id) localStorage.setItem(LAST_WORKSPACE_KEY, next.workspace_id);
    await loadFile(next.workspace_id ?? "", next.main_path);
    try {
      const settings = await api.settings();
      setReferenceRows(settings.references);
    } catch {
      /* reference list is best-effort */
    }
  }

  async function loadDemo() {
    setBusy("Loading the synthetic demo…");
    setError(null);
    try {
      await adopt(await api.demo());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function reaudit() {
    if (!wsId) return;
    setBusy("Re-running the offline audit…");
    setError(null);
    try {
      await adopt(await api.reaudit(wsId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function selectFinding(finding: Finding) {
    setActiveFinding(finding.id);
    setJumpTarget({ file: finding.source_span.file_path, line: finding.source_span.start_line });
    setTab("evidence");
    if (finding.source_span.file_path !== filePath) {
      void loadFile(wsId, finding.source_span.file_path);
    }
  }

  useEffect(() => {
    if (!activeFinding || !run) return;
    const finding = run.findings.find((f) => f.id === activeFinding);
    if (!finding) return;
    const node = document.querySelector(`[data-line="${finding.source_span.start_line}"]`);
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeFinding, filePath, run]);

  async function refreshStyle(ids: string[]) {
    if (!wsId) return;
    const next = await api.style(wsId, ids);
    setRun(next);
  }

  async function decide(finding: Finding, decision: string) {
    const next = decision === finding.human_decision ? "unreviewed" : decision;
    try {
      await api.decide(wsId, finding.id, next);
      setRun({
        ...run as RunSummary,
        findings: (run as RunSummary).findings.map((f) =>
          f.id === finding.id ? { ...f, human_decision: next as Finding["human_decision"] } : f,
        ),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function labelSection(section: SectionMeta, contribution: string) {
    try {
      await api.label(wsId, section.id, contribution);
      const optimistic = {
        ...run as RunSummary,
        sections: (run as RunSummary).sections.map((s) =>
          s.id === section.id
            ? { ...s, contribution, author_approved: contribution === "sole_or_primary" }
            : s,
        ),
      };
      setRun(optimistic);
      const ids = run?.style.reference_ids ?? [];
      if (ids.length) await refreshStyle(ids);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function runNavigator() {
    if (!wsId || !query.trim()) return;
    try {
      setNav(await api.navigate(wsId, query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function doExport() {
    if (!wsId || !run) return;
    setBusy("Writing exports…");
    try {
      const info = await api.exportRun(wsId);
      setExportInfo(info);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function jumpToSpan(span: SourceSpan) {
    setJumpTarget({ file: span.file_path, line: span.start_line });
    const finding = run?.findings.find(
      (f) =>
        f.source_span.file_path === span.file_path &&
        f.source_span.start_line === span.start_line,
    );
    if (finding) {
      selectFinding(finding);
      return;
    }
    if (!run) return;
    const scroll = () => {
      requestAnimationFrame(() => {
        document.querySelector(`[data-line="${span.start_line}"]`)?.scrollIntoView({
          block: "center",
          behavior: "smooth",
        });
      });
    };
    if (span.file_path === filePath) {
      scroll();
    } else {
      void loadFile(wsId, span.file_path).then(scroll);
    }
  }

  function onReferenceAdded(id: string, label: string) {
    setReferenceRows((rows) => [...rows, {
      id, label, kind: "reference", created_at: "", revision_id: "", main_path: "",
      run_id: "", root: "", stats: {},
    }]);
    setManageReference(id);
  }

  if (!run) {
    return (
      <div className="landing">
        <div className="landing-inner">
          <p className="eyebrow">PaperFamiliar · local-first manuscript instrument</p>
          <h1>Verify the research.<br />Preserve the author's voice.</h1>
          <p className="lede">
            A local web workbench for LaTeX papers. It shows only what it can point to:
            mechanically decidable citation errors, honest reference metadata, and your own
            writing habits. No account. No cloud. No similarity percentage.
          </p>
          <div className="landing-actions">
            <button className="primary" onClick={loadDemo} disabled={!!busy}>
              Load the offline demo
            </button>
            <button className="ghost" onClick={() => setShowImport("manuscript")} disabled={!!busy}>
              Upload a paper
            </button>
            <button className="ghost" onClick={() => setShowImport("reference")} disabled={!!busy}>
              Add reference papers
            </button>
          </div>
          {busy && <p className="busy">{busy}</p>}
          {error && <p className="error">{error}</p>}
          {manuscripts.length > 0 && (
            <div className="recent">
              <h3>Resume a saved review</h3>
              <ul>
                {manuscripts.map((row) => (
                  <li key={row.id}>
                    <button onClick={() => api.workspace(row.id).then(adopt)}>
                      <strong>{row.label}</strong>
                      <span className="mono small">rev {shortSha(row.revision_id)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <ul className="privacy">
            <li>One local Python service, opened at 127.0.0.1 — no telemetry, fonts or CDN.</li>
            <li>Every finding must reproduce an exact quote from your bytes; originals are never edited.</li>
            <li>Style differences are described, never scored, and never called academic errors.</li>
          </ul>
          <p className="fine">
            The demo is synthetic and contains deliberate defects: a missing citation, a duplicate
            label, an undefined reference, a misattributed real citation, and prompt-injection text
            inside a comment.
          </p>
        </div>
        {showImport && (
          <ImportModal
            presetKind={showImport}
            onClose={() => setShowImport(null)}
            onManuscript={adopt}
            onReference={onReferenceAdded}
            setError={setError}
          />
        )}
      </div>
    );
  }

  const drift = run.style.drift;
  const selectedRefs = run.style.reference_ids ?? [];
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
          <span className="mono" title={run.revision_id}>rev {shortSha(run.revision_id)}</span>
          <span>{run.files.length} files · {run.findings.length} findings</span>
          {!fileUnchanged && <span className="warn">source changed on disk</span>}
        </div>
        <div className="top-actions">
          <button className="ghost" onClick={() => setShowImport("manuscript")}>Import</button>
          <button className="ghost" onClick={reaudit} title="Re-run the deterministic audit">Re-audit</button>
          <button
            className="ghost"
            title="Optional local or cloud model; off by default"
            onClick={() => {
              const selection = window.getSelection()?.toString() ?? "";
              setSelectedText(selection.trim().length > 40 ? selection : fileText);
              setShowModels(true);
            }}
          >
            Models
          </button>
          <button className="ghost" onClick={() => setShowSettings(true)}>Data</button>
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
          <strong>Assumptions:</strong> {run.assumptions[0]}
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
          <SectionTree
            sections={run.sections}
            onSelect={(s) => jumpToSpan(s.heading_span)}
            onLabel={labelSection}
          />
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
                onClick={() => loadFile(wsId, file.path)}
                title={file.path}
              >
                {file.path.split("/").pop()}
                {file.count > 0 && <span className="badge">{file.count}</span>}
              </button>
            ))}
          </div>
          <div className="source-head">
            <span className="mono">{filePath}</span>
            <span className="mono muted">
              sha {shortSha(run.files.find((f) => f.path === filePath)?.sha256 ?? "")}
            </span>
          </div>
          <div className="source">
            <pre>
              {lines.map((line, index) => {
                const number = index + 1;
                const marks = marksForLine(run.findings, lines, filePath, number);
                const activeLine =
                  (jumpTarget && jumpTarget.file === filePath && jumpTarget.line === number) ||
                  (activeFinding
                    ? run.findings.find((f) => f.id === activeFinding)?.source_span.start_line ===
                      number
                    : false);
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
              {run.security_events.length > 0 && (
                <details className="rejections">
                  <summary>{run.security_events.length} security event(s)</summary>
                  <ul>
                    {run.security_events.map((event, index) => (
                      <li key={index}>
                        <code>{event.kind}</code> — {event.detail}
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
                <h3>Reference papers (your approved writing)</h3>
                {referenceRows.length === 0 && (
                  <p className="hint">
                    No reference papers yet. Upload your earlier LaTeX papers with
                    “Add reference papers”, mark the sections you wrote, then select them here.
                  </p>
                )}
                <ul className="ref-list">
                  {referenceRows.map((row) => (
                    <li key={row.id}>
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={selectedRefs.includes(row.id)}
                          onChange={(event) => {
                            const ids = event.target.checked
                              ? [...selectedRefs, row.id]
                              : selectedRefs.filter((x) => x !== row.id);
                            void refreshStyle(ids).catch((err: Error) => setError(err.message));
                          }}
                        />
                        <span>{row.label}</span>
                      </label>
                      <button className="ghost small" onClick={() => setManageReference(row.id)}>
                        label sections
                      </button>
                    </li>
                  ))}
                </ul>
                {selectedRefs.length === 0 && (
                  <p className="hint">Select at least three papers; fewer means honest abstention, not a score.</p>
                )}
                <p className={`status-line ${run.style.baseline.status}`}>
                  {run.style.baseline.status === "ok"
                    ? `${run.style.baseline.papers_used} approved papers · ${run.style.baseline.sentences} sentences`
                    : "Insufficient reference data"}
                </p>
                {run.style.baseline.status !== "ok" && <p>{run.style.baseline.reason}</p>}
                {(run.style.references ?? []).length > 0 && (
                  <p className="hint small">
                    {(run.style.references ?? [])
                      .map((ref) => `${ref.label ?? ref.id}: ${ref.status}${ref.sections_used ? ` (${ref.sections_used} sections)` : ""}`)
                      .join(" · ")}
                  </p>
                )}
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
                Sections you mark “I wrote it” are compared with the baseline above. A difference
                is a description, not a quality judgement. Small samples are marked low confidence.
              </p>
              {drift.length === 0 && (
                <p className="empty">No drift cards: {run.style.baseline.reason}</p>
              )}
              {drift.map((card) => <DriftCardView key={card.section_id} card={card} onJump={jumpToSpan} />)}
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

      {showImport && (
        <ImportModal
          presetKind={showImport}
          onClose={() => setShowImport(null)}
          onManuscript={adopt}
          onReference={onReferenceAdded}
          setError={setError}
        />
      )}

      {manageReference && (
        <ReferenceModal
          workspaceId={manageReference}
          onClose={() => setManageReference(null)}
          setError={setError}
        />
      )}

      {showSettings && (
        <SettingsModal
          onClose={() => setShowSettings(false)}
          onChanged={() => {
            localStorage.removeItem(LAST_WORKSPACE_KEY);
            setRun(null);
          }}
          setError={setError}
        />
      )}

      {exportInfo && run && (
        <div className="modal-backdrop" onClick={() => setExportInfo(null)}>
          <div className="modal wide" onClick={(event) => event.stopPropagation()}>
            <h2>Exports written</h2>
            <p className="mono small">{exportInfo.directory}</p>
            <ul className="export-list">
              {exportInfo.files.map((name) => (
                <li key={name}>
                  <a href={api.exportUrl(wsId, name)} download>{name}</a>
                </li>
              ))}
            </ul>
            <p className={exportInfo.source_integrity.status !== "unchanged" ? "error" : "ok-line"}>
              {exportInfo.source_integrity.status === "unchanged"
                ? "All source hashes match the analyzed revision."
                : exportInfo.source_integrity.status === "unavailable"
                  ? "Source folder unavailable — exports describe the stored snapshot."
                  : "Source changed on disk — exports carry a warning and may point to stale lines."}
            </p>
            {exportInfo.source_integrity.status === "changed" && (
              <ul className="privacy">
                {exportInfo.source_integrity.files
                  .filter((row) => row.state !== "unchanged")
                  .map((row) => (
                    <li key={row.path}>
                      <span className="mono small">{row.path}</span> — {row.state}
                    </li>
                  ))}
              </ul>
            )}
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

      {showModels && (
        <ModelsPanel
          getSelectedText={() => selectedText || fileText}
          onClose={() => setShowModels(false)}
        />
      )}

      {busy && <div className="busy-toast">{busy}</div>}
    </div>
  );
}
