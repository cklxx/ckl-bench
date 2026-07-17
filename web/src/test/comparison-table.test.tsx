import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComparisonTable } from "@/components/comparison-table";
import { I18nProvider } from "@/lib/i18n";
import type { RunSummary } from "@/lib/types";
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
      clarity: { score: 0.8, passed: 4, count: 5, pass_rate_ci: [0.5, 0.95] },
      accuracy: { score: 0.4, passed: 2, count: 5, pass_rate_ci: [0.1, 0.7] },
    },
    cost_usd: 0.5,
    usage: { total_tokens: 1000 },
    ...overrides,
  } as RunSummary;
}

function renderTable(runs: RunSummary[]) {
  localStorage.setItem("ckl-bench-locale", "en");
  return render(
    <I18nProvider>
      <ComparisonTable runs={runs} />
    </I18nProvider>
  );
}

describe("ComparisonTable", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders nothing when runs have no capabilities", () => {
    const { container } = renderTable([
      makeRunSummary({ by_capability: {} }),
    ]);
    expect(container.firstChild).toBeNull();
  });

  it("renders capability rows with scores", () => {
    renderTable([makeRunSummary()]);
    expect(screen.getByText("clarity")).toBeInTheDocument();
    expect(screen.getByText("accuracy")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
    expect(screen.getByText("40.0%")).toBeInTheDocument();
  });

  it("highlights the best adapter per capability with a ★", () => {
    renderTable([
      makeRunSummary({
        run_id: "run-a",
        adapter_display: "adapter-a",
        by_capability: {
          clarity: { score: 0.8, passed: 4, count: 5 },
          accuracy: { score: 0.3, passed: 1, count: 5 },
        },
      }),
      makeRunSummary({
        run_id: "run-b",
        adapter_display: "adapter-b",
        by_capability: {
          clarity: { score: 0.4, passed: 2, count: 5 },
          accuracy: { score: 0.6, passed: 3, count: 5 },
        },
      }),
    ]);
    // run A wins clarity, run B wins accuracy → 2 stars total
    expect(screen.getAllByText("★").length).toBe(2);
  });

  it("keeps confidence intervals descriptive without significance claims", () => {
    renderTable([
      makeRunSummary({
        run_id: "run-a",
        by_capability: {
          clarity: { score: 0.2, passed: 1, count: 5, pass_rate_ci: [0.1, 0.3] },
        },
      }),
      makeRunSummary({
        run_id: "run-b",
        by_capability: {
          clarity: { score: 0.6, passed: 3, count: 5, pass_rate_ci: [0.5, 0.7] },
        },
      }),
    ]);
    expect(screen.queryByText("Significant")).not.toBeInTheDocument();
    expect(screen.queryByText("Not significant")).not.toBeInTheDocument();
  });

  it("shows cost-effectiveness footer when cost/tokens data exists", () => {
    renderTable([makeRunSummary()]);
    expect(screen.getByText("Cost Effectiveness")).toBeInTheDocument();
  });

  it("does NOT show cost-effectiveness when no cost data", () => {
    renderTable([
      makeRunSummary({ cost_usd: 0, usage: { total_tokens: 0 } }),
    ]);
    expect(screen.queryByText("Cost Effectiveness")).not.toBeInTheDocument();
  });
});
