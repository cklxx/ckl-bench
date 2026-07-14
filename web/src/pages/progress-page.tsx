import { useEffect, useState } from "react";
import { getRun, getRunProgress, ProgressSocket } from "@/lib/api";
import type { RunInfo, CaseProgress } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface ProgressPageProps {
  runId: string;
}

function statusColor(status: string): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "completed":
    case "passed":
      return "default";
    case "running":
    case "pending":
      return "secondary";
    case "failed":
    case "cancelled":
      return "destructive";
    default:
      return "outline";
  }
}

export function ProgressPage({ runId }: ProgressPageProps) {
  const [run, setRun] = useState<RunInfo | null>(null);
  const [error, setError] = useState("");
  const [wsConnected, setWsConnected] = useState(false);

  const refresh = () => {
    if (!runId) return;
    getRun(runId).then(setRun).catch((e) => setError(String(e)));
    getRunProgress(runId).then(setRun).catch(() => {});
  };

  useEffect(() => {
    refresh();
  }, [runId]);

  // WebSocket for live updates.
  useEffect(() => {
    if (!runId) return;
    const socket = new ProgressSocket(run?.progress ? undefined : undefined);
    // ponytail: ws_port comes from config; fallback to polling if WS fails.
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
  const cases = progress.cases || {};
  const totalCases = progress.total_cases || Object.keys(cases).length;
  const completedCases = Object.values(cases).filter((c) => c.status === "completed" || c.status === "failed").length;
  const pct = totalCases > 0 ? Math.round((completedCases / totalCases) * 100) : 0;

  return (
    <div className="space-y-4">
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
          <Badge variant={statusColor(run.status)}>{run.status}</Badge>
          <Button variant="ghost" size="icon" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {run.error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {run.error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Overall Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span>{completedCases} / {totalCases} cases</span>
              <span className="font-medium">{pct}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cases</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Object.entries(cases).map(([caseId, cp]) => (
              <CaseRow key={caseId} caseId={caseId} cp={cp} />
            ))}
            {Object.keys(cases).length === 0 && (
              <p className="text-sm text-muted-foreground">No cases started yet.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CaseRow({ caseId, cp }: { caseId: string; cp: CaseProgress }) {
  return (
    <div className="flex items-center justify-between rounded-md border px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs">{caseId}</span>
        <Badge variant="outline" className="text-[10px]">
          attempt {cp.attempt}
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        {cp.score != null && (
          <span className="text-sm font-medium tabular-nums">{cp.score.toFixed(2)}</span>
        )}
        <Badge variant={statusColor(cp.status)}>{cp.status}</Badge>
      </div>
    </div>
  );
}
