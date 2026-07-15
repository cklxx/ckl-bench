import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Result, RunSummary } from "@/lib/types";
import { formatPercent, formatNumber } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface FailureAnalysisProps {
  runs: RunSummary[];
  results?: Result[];
}

export function FailureAnalysis({ runs, results }: FailureAnalysisProps) {
  const t = useT();

  // --- Per-capability failure summary (from runs) ---
  const capFailures = new Map<
    string,
    { failed: number; total: number }
  >();
  for (const r of runs) {
    if (!r.by_capability) continue;
    for (const [cap, bucket] of Object.entries(r.by_capability)) {
      const existing = capFailures.get(cap);
      const failed = bucket.count - bucket.passed;
      if (existing) {
        existing.failed += failed;
        existing.total += bucket.count;
      } else {
        capFailures.set(cap, { failed, total: bucket.count });
      }
    }
  }

  const capRows = Array.from(capFailures.entries())
    .filter(([, v]) => v.failed > 0)
    .map(([cap, v]) => ({
      cap,
      ...v,
      rate: v.total > 0 ? v.failed / v.total : 0,
    }))
    .sort((a, b) => b.rate - a.rate || b.failed - a.failed);

  // --- Results-based analysis ---
  const failedResults = (results ?? []).filter((r) => !r.passed);

  // By check type: count failed checks by kind.
  const checkTypeCounts = new Map<string, number>();
  for (const r of failedResults) {
    if (!r.checks) continue;
    for (const ch of r.checks) {
      if (!ch.passed) {
        checkTypeCounts.set(ch.kind, (checkTypeCounts.get(ch.kind) ?? 0) + 1);
      }
    }
  }
  const checkTypeRows = Array.from(checkTypeCounts.entries())
    .map(([kind, count]) => ({ kind, count }))
    .sort((a, b) => b.count - a.count);

  // By error pattern: group error strings.
  const errorCounts = new Map<string, number>();
  for (const r of failedResults) {
    if (!r.error) continue;
    // Normalize: trim and collapse whitespace.
    const normalized = r.error.trim().replace(/\s+/g, " ");
    errorCounts.set(normalized, (errorCounts.get(normalized) ?? 0) + 1);
  }
  const errorRows = Array.from(errorCounts.entries())
    .map(([pattern, count]) => ({ pattern, count }))
    .sort((a, b) => b.count - a.count);

  // Top failed capabilities.
  const capFailedCounts = new Map<string, number>();
  for (const r of failedResults) {
    if (!r.capability) continue;
    for (const c of r.capability) {
      capFailedCounts.set(c, (capFailedCounts.get(c) ?? 0) + 1);
    }
  }
  const topFailedCaps = Array.from(capFailedCounts.entries())
    .map(([cap, count]) => ({ cap, count }))
    .sort((a, b) => b.count - a.count);

  const hasResults = failedResults.length > 0;

  if (capRows.length === 0 && !hasResults) return null;

  return (
    <div className="space-y-4">
      {capRows.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {t("failure.byCapability")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("capabilityTable.capability")}</TableHead>
                    <TableHead className="text-right">
                      {t("failure.failed")}
                    </TableHead>
                    <TableHead className="text-right">
                      {t("failure.total")}
                    </TableHead>
                    <TableHead className="text-right">
                      {t("failure.failureRate")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {capRows.map((row) => (
                    <TableRow key={row.cap}>
                      <TableCell className="font-medium capitalize">
                        {row.cap}
                      </TableCell>
                      <TableCell className="text-right font-variant-numeric">
                        {formatNumber(row.failed)}
                      </TableCell>
                      <TableCell className="text-right font-variant-numeric">
                        {formatNumber(row.total)}
                      </TableCell>
                      <TableCell className="text-right font-variant-numeric">
                        <Badge variant="destructive">
                          {formatPercent(row.rate)}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {hasResults && (
        <>
          {topFailedCaps.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t("failure.topFailed")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {topFailedCaps.map((c) => (
                    <Badge key={c.cap} variant="destructive" className="text-xs">
                      {c.cap} ({formatNumber(c.count)})
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {checkTypeRows.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t("failure.byCheckType")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("failure.checkKind")}</TableHead>
                        <TableHead className="text-right">
                          {t("failure.count")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {checkTypeRows.map((row) => (
                        <TableRow key={row.kind}>
                          <TableCell className="font-medium">
                            {row.kind}
                          </TableCell>
                          <TableCell className="text-right font-variant-numeric">
                            {formatNumber(row.count)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}

          {errorRows.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t("failure.byError")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("failure.errorPattern")}</TableHead>
                        <TableHead className="text-right">
                          {t("failure.count")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {errorRows.map((row) => (
                        <TableRow key={row.pattern}>
                          <TableCell className="text-sm break-words max-w-md">
                            {row.pattern}
                          </TableCell>
                          <TableCell className="text-right font-variant-numeric">
                            {formatNumber(row.count)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
