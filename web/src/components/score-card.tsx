import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, formatPercent } from "@/lib/utils";

interface ScoreCardProps {
  title: string;
  value: number;
  description?: string;
  ci?: [number, number];
  variant?: "default" | "success" | "destructive" | "warning";
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
            95% CI: [{formatPercent(ci[0])}, {formatPercent(ci[1])}]
          </p>
        )}
      </CardContent>
    </Card>
  );
}
