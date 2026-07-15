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
} from "./types";

const BASE = ""; // Same-origin; the server serves both the app and the API.

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
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

export function createCase(c: Partial<CaseDetail>): Promise<CaseDetail> {
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

export interface LaunchRunParams {
  adapter?: string;
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

export function updateSettings(settings: Settings): Promise<{ ok: boolean }> {
  return request("/api/settings", {
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

// --- WebSocket ---

export type ProgressListener = (event: any) => void;

export class ProgressSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<ProgressListener>();
  private reconnectTimer: any = null;
  private url: string;
  private retries = 0;
  private maxRetries = 10;

  constructor(wsPort?: number) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const port = wsPort ? `:${wsPort}` : "";
    this.url = `${proto}://${location.hostname}${port}/ws`;
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);
      this.ws.onmessage = (ev) => {
        let event: any;
        try {
          event = JSON.parse(ev.data);
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
