import { useEffect, useState } from "react";
import { getRun, getRunProgress, listCases, ProgressSocket } from "@/lib/api";
import type { RunInfo, CaseProgress, CaseListItem } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface ProgressPageProps {
  runId: string;
}

function statusBadge(status: string): { variant: "default" | "secondary" | "destructive" | "outline"; label: string } {
  switch (status) {
    case "completed":
    case "passed":
      return { variant: "default", label: status };
    case "running":
    case "pending":
      return { variant: "secondary", label: status };
    case "failed":
    case "cancelled":
      return { variant: "destructive", label: status };
    default:
      return { variant: "outline", label: status };
  }
}

export function ProgressPage({ runId }: ProgressPageProps) {
  const [run, setRun] = useState<RunInfo | null>(null);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [error, setError] = useState("");
  const [wsConnected, setWsConnected] = useState(false);

  const refresh = () => {
    if (!runId) return;
    getRun(runId).then(setRun).catch((e) => setError(String(e)));
    getRunProgress(runId).then(setRun).catch(() => {});
  };

  useEffect(() => {
    refresh();
    listCases().then(setCases).catch(() => {});
  }, [runId]);

  // WebSocket for live updates.
  useEffect(() => {
    if (!runId) return;
    const socket = new ProgressSocket(run?.progress ? undefined : undefined);
    socket.on((event: any) => {
      if (event.run_id !== runId) return;
      setRun((prev) => {
        if (!prev) return prev;
        const progress = { ...(prev.progress || {}) };
        if (event.type === "case_started") {
          progress.cases = { ...(progress.cases || {}), [event.case_id]: { status: "running", attempt: event.attempt || 1 } };
        } else if (event.type === "case_completed") {
          progress.cases = { ...(progress.cases || {}), [event.case_id]: { status: event.error ? "failed" : "completed", attempt: event.attempt || 1, score: event.score ?? null, passed: event.passed ?? null, error: event.error || null } };
        } else if (event.type === "run_completed") {
          return { ...prev, status: "completed", progress };
        } else if (event.type === "run_failed") {
          return { ...prev, status: "failed", progress, error: event.error };
        }
        return { ...prev, progress };
      });
    });
    socket.connect();
    const timer = setInterval(() => setWsConnected(socket.connected), 1000);
    // Polling fallback every 2s.
    const poll = setInterval(() => {
      if (!socket.connected) refresh();
    }, 2000);
    return () => {
      socket.disconnect();
      clearInterval(timer);
      clearInterval(poll);
    };
  }, [runId]);

  if (!run) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">Run Progress</h1>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <p className="text-sm text-muted-foreground">Loading run {runId}...</p>
      </div>
    );
  }

  const progress = run.progress || { total_cases: 0, cases: {} };
  const progCases = progress.cases || {};
  const totalCases = progress.total_cases || Object.keys(progCases).length;
  const completedCases = Object.values(progCases).filter((c) => c.status === "completed" || c.status === "failed").length;
  const passedCases = Object.values(progCases).filter((c) => c.status === "completed" && c.passed !== false).length;
  const pct = totalCases > 0 ? Math.round((completedCases / totalCases) * 100) : 0;

  // Build case_id → capability map.
  const capMap = new Map<string, string[]>();
  for (const c of cases) {
    capMap.set(c.id, c.capability || []);
  }

  // Group progress by capability.
  const byCapability = new Map<string, { total: number; completed: number; passed: number; failed: number; running: number; cases: Array<{ id: string; cp: CaseProgress }> }>();
  for (const [caseId, cp] of Object.entries(progCases)) {
    const caps = capMap.get(caseId) || [];
    const keys = caps.length > 0 ? caps : ["uncategorized"];
    for (const cap of keys) {
      if (!byCapability.has(cap)) {
        byCapability.set(cap, { total: 0, completed: 0, passed: 0, failed: 0, running: 0, cases: [] });
      }
      const bucket = byCapability.get(cap)!;
      bucket.total++;
      bucket.cases.push({ id: caseId, cp });
      if (cp.status === "completed") {
        bucket.completed++;
        if (cp.passed !== false) bucket.passed++;
      } else if (cp.status === "failed") {
        bucket.failed++;
        bucket.completed++;
      } else if (cp.status === "running") {
        bucket.running++;
      }
    }
  }

  const sb = statusBadge(run.status);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Run Progress</h1>
          <p className="text-sm text-muted-foreground">
            {run.run_id} &middot; {run.summary?.adapter || "unknown adapter"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={wsConnected ? "default" : "secondary"}>
            {wsConnected ? "Live" : "Polling"}
          </Badge>
          <Badge variant={sb.variant}>{sb.label}</Badge>
          <Button variant="ghost" size="icon" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {run.error && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {run.error}
        </div>
      )}

      {/* Overall progress card */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-3 flex items-center justify-between text-sm">
            <span className="font-medium">Overall</span>
            <span className="tabular-nums text-muted-foreground">
              {completedCases}/{totalCases} cases &middot; {passedCases} passed &middot; {pct}%
            </span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Category cards */}
      {byCapability.size > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">By Capability</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from(byCapability.entries())
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([cap, data]) => {
                const capPct = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;
                return (
                  <Card key={cap}>
                    <CardContent className="p-4">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-sm font-semibold capitalize">{cap}</span>
                        <Badge variant="secondary" className="text-[10px]">
                          {data.passed}/{data.total} passed
                        </Badge>
                      </div>
                      <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-success transition-all duration-300"
                          style={{ width: `${capPct}%` }}
                        />
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                        <span className="text-success">✓ {data.passed}</span>
                        {data.failed > 0 && <span className="text-destructive">✗ {data.failed}</span>}
                        {data.running > 0 && <span className="text-warning">… {data.running}</span>}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
          </div>
        </div>
      )}

      {/* Case list */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Cases</h2>
        {Object.entries(progCases).map(([caseId, cp]) => (
          <CaseRow key={caseId} caseId={caseId} cp={cp} />
        ))}
        {Object.keys(progCases).length === 0 && (
          <p className="text-sm text-muted-foreground">No cases started yet.</p>
        )}
      </div>
    </div>
  );
}

function CaseRow({ caseId, cp }: { caseId: string; cp: CaseProgress }) {
  const sb = statusBadge(cp.status);
  const title = caseId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return (
    <div className="flex items-center justify-between rounded-lg bg-background px-4 py-3 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{title}</span>
        <Badge variant="outline" className="text-[10px]">
          attempt {cp.attempt}
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        {cp.score != null && (
          <span className="text-sm font-medium tabular-nums">{cp.score.toFixed(2)}</span>
        )}
        <Badge variant={sb.variant}>{sb.label}</Badge>
      </div>
    </div>
  );
}
