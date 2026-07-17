import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { RunSummary } from "@/lib/types";
import {
  formatPercent,
  formatNumber,
  scoreVariant,
  formatScorePerDollar,
  formatScorePerMTokens,
} from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface ComparisonTableProps {
  runs: RunSummary[];
}

export function ComparisonTable({ runs }: ComparisonTableProps) {
  const t = useT();

  // Collect all capabilities across all runs, sorted.
  const capSet = new Set<string>();
  for (const r of runs) {
    if (r.by_capability) {
      for (const k of Object.keys(r.by_capability)) capSet.add(k);
    }
  }
  const caps = Array.from(capSet).sort();
  if (caps.length === 0) return null;

  // Per-capability best score (for highlighting).
  const bestByCap = new Map<string, number>();
  for (const cap of caps) {
    let best = -1;
    for (const r of runs) {
      const s = r.by_capability?.[cap]?.score ?? -1;
      if (s > best) best = s;
    }
    bestByCap.set(cap, best);
  }

  // Cost-effectiveness data.
  const hasCostData = runs.some(
    (r) => (r.cost_usd != null && r.cost_usd > 0) || (r.usage?.total_tokens != null && r.usage.total_tokens > 0)
  );

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sticky left-0 bg-background">
                {t("comparison.score")}
              </TableHead>
              {runs.map((r) => (
                <TableHead key={r.run_id} className="text-right">
                  {r.adapter_display || r.adapter}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {caps.map((cap) => {
              const best = bestByCap.get(cap) ?? -1;
              return (
                <TableRow key={cap}>
                  <TableCell className="sticky left-0 bg-background font-medium capitalize">
                    {cap}
                  </TableCell>
                  {runs.map((r) => {
                    const bucket = r.by_capability?.[cap];
                    const score = bucket?.score ?? 0;
                    const isBest = bucket != null && score === best && best >= 0;
                    const ci = bucket?.pass_rate_ci;
                    const detail = bucket
                      ? `${formatNumber(bucket.passed)}/${formatNumber(bucket.count)}${ci ? ` [${formatPercent(ci[0], 0)}, ${formatPercent(ci[1], 0)}]` : ""}`
                      : undefined;
                    return (
                      <TableCell
                        key={r.run_id}
                        className="text-right font-variant-numeric"
                        title={detail}
                      >
                        <div className="flex items-center justify-end gap-1.5">
                          {isBest && (
                            <span className="text-success text-xs">★</span>
                          )}
                          <Badge variant={scoreVariant(score)}>
                            {formatPercent(score)}
                          </Badge>
                        </div>
                      </TableCell>
                    );
                  })}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {hasCostData && (
        <div className="space-y-2">
          <h3 className="text-base font-semibold">
            {t("comparison.costEffectiveness")}
          </h3>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("comparison.score")}</TableHead>
                  {runs.map((r) => (
                    <TableHead key={r.run_id} className="text-right">
                      {r.adapter_display || r.adapter}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">
                    {t("comparison.scorePerDollar")}
                  </TableCell>
                  {runs.map((r) => (
                    <TableCell
                      key={r.run_id}
                      className="text-right font-variant-numeric"
                    >
                      {formatScorePerDollar(r.score, r.cost_usd)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">
                    {t("comparison.scorePerMTokens")}
                  </TableCell>
                  {runs.map((r) => (
                    <TableCell
                      key={r.run_id}
                      className="text-right font-variant-numeric"
                    >
                      {formatScorePerMTokens(r.score, r.usage?.total_tokens)}
                    </TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
}
