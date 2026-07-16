import type { RunSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

function heatColor(score: number): string {
  if (score >= 0.9) return "bg-success";
  if (score >= 0.75) return "bg-success/70";
  if (score >= 0.6) return "bg-warning/80";
  if (score >= 0.4) return "bg-warning";
  return "bg-destructive";
}

interface HeatmapProps {
  runs: RunSummary[];
}

export function Heatmap({ runs }: HeatmapProps) {
  // Collect all capabilities across all runs.
  const capSet = new Set<string>();
  for (const r of runs) {
    if (r.by_capability) {
      for (const k of Object.keys(r.by_capability)) capSet.add(k);
    }
  }
  const caps = Array.from(capSet).sort();
  if (caps.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <div className="inline-block">
        {/* Header row with run labels */}
        <div className="flex gap-1 mb-1">
          <div className="w-28 shrink-0" />
          {runs.map((r) => (
            <div
              key={r.run_id}
              className="w-16 shrink-0 text-center text-[10px] text-muted-foreground truncate px-1"
              title={r.run_id}
            >
              {r.adapter_display || r.adapter}
            </div>
          ))}
        </div>
        {/* Rows per capability */}
        {caps.map((cap) => (
          <div key={cap} className="flex gap-1 mb-1 items-center">
            <div className="w-28 shrink-0 text-xs font-medium capitalize truncate pr-2">
              {cap}
            </div>
            {runs.map((r) => {
              const bucket = r.by_capability?.[cap];
              const score = bucket?.score ?? 0;
              return (
                <div
                  key={r.run_id}
                  className={cn(
                    "w-16 shrink-0 h-7 rounded-sm flex items-center justify-center text-[10px] font-semibold text-white",
                    heatColor(score)
                  )}
                  title={`${cap}: ${(score * 100).toFixed(1)}%`}
                >
                  {bucket ? `${(score * 100).toFixed(0)}` : "—"}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
