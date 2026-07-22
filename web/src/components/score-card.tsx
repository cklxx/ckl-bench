import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, formatPercent } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface ScoreCardProps {
  title: string;
  value: number | null;
  description?: string;
  ci?: [number, number] | null;
  variant?: "default" | "success" | "destructive" | "warning" | "outline";
}

function variantColor(variant: ScoreCardProps["variant"]) {
  switch (variant) {
    case "success":
      return "text-success";
    case "destructive":
      return "text-destructive";
    case "warning":
      return "text-warning";
    default:
      return "text-foreground";
  }
}

export function ScoreCard({
  title,
  value,
  description,
  ci,
  variant = "default",
}: ScoreCardProps) {
  const t = useT();
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "text-3xl font-bold font-variant-numeric",
            variantColor(variant)
          )}
        >
          {formatPercent(value)}
        </div>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
        {ci && (
          <p className="mt-1 text-xs text-muted-foreground font-variant-numeric">
            {t("common.ci", {
              low: formatPercent(ci[0]),
              high: formatPercent(ci[1]),
            })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
