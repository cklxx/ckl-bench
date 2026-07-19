import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SettingsDrawer } from "@/components/settings-drawer";
import { I18nProvider } from "@/lib/i18n";
import type { ProviderInfo, Settings } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  updateSettings: vi.fn(),
  testAdapter: vi.fn(),
}));

const settings: Settings = {
  adapters: {
    "claude-code": { command: "claude" },
    codex: { command: "codex" },
    dsx: { command: "dsx" },
  },
  defaults: {
    repeat: 1,
    concurrency: 1,
    seed: 0,
    judge: "",
  },
  active_adapters: [],
};

const providers: ProviderInfo[] = [
  { namespace: "deepseekv4", aliases: [], default: "" },
  { namespace: "dsx", aliases: [], default: "" },
];

describe("SettingsDrawer provider catalog", () => {
  it("keeps built-in CLI adapters alongside discovered providers", () => {
    localStorage.setItem("ckl-bench-locale", "en");
    render(
      <I18nProvider>
        <SettingsDrawer
          open
          value={settings}
          providers={providers}
          onClose={() => {}}
          onSaved={() => {}}
        />
      </I18nProvider>
    );

    expect(screen.getAllByText("Claude Code")).toHaveLength(2);
    expect(screen.getAllByText("Codex")).toHaveLength(2);
    expect(screen.getAllByText("DSX")).toHaveLength(2);
    expect(screen.getAllByText("deepseekv4")).toHaveLength(2);
    expect(screen.getByText("DS")).toBeInTheDocument();
  });
});
