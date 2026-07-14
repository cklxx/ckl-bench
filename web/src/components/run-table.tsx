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
import { formatPercent, formatCost, formatNumber, shortId } from "@/lib/utils";

function scoreVariant(score: number): "success" | "warning" | "destructive" {
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "destructive";
}

interface RunTableProps {
  runs: RunSummary[];
}

export function RunTable({ runs }: RunTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Run ID</TableHead>
          <TableHead>Adapter</TableHead>
          <TableHead className="text-right">Score</TableHead>
          <TableHead className="text-right">Passed</TableHead>
          <TableHead className="text-right">Total</TableHead>
          <TableHead className="text-right">Pass Rate</TableHead>
          <TableHead className="text-right">Cost</TableHead>
          <TableHead className="text-right">Tokens</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((r) => (
          <TableRow key={r.run_id}>
            <TableCell className="font-medium font-variant-numeric">
              {shortId(r.run_id)}
            </TableCell>
            <TableCell>
              <Badge variant="secondary">{r.adapter}</Badge>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              <Badge variant={scoreVariant(r.score)}>
                {formatPercent(r.score)}
              </Badge>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatNumber(r.passed)}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatNumber(r.total)}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatPercent(r.pass_rate)}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {r.cost_usd != null ? formatCost(r.cost_usd) : "—"}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {r.usage?.total_tokens != null
                ? formatNumber(r.usage.total_tokens)
                : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
