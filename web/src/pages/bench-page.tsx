import { useCallback, useEffect, useState } from "react";
import {
  cancelRun,
  getConfig,
  getRun,
  getRunProgress,
  getSettings,
  launchRun,
  listCases,
  listProviders,
  listRuns,
  ProgressSocket,
  normalizeRunProgress,
} from "@/lib/api";
import { readData } from "@/lib/data";
import type {
  CaseListItem,
  ConfigInfo,
  ProviderInfo,
  ProgressEvent,
  Result,
  RunInfo,
  Settings,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { SettingsDrawer } from "@/components/settings-drawer";
import { CaseEditor } from "@/components/case-editor";
import { RunDetail } from "@/components/run-detail";
import {
  PackDetail,
  type PackInfo,
  type PackRunState,
} from "@/components/pack-detail";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageToggle, useT } from "@/lib/i18n";
import { useCopyToast } from "@/lib/use-copy-toast";
import { AnalysisCards } from "@/components/analysis-cards";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { RunTable } from "@/components/run-table";
import { ComparisonTable } from "@/components/comparison-table";
import { FailureAnalysis } from "@/components/failure-analysis";
import { PlayCircle, Settings as SettingsIcon, Box, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

function packFromSource(source: string): string {
  const m = source.match(/cases\/([^/]+)/);
  return m ? m[1] : "other";
}

function packFromPaths(paths: string[] | undefined | null): string | null {
  if (!paths || paths.length === 0) return null;
  const m = paths[0].match(/cases\/([^/]+)/);
  return m ? m[1] : null;
}


export function isActiveRun(status: RunInfo["status"]): boolean {
  return status === "pending" || status === "running" || status === "cancellation_requested";
}

export function applyProgressEvent(runs: RunInfo[], event: ProgressEvent): RunInfo[] {
  if (event.type === "connected") return runs;
  return runs.map((run) => {
    if (run.run_id !== event.run_id) return run;
    const progress = normalizeRunProgress(run.progress ?? {}, run.run_id, run.status);
    if (event.type === "run_started") {
      return {
        ...run,
        status: run.status === "cancellation_requested" ? run.status : "running",
        progress: {
          ...progress,
          status: run.status === "cancellation_requested" ? run.status : "running",
          total_cases: event.total_cases,
          planned_attempts: event.planned_attempts ?? event.total_cases * event.repeat,
        },
      };
    }
    if (event.type === "attempt_started" || event.type === "attempt_completed") {
      const attempts = { ...progress.attempts };
      const caseAttempts = { ...(attempts[event.case_id] ?? {}) };
      const previous = caseAttempts[String(event.attempt)];
      caseAttempts[String(event.attempt)] = event.type === "attempt_started"
        ? {
            attempt: event.attempt,
            status: "running",
            score: previous?.score ?? null,
            passed: previous?.passed ?? null,
            error: previous?.error ?? null,
            error_type: previous?.error_type ?? null,
          }
        : {
            attempt: event.attempt,
            status: event.status,
            score: event.score,
            passed: event.passed,
            error: event.error,
            error_type: event.error_type ?? null,
          };
      attempts[event.case_id] = caseAttempts;
      return { ...run, progress: { ...progress, attempts } };
    }
    return {
      ...run,
      status: event.status,
      summary: event.summary,
      error: event.error,
      progress: { ...progress, status: event.status },
    };
  });
}

// Built-in CLI adapters run through the command wrapper; discovered providers
// are launched by their registry target instead.
const BUILTIN_CLI_ADAPTER_KEYS = new Set(["claude-code", "codex", "dsx"]);

export function BenchPage() {
  const t = useT();
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null);
  const [creatingCasePack, setCreatingCasePack] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detailPack, setDetailPack] = useState<PackInfo | null>(null);
  const [reportTab, setReportTab] = useState("overview");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    listCases().then(setCases).catch((e) => setError(String(e)));
    listRuns().then(setRuns).catch(() => {});
    getConfig().then(setConfig).catch(() => {});
    getSettings().then(setSettings).catch(() => {});
    listProviders().then(setProviders).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // WebSocket for live progress updates. Normalize legacy transport shapes at
  // the API boundary; state always uses canonical attempt-aware progress.
  const injectedWsPort = readData().ws_port;
  useEffect(() => {
    const wsPort = config?.ws_port ?? injectedWsPort;
    const socket = new ProgressSocket(wsPort);
    socket.on((event: ProgressEvent) => {
      setRuns((prev) => applyProgressEvent(prev, event));
    });
    socket.connect();
    const poll = setInterval(() => {
      if (!socket.connected) {
        setRuns((current) => {
          const active = current.filter((run) => isActiveRun(run.status));
          void Promise.allSettled(active.map((run) => getRunProgress(run.run_id))).then(
            (outcomes) => {
              const updates = new Map(
                outcomes
                  .filter((outcome): outcome is PromiseFulfilledResult<RunInfo> => outcome.status === "fulfilled")
                  .map((outcome) => {
                    const run = outcome.value;
                    return [run.run_id, {
                      ...run,
                      progress: normalizeRunProgress(run.progress ?? {}, run.run_id, run.status),
                    } satisfies RunInfo] as const;
                  })
              );
              setRuns((previous) => previous.map((run) => updates.get(run.run_id) || run));
            }
          );
          return current;
        });
      }
    }, 2000);
    const discover = setInterval(() => {
      if (!socket.connected) listRuns().then(setRuns).catch(() => {});
    }, 15000);
    return () => {
      socket.disconnect();
      clearInterval(poll);
      clearInterval(discover);
    };
  }, [config?.ws_port, injectedWsPort]);

  // Group cases into packs.
  const packMap = new Map<string, CaseListItem[]>();
  for (const c of cases) {
    const p = packFromSource(c.source);
    if (!packMap.has(p)) packMap.set(p, []);
    packMap.get(p)!.push(c);
  }
  const packs: PackInfo[] = Array.from(packMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, packCases]) => {
      const capSet = new Set<string>();
      for (const c of packCases) c.capability.forEach((cap) => capSet.add(cap));
      return { name, cases: packCases, capabilities: Array.from(capSet) };
    });

  // Map runs -> pack + adapter run states.
  const packRunMap = new Map<string, PackRunState[]>();
  for (const run of runs) {
    const cp = run.summary?.manifest?.case_paths;
    const packName = packFromPaths(cp && Array.isArray(cp) ? cp : null);
    if (!packName) continue;
    const adapter =
      (run.summary as any)?.adapter_display || run.summary?.adapter || "unknown";
    const progress = normalizeRunProgress(run.progress ?? {}, run.run_id, run.status);
    const total = progress.planned_attempts || progress.total_cases;
    const completed = progress.completed_attempts;
    const passed = progress.passed_attempts;
    const existing = packRunMap.get(packName) || [];
    existing.push({
      runId: run.run_id,
      adapter,
      status: run.status,
      progress: { total, completed, passed },
      summary: run.summary,
    });
    packRunMap.set(packName, existing);
  }

  // Launch a run for one pack + one adapter.
  const launchPackAdapter = async (packName: string, adapterKey: string) => {
    const adapterConfig = settings?.adapters[adapterKey] || {};
    const pack = packs.find((p) => p.name === packName);
    const caseCount = pack?.cases.length || 0;
    const isBuiltin = BUILTIN_CLI_ADAPTER_KEYS.has(adapterKey);
    const params: any = isBuiltin
      ? {
          adapter: "command",
          adapter_config: {
            command: adapterConfig.command || "",
            ...(adapterConfig.model && { model: adapterConfig.model }),
          },
        }
      : {
          adapter_target: adapterKey,
        };
    params.case_paths = [`cases/${packName}`];
    params.repeat = settings?.defaults.repeat ?? 1;
    params.concurrency = settings?.defaults.concurrency ?? 1;
    params.seed = settings?.defaults.seed ?? 0;
    if (settings?.defaults.judge) params.judge = settings.defaults.judge;
    if (settings?.defaults.reviewer) params.reviewer = settings.defaults.reviewer;
    if (settings?.defaults.verifier) params.verifier = settings.defaults.verifier;
    try {
      const result = await launchRun(params);
      setRuns((prev) => [
        {
          run_id: result.run_id,
          status: "running",
          progress: {
            run_id: result.run_id,
            status: "running",
            total_cases: caseCount,
            planned_attempts: caseCount * (settings?.defaults.repeat ?? 1),
            started_attempts: 0,
            completed_attempts: 0,
            passed_attempts: 0,
            failed_attempts: 0,
            error_attempts: 0,
            cancelled_attempts: 0,
            attempts: {},
          },
          summary: {
            run_id: result.run_id,
            adapter: isBuiltin ? "command" : adapterKey,
            adapter_display: adapterKey,
            manifest: { case_paths: [`cases/${packName}`] },
            total: 0,
            passed: 0,
          } as any,
        },
        ...prev,
      ]);
    } catch (e) {
      setError(String(e));
    }
  };

  const launchPack = async (packName: string) => {
    const active = settings?.active_adapters || [];
    if (active.length === 0) {
      setError(t("bench.noAdapters"));
      return;
    }
    for (const adapterKey of active) {
      await launchPackAdapter(packName, adapterKey);
    }
  };

  const launchAll = async () => {
    setLaunching(true);
    setError("");
    const active = settings?.active_adapters || [];
    if (active.length === 0) {
      setError(t("bench.noAdapters"));
      setLaunching(false);
      return;
    }
    for (const pack of packs) {
      for (const adapterKey of active) {
        await launchPackAdapter(pack.name, adapterKey);
      }
    }
    setLaunching(false);
  };

  const requestCancel = async (runId: string) => {
    try {
      await cancelRun(runId);
      setRuns((prev) => prev.map((run) =>
        run.run_id === runId ? { ...run, status: "cancellation_requested" } : run
      ));
    } catch (e) {
      setError(String(e));
    }
  };

  // Only completed runs have valid scores; sort oldest-first so the trend
  // chart reads left-to-right in time and analysis-cards can take the last
  // two entries as "latest" and "previous".
  const summaries = runs
    .filter((r) => r.status === "completed" && r.summary != null)
    .sort((a, b) => (a.started_at ?? 0) - (b.started_at ?? 0))
    .map((r) => r.summary as NonNullable<typeof r.summary>);

  // Fetch results for completed runs so FailureAnalysis can show check-type
  // and error-pattern breakdowns (the list endpoint doesn't include results).
  const [runResults, setRunResults] = useState<Record<string, Result[]>>({});
  useEffect(() => {
    const need = runs.filter(
      (r) => ["completed", "failed", "cancelled"].includes(r.status) && !r.results && !runResults[r.run_id]
    );
    if (need.length === 0) return;
    Promise.allSettled(need.map((r) => getRun(r.run_id))).then((outcomes) => {
      const patch: Record<string, Result[]> = {};
      for (const oc of outcomes) {
        if (oc.status === "fulfilled" && oc.value.results) {
          patch[oc.value.run_id] = oc.value.results;
        }
      }
      setRunResults((prev) => ({ ...prev, ...patch }));
    });
  }, [runs]);

  const allResults = runs.flatMap(
    (r) => r.results ?? runResults[r.run_id] ?? []
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 flex h-12 items-center justify-between bg-background/80 px-4 backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold tracking-tight">ckl-bench</span>
          <Badge variant="muted" className="text-[10px] uppercase">
            bench
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setCreatingCasePack("")}>
            New Case
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={launchAll}
            disabled={launching || packs.length === 0}
          >
            <PlayCircle className="h-3.5 w-3.5" />
            {launching ? t("common.launching") : t("common.runAll")}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSettingsOpen(true)}
            aria-label={t("bench.settings")}
          >
            <SettingsIcon className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={refresh} aria-label={t("common.refresh")}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <LanguageToggle />
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {error && (
          <div className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <section className="space-y-4">
          <h1 className="text-xl font-semibold tracking-tight">{t("bench.title")}</h1>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {packs.map((pack) => (
              <BenchPackCard
                key={pack.name}
                pack={pack}
                runStates={packRunMap.get(pack.name) || []}
                onRun={() => launchPack(pack.name)}
                onView={() => setDetailPack(pack)}
                onEditCase={(id) => setEditingCaseId(id)}
              />
            ))}
          </div>
        </section>

        {summaries.length > 0 && (
          <section className="mt-10 space-y-6">
            <h2 className="text-lg font-semibold tracking-tight">{t("bench.reports")}</h2>
            <Tabs value={reportTab} onValueChange={setReportTab}>
              <TabsList>
                <TabsTrigger value="overview">{t("bench.overview")}</TabsTrigger>
                <TabsTrigger value="heatmap">{t("bench.heatmap")}</TabsTrigger>
                <TabsTrigger value="runs">{t("bench.allRuns")}</TabsTrigger>
                {summaries.length >= 2 && (
                  <>
                    <TabsTrigger value="comparison">
                      {t("comparison.title")}
                    </TabsTrigger>
                    <TabsTrigger value="failures">
                      {t("failure.title")}
                    </TabsTrigger>
                  </>
                )}
              </TabsList>

              <TabsContent value="overview">
                <div className="space-y-6">
                  <AnalysisCards runs={summaries} />
                  {summaries.length >= 2 && (
                    <Card>
                      <CardContent className="p-6">
                        <h3 className="mb-3 text-base font-semibold">
                          {t("bench.scoreTrend")}
                        </h3>
                        <TrendChart runs={summaries} />
                      </CardContent>
                    </Card>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="heatmap">
                <Card>
                  <CardContent className="p-6">
                    <h3 className="mb-3 text-base font-semibold">
                      {t("bench.capabilityHeatmap")}
                    </h3>
                    <Heatmap runs={summaries} />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="runs">
                <Card>
                  <CardContent className="p-6">
                    <h3 className="mb-3 text-base font-semibold">{t("bench.allRuns")}</h3>
                    <RunTable runs={summaries} onSelectRun={setSelectedRunId} />
                  </CardContent>
                </Card>
              </TabsContent>

              {summaries.length >= 2 && (
                <>
                  <TabsContent value="comparison">
                    <ComparisonTable runs={summaries} />
                  </TabsContent>

                  <TabsContent value="failures">
                    <FailureAnalysis runs={summaries} results={allResults} />
                  </TabsContent>
                </>
              )}
            </Tabs>
          </section>
        )}
      </main>

      <SettingsDrawer
        open={settingsOpen}
        value={settings}
        providers={providers}
        onClose={() => setSettingsOpen(false)}
        onSaved={setSettings}
      />
      {/* Sheet stack: PackDetail (z-50) → CaseEditor (z-51) on top.
          Closing the editor reveals the pack detail underneath. */}
      <PackDetail
        pack={detailPack}
        runStates={
          detailPack ? packRunMap.get(detailPack.name) || [] : []
        }
        onClose={() => setDetailPack(null)}
        onEditCase={setEditingCaseId}
        onAddCase={() => detailPack && setCreatingCasePack(detailPack.name)}
        onCancelRun={requestCancel}
        onRun={() => {
          if (detailPack) launchPack(detailPack.name);
          setDetailPack(null);
        }}
      />
      <RunDetail
        runId={selectedRunId}
        onClose={() => setSelectedRunId(null)}
      />
      <CaseEditor
        caseId={editingCaseId}
        createPack={creatingCasePack}
        onClose={() => {
          setEditingCaseId(null);
          setCreatingCasePack(null);
        }}
        onSaved={refresh}
      />
    </div>
  );
}

function BenchPackCard({
  pack,
  runStates,
  onRun,
  onView,
  onEditCase,
}: {
  pack: PackInfo;
  runStates: PackRunState[];
  onRun: () => void;
  onView: () => void;
  onEditCase: (id: string) => void;
}) {
  const t = useT();
  const copyTag = useCopyToast();
  const hasRunning = runStates.some(
    (r) => isActiveRun(r.status)
  );
  const hasCompleted = runStates.some((r) => r.status === "completed");

  return (
    <Card
      className="group relative flex min-h-[220px] flex-col overflow-hidden cursor-pointer transition-colors hover:bg-muted/40"
      onClick={onView}
    >
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary/60 to-primary/20" />

      <CardContent className="flex flex-1 flex-col p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Box className="h-5 w-5" />
          </div>
          <Badge variant="secondary" className="text-xs">
            {pack.cases.length}
          </Badge>
        </div>

        <h3 className="mb-1 text-base font-bold capitalize tracking-tight">
          {pack.name}
        </h3>
        <p className="mb-3 flex-1 text-xs leading-relaxed text-muted-foreground">
          {t("bench.cases", { count: pack.cases.length })}
        </p>

        <div className="mb-3 flex flex-wrap gap-1">
          {pack.capabilities.slice(0, 3).map((cap) => (
            <Badge
              key={cap}
              variant="outline"
              className="text-[10px] cursor-pointer hover:bg-muted"
              onClick={(e) => copyTag(e, cap)}
            >
              {cap}
            </Badge>
          ))}
          {pack.capabilities.length > 3 && (
            <Badge
              variant="outline"
              className="text-[10px] cursor-pointer hover:bg-muted"
              onClick={(e) =>
                copyTag(e, pack.capabilities.slice(3).join(", "))
              }
            >
              +{pack.capabilities.length - 3}
            </Badge>
          )}
        </div>

        {runStates.length > 0 && (
          <div className="mb-3 space-y-1.5">
            {runStates.map((rs) => {
              const pct =
                rs.progress.total > 0
                  ? Math.round((rs.progress.completed / rs.progress.total) * 100)
                  : 0;
              return (
                <div key={rs.runId}>
                  <div className="mb-0.5 flex items-center justify-between text-[11px]">
                    <span className="font-medium capitalize">{rs.adapter}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {rs.status === "completed"
                        ? t("pack.passed", {
                            passed: rs.progress.passed,
                            total: rs.progress.total,
                          })
                        : t("pack.progress", {
                            completed: rs.progress.completed,
                            total: rs.progress.total,
                          })}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all duration-300",
                        rs.status === "completed" ? "bg-success" : "bg-primary"
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-auto flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={(e) => {
              e.stopPropagation();
              onView();
            }}
          >
            {t("common.view")}
          </Button>
          <Button
            variant={!hasRunning && !hasCompleted ? "default" : "outline"}
            size="sm"
            className="flex-1"
            onClick={(e) => {
              e.stopPropagation();
              onRun();
            }}
            disabled={hasRunning}
          >
            <PlayCircle className="h-3.5 w-3.5" />
            {hasRunning
              ? t("common.running")
              : hasCompleted
                ? t("common.runAgain")
                : t("common.run")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
