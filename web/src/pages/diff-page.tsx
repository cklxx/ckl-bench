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

function statusLabel(status: string): string {
  switch (status) {
    case "improved":
      return "↑ Improved";
    case "regressed":
      return "↓ Regressed";
    case "added":
      return "+ Added";
    case "removed":
      return "− Removed";
    default:
      return "→ Unchanged";
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
  const d = diff;
  const scoreDelta = Math.round(d.score_delta * 1000) / 10;
  const scoreDeltaColor =
    scoreDelta > 0
      ? "text-success"
      : scoreDelta < 0
      ? "text-destructive"
      : "text-muted-foreground";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Run Diff</h1>
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
              Run A
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
              Run B
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
              Delta
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
              {d.counts.improved} improved, {d.counts.regressed} regressed
            </p>
          </CardContent>
        </Card>
      </div>

      <Separator />

      {/* Diff table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Case Changes ({d.cases.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Case</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Score A</TableHead>
                <TableHead className="text-right">Score B</TableHead>
                <TableHead className="text-right">Delta</TableHead>
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
