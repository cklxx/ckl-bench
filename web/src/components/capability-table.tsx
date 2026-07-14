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
import { formatPercent, formatNumber } from "@/lib/utils";

function scoreVariant(score: number): "success" | "warning" | "destructive" {
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "destructive";
}

export function CapabilityTable({ summary }: { summary: RunSummary }) {
  const caps = summary.by_capability;
  if (!caps) return null;

  const entries = Object.entries(caps).sort((a, b) => b[1].score - a[1].score);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Capability</TableHead>
          <TableHead className="text-right">Score</TableHead>
          <TableHead className="text-right">Passed</TableHead>
          <TableHead className="text-right">Total</TableHead>
          <TableHead className="text-right">Pass Rate</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map(([name, bucket]) => (
          <TableRow key={name}>
            <TableCell className="font-medium capitalize">{name}</TableCell>
            <TableCell className="text-right font-variant-numeric">
              <Badge variant={scoreVariant(bucket.score)}>
                {formatPercent(bucket.score)}
              </Badge>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatNumber(bucket.passed)}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatNumber(bucket.count)}
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatPercent(bucket.passed / bucket.count)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
