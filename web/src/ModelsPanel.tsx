import { useEffect, useState } from "react";
import { api } from "./api";
import type { ProviderStatus, ProviderPreview, ProviderResult } from "./types";

const TASKS = [
  {
    id: "candidate_issues",
    label: "Candidate writing issues",
    task: "List candidate clarity or citation problems in this excerpt. Quote the exact text for each. Never claim a citation supports a claim.",
  },
  {
    id: "role_hint",
    label: "Section role hints",
    task: "Name the rhetorical role of this section (hook, gap, contribution, method, evaluation). Say 'unknown' when the text is insufficient.",
  },
];

export default function ModelsPanel({
  getSelectedText,
  onClose,
}: {
  getSelectedText: () => string;
  onClose: () => void;
}) {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [provider, setProvider] = useState<"local" | "cloud">("local");
  const [taskId, setTaskId] = useState(TASKS[0].id);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<ProviderPreview | null>(null);
  const [result, setResult] = useState<ProviderResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    api
      .providers()
      .then(setStatus)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    setText(getSelectedText());
  }, [getSelectedText]);

  async function makePreview() {
    setBusy(true);
    setError(null);
    setResult(null);
    setConfirmed(false);
    try {
      const task = TASKS.find((t) => t.id === taskId)?.task ?? TASKS[0].task;
      setPreview(await api.previewModel(task, text, provider));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const task = TASKS.find((t) => t.id === taskId)?.task ?? TASKS[0].task;
      setResult(await api.sendModel(preview.consent_id, task, text, provider, confirmed));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const needsNetwork = Boolean(preview && !preview.is_local);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide models" onClick={(event) => event.stopPropagation()}>
        <h2>Models (optional)</h2>
        <p>
          Offline mode is the default and never sends anything. A request only leaves this
          machine after you preview the exact payload and confirm it.
        </p>

        <div className="model-status">
          <div>
            <span className="label">Local</span>
            <strong className={status?.local.status === "available" ? "ok-line" : "muted"}>
              {status ? status.local.status : "checking…"}
            </strong>
            <span className="mono small">{status?.local.endpoint}</span>
            {status?.local.models?.length ? (
              <span className="small muted">{status.local.models.slice(0, 3).join(", ")}</span>
            ) : null}
          </div>
          <div>
            <span className="label">Cloud</span>
            <strong className={status?.cloud.configured ? "ok-line" : "muted"}>
              {status?.cloud.configured ? "configured" : "not configured"}
            </strong>
            <span className="mono small">{status?.cloud.endpoint ?? "set env vars to enable"}</span>
            {status?.cloud.configured && (
              <span className="small muted">
                key {status.cloud.key_present ? "present in environment" : "missing"}
              </span>
            )}
          </div>
        </div>

        <div className="model-form">
          <label>
            Provider
            <select value={provider} onChange={(event) => setProvider(event.target.value as "local" | "cloud")}>
              <option value="local">Local (loopback)</option>
              <option value="cloud" disabled={!status?.cloud.configured}>
                Cloud{status?.cloud.configured ? "" : " (not configured)"}
              </option>
            </select>
          </label>
          <label>
            Task
            <select value={taskId} onChange={(event) => setTaskId(event.target.value)}>
              {TASKS.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </label>
        </div>

        <label className="wide-label">
          Text to send (prefilled with the selected source or the whole main file)
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={6}
            spellCheck={false}
          />
        </label>

        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>Close</button>
          <button className="primary" onClick={makePreview} disabled={busy || !text.trim()}>
            Preview payload
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {preview && (
          <div className={`payload ${needsNetwork ? "egress" : "loopback"}`}>
            <h3>{preview.is_local ? "Loopback request" : "This would leave your computer"}</h3>
            <dl className="payload-meta">
              <div><dt>Endpoint</dt><dd className="mono">{preview.endpoint}</dd></div>
              <div><dt>Model</dt><dd className="mono">{preview.model}</dd></div>
              <div><dt>Size</dt><dd>{preview.payload_bytes} bytes · ~{preview.estimated_tokens} tokens</dd></div>
              <div><dt>Redactions</dt><dd>{preview.redactions}</dd></div>
              <div><dt>SHA-256</dt><dd className="mono">{preview.payload_sha256.slice(0, 24)}…</dd></div>
            </dl>
            <p>{preview.notice}</p>
            <pre className="payload-body">{JSON.stringify(preview.payload, null, 2)}</pre>
            <div className="modal-actions">
              {needsNetwork && (
                <label className="confirm">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  I accept sending exactly this payload to {preview.endpoint}
                </label>
              )}
              <button
                className="primary"
                onClick={send}
                disabled={busy || (Boolean(needsNetwork) && !confirmed)}
              >
                Send this request
              </button>
            </div>
          </div>
        )}

        {result && (
          <div className={`model-result ${result.status}`}>
            <h3>
              {result.status === "candidate" ? "Candidate output" : `Provider ${result.status}`}
            </h3>
            {result.content ? <pre>{result.content}</pre> : <p>{result.detail}</p>}
            <p className="note">{result.notice}</p>
          </div>
        )}
      </div>
    </div>
  );
}
