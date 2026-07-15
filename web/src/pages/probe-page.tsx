import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScoreCard } from "@/components/score-card";
import type { RunSummary, ProbeRow } from "@/lib/types";
import { formatPercent } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface ProbePageProps {
  summary?: RunSummary;
  rows: ProbeRow[];
}

function statusVariant(
  status: ProbeRow["status"]
): "success" | "destructive" | "muted" {
  if (status === "pass") return "success";
  if (status === "fail") return "destructive";
  return "muted";
}

export function ProbePage({ summary, rows }: ProbePageProps) {
  const t = useT();
  const passCount = rows.filter((r) => r.status === "pass").length;
  const failCount = rows.filter((r) => r.status === "fail").length;
  const skipCount = rows.filter((r) => r.status === "skip").length;

  const statusLabel = (status: ProbeRow["status"]): string => {
    if (status === "pass") return t("probe.pass");
    if (status === "fail") return t("probe.fail");
    return t("probe.skip");
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("probe.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {summary
            ? `${t("report.run")} ${summary.run_id.slice(0, 16)} &middot; ${summary.adapter}`
            : t("probe.summary", {
                count: rows.length,
                plural: rows.length !== 1 ? "s" : "",
              })}
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <ScoreCard
          title={t("probe.passed")}
          value={passCount / Math.max(rows.length, 1)}
          description={t("probe.passedDesc", { count: passCount, total: rows.length })}
          variant="success"
        />
        <ScoreCard
          title={t("probe.failed")}
          value={failCount / Math.max(rows.length, 1)}
          description={t("probe.failedDesc", { count: failCount, total: rows.length })}
          variant="destructive"
        />
        <ScoreCard
          title={t("probe.skipped")}
          value={skipCount / Math.max(rows.length, 1)}
          description={t("probe.skippedDesc", { count: skipCount, total: rows.length })}
        />
      </div>

      {/* Probe table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("probe.results")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("probe.target")}</TableHead>
                <TableHead>{t("probe.kind")}</TableHead>
                <TableHead>{t("probe.status")}</TableHead>
                <TableHead className="text-right">{t("probe.score")}</TableHead>
                <TableHead>{t("probe.detail")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, i) => (
                <TableRow key={`${row.target}-${i}`}>
                  <TableCell className="font-medium">{row.target}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{row.kind}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(row.status)}>
                      {statusLabel(row.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-variant-numeric">
                    {row.score != null ? formatPercent(row.score) : "—"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {row.detail}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
