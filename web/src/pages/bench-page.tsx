import { useCallback, useEffect, useRef, useState } from "react";
import {
  getConfig,
  getSettings,
  launchRun,
  listCases,
  listRuns,
  ProgressSocket,
} from "@/lib/api";
import { readData } from "@/lib/data";
import type {
  CaseListItem,
  ConfigInfo,
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
import { AnalysisCards } from "@/components/analysis-cards";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { RunTable } from "@/components/run-table";
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

export function BenchPage() {
  const t = useT();
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detailPack, setDetailPack] = useState<PackInfo | null>(null);
  const [reportTab, setReportTab] = useState("overview");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef<ProgressSocket | null>(null);

  const refresh = useCallback(() => {
    listCases().then(setCases).catch((e) => setError(String(e)));
    listRuns().then(setRuns).catch(() => {});
    getConfig().then(setConfig).catch(() => {});
    getSettings().then(setSettings).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // WebSocket for live progress updates. ws_port comes from the injected
  // window.__CKL_BENCH_DATA__ (available immediately) or /api/config.
  const injectedWsPort = readData().ws_port;
  useEffect(() => {
    const wsPort = config?.ws_port ?? injectedWsPort;
    const socket = new ProgressSocket(wsPort);
    socketRef.current = socket;
    socket.on((event: any) => {
      if (event.type === "run_started") {
        setRuns((prev) =>
          prev.map((r) => {
            if (r.run_id !== event.run_id) return r;
            return {
              ...r,
              progress: {
                ...(r.progress || {}),
                total_cases: event.total_cases || 0,
                repeat: event.repeat || 1,
                cases: (r.progress as any)?.cases || {},
              },
            };
          })
        );
      } else if (event.type === "case_completed" || event.type === "case_started") {
        setRuns((prev) =>
          prev.map((r) => {
            if (r.run_id !== event.run_id) return r;
            const progress = { ...(r.progress || {}) };
            const progCases = { ...(progress.cases || {}) };
            progCases[event.case_id] = {
              status:
                event.type === "case_started"
                  ? "running"
                  : event.error
                    ? "failed"
                    : "completed",
              attempt: event.attempt || 0,
              score: event.score ?? null,
              passed: event.passed ?? null,
              error: event.error || null,
            };
            return { ...r, progress: { ...progress, cases: progCases } };
          })
        );
      } else if (event.type === "run_finished") {
        setRuns((prev) =>
          prev.map((r) =>
            r.run_id === event.run_id
              ? { ...r, status: event.status, summary: event.summary }
              : r
          )
        );
      }
    });
    socket.connect();
    const poll = setInterval(() => {
      if (!socket.connected) refresh();
    }, 2000);
    return () => {
      socket.disconnect();
      clearInterval(poll);
    };
  }, [config?.ws_port, injectedWsPort, refresh]);

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
    const progress = run.progress || { total_cases: 0, cases: {} };
    const progCases = progress.cases || {};
    const total = progress.total_cases || Object.keys(progCases).length;
    const completed = Object.values(progCases).filter(
      (c: any) => c.status === "completed" || c.status === "failed"
    ).length;
    const passed = Object.values(progCases).filter(
      (c: any) => c.status === "completed" && c.passed !== false
    ).length;
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
    const params: any = {
      adapter: "command",
      adapter_config: {
        command: adapterConfig.command || "",
        ...(adapterConfig.model && { model: adapterConfig.model }),
      },
      case_paths: [`cases/${packName}`],
      repeat: settings?.defaults.repeat ?? 1,
      concurrency: settings?.defaults.concurrency ?? 1,
      seed: settings?.defaults.seed ?? 0,
    };
    if (settings?.defaults.judge) params.judge = settings.defaults.judge;
    try {
      const result = await launchRun(params);
      setRuns((prev) => [
        {
          run_id: result.run_id,
          status: "running",
          progress: { total_cases: caseCount, cases: {} },
          summary: {
            run_id: result.run_id,
            adapter: "command",
            adapter_display: adapterKey,
            manifest: { case_paths: [`cases/${packName}`] },
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

  const summaries = runs
    .map((r) => r.summary)
    .filter((s): s is NonNullable<typeof s> => s != null);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 flex h-12 items-center justify-between border-b bg-background/80 px-4 backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold tracking-tight">ckl-bench</span>
          <Badge variant="muted" className="text-[10px] uppercase">
            bench
          </Badge>
        </div>
        <div className="flex items-center gap-2">
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
          <Button variant="ghost" size="icon" onClick={refresh}>
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
            </Tabs>
          </section>
        )}
      </main>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      {/* Sheet stack: PackDetail (z-50) → CaseEditor (z-51) on top.
          Closing the editor reveals the pack detail underneath. */}
      <PackDetail
        pack={detailPack}
        runStates={
          detailPack ? packRunMap.get(detailPack.name) || [] : []
        }
        onClose={() => setDetailPack(null)}
        onEditCase={setEditingCaseId}
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
        onClose={() => setEditingCaseId(null)}
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
  const hasRunning = runStates.some(
    (r) => r.status === "running" || r.status === "pending"
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
              onClick={(e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(cap);
              }}
            >
              {cap}
            </Badge>
          ))}
          {pack.capabilities.length > 3 && (
            <Badge
              variant="outline"
              className="text-[10px] cursor-pointer hover:bg-muted"
              onClick={(e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(
                  pack.capabilities.slice(3).join(", ")
                );
              }}
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
