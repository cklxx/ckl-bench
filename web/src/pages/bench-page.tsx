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
import { SettingsDrawer } from "@/components/settings-drawer";
import { ThemeToggle } from "@/components/theme-toggle";
import { AnalysisCards } from "@/components/analysis-cards";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { RunTable } from "@/components/run-table";
import { PlayCircle, Settings as SettingsIcon, Box, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

const PACK_DESC: Record<string, string> = {
  chat: "API-only and chat cases covering reasoning, math, code, and long-tail knowledge.",
  agent: "Agent cases with temporary workspaces and artifact checks.",
  "doc-writing": "Documentation writing: API docs, READMEs, changelogs.",
  "infra-code": "Infrastructure code: Docker, systemd, nginx, deploy scripts.",
  "paper-reading": "Paper reading: abstract comprehension, method comparison, results.",
};

function packFromSource(source: string): string {
  const m = source.match(/cases\/([^/]+)/);
  return m ? m[1] : "other";
}

function packFromPaths(paths: string[] | undefined | null): string | null {
  if (!paths || paths.length === 0) return null;
  const m = paths[0].match(/cases\/([^/]+)/);
  return m ? m[1] : null;
}

interface PackInfo {
  name: string;
  cases: CaseListItem[];
  capabilities: string[];
}

interface PackRunState {
  runId: string;
  adapter: string;
  status: string;
  progress: { total: number; completed: number; passed: number };
  summary?: any;
}

export function BenchPage() {
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
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
      setError("No active adapters selected. Configure adapters in Settings.");
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
      setError("No active adapters selected. Configure adapters in Settings.");
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
            {launching ? "Launching..." : "Run All"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSettingsOpen(true)}
            aria-label="Settings"
          >
            <SettingsIcon className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
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
          <h1 className="text-xl font-semibold tracking-tight">Bench Collections</h1>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {packs.map((pack) => (
              <BenchPackCard
                key={pack.name}
                pack={pack}
                runStates={packRunMap.get(pack.name) || []}
                onRun={() => launchPack(pack.name)}
              />
            ))}
          </div>
        </section>

        {summaries.length > 0 && (
          <section className="mt-10 space-y-6">
            <h2 className="text-lg font-semibold tracking-tight">Reports</h2>
            <AnalysisCards runs={summaries} />
            {summaries.length >= 2 && (
              <Card>
                <CardContent className="p-6">
                  <h3 className="mb-3 text-base font-semibold">Score Trend</h3>
                  <TrendChart runs={summaries} />
                </CardContent>
              </Card>
            )}
            <Card>
              <CardContent className="p-6">
                <h3 className="mb-3 text-base font-semibold">Capability Heatmap</h3>
                <Heatmap runs={summaries} />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-6">
                <h3 className="mb-3 text-base font-semibold">All Runs</h3>
                <RunTable runs={summaries} />
              </CardContent>
            </Card>
          </section>
        )}
      </main>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

function BenchPackCard({
  pack,
  runStates,
  onRun,
}: {
  pack: PackInfo;
  runStates: PackRunState[];
  onRun: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasRunning = runStates.some(
    (r) => r.status === "running" || r.status === "pending"
  );
  const hasCompleted = runStates.some((r) => r.status === "completed");

  return (
    <Card className="group relative flex min-h-[220px] flex-col overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary/60 to-primary/20" />

      <CardContent
        className="flex flex-1 flex-col p-5 cursor-pointer"
        onClick={() => setExpanded((e) => !e)}
      >
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
          {PACK_DESC[pack.name] || `${pack.cases.length} cases`}
        </p>

        <div className="mb-3 flex flex-wrap gap-1">
          {pack.capabilities.slice(0, 3).map((cap) => (
            <Badge key={cap} variant="outline" className="text-[10px]">
              {cap}
            </Badge>
          ))}
          {pack.capabilities.length > 3 && (
            <Badge variant="outline" className="text-[10px]">
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
                        ? `${rs.progress.passed}/${rs.progress.total} passed`
                        : `${rs.progress.completed}/${rs.progress.total}`}
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

        <div className="mt-auto" onClick={(e) => e.stopPropagation()}>
          <Button
            variant={!hasRunning && !hasCompleted ? "default" : "outline"}
            size="sm"
            className="w-full"
            onClick={onRun}
            disabled={hasRunning}
          >
            <PlayCircle className="h-3.5 w-3.5" />
            {hasRunning ? "Running..." : hasCompleted ? "Run Again" : "Run"}
          </Button>
        </div>

        {expanded && (
          <div className="mt-3 border-t pt-3" onClick={(e) => e.stopPropagation()}>
            <h4 className="mb-2 text-xs font-semibold text-muted-foreground">
              Cases ({pack.cases.length})
            </h4>
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {pack.cases.map((c) => (
                <div
                  key={c.id}
                  className="rounded px-2 py-1.5 text-xs hover:bg-muted/50"
                >
                  <div className="font-medium text-foreground">{c.title}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {c.type} · {c.capability.join(", ")}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
