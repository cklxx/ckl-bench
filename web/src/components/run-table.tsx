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
import { formatPercent, formatCost, formatNumber, shortId, scoreVariant } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface RunTableProps {
  runs: RunSummary[];
  onSelectRun?: (runId: string) => void;
}

export function RunTable({ runs, onSelectRun }: RunTableProps) {
  const t = useT();
  const hasCost = runs.some((r) => r.cost_usd != null && r.cost_usd > 0);
  const hasTokens = runs.some(
    (r) => r.usage?.total_tokens != null && r.usage.total_tokens > 0
  );
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("runTable.runId")}</TableHead>
          <TableHead>{t("runTable.adapter")}</TableHead>
          <TableHead className="text-right">{t("runTable.score")}</TableHead>
          <TableHead className="text-right">{t("runTable.passRate")}</TableHead>
          {hasCost && (
            <TableHead className="text-right">{t("runTable.cost")}</TableHead>
          )}
          {hasTokens && (
            <TableHead className="text-right">{t("runTable.tokens")}</TableHead>
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((r) => (
          <TableRow
            key={r.run_id}
            className={onSelectRun ? "cursor-pointer" : ""}
            onClick={onSelectRun ? () => onSelectRun(r.run_id) : undefined}
          >
            <TableCell className="font-medium font-variant-numeric">
              {shortId(r.run_id)}
            </TableCell>
            <TableCell>
              <Badge variant="secondary">{r.adapter_display || r.adapter}</Badge>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              <Badge variant={r.score != null ? scoreVariant(r.score) : "outline"}>
                {formatPercent(r.score)}
              </Badge>
            </TableCell>
            <TableCell className="text-right font-variant-numeric">
              {formatPercent(r.pass_rate)}
              <div className="text-[10px] text-muted-foreground">
                {formatNumber(r.passed)}/{formatNumber(r.total)}
                {r.errored ? (
                  <span className="text-amber-600"> +{r.errored}e</span>
                ) : null}
              </div>
            </TableCell>
            {hasCost && (
              <TableCell className="text-right font-variant-numeric">
                {r.cost_usd != null && r.cost_usd > 0
                  ? formatCost(r.cost_usd)
                  : "—"}
              </TableCell>
            )}
            {hasTokens && (
              <TableCell className="text-right font-variant-numeric">
                {r.usage?.total_tokens != null && r.usage.total_tokens > 0
                  ? formatNumber(r.usage.total_tokens)
                  : "—"}
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
