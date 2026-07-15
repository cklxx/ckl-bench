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
import { formatPercent, formatCost, shortId, scoreVariant } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface CaseTableProps {
  results: Result[];
}

export function CaseTable({ results }: CaseTableProps) {
  const t = useT();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("caseTable.case")}</TableHead>
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
              <Badge variant={r.passed ? "success" : "destructive"}>
                {r.passed ? t("caseTable.pass") : t("caseTable.fail")}
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
                    onClick={(e) => {
                      e.stopPropagation();
                      navigator.clipboard.writeText(c);
                    }}
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
