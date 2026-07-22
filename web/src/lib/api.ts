// API client for the ckl-bench dashboard server (app mode).
// Fetches from /api/* and manages a WebSocket connection for live progress.

import type {
  CaseDetail,
  CaseListItem,
  ConfigInfo,
  ProviderInfo,
  RunInfo,
  Settings,
  AdapterTestResult,
  ProgressEvent,
  RunProgress,
  RunStatus,
  AttemptProgress,
} from "./types";
import { readAppBootstrap } from "./data";

const BASE = ""; // Same-origin; the server serves both the app and the API.
const BOOTSTRAP = readAppBootstrap();
const API_TOKEN = BOOTSTRAP?.api_token;

function tokenSubprotocol(token: string): string {
  const bytes = new TextEncoder().encode(token);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `ckl-bench-token.${btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  headers.set("Content-Type", "application/json");
  if (API_TOKEN) headers.set("Authorization", `Bearer ${API_TOKEN}`);
  const res = await fetch(BASE + path, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Cases ---

export function listCases(pack?: string): Promise<CaseListItem[]> {
  const q = pack ? `?pack=${encodeURIComponent(pack)}` : "";
  return request<CaseListItem[]>(`/api/cases${q}`);
}

export function getCase(id: string): Promise<CaseDetail> {
  return request<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`);
}

export function createCase(c: Partial<CaseDetail> & { pack?: string }): Promise<CaseDetail> {
  return request<CaseDetail>("/api/cases", { method: "POST", body: JSON.stringify(c) });
}

export function updateCase(id: string, c: Partial<CaseDetail>): Promise<CaseDetail> {
  return request<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(c),
  });
}

export function deleteCase(id: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/api/cases/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// --- Runs ---

export function listRuns(): Promise<RunInfo[]> {
  return request<RunInfo[]>("/api/runs");
}

export function getRun(runId: string): Promise<RunInfo> {
  return request<RunInfo>(`/api/runs/${encodeURIComponent(runId)}`);
}

export function getRunProgress(runId: string): Promise<RunInfo> {
  return request<RunInfo>(`/api/runs/${encodeURIComponent(runId)}/progress`);
}

export function cancelRun(runId: string): Promise<{ run_id: string; status: RunStatus }> {
  return request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST", body: "{}" });
}

export interface LaunchRunParams {
  adapter?: string;
  adapter_target?: string;
  adapter_config?: Record<string, any>;
  case_paths?: string[];
  case_ids?: string[];
  repeat?: number;
  concurrency?: number;
  seed?: number;
  judge?: string;
}

export function launchRun(params: LaunchRunParams): Promise<{ run_id: string; status: string }> {
  return request("/api/runs", { method: "POST", body: JSON.stringify(params) });
}

// --- Config / Providers ---

export function getConfig(): Promise<ConfigInfo> {
  return request<ConfigInfo>("/api/config");
}

export function listProviders(): Promise<ProviderInfo[]> {
  return request<ProviderInfo[]>("/api/providers");
}

// --- Settings ---

export function getSettings(): Promise<Settings> {
  return request<Settings>("/api/settings");
}

export function updateSettings(settings: Settings): Promise<Settings> {
  return request<Settings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export function testAdapter(
  adapter_name: string,
  config: Record<string, any>,
  signal?: AbortSignal
): Promise<AdapterTestResult> {
  return request("/api/settings/test", {
    method: "POST",
    body: JSON.stringify({ adapter_name, config }),
    signal,
  });
}

export function normalizeRunProgress(
  value: Partial<RunProgress> & Record<string, any>,
  runId = value.run_id ?? "",
  status: RunStatus = value.status ?? "running"
): RunProgress {
  const source = value.attempts ?? value.cases ?? {};
  const attempts: RunProgress["attempts"] = {};
  for (const [caseId, rawCase] of Object.entries(source)) {
    const rawAttempts = rawCase && typeof rawCase === "object" && "status" in rawCase
      ? { [String((rawCase as any).attempt ?? 0)]: rawCase }
      : rawCase as Record<string, any>;
    attempts[caseId] = {};
    for (const [attemptKey, rawAttempt] of Object.entries(rawAttempts ?? {})) {
      const item = rawAttempt as Partial<AttemptProgress>;
      const keyNumber = Number(attemptKey);
      attempts[caseId][attemptKey] = {
        attempt: item.attempt ?? (Number.isFinite(keyNumber) ? keyNumber : 0),
        status: item.status === "failed" && item.error ? "error" : item.status ?? "running",
        score: item.score ?? null,
        passed: item.passed ?? null,
        error: item.error ?? null,
        error_type: item.error_type ?? null,
      };
    }
  }
  return {
    run_id: runId,
    status,
    total_cases: value.total_cases ?? 0,
    planned_attempts: value.planned_attempts ?? value.total_attempts ?? value.total ?? 0,
    started_attempts: value.started_attempts ?? value.started ?? 0,
    completed_attempts: value.completed_attempts ?? value.completed ?? 0,
    passed_attempts: value.passed_attempts ?? value.passed ?? 0,
    failed_attempts: value.failed_attempts ?? value.failed ?? 0,
    error_attempts: value.error_attempts ?? value.error ?? 0,
    cancelled_attempts: value.cancelled_attempts ?? value.cancelled ?? 0,
    attempts,
  };
}

export function normalizeProgressEvent(value: any): ProgressEvent | null {
  if (!value || typeof value !== "object" || typeof value.type !== "string") return null;
  if (value.type === "case_started") return { ...value, type: "attempt_started" } as ProgressEvent;
  if (value.type === "case_completed") {
    return {
      ...value,
      type: "attempt_completed",
      status: value.status ?? (value.error ? "error" : value.passed === false ? "failed" : "completed"),
      score: value.score ?? null,
      passed: value.passed ?? null,
      error: value.error ?? null,
    } as ProgressEvent;
  }
  return value as ProgressEvent;
}

// --- WebSocket ---

export type ProgressListener = (event: ProgressEvent) => void;

export class ProgressSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<ProgressListener>();
  private reconnectTimer: any = null;
  private url: string;
  private retries = 0;
  private maxRetries = 10;

  constructor(wsPort = BOOTSTRAP?.ws_port, private token = API_TOKEN) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const port = wsPort ? `:${wsPort}` : "";
    this.url = `${proto}://${location.hostname}${port}/ws`;
  }

  connect() {
    try {
      const protocols = this.token
        ? ["ckl-bench", tokenSubprotocol(this.token)]
        : ["ckl-bench"];
      this.ws = new WebSocket(this.url, protocols);
      this.ws.onmessage = (ev) => {
        let event: ProgressEvent;
        try {
          const parsed = normalizeProgressEvent(JSON.parse(ev.data));
          if (!parsed) return;
          event = parsed;
        } catch {
          return;
        }
        this.listeners.forEach((fn) => fn(event));
      };
      this.ws.onopen = () => {
        this.retries = 0; // reset on successful connection
      };
      this.ws.onclose = () => {
        // Try to reconnect after a delay, up to maxRetries (polling fallback
        // takes over if we give up).
        if (this.retries < this.maxRetries) {
          this.retries++;
          this.reconnectTimer = setTimeout(() => this.connect(), 3000);
        }
      };
      this.ws.onerror = () => {
        // Will trigger onclose -> reconnect.
        this.ws?.close();
      };
    } catch {
      // WebSocket unsupported — polling fallback is used by the caller.
      this.ws = null;
    }
  }

  on(listener: ProgressListener) {
    this.listeners.add(listener);
  }

  off(listener: ProgressListener) {
    this.listeners.delete(listener);
  }

  disconnect() {
    clearTimeout(this.reconnectTimer);
    this.listeners.clear();
    this.ws?.close();
    this.ws = null;
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
