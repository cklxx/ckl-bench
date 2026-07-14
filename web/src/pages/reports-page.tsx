import { useEffect, useState } from "react";
import { listRuns } from "@/lib/api";
import type { RunInfo } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AnalysisCards } from "@/components/analysis-cards";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { RunTable } from "@/components/run-table";
import { RefreshCw } from "lucide-react";

export function ReportsPage() {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [error, setError] = useState("");

  const refresh = () => {
    listRuns().then(setRuns).catch((e) => setError(String(e)));
  };

  useEffect(() => {
    refresh();
  }, []);

  const summaries = runs.map((r) => r.summary).filter((s): s is NonNullable<typeof s> => s != null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Reports</h1>
          <p className="text-sm text-muted-foreground">
            {runs.length} run{runs.length !== 1 ? "s" : ""} collected
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={refresh}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {summaries.length > 0 && <AnalysisCards runs={summaries} />}

      {summaries.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Score Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart runs={summaries} />
          </CardContent>
        </Card>
      )}

      {summaries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Capability Heatmap</CardTitle>
          </CardHeader>
          <CardContent>
            <Heatmap runs={summaries} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {summaries.length > 0 ? (
            <RunTable runs={summaries} />
          ) : (
            <p className="text-sm text-muted-foreground">
              No runs yet. Launch a run from the Launch page.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
