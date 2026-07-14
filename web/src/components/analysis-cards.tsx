import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { RunSummary } from "@/lib/types";
import { formatPercent } from "@/lib/utils";

interface AnalysisCardsProps {
  runs: RunSummary[];
}

interface AnalysisItem {
  title: string;
  value: string;
  description: string;
  variant: "success" | "destructive" | "warning" | "default";
}

function analyze(runs: RunSummary[]): AnalysisItem[] {
  if (runs.length === 0) return [];

  const latest = runs[runs.length - 1];
  const items: AnalysisItem[] = [];

  // Strongest capability
  const caps = latest.by_capability;
  if (caps) {
    const sorted = Object.entries(caps).sort(
      (a, b) => b[1].score - a[1].score
    );
    if (sorted.length > 0) {
      const [name, bucket] = sorted[0];
      items.push({
        title: "Strongest Capability",
        value: name,
        description: `${formatPercent(bucket.score)} (${bucket.passed}/${bucket.count})`,
        variant: "success",
      });
    }
    if (sorted.length > 1) {
      const [name, bucket] = sorted[sorted.length - 1];
      items.push({
        title: "Weakest Capability",
        value: name,
        description: `${formatPercent(bucket.score)} (${bucket.passed}/${bucket.count})`,
        variant: "destructive",
      });
    }
  }

  // Trend: compare latest vs previous
  if (runs.length >= 2) {
    const prev = runs[runs.length - 2];
    const delta = latest.score - prev.score;
    const pct = Math.round(delta * 1000) / 10;
    if (pct > 0) {
      items.push({
        title: "Most Improved",
        value: `+${pct.toFixed(1)}%`,
        description: `vs previous run (${formatPercent(prev.score)} → ${formatPercent(latest.score)})`,
        variant: "success",
      });
    } else if (pct < 0) {
      items.push({
        title: "Regressed",
        value: `${pct.toFixed(1)}%`,
        description: `vs previous run (${formatPercent(prev.score)} → ${formatPercent(latest.score)})`,
        variant: "destructive",
      });
    }
  }

  // Overall score
  items.push({
    title: "Overall Score",
    value: formatPercent(latest.score),
    description: `${latest.passed}/${latest.total} cases passed`,
    variant: "default",
  });

  return items;
}

export function AnalysisCards({ runs }: AnalysisCardsProps) {
  const items = analyze(runs);
  if (items.length === 0) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map((item) => (
        <Card key={item.title}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {item.title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold font-variant-numeric">
                {item.value}
              </span>
              <Badge variant={item.variant === "default" ? "muted" : item.variant}>
                {item.variant === "success"
                  ? "↑"
                  : item.variant === "destructive"
                  ? "↓"
                  : item.variant === "warning"
                  ? "→"
                  : "•"}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {item.description}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
