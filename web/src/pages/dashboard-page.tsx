import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { RunTable } from "@/components/run-table";
import { TrendChart } from "@/components/trend-chart";
import { Heatmap } from "@/components/heatmap";
import { AnalysisCards } from "@/components/analysis-cards";
import { ComparisonTable } from "@/components/comparison-table";
import { FailureAnalysis } from "@/components/failure-analysis";
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

      {/* Heatmap — primary capability×run view */}
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

      {/* Adapter comparison — collapsible */}
      {runs.length >= 2 && (
        <Card>
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-2">
              <CardHeader className="flex-1 py-4">
                <CardTitle className="flex items-center gap-2 text-base">
                  <span className="text-xs transition-transform group-open:rotate-90">
                    ▶
                  </span>
                  {t("comparison.title")}
                </CardTitle>
              </CardHeader>
            </summary>
            <CardContent>
              <ComparisonTable runs={runs} />
            </CardContent>
          </details>
        </Card>
      )}

      {/* Failure analysis */}
      {runs.length >= 2 && <FailureAnalysis runs={runs} />}

      {/* Trend chart — only meaningful with ≥3 runs */}
      {runs.length >= 3 && (
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
