import { useEffect, useRef, useState } from "react";
import { getSettings, updateSettings, testAdapter } from "@/lib/api";
import type { Settings, AdapterConfig, AdapterTestResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { X, Save, CheckCircle2, XCircle, Loader2, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

const ADAPTER_DEFS = [
  { key: "claude-code", label: "Claude Code", icon: "CC" },
  { key: "codex", label: "Codex", icon: "CX" },
  { key: "dsx", label: "DSX", icon: "DS" },
];

export function SettingsDrawer({ open, onClose }: SettingsDrawerProps) {
  const t = useT();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, AdapterTestResult>>({});
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (open) {
      getSettings()
        .then(setSettings)
        .catch((e) => setError(String(e)));
    }
  }, [open]);

  // Clean up abort + timer on close.
  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
      abortRef.current = null;
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setTesting(null);
      setElapsed(0);
    }
  }, [open]);

  if (!open) return null;

  const updateAdapter = (key: string, field: string, value: string) => {
    setSettings((prev) => {
      if (!prev) return prev;
      const adapters = { ...prev.adapters };
      adapters[key] = { ...(adapters[key] || {}), [field]: value };
      return { ...prev, adapters };
    });
  };

  const updateDefault = (field: string, value: any) => {
    setSettings((prev) => {
      if (!prev) return prev;
      return { ...prev, defaults: { ...prev.defaults, [field]: value } };
    });
  };

  const toggleActive = (key: string) => {
    setSettings((prev) => {
      if (!prev) return prev;
      const active = prev.active_adapters.includes(key)
        ? prev.active_adapters.filter((a) => a !== key)
        : [...prev.active_adapters, key];
      return { ...prev, active_adapters: active };
    });
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError("");
    try {
      await updateSettings(settings);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (key: string, config: AdapterConfig) => {
    // Abort any in-progress test first.
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setTesting(key);
    setElapsed(0);
    setError("");

    // Elapsed timer so the user sees something is happening.
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setElapsed((e) => e + 1);
    }, 1000);

    const testConfig: Record<string, any> = {};
    if (config.command) testConfig.command = config.command;
    if (config.model) testConfig.model = config.model;
    if (config.api_key) testConfig.api_key = config.api_key;
    if (config.base_url) testConfig.base_url = config.base_url;

    try {
      const result = await testAdapter("command", testConfig, abortRef.current.signal);
      setTestResults((prev) => ({ ...prev, [key]: result }));
    } catch (e: any) {
      if (e?.name === "AbortError") {
        setTestResults((prev) => ({
          ...prev,
          [key]: { ok: false, output: "", error: t("settings.testCancelled") },
        }));
      } else {
        setTestResults((prev) => ({
          ...prev,
          [key]: { ok: false, output: "", error: String(e) },
        }));
      }
    } finally {
      setTesting(null);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setElapsed(0);
    }
  };

  const handleCancelTest = () => {
    abortRef.current?.abort();
    abortRef.current = null;
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex w-[420px] flex-col bg-background shadow-lg">
        <div className="flex h-12 items-center justify-between border-b px-4">
          <h2 className="text-base font-semibold">{t("settings.title")}</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Active adapters selection */}
          <section>
            <h3 className="mb-2 text-sm font-semibold">{t("settings.activeAdapters")}</h3>
            <p className="mb-2 text-xs text-muted-foreground">
              {t("settings.activeDesc")}
            </p>
            <div className="space-y-2">
              {ADAPTER_DEFS.map((def) => {
                const active = settings?.active_adapters.includes(def.key);
                return (
                  <button
                    key={def.key}
                    onClick={() => toggleActive(def.key)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border hover:bg-muted"
                    )}
                  >
                    <Badge variant={active ? "default" : "outline"} className="text-[10px]">
                      {def.icon}
                    </Badge>
                    <span className="font-medium">{def.label}</span>
                    {active && (
                      <CheckCircle2 className="ml-auto h-4 w-4 text-success" />
                    )}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Adapter config sections */}
          {ADAPTER_DEFS.map((def) => {
            const config = settings?.adapters[def.key] || {};
            const testResult = testResults[def.key];
            const isTesting = testing === def.key;
            return (
              <section key={def.key}>
                <h3 className="mb-2 text-sm font-semibold">{def.label}</h3>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">{t("settings.command")}</label>
                    <textarea
                      value={config.command || ""}
                      onChange={(e) => updateAdapter(def.key, "command", e.target.value)}
                      placeholder={t("settings.commandPh")}
                      rows={3}
                      className="w-full rounded-md bg-muted/50 px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring border border-input resize-y"
                    />
                  </div>
                  {def.key === "claude-code" && (
                    <>
                      <div className="space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">{t("settings.apiKey")}</label>
                        <Input
                          type="password"
                          value={config.api_key || ""}
                          onChange={(e) => updateAdapter(def.key, "api_key", e.target.value)}
                          placeholder={t("settings.apiKeyPh")}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">{t("settings.baseUrl")}</label>
                        <Input
                          value={config.base_url || ""}
                          onChange={(e) => updateAdapter(def.key, "base_url", e.target.value)}
                          placeholder="https://api.example.com/anthropic"
                        />
                      </div>
                    </>
                  )}
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">{t("settings.model")}</label>
                    <Input
                      value={config.model || ""}
                      onChange={(e) => updateAdapter(def.key, "model", e.target.value)}
                      placeholder={t("settings.modelPh")}
                    />
                  </div>

                  {/* Test button with cancel and progress */}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleTest(def.key, config)}
                      disabled={isTesting || !config.command}
                    >
                      {isTesting ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : testResult?.ok ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                      ) : testResult && !testResult.ok ? (
                        <XCircle className="h-3.5 w-3.5 text-destructive" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                      {isTesting
                        ? `${t("common.testing")}${elapsed > 0 ? ` (${elapsed}s)` : ""}`
                        : t("common.test")}
                    </Button>
                    {isTesting && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleCancelTest}
                        className="text-xs text-muted-foreground"
                      >
                        {t("common.cancel")}
                      </Button>
                    )}
                  </div>

                  {/* Show what command is being tested */}
                  {isTesting && config.command && (
                    <p className="text-[11px] text-muted-foreground font-mono break-all">
                      {t("settings.testingCommand", { command: config.command })}
                    </p>
                  )}

                  {/* Test result */}
                  {testResult && !isTesting && (
                    <div
                      className={cn(
                        "rounded-md px-2 py-1.5 text-xs",
                        testResult.ok
                          ? "bg-success/10 text-success"
                          : "bg-destructive/10 text-destructive"
                      )}
                    >
                      {testResult.ok
                        ? testResult.output || t("settings.testOk")
                        : testResult.error}
                    </div>
                  )}
                </div>
              </section>
            );
          })}

          {/* Default run options */}
          <section>
            <h3 className="mb-2 text-sm font-semibold">{t("settings.defaultOptions")}</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("settings.repeat")}</label>
                <Input
                  type="number"
                  min={1}
                  value={settings?.defaults.repeat ?? 1}
                  onChange={(e) => updateDefault("repeat", Number(e.target.value))}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("settings.concurrency")}</label>
                <Input
                  type="number"
                  min={1}
                  value={settings?.defaults.concurrency ?? 1}
                  onChange={(e) => updateDefault("concurrency", Number(e.target.value))}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("settings.seed")}</label>
                <Input
                  type="number"
                  value={settings?.defaults.seed ?? 0}
                  onChange={(e) => updateDefault("seed", Number(e.target.value))}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("settings.judge")}</label>
                <Input
                  value={settings?.defaults.judge ?? ""}
                  onChange={(e) => updateDefault("judge", e.target.value)}
                  placeholder={t("settings.judgePh")}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("settings.reviewer")}</label>
                <Input
                  value={settings?.defaults.reviewer ?? ""}
                  onChange={(e) => updateDefault("reviewer", e.target.value)}
                  placeholder={t("settings.reviewerPh")}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("settings.verifier")}</label>
                <Input
                  value={settings?.defaults.verifier ?? ""}
                  onChange={(e) => updateDefault("verifier", e.target.value)}
                  placeholder={t("settings.verifierPh")}
                />
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="border-t p-4">
          <Button className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saving ? t("settings.saving") : t("settings.save")}
          </Button>
        </div>
      </div>
    </div>
  );
}
