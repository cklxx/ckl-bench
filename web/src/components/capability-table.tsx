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
import { formatPercent, formatNumber, scoreVariant } from "@/lib/utils";
import { useT } from "@/lib/i18n";

export function CapabilityTable({ summary }: { summary: RunSummary }) {
  const t = useT();
  const caps = summary.by_capability;
  if (!caps) return null;

  const entries = Object.entries(caps).sort((a, b) => b[1].score - a[1].score);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("capabilityTable.capability")}</TableHead>
          <TableHead className="text-right">{t("capabilityTable.score")}</TableHead>
          <TableHead className="text-right">{t("capabilityTable.passed")}</TableHead>
          <TableHead className="text-right">{t("capabilityTable.total")}</TableHead>
          <TableHead className="text-right">{t("capabilityTable.passRate")}</TableHead>
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
