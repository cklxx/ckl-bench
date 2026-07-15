import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { RunTable } from "@/components/run-table";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { AnalysisCards } from "@/components/analysis-cards";
import type { RunSummary } from "@/lib/types";
import { useT } from "@/lib/i18n";

interface DashboardPageProps {
  runs: RunSummary[];
}

export function DashboardPage({ runs }: DashboardPageProps) {
  const t = useT();
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("dashboard.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("dashboard.collected", {
            count: runs.length,
            plural: runs.length !== 1 ? "s" : "",
          })}
        </p>
      </div>

      {/* Auto analysis */}
      {runs.length > 0 && <AnalysisCards runs={runs} />}

      {/* Trend chart */}
      {runs.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.scoreTrend")}</CardTitle>
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
            <CardTitle className="text-base">{t("dashboard.heatmap")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Heatmap runs={runs} />
          </CardContent>
        </Card>
      )}

      {/* Runs table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("dashboard.allRuns")}</CardTitle>
        </CardHeader>
        <CardContent>
          <RunTable runs={runs} />
        </CardContent>
      </Card>
    </div>
  );
}
