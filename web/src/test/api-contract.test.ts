import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/data", () => ({
  readAppBootstrap: () => ({ page: "app", ws_port: 9876, api_token: "tøken" }),
}));

describe("API authentication and progress normalization", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("adds the bootstrap bearer token to HTTP requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);
    const { listRuns } = await import("@/lib/api");
    await listRuns();
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tøken");
  });

  it("uses the exact authenticated WebSocket protocols", async () => {
    const socket = { close: vi.fn(), readyState: 0 };
    const WebSocketMock = vi.fn().mockImplementation(() => socket);
    Object.assign(WebSocketMock, { OPEN: 1 });
    vi.stubGlobal("WebSocket", WebSocketMock);
    const { ProgressSocket } = await import("@/lib/api");
    new ProgressSocket().connect();
    expect(WebSocketMock).toHaveBeenCalledWith(
      "ws://localhost:9876/ws",
      ["ckl-bench", "ckl-bench-token.dMO4a2Vu"]
    );
  });

  it("normalizes legacy progress without collapsing attempts", async () => {
    const { normalizeRunProgress, normalizeProgressEvent } = await import("@/lib/api");
    const progress = normalizeRunProgress({
      total: 2,
      completed: 1,
      cases: { c1: { "0": { status: "completed", score: 1 }, "1": { status: "running" } } },
    }, "run-1", "running");
    expect(progress.planned_attempts).toBe(2);
    expect(Object.keys(progress.attempts.c1)).toEqual(["0", "1"]);
    expect(normalizeProgressEvent({ type: "case_started", run_id: "r", case_id: "c", attempt: 2 })?.type)
      .toBe("attempt_started");
  });
});
