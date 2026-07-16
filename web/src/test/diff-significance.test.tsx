import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiffPage } from "@/pages/diff-page";
import { I18nProvider } from "@/lib/i18n";
import type { DiffData } from "@/lib/types";
import * as React from "react";

function makeDiffData(overrides: Partial<DiffData> = {}): DiffData {
  return {
    run_a: "run-a-aaaaaaaaaaaa",
    run_b: "run-b-bbbbbbbbbbbb",
    score_a: 0.4,
    score_b: 0.6,
    score_delta: 0.2,
    counts: {
      improved: 0,
      regressed: 0,
      unchanged: 0,
      added: 0,
      removed: 0,
    },
    cases: [],
    ...overrides,
  } as DiffData;
}

function renderDiff(diff: DiffData) {
  localStorage.setItem("ckl-bench-locale", "en");
  return render(
    <I18nProvider>
      <DiffPage diff={diff} />
    </I18nProvider>
  );
}

describe("DiffPage significance", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("does NOT show significance badge when CIs are missing", () => {
    renderDiff(makeDiffData());
    expect(screen.queryByText("Significant")).not.toBeInTheDocument();
    expect(screen.queryByText("Not significant")).not.toBeInTheDocument();
  });

  it("shows 'Significant' badge when CIs don't overlap", () => {
    renderDiff(
      makeDiffData({
        score_ci_a: [0.1, 0.3],
        score_ci_b: [0.5, 0.7],
      })
    );
    expect(screen.getByText("Significant")).toBeInTheDocument();
  });

  it("shows 'Not significant' badge when CIs overlap", () => {
    renderDiff(
      makeDiffData({
        score_ci_a: [0.1, 0.5],
        score_ci_b: [0.3, 0.7],
      })
    );
    expect(screen.getByText("Not significant")).toBeInTheDocument();
  });
});
