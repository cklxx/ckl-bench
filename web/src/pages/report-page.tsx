import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScoreCard } from "@/components/score-card";
import { CapabilityTable } from "@/components/capability-table";
import { DifficultyTable } from "@/components/difficulty-table";
import { CaseTable } from "@/components/case-table";
import type { RunSummary, Result } from "@/lib/types";
import { formatCost, formatNumber, shortId } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface ReportPageProps {
  summary: RunSummary;
  results?: Result[];
}

export function ReportPage({ summary, results }: ReportPageProps) {
  const t = useT();
  const s = summary;
  const totalTokens = s.usage?.total_tokens ?? 0;
  const cost = s.cost_usd ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("report.title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("report.run")}{" "}
            <span className="font-variant-numeric">{shortId(s.run_id)}</span>{" "}
            &middot; {s.adapter}
            {s.judge && ` · judge: ${s.judge}`}
            {s.reviewer && ` · reviewer: ${s.reviewer}`}
            {s.verifier && ` · verifier: ${s.verifier}`}
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant="secondary">
            {t("report.passed", { passed: s.passed, total: s.total })}
          </Badge>
          {s.repeat != null && s.repeat > 1 && (
            <Badge variant="outline">{t("report.repeat", { repeat: s.repeat })}</Badge>
          )}
        </div>
      </div>

      {/* Score cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <ScoreCard
          title={t("report.score")}
          value={s.score}
          ci={s.score_ci}
          variant={s.score != null ? (s.score >= 0.8 ? "success" : s.score >= 0.5 ? "warning" : "destructive") : "default"}
        />
        <ScoreCard
          title={t("report.passRate")}
          value={s.pass_rate}
          ci={s.pass_rate_ci}
          description={`${s.passed} of ${s.total} cases`}
        />
        {s.pass_at_1 != null && (
          <ScoreCard title={t("report.passAt1")} value={s.pass_at_1} />
        )}
        {s.pass_at_k != null && (
          <ScoreCard
            title={t("report.passAtK", { k: s.repeat ?? "k" })}
            value={s.pass_at_k}
          />
        )}
      </div>

      {/* Usage */}
      {(totalTokens > 0 || cost > 0) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t("report.usage")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {totalTokens > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">{t("report.totalTokens")}</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatNumber(totalTokens)}
                  </p>
                </div>
              )}
              {s.usage?.input_tokens != null && (
                <div>
                  <p className="text-xs text-muted-foreground">{t("report.inputTokens")}</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatNumber(s.usage.input_tokens)}
                  </p>
                </div>
              )}
              {s.usage?.output_tokens != null && (
                <div>
                  <p className="text-xs text-muted-foreground">{t("report.outputTokens")}</p>
                  <p className="text-lg font-bold font-variant-numeric">
                    {formatNumber(s.usage.output_tokens)}
                  </p>
                </div>
              )}
              {cost > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">{t("report.cost")}</p>
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
            <CardTitle className="text-base">{t("report.capabilities")}</CardTitle>
          </CardHeader>
          <CardContent>
            <CapabilityTable summary={s} />
          </CardContent>
        </Card>
      )}

      {/* Difficulty breakdown */}
      {s.by_difficulty && Object.keys(s.by_difficulty).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("report.difficulty")}</CardTitle>
          </CardHeader>
          <CardContent>
            <DifficultyTable summary={s} />
          </CardContent>
        </Card>
      )}

      <Separator />

      {/* Results */}
      {results && results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {t("report.cases", { count: results.length })}
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
