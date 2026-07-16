import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { FailureAnalysis } from "@/components/failure-analysis";
import { I18nProvider } from "@/lib/i18n";
import type { Result, RunSummary } from "@/lib/types";
import * as React from "react";

function makeRunSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "run-1",
    adapter: "command",
    adapter_display: "dsx",
    score: 0.6,
    total: 5,
    passed: 3,
    failed: 2,
    pass_rate: 0.6,
    by_capability: {
      clarity: { score: 0.4, passed: 2, count: 5 },
      accuracy: { score: 0.8, passed: 4, count: 5 },
    },
    ...overrides,
  } as RunSummary;
}

function makeFailedResult(overrides: Partial<Result> = {}): Result {
  return {
    case_id: "case-1",
    passed: false,
    score: 0,
    capability: ["clarity"],
    checks: [],
    ...overrides,
  } as Result;
}

function renderFailure(runs: RunSummary[], results?: Result[]) {
  localStorage.setItem("ckl-bench-locale", "en");
  return render(
    <I18nProvider>
      <FailureAnalysis runs={runs} results={results} />
    </I18nProvider>
  );
}

describe("FailureAnalysis", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders nothing when no failures and no results", () => {
    const { container } = renderFailure([
      makeRunSummary({
        by_capability: {
          clarity: { score: 1.0, passed: 5, count: 5 },
        },
      }),
    ]);
    expect(container.firstChild).toBeNull();
  });

  it("shows per-capability failure table with failure rates", () => {
    renderFailure([makeRunSummary()]);
    expect(screen.getByText("By Capability")).toBeInTheDocument();
    expect(screen.getByText("clarity")).toBeInTheDocument();
    expect(screen.getByText("accuracy")).toBeInTheDocument();
    // clarity: 3 failed / 5 = 60%; accuracy: 1 failed / 5 = 20%
    expect(screen.getByText("60.0%")).toBeInTheDocument();
    expect(screen.getByText("20.0%")).toBeInTheDocument();
  });

  it("shows top failed capabilities badges from results", () => {
    renderFailure([], [
      makeFailedResult({ case_id: "c1", capability: ["clarity", "accuracy"] }),
      makeFailedResult({ case_id: "c2", capability: ["clarity"] }),
    ]);
    expect(screen.getByText("Top Failed Capabilities")).toBeInTheDocument();
    expect(screen.getByText("clarity (2)")).toBeInTheDocument();
    expect(screen.getByText("accuracy (1)")).toBeInTheDocument();
  });

  it("shows check type breakdown from failed results", () => {
    renderFailure([], [
      makeFailedResult({
        case_id: "c1",
        checks: [
          { kind: "llm_judge", passed: false },
          { kind: "regex", passed: false },
        ],
      }),
      makeFailedResult({
        case_id: "c2",
        checks: [{ kind: "llm_judge", passed: false }],
      }),
    ]);
    expect(screen.getByText("By Check Type")).toBeInTheDocument();
    expect(screen.getByText("llm_judge")).toBeInTheDocument();
    expect(screen.getByText("regex")).toBeInTheDocument();
  });

  it("shows error pattern grouping from failed results", () => {
    renderFailure([], [
      makeFailedResult({ case_id: "c1", error: "Connection timeout" }),
      makeFailedResult({ case_id: "c2", error: "Connection timeout" }),
      makeFailedResult({ case_id: "c3", error: "Invalid response" }),
    ]);
    expect(screen.getByText("By Error Pattern")).toBeInTheDocument();
    expect(screen.getByText("Connection timeout")).toBeInTheDocument();
    expect(screen.getByText("Invalid response")).toBeInTheDocument();
  });
});
