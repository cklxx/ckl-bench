import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";
import type { RunSummary } from "@/lib/types";
import { cn, shortId } from "@/lib/utils";
import { useT } from "@/lib/i18n";

interface TrendChartProps {
  runs: RunSummary[];
}

export function TrendChart({ runs }: TrendChartProps) {
  const t = useT();
  const [showPassRate, setShowPassRate] = useState(false);
  const data = runs
    .filter((r) => r.score != null && r.pass_rate != null)
    .map((r) => ({
      name: shortId(r.run_id, 8),
      score: Math.round((r.score ?? 0) * 1000) / 10,
      passRate: Math.round((r.pass_rate ?? 0) * 1000) / 10,
    }));

  return (
    <div className="h-[280px] w-full">
      <div className="mb-2 flex items-center gap-4 text-[11px]">
        <button
          type="button"
          className="flex items-center gap-1.5 cursor-pointer"
          onClick={() => setShowPassRate(!showPassRate)}
        >
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              showPassRate ? "bg-success" : "bg-muted"
            )}
          />
          {t("trend.passRate")}
        </button>
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            tickFormatter={(v) => `${v}%`}
          />
          <RechartsTooltip
            contentStyle={{
              backgroundColor: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              fontSize: 12,
            }}
            formatter={(value: number) => [`${value.toFixed(1)}%`]}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={{ r: 3 }}
            name={t("trend.score")}
          />
          {showPassRate && (
            <Line
              type="monotone"
              dataKey="passRate"
              stroke="hsl(var(--success))"
              strokeWidth={2}
              dot={{ r: 3 }}
              name={t("trend.passRate")}
              strokeDasharray="5 3"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
