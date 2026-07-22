import { describe, expect, it } from "vitest";
import { applyProgressEvent, isActiveRun } from "@/pages/bench-page";
import type { RunInfo } from "@/lib/types";

function run(status: RunInfo["status"] = "running"): RunInfo {
  return {
    run_id: "run-1",
    status,
    progress: {
      run_id: "run-1", status, total_cases: 1, planned_attempts: 2,
      started_attempts: 0, completed_attempts: 0, passed_attempts: 0,
      failed_attempts: 0, error_attempts: 0, cancelled_attempts: 0, attempts: {},
    },
  };
}

describe("bench progress reducer", () => {
  it("preserves each (case_id, attempt) independently", () => {
    let state = applyProgressEvent([run()], {
      type: "attempt_started", run_id: "run-1", case_id: "case-1", case_index: 0, attempt: 0,
    });
    state = applyProgressEvent(state, {
      type: "attempt_completed", run_id: "run-1", case_id: "case-1", case_index: 0,
      attempt: 1, status: "failed", score: 0, passed: false, error: null,
    });
    expect(Object.keys(state[0].progress!.attempts["case-1"])).toEqual(["0", "1"]);
  });

  it("updates counters without double-counting duplicate events", () => {
    let state = applyProgressEvent([run()], {
      type: "attempt_started", run_id: "run-1", case_id: "case-1", case_index: 0, attempt: 0,
    });
    state = applyProgressEvent(state, {
      type: "attempt_started", run_id: "run-1", case_id: "case-1", case_index: 0, attempt: 0,
    });
    expect(state[0].progress!.started_attempts).toBe(1);

    const completed = {
      type: "attempt_completed", run_id: "run-1", case_id: "case-1", case_index: 0,
      attempt: 0, status: "completed", score: 1, passed: true, error: null,
    } as const;
    state = applyProgressEvent(state, completed);
    state = applyProgressEvent(state, completed);
    expect(state[0].progress).toMatchObject({
      started_attempts: 1,
      completed_attempts: 1,
      passed_attempts: 1,
      failed_attempts: 0,
      error_attempts: 0,
      cancelled_attempts: 0,
    });
  });

  it("reclassifies an attempt when a later terminal event arrives", () => {
    let state = applyProgressEvent([run()], {
      type: "attempt_completed", run_id: "run-1", case_id: "case-1", case_index: 0,
      attempt: 0, status: "failed", score: 0, passed: false, error: null,
    });
    expect(state[0].progress!.failed_attempts).toBe(1);
    state = applyProgressEvent(state, {
      type: "attempt_completed", run_id: "run-1", case_id: "case-1", case_index: 0,
      attempt: 0, status: "error", score: null, passed: null, error: "network",
    });
    state = applyProgressEvent(state, {
      type: "attempt_completed", run_id: "run-1", case_id: "case-2", case_index: 1,
      attempt: 0, status: "cancelled", score: null, passed: null, error: "cancelled",
    });
    expect(state[0].progress).toMatchObject({
      started_attempts: 2,
      completed_attempts: 2,
      passed_attempts: 0,
      failed_attempts: 0,
      error_attempts: 1,
      cancelled_attempts: 1,
    });
  });

  it("keeps cancellation_requested active and does not regress it on run_started", () => {
    expect(isActiveRun("cancellation_requested")).toBe(true);
    const state = applyProgressEvent([run("cancellation_requested")], {
      type: "run_started", run_id: "run-1", total_cases: 1, repeat: 2, planned_attempts: 2,
    });
    expect(state[0].status).toBe("cancellation_requested");
  });
});
