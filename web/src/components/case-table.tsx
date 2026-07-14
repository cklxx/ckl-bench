import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { Result } from "@/lib/types";
import { formatPercent, formatCost, shortId } from "@/lib/utils";

function scoreVariant(score: number): "success" | "warning" | "destructive" {
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "destructive";
}

interface CaseTableProps {
  results: Result[];
}

export function CaseTable({ results }: CaseTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Case</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Score</TableHead>
          <TableHead>Capabilities</TableHead>
          <TableHead className="text-right">Cost</TableHead>
          <TableHead className="text-right">Tokens</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {results.map((r, i) => (
          <TableRow key={`${r.case_id}-${i}`}>
            <TableCell className="font-medium font-variant-numeric">
              {shortId(r.case_id, 20)}
            </TableCell>
            <TableCell>
              <Badge variant={r.passed ? "success" : "destructive"}>
                {r.passed ? "PASS" : "FAIL"}
              </Badge>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              <Badge variant={scoreVariant(r.score)}>
                {formatPercent(r.score)}
              </Badge>
            </TableCell>
            <TableCell>
              <div className="flex flex-wrap gap-1">
                {r.capability?.map((c) => (
                  <Badge key={c} variant="muted" className="text-[10px]">
                    {c}
                  </Badge>
                ))}
              </div>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {r.cost_usd != null ? formatCost(r.cost_usd) : "—"}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {r.usage?.total_tokens != null
                ? r.usage.total_tokens.toLocaleString("en-US")
                : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
