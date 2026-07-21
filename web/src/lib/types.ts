// Shared TypeScript types matching the Python summary.json / results.jsonl schema.

export interface CapabilityBucket {
  score: number;
  passed: number;
  count: number;
  errored?: number;
  pass_rate_ci?: [number, number];
}

export interface Usage {
  total_tokens?: number;
  input_tokens?: number;
  output_tokens?: number;
}

export interface Check {
  kind: string;
  passed: boolean;
  detail?: string;
}

export interface Result {
  case_id: string;
  passed: boolean;
  score: number;
  capability?: string[];
  difficulty?: string | null;
  checks?: Check[];
  response_text?: string;
  error?: string;
  usage?: Usage;
  cost_usd?: number;
  latency_ms?: number;
  repeat?: number;
  passes?: number;
  pass_at_1?: number;
  pass_at_k?: number;
  pass_pow_k?: number;
  source?: string;
}

export interface RunSummary {
  run_id: string;
  adapter: string;
  adapter_display?: string;
  judge?: string;
  reviewer?: string;
  verifier?: string;
  total: number;
  passed: number;
  failed: number;
  errored?: number;
  score: number;
  pass_rate: number;
  pass_rate_ci?: [number, number];
  score_ci?: [number, number];
  by_capability?: Record<string, CapabilityBucket>;
  by_difficulty?: Record<string, CapabilityBucket>;
  usage?: Usage;
  cost_usd?: number;
  latency_ms_total?: number;
  repeat?: number;
  pass_at_1?: number;
  pass_at_k?: number;
  pass_pow_k?: number;
  manifest?: {
    schema_version?: string;
    ckl_bench_version?: string;
    created_at?: string;
    git_sha?: string;
    model?: { model?: string; [key: string]: unknown };
    repeat?: number;
    case_paths?: string[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface ProbeRow {
  target: string;
  kind: string;
  status: "pass" | "fail" | "skip";
  score: number | null;
  detail: string;
}

export interface DiffCase {
  case_id: string;
  status: "regressed" | "improved" | "unchanged" | "added" | "removed";
  a_score: number | null;
  b_score: number | null;
  a_passed: boolean | null;
  b_passed: boolean | null;
  delta: number | null;
}

export interface DiffData {
  run_a: string;
  run_b: string;
  adapter_a?: string;
  adapter_b?: string;
  score_a: number;
  score_b: number;
  score_delta: number;
  score_ci_a?: [number, number];
  score_ci_b?: [number, number];
  passed_a?: number;
  passed_b?: number;
  counts: {
    improved: number;
    regressed: number;
    unchanged: number;
    added: number;
    removed: number;
  };
  cases: DiffCase[];
}

// The data injected by the Python side as window.__CKL_BENCH_DATA__.
export type PageKind = "report" | "dashboard" | "probe" | "diff" | "app";

export interface BenchData {
  page: PageKind;
  // report
  summary?: RunSummary;
  results?: Result[];
  // dashboard
  runs?: RunSummary[];
  // probe
  probe_summary?: RunSummary;
  probe_rows?: ProbeRow[];
  // diff
  diff?: DiffData;
  // app mode (server)
  ws_port?: number;
}

// --- API response types (server mode) ---

export interface CaseListItem {
  id: string;
  title: string;
  type: string;
  capability: string[];
  difficulty: string | null;
  timeout_s: number | null;
  source: string;
}

export interface CaseDetail {
  id: string;
  title: string;
  type: string;
  input: { prompt?: string; messages?: Array<{ role: string; content: string }>; workspace?: any };
  expectations: Array<{ kind: string; [key: string]: any }>;
  capability?: string[];
  difficulty?: string | null;
  timeout_s?: number | null;
  metadata?: Record<string, any>;
}

export interface RunInfo {
  run_id: string;
  status: "pending" | "running" | "cancellation_requested" | "completed" | "failed" | "cancelled";
  progress?: RunProgress;
  summary?: RunSummary;
  error?: string | null;
  results?: Result[];
  started_at?: number | null;
  completed_at?: number | null;
}

export interface RunProgress {
  total_cases?: number;
  repeat?: number;
  total_attempts?: number;
  started_attempts?: number;
  completed_attempts?: number;
  passed_attempts?: number;
  failed_attempts?: number;
  error_attempts?: number;
  cancelled_attempts?: number;
  cases?: Record<string, CaseProgress>;
}

export interface CaseProgress {
  status: "running" | "completed" | "failed";
  attempt: number;
  score?: number | null;
  passed?: boolean | null;
  error?: string | null;
}

export interface ConfigInfo {
  case_packs: string[];
  adapters: string[];
  runs_dir: string;
  cases_dir: string;
  ws_port: number;
}

export interface ProviderInfo {
  namespace: string;
  aliases: string[];
  default: string;
}

// --- Settings types (server mode) ---

export interface AdapterConfig {
  api_key?: string;
  base_url?: string;
  model?: string;
  command?: string;
  workspace_dir?: string;
  [key: string]: any;
}

export interface Settings {
  adapters: Record<string, AdapterConfig>;
  defaults: {
    repeat: number;
    concurrency: number;
    seed: number;
    judge: string;
    reviewer?: string;
    verifier?: string;
  };
  active_adapters: string[];
}

export interface AdapterTestResult {
  ok: boolean;
  output: string;
  error: string;
}
