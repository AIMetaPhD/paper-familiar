export interface SourceSpan {
  file_path: string;
  start_line: number;
  start_col: number;
  end_line: number;
  end_col: number;
  exact_quote: string;
  file_sha256: string;
}

export interface Finding {
  id: string;
  rule_id: string;
  finding_class: "mechanical" | "metadata" | "heuristic" | "semantic";
  evidence_status:
    | "verified_error"
    | "source_corroborated"
    | "candidate"
    | "insufficient_evidence"
    | "unavailable_offline"
    | "needs_expert_review"
    | "rejected_source_target_invalid";
  human_decision: "unreviewed" | "accepted" | "dismissed" | "needs_review";
  severity: string;
  claim: string;
  detail: string;
  source_span: SourceSpan;
  evidence_refs: unknown[];
  model_id: string | null;
  rule_scope: string | null;
}

export interface SectionMeta {
  id: string;
  title: string;
  level: number;
  role: string;
  file_path: string;
  heading_span: SourceSpan;
  contribution: string;
  author_approved: boolean;
  word_count: number;
  sentence_count: number;
}

export interface Baseline {
  status: string;
  reason: string;
  papers_used: number;
  sentences: number;
  profile: {
    sentence_count: number;
    word_count: number;
    mean_sentence_len: number;
    std_sentence_len: number;
    transition_rate: number;
    math_lead_rate: number;
    passive_rate: number;
    function_word_profile: Record<string, number>;
    top_transitions: [string, number][];
    type_token_ratio: number;
    paragraph_count: number;
  } | null;
  axes: Record<string, [number, number]>;
}

export interface DriftCard {
  section_id: string;
  title: string;
  status: "observed" | "insufficient_evidence";
  reason?: string;
  axes?: Record<string, { value: number; baseline: number; difference_in_baseline_spread: number }>;
  combined_deviation?: number;
  sample?: { sentences: number; words: number; confidence?: string };
  note?: string;
  span: SourceSpan;
}

export interface Cognitive {
  section_tree: TreeNode[];
  environment_sequence: { name: string; span: SourceSpan }[];
  label_topology: { labels: { key: string; span: SourceSpan }[]; reference_counts: Record<string, number> };
  symbol_index: { symbol: string; count: number; first: SourceSpan }[];
  notes: Record<string, string | null>;
}

export interface TreeNode {
  id: string;
  title: string;
  role: string;
  level: number;
  file: string;
  span: SourceSpan;
  children: TreeNode[];
}

export interface FileRow {
  path: string;
  sha256: string;
  bytes: number;
  lines: number;
  kind: "tex" | "bib";
}

export interface RunSummary {
  id: string;
  workspace_id: string | null;
  created_at: string;
  label: string;
  main_path: string;
  revision_id: string;
  findings: Finding[];
  rejections: { finding_id: string; rule_id: string; reason: string; claimed_span: SourceSpan; note?: string }[];
  security_events: { kind: string; detail: string; path?: string; source_span?: SourceSpan }[];
  stats: Record<string, number>;
  sections: SectionMeta[];
  style: {
    baseline: Baseline;
    drift: DriftCard[];
    reference_ids?: string[];
    references?: { id: string; label?: string; status: string; sections_used?: number }[];
    history?: { path: string; contribution?: string; sections_used?: number; status?: string }[];
    note: string;
  };
  cognitive: Cognitive;
  files: FileRow[];
  bibliography_files: string[];
  assumptions: string[];
  mode: string;
}

export interface WorkspaceRow {
  id: string;
  label: string;
  kind: "manuscript" | "reference" | "demo";
  created_at: string;
  revision_id: string;
  main_path: string;
  run_id: string;
  root: string;
  stats: Record<string, number>;
}

export interface ReferenceResponse {
  workspace_id: string;
  kind: "reference";
  label: string;
  sections: { id: string; title: string; contribution: string; sentences: number }[];
}

export interface Usage {
  data_dir: string;
  workspaces: number;
  runs: number;
  stored_workspaces: number;
  path_workspaces: number;
  database_bytes: number;
  workspaces_bytes: number;
  exports_bytes: number;
  cache_bytes: number;
}

export interface Settings {
  usage: Usage;
  references: WorkspaceRow[];
  providers: ProviderStatus;
}

export interface NavigateResult {
  status: "found" | "not_found";
  query: string;
  reason?: string;
  matches: { section_id: string; title: string; role: string; score: number; reasons: string[]; span: SourceSpan }[];
}

export interface ProviderStatus {
  local: { status: string; models: string[]; endpoint: string; detail?: string };
  cloud: {
    configured: boolean;
    endpoint: string | null;
    model: string | null;
    key_env: string | null;
    key_present: boolean;
  };
  strict_offline_default: boolean;
}

export interface ProviderPreview {
  consent_id: string;
  provider: string;
  endpoint: string;
  model: string;
  payload: unknown;
  payload_sha256: string;
  payload_bytes: number;
  estimated_tokens: number;
  redactions: number;
  is_local: boolean;
  requires_network: boolean;
  notice: string;
  created_at: string;
}

export interface ProviderResult {
  status: string;
  provider: string;
  model?: string;
  content?: string;
  detail?: string;
  candidate_only?: boolean;
  notice?: string;
}
