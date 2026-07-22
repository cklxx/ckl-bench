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
import { formatPercent, formatNumber, scoreVariant, difficultyVariant } from "@/lib/utils";
import { useT } from "@/lib/i18n";

const DIFFICULTY_ORDER = ["frontier", "extreme", "hard", "medium", "unspecified"];

export function DifficultyTable({ summary }: { summary: RunSummary }) {
  const t = useT();
  const diffs = summary.by_difficulty;
  if (!diffs) return null;

  const entries = Object.entries(diffs).sort(
    (a, b) => DIFFICULTY_ORDER.indexOf(a[0]) - DIFFICULTY_ORDER.indexOf(b[0])
  );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("difficultyTable.difficulty")}</TableHead>
          <TableHead className="text-right">{t("difficultyTable.score")}</TableHead>
          <TableHead className="text-right">{t("difficultyTable.passed")}</TableHead>
          <TableHead className="text-right">{t("difficultyTable.total")}</TableHead>
          <TableHead className="text-right">{t("difficultyTable.passRate")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map(([name, bucket]) => (
          <TableRow key={name}>
            <TableCell className="font-medium">
              <Badge variant={difficultyVariant(name)}>{name}</Badge>
            </TableCell>
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
              {formatPercent(bucket.count > 0 ? bucket.passed / bucket.count : null)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
