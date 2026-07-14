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

function statusLabel(status: ProbeRow["status"]): string {
  if (status === "pass") return "PASS";
  if (status === "fail") return "FAIL";
  return "SKIP";
}

export function ProbePage({ summary, rows }: ProbePageProps) {
  const passCount = rows.filter((r) => r.status === "pass").length;
  const failCount = rows.filter((r) => r.status === "fail").length;
  const skipCount = rows.filter((r) => r.status === "skip").length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Probe Report</h1>
        <p className="text-sm text-muted-foreground">
          {summary
            ? `Run ${summary.run_id.slice(0, 16)} &middot; ${summary.adapter}`
            : `${rows.length} probe${rows.length !== 1 ? "s" : ""}`}
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <ScoreCard
          title="Passed"
          value={passCount / Math.max(rows.length, 1)}
          description={`${passCount} of ${rows.length} probes`}
          variant="success"
        />
        <ScoreCard
          title="Failed"
          value={failCount / Math.max(rows.length, 1)}
          description={`${failCount} of ${rows.length} probes`}
          variant="destructive"
        />
        <ScoreCard
          title="Skipped"
          value={skipCount / Math.max(rows.length, 1)}
          description={`${skipCount} of ${rows.length} probes`}
        />
      </div>

      {/* Probe table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Probe Results</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Target</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead>Detail</TableHead>
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
