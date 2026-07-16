import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, findByLabelText } from "@testing-library/react";
import { CaseEditor } from "@/components/case-editor";
import { I18nProvider } from "@/lib/i18n";
import type { CaseDetail } from "@/lib/types";
import * as React from "react";

const mockGetCase = vi.fn();
const mockUpdateCase = vi.fn();

vi.mock("@/lib/api", () => ({
  getCase: (...args: any[]) => mockGetCase(...args),
  updateCase: (...args: any[]) => mockUpdateCase(...args),
}));

function makeCaseDetail(overrides: Partial<CaseDetail> = {}): CaseDetail {
  return {
    id: "test-case",
    title: "Test Case",
    type: "chat",
    input: { prompt: "Hello prompt" },
    expectations: [],
    capability: ["clarity"],
    difficulty: "easy",
    timeout_s: 60,
    ...overrides,
  };
}

function renderEditor(caseId: string | null = "test-case") {
  localStorage.setItem("ckl-bench-locale", "en");
  return render(
    <I18nProvider>
      <CaseEditor caseId={caseId} onClose={() => {}} />
    </I18nProvider>
  );
}

describe("CaseEditor prompt display", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("shows input.prompt when present", async () => {
    mockGetCase.mockResolvedValue(makeCaseDetail());
    renderEditor();
    const textarea = await screen.findByLabelText(/prompt/i);
    expect(textarea).toHaveValue("Hello prompt");
  });

  it("falls back to last user message when prompt is absent", async () => {
    mockGetCase.mockResolvedValue(
      makeCaseDetail({
        input: {
          messages: [
            { role: "system", content: "You are helpful." },
            { role: "user", content: "Please fix the bug." },
          ],
        },
      })
    );
    renderEditor();
    const textarea = await screen.findByLabelText(/prompt/i);
    expect(textarea).toHaveValue("Please fix the bug.");
  });

  it("picks the LAST user message when multiple exist", async () => {
    mockGetCase.mockResolvedValue(
      makeCaseDetail({
        input: {
          messages: [
            { role: "user", content: "First message." },
            { role: "assistant", content: "Sure." },
            { role: "user", content: "Second message." },
          ],
        },
      })
    );
    renderEditor();
    const textarea = await screen.findByLabelText(/prompt/i);
    expect(textarea).toHaveValue("Second message.");
  });

  it("shows empty textarea when neither prompt nor messages exist", async () => {
    mockGetCase.mockResolvedValue(makeCaseDetail({ input: {} }));
    renderEditor();
    const textarea = await screen.findByLabelText(/prompt/i);
    expect(textarea).toHaveValue("");
  });

  it("does not render the editor when caseId is null", () => {
    renderEditor(null);
    expect(screen.queryByLabelText(/prompt/i)).not.toBeInTheDocument();
  });
});
