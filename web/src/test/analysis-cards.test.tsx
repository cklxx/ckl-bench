import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { AnalysisCards } from "@/components/analysis-cards";
import { I18nProvider } from "@/lib/i18n";
import type { RunSummary } from "@/lib/types";
import * as React from "react";

function makeSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "test-run",
    adapter: "command",
    adapter_display: "dsx",
    total: 5,
    passed: 3,
    failed: 2,
    score: 0.6,
    pass_rate: 0.6,
    by_capability: {
      clarity: { score: 0.8, passed: 4, count: 5 },
      accuracy: { score: 0.4, passed: 2, count: 5 },
    },
    ...overrides,
  } as RunSummary;
}

function renderCards(runs: RunSummary[]) {
  localStorage.setItem("ckl-bench-locale", "en");
  render(
    <I18nProvider>
      <AnalysisCards runs={runs} />
    </I18nProvider>
  );
}

describe("AnalysisCards", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders nothing when runs is empty", () => {
    const { container } = render(
      <I18nProvider>
        <AnalysisCards runs={[]} />
      </I18nProvider>
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows passed/total with full data", () => {
    renderCards([makeSummary()]);
    expect(screen.getByText("3/5 cases passed")).toBeInTheDocument();
  });

  it("does NOT show raw {{passed}}/{{total}} when fields are missing", () => {
    const summary = makeSummary({ passed: undefined, total: undefined });
    delete (summary as any).passed;
    delete (summary as any).total;
    renderCards([summary]);
    // Should fall back to 0/0, not raw template syntax
    const desc = screen.getByText(/cases passed/).textContent || "";
    expect(desc).not.toMatch(/{{\w+}}/);
    expect(desc).toBe("0/0 cases passed");
  });

  it("does NOT show raw template syntax when only passed is missing", () => {
    const summary = makeSummary({ passed: undefined });
    delete (summary as any).passed;
    renderCards([summary]);
    const desc = screen.getByText(/\/5 cases passed/).textContent || "";
    expect(desc).not.toMatch(/{{\w+}}/);
  });

  it("shows 0/0 when both are zero", () => {
    renderCards([makeSummary({ passed: 0, total: 0 })]);
    expect(screen.getByText("0/0 cases passed")).toBeInTheDocument();
  });

  it("renders strongest and weakest capabilities", () => {
    renderCards([makeSummary()]);
    expect(screen.getByText("clarity")).toBeInTheDocument();
    expect(screen.getByText("accuracy")).toBeInTheDocument();
  });

  it("shows trend when two runs provided", () => {
    renderCards([
      makeSummary({ score: 0.4, run_id: "old" }),
      makeSummary({ score: 0.8, run_id: "new" }),
    ]);
    // Should show improvement
    expect(screen.getByText("+40.0%")).toBeInTheDocument();
  });
});
