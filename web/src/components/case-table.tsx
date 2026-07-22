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
import { formatPercent, formatCost, shortId, scoreVariant, difficultyVariant } from "@/lib/utils";
import { useT } from "@/lib/i18n";
import { useCopyToast } from "@/lib/use-copy-toast";

interface CaseTableProps {
  results: Result[];
}

export function CaseTable({ results }: CaseTableProps) {
  const t = useT();
  const copyTag = useCopyToast();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("caseTable.case")}</TableHead>
          <TableHead>{t("caseTable.difficulty")}</TableHead>
          <TableHead>{t("caseTable.status")}</TableHead>
          <TableHead className="text-right">{t("caseTable.score")}</TableHead>
          <TableHead>{t("caseTable.capabilities")}</TableHead>
          <TableHead className="text-right">{t("caseTable.cost")}</TableHead>
          <TableHead className="text-right">{t("caseTable.tokens")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {results.map((r, i) => (
          <TableRow key={`${r.case_id}-${i}`}>
            <TableCell className="font-medium font-variant-numeric">
              {shortId(r.case_id, 20)}
            </TableCell>
            <TableCell>
              {r.difficulty ? (
                <Badge variant={difficultyVariant(r.difficulty)}>{r.difficulty}</Badge>
              ) : (
                "—"
              )}
            </TableCell>
            <TableCell>
              <Badge
                variant={
                  r.status === "error" ? "warning" :
                  r.status === "cancelled" || r.status === "incomplete" ? "outline" :
                  r.passed ? "success" : "destructive"
                }
              >
                {r.status === "error"
                  ? "Error"
                  : r.status === "cancelled"
                    ? "Cancelled"
                    : r.status === "incomplete"
                      ? "Incomplete"
                      : r.passed ? t("caseTable.pass") : t("caseTable.fail")}
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
                  <Badge
                    key={c}
                    variant="muted"
                    className="text-[10px] cursor-pointer hover:bg-muted"
                    onClick={(e) => copyTag(e, c)}
                  >
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
