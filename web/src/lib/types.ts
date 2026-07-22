// Shared TypeScript types matching the Python summary.json / results.jsonl schema.

export interface CapabilityBucket {
  score: number | null;
  passed: number;
  count: number;
  errored?: number;
  pass_rate_ci?: [number, number] | null;
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

export type ResultStatus = "completed" | "failed" | "error" | "incomplete" | "cancelled";

export interface Result {
  case_id: string;
  attempt?: number;
  status?: ResultStatus;
  passed: boolean | null;
  score: number | null;
  capability?: string[];
  difficulty?: string | null;
  checks?: Check[];
  response_text?: string;
  error?: string | null;
  error_type?: string | null;
  usage?: Usage;
  cost_usd?: number | null;
  latency_ms?: number | null;
  repeat?: number;
  passes?: number;
  pass_at_1?: number | null;
  pass_at_k?: number | null;
  pass_pow_k?: number | null;
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
  score: number | null;
  pass_rate: number | null;
  pass_rate_ci?: [number, number] | null;
  score_ci?: [number, number] | null;
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
  score_a: number | null;
  score_b: number | null;
  score_delta: number | null;
  score_ci_a?: [number, number] | null;
  score_ci_b?: [number, number] | null;
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

export interface AppBootstrap {
  page: "app";
  ws_port: number;
  api_token: string;
}

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
  api_token?: string;
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

export type RunStatus =
  | "pending"
  | "running"
  | "cancellation_requested"
  | "completed"
  | "failed"
  | "cancelled";

export type TerminalRunStatus = Extract<RunStatus, "completed" | "failed" | "cancelled">;

export interface RunInfo {
  run_id: string;
  status: RunStatus;
  progress?: RunProgress;
  summary?: RunSummary | null;
  error?: string | null;
  results?: Result[];
  started_at?: number | null;
  completed_at?: number | null;
}

export type AttemptStatus = "running" | "completed" | "failed" | "error" | "cancelled";

export interface AttemptProgress {
  attempt: number;
  status: AttemptStatus;
  score: number | null;
  passed: boolean | null;
  error: string | null;
  error_type?: string | null;
}

export interface RunProgress {
  run_id: string;
  status: RunStatus;
  total_cases: number;
  planned_attempts: number;
  started_attempts: number;
  completed_attempts: number;
  passed_attempts: number;
  failed_attempts: number;
  error_attempts: number;
  cancelled_attempts: number;
  attempts: Record<string, Record<string, AttemptProgress>>;
}

export type ProgressEvent =
  | { type: "connected"; ws_port: number }
  | { type: "run_started"; run_id: string; total_cases: number; repeat: number; planned_attempts: number }
  | { type: "attempt_started"; run_id: string; case_id: string; case_index: number; attempt: number }
  | {
      type: "attempt_completed";
      run_id: string;
      case_id: string;
      case_index: number;
      attempt: number;
      status: AttemptStatus;
      score: number | null;
      passed: boolean | null;
      error: string | null;
      error_type?: string | null;
    }
  | {
      type: "run_finished";
      run_id: string;
      status: RunStatus;
      summary: RunSummary | null;
      error: string | null;
    };

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
