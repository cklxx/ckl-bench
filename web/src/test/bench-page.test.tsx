import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BenchPage } from "@/pages/bench-page";
import { I18nProvider } from "@/lib/i18n";
import { ToastProvider } from "@/components/ui/toast";

vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
}));

vi.mock("@/lib/data", () => ({
  readData: () => ({}),
}));

vi.mock("@/lib/api", () => ({
  cancelRun: vi.fn(),
  getConfig: vi.fn().mockResolvedValue({ ws_port: 0 }),
  getRun: vi.fn(),
  getRunProgress: vi.fn(),
  getSettings: vi.fn().mockResolvedValue({
    adapters: {},
    defaults: { repeat: 1, concurrency: 1, seed: 0, judge: "" },
    active_adapters: [],
  }),
  launchRun: vi.fn(),
  listCases: vi.fn().mockResolvedValue([]),
  listProviders: vi.fn().mockResolvedValue([]),
  listRuns: vi.fn().mockResolvedValue([]),
  createCase: vi.fn(),
  deleteCase: vi.fn(),
  getCase: vi.fn(),
  updateCase: vi.fn(),
  updateSettings: vi.fn(),
  testAdapter: vi.fn(),
  ProgressSocket: class {
    connected = false;
    on() {}
    connect() {}
    disconnect() {}
  },
}));

describe("BenchPage case creation", () => {
  it("opens the global case editor from New Case", async () => {
    localStorage.setItem("ckl-bench-locale", "en");
    render(
      <I18nProvider>
        <ToastProvider>
          <BenchPage />
        </ToastProvider>
      </I18nProvider>
    );

    await userEvent.click(screen.getByRole("button", { name: "New Case" }));
    expect(screen.getByDisplayValue("new_case.v1")).toBeInTheDocument();
  });
});
