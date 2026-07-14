import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScoreCard } from "@/components/score-card";
import { CapabilityTable } from "@/components/capability-table";
import { CaseTable } from "@/components/case-table";
import type { RunSummary, Result } from "@/lib/types";
import { formatCost, formatNumber, shortId } from "@/lib/utils";

interface ReportPageProps {
  summary: RunSummary;
  results?: Result[];
}

export function ReportPage({ summary, results }: ReportPageProps) {
  const s = summary;
  const totalTokens = s.usage?.total_tokens ?? 0;
  const cost = s.cost_usd ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Evaluation Report
          </h1>
          <p className="text-sm text-muted-foreground">
            Run <span className="font-variant-numeric">{shortId(s.run_id)}</span>{" "}
            &middot; {s.adapter}
            {s.judge && ` &middot; judge: ${s.judge}`}
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant="secondary">
            {s.passed}/{s.total} passed
          </Badge>
          {s.repeat != null && s.repeat > 1 && (
            <Badge variant="outline">repeat={s.repeat}</Badge>
          )}
        </div>
      </div>

      {/* Score cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <ScoreCard
          title="Score"
          value={s.score}
          ci={s.score_ci}
          variant={s.score >= 0.8 ? "success" : s.score >= 0.5 ? "warning" : "destructive"}
        />
        <ScoreCard
          title="Pass Rate"
          value={s.pass_rate}
          ci={s.pass_rate_ci}
          description={`${s.passed} of ${s.total} cases`}
        />
        {s.pass_at_1 != null && (
          <ScoreCard title="Pass@1" value={s.pass_at_1} />
        )}
        {s.pass_at_k != null && (
          <ScoreCard
            title={`Pass@${s.repeat ?? "k"}`}
            value={s.pass_at_k}
          />
        )}
      </div>

      {/* Usage */}
      {(totalTokens > 0 || cost > 0) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {totalTokens > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Total Tokens</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatNumber(totalTokens)}
                  </p>
                </div>
              )}
              {s.usage?.input_tokens != null && (
                <div>
                  <p className="text-xs text-muted-foreground">Input Tokens</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatNumber(s.usage.input_tokens)}
                  </p>
                </div>
              )}
              {s.usage?.output_tokens != null && (
                <div>
                  <p className="text-xs text-muted-foreground">Output Tokens</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatNumber(s.usage.output_tokens)}
                  </p>
                </div>
              )}
              {cost > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Cost</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatCost(cost)}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Capabilities */}
      {s.by_capability && Object.keys(s.by_capability).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Capabilities</CardTitle>
          </CardHeader>
          <CardContent>
            <CapabilityTable summary={s} />
          </CardContent>
        </Card>
      )}

      <Separator />

      {/* Results */}
      {results && results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Cases ({results.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CaseTable results={results} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
