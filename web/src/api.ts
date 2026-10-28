import type {
  NavigateResult,
  ProviderPreview,
  ProviderResult,
  ProviderStatus,
  ReferenceResponse,
  RunSummary,
  Settings,
  Usage,
  WorkspaceRow,
} from "./types";

let csrf = document.querySelector('meta[name="pf-csrf"]')?.getAttribute("content") ?? "";

export function setCsrf(token: string) {
  csrf = token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      "X-PF-CSRF": csrf,
      ...((options.headers as Record<string, string>) ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string; mode: string }>("/api/health"),
  session: () => request<{ csrf: string; version: string; data_dir: string }>("/api/session"),
  workspaces: () => request<{ workspaces: WorkspaceRow[] }>("/api/workspaces"),
  demo: () => request<RunSummary>("/api/demo", { method: "POST", body: "{}" }),
  upload: (files: File[], label: string | null, kind: "manuscript" | "reference") => {
    const form = new FormData();
    files.forEach((file) => {
      const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
      form.append("files", file, rel && rel.length > 0 ? rel : file.name);
    });
    if (label) form.append("label", label);
    form.append("kind", kind);
    return request<RunSummary | ReferenceResponse>("/api/workspace/upload", {
      method: "POST",
      body: form,
    });
  },
  openPath: (path: string, label: string | null, kind: "manuscript" | "reference") =>
    request<RunSummary | ReferenceResponse>("/api/workspace/path", {
      method: "POST",
      body: JSON.stringify({ path, label, kind }),
    }),
  workspace: (id: string) => request<RunSummary>(`/api/workspace/${id}`),
  reaudit: (id: string) =>
    request<RunSummary>(`/api/workspace/${id}/audit`, { method: "POST", body: "{}" }),
  deleteWorkspace: (id: string) =>
    request<{ workspace: string; deleted_directory?: string; deleted_exports?: string }>(
      `/api/workspace/${id}`,
      { method: "DELETE" },
    ),
  file: (id: string, path: string) =>
    request<{ path: string; text: string; sha256: string; unchanged: boolean }>(
      `/api/workspace/${id}/file?path=${encodeURIComponent(path)}`,
    ),
  decide: (id: string, findingId: string, decision: string) =>
    request<{ ok: boolean }>(`/api/workspace/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ finding_id: findingId, decision }),
    }),
  label: (id: string, sectionId: string, contribution: string) =>
    request<{ ok: boolean }>(`/api/workspace/${id}/label`, {
      method: "POST",
      body: JSON.stringify({ workspace_id: id, section_id: sectionId, contribution }),
    }),
  style: (id: string, referenceIds: string[]) =>
    request<RunSummary>(`/api/workspace/${id}/style`, {
      method: "POST",
      body: JSON.stringify({ reference_ids: referenceIds }),
    }),
  navigate: (id: string, query: string) =>
    request<NavigateResult>(`/api/workspace/${id}/navigate`, {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  exportRun: (id: string) =>
    request<{ directory: string; files: string[] }>(`/api/workspace/${id}/export`, {
      method: "POST",
      body: "{}",
    }),
  exportUrl: (id: string, name: string) => `/api/workspace/${id}/export/${name}`,
  settings: () => request<Settings>("/api/settings"),
  clearAll: () => request<Usage>("/api/settings/clear", { method: "POST", body: "{}" }),
  providers: () => request<ProviderStatus>("/api/providers"),
  previewModel: (task: string, text: string, provider: string) =>
    request<ProviderPreview>("/api/providers/preview", {
      method: "POST",
      body: JSON.stringify({ task, text, provider }),
    }),
  sendModel: (consentId: string, task: string, text: string, provider: string, confirm: boolean) =>
    request<ProviderResult>("/api/providers/send", {
      method: "POST",
      body: JSON.stringify({ consent_id: consentId, task, text, provider, confirm }),
    }),
  metadata: (doi: string, allowNetwork: boolean) =>
    request<Record<string, unknown>>("/api/metadata", {
      method: "POST",
      body: JSON.stringify({ doi, allow_network: allowNetwork }),
    }),
};
