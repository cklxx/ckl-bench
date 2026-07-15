import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DiffData } from "@/lib/types";
import { formatPercent, shortId } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface DiffPageProps {
  diff: DiffData;
}

function statusVariant(
  status: string
): "success" | "destructive" | "muted" | "warning" {
  switch (status) {
    case "improved":
      return "success";
    case "regressed":
      return "destructive";
    case "added":
      return "warning";
    case "removed":
      return "destructive";
    default:
      return "muted";
  }
}

function deltaBadge(delta: number | null) {
  if (delta == null) return <span className="text-muted-foreground">—</span>;
  const pct = Math.round(delta * 1000) / 10;
  const sign = pct > 0 ? "+" : "";
  const color =
    pct > 0 ? "text-success" : pct < 0 ? "text-destructive" : "text-muted-foreground";
  return (
    <span className={`font-semibold font-variant-numeric ${color}`}>
      {sign}{pct.toFixed(1)}%
    </span>
  );
}

export function DiffPage({ diff }: DiffPageProps) {
  const t = useT();
  const d = diff;
  const scoreDelta = Math.round(d.score_delta * 1000) / 10;
  const scoreDeltaColor =
    scoreDelta > 0
      ? "text-success"
      : scoreDelta < 0
      ? "text-destructive"
      : "text-muted-foreground";

  const statusLabel = (status: string): string => {
    switch (status) {
      case "improved":
        return t("diff.improved");
      case "regressed":
        return t("diff.regressed");
      case "added":
        return t("diff.added");
      case "removed":
        return t("diff.removed");
      default:
        return t("diff.unchanged");
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("diff.title")}</h1>
        <p className="text-sm text-muted-foreground">
          <span className="font-variant-numeric">{shortId(d.run_a)}</span>
          {" → "}
          <span className="font-variant-numeric">{shortId(d.run_b)}</span>
        </p>
      </div>

      {/* Score comparison */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("diff.runA")}
              {d.adapter_a && (
                <Badge variant="secondary" className="ml-2">
                  {d.adapter_a}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-variant-numeric">
              {formatPercent(d.score_a)}
            </div>
            <p className="text-xs text-muted-foreground font-variant-numeric">
              {shortId(d.run_a)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("diff.runB")}
              {d.adapter_b && (
                <Badge variant="secondary" className="ml-2">
                  {d.adapter_b}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-variant-numeric">
              {formatPercent(d.score_b)}
            </div>
            <p className="text-xs text-muted-foreground font-variant-numeric">
              {shortId(d.run_b)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("diff.delta")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div
              className={`text-3xl font-bold font-variant-numeric ${scoreDeltaColor}`}
            >
              {scoreDelta > 0 ? "+" : ""}
              {scoreDelta.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              {t("diff.summary", {
                improved: d.counts.improved,
                regressed: d.counts.regressed,
              })}
            </p>
          </CardContent>
        </Card>
      </div>

      <Separator />

      {/* Diff table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t("diff.caseChanges", { count: d.cases.length })}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("diff.case")}</TableHead>
                <TableHead>{t("diff.status")}</TableHead>
                <TableHead className="text-right">{t("diff.scoreA")}</TableHead>
                <TableHead className="text-right">{t("diff.scoreB")}</TableHead>
                <TableHead className="text-right">{t("diff.delta")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.cases.map((c) => (
                <TableRow key={c.case_id}>
                  <TableCell className="font-medium font-variant-numeric">
                    {shortId(c.case_id, 20)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(c.status)}>
                      {statusLabel(c.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-variant-numeric">
                    {c.a_score != null ? formatPercent(c.a_score) : "—"}
                  </TableCell>
                  <TableCell className="text-right font-variant-numeric">
                    {c.b_score != null ? formatPercent(c.b_score) : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {deltaBadge(c.delta)}
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
