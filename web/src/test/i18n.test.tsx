import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, useT } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";
import * as React from "react";

function Tester({
  tKey,
  params,
}: {
  tKey: string;
  params?: Record<string, string | number>;
}) {
  const t = useT();
  return <span>{t(tKey, params)}</span>;
}

function renderT(
  tKey: string,
  params?: Record<string, string | number>,
  locale: Locale = "en"
) {
  localStorage.setItem("ckl-bench-locale", locale);
  render(
    <I18nProvider>
      <Tester tKey={tKey} params={params} />
    </I18nProvider>
  );
}

describe("i18n t() function", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("substitutes all params when present (en)", () => {
    renderT("analysis.overallDesc", { passed: 3, total: 5 }, "en");
    expect(screen.getByText("3/5 cases passed")).toBeInTheDocument();
  });

  it("substitutes all params when present (zh)", () => {
    renderT("analysis.overallDesc", { passed: 3, total: 5 }, "zh");
    expect(screen.getByText("3/5 个用例通过")).toBeInTheDocument();
  });

  it("does NOT leave raw {{k}} when a param is undefined", () => {
    renderT("analysis.overallDesc", { passed: undefined, total: 5 } as any, "en");
    const text = screen.getByText(/\/5/).textContent || "";
    expect(text).not.toMatch(/{{\w+}}/);
  });

  it("does NOT leave raw {{k}} when a param is null", () => {
    renderT("analysis.overallDesc", { passed: null, total: null } as any, "en");
    const text = screen.getByText(/cases passed/).textContent || "";
    expect(text).not.toMatch(/{{\w+}}/);
  });

  it("does NOT leave raw {{k}} when params object is empty", () => {
    renderT("analysis.overallDesc", {}, "en");
    const text = screen.getByText(/cases passed/).textContent || "";
    expect(text).not.toMatch(/{{\w+}}/);
  });

  it("renders plain strings with no params (en)", () => {
    renderT("analysis.overall", undefined, "en");
    expect(screen.getByText("Overall Score")).toBeInTheDocument();
  });

  it("renders plain strings with no params (zh)", () => {
    renderT("analysis.overall", undefined, "zh");
    expect(screen.getByText("总得分")).toBeInTheDocument();
  });

  it("substitutes multiple params in a single template (en)", () => {
    renderT("common.ci", { low: 0.1, high: 0.9 }, "en");
    expect(screen.getByText("95% CI: [0.1, 0.9]")).toBeInTheDocument();
  });

  it("substitutes multiple params in a single template (zh)", () => {
    renderT("common.ci", { low: 0.1, high: 0.9 }, "zh");
    expect(screen.getByText("95% 置信区间: [0.1, 0.9]")).toBeInTheDocument();
  });
});
