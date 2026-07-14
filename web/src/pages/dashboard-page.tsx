import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { RunTable } from "@/components/run-table";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { AnalysisCards } from "@/components/analysis-cards";
import type { RunSummary } from "@/lib/types";

interface DashboardPageProps {
  runs: RunSummary[];
}

export function DashboardPage({ runs }: DashboardPageProps) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          {runs.length} run{runs.length !== 1 ? "s" : ""} collected
        </p>
      </div>

      {/* Auto analysis */}
      {runs.length > 0 && <AnalysisCards runs={runs} />}

      {/* Trend chart */}
      {runs.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Score Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart runs={runs} />
          </CardContent>
        </Card>
      )}

      <Separator />

      {/* Heatmap */}
      {runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Capability Heatmap</CardTitle>
          </CardHeader>
          <CardContent>
            <Heatmap runs={runs} />
          </CardContent>
        </Card>
      )}

      {/* Runs table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Runs</CardTitle>
        </CardHeader>
        <CardContent>
          <RunTable runs={runs} />
        </CardContent>
      </Card>
    </div>
  );
}
