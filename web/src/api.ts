import type { NavigateResult, RunSummary } from "./types";

const csrf = document.querySelector('meta[name="pf-csrf"]')?.getAttribute("content") ?? "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-PF-CSRF": csrf,
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string; mode: string }>("/api/health"),
  demo: () => request<RunSummary>("/api/demo", { method: "POST", body: "{}" }),
  openWorkspace: (path: string) =>
    request<RunSummary>("/api/workspace", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  file: (runId: string, path: string) =>
    request<{ path: string; text: string; sha256: string; unchanged: boolean }>(
      `/api/run/${runId}/file?path=${encodeURIComponent(path)}`,
    ),
  decide: (runId: string, findingId: string, decision: string) =>
    request<{ ok: boolean }>(`/api/run/${runId}/decision`, {
      method: "POST",
      body: JSON.stringify({ finding_id: findingId, decision }),
    }),
  label: (runId: string, sectionId: string, contribution: string) =>
    request<{ ok: boolean }>(`/api/run/${runId}/label`, {
      method: "POST",
      body: JSON.stringify({ section_id: sectionId, contribution }),
    }),
  navigate: (runId: string, query: string) =>
    request<NavigateResult>(`/api/run/${runId}/navigate`, {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  exportRun: (runId: string) =>
    request<{ directory: string; files: string[] }>(`/api/run/${runId}/export`, {
      method: "POST",
      body: "{}",
    }),
  exportUrl: (runId: string, name: string) => `/api/run/${runId}/export/${name}`,
};
