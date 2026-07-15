import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sheet } from "@/components/ui/sheet";
import { PlayCircle, Box } from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n";
import type { CaseListItem } from "@/lib/types";

export interface PackInfo {
  name: string;
  cases: CaseListItem[];
  capabilities: string[];
}

export interface PackRunState {
  runId: string;
  adapter: string;
  status: string;
  progress: { total: number; completed: number; passed: number };
  summary?: any;
}

function difficultyVariant(
  d: string | null
): "destructive" | "warning" | "success" | "outline" {
  if (d === "hard") return "destructive";
  if (d === "medium") return "warning";
  if (d === "easy") return "success";
  return "outline";
}

interface PackDetailProps {
  pack: PackInfo | null;
  runStates: PackRunState[];
  onClose: () => void;
  onEditCase: (id: string) => void;
  onRun: () => void;
}

export function PackDetail({
  pack,
  runStates,
  onClose,
  onEditCase,
  onRun,
}: PackDetailProps) {
  const t = useT();
  const hasRunning = runStates.some(
    (r) => r.status === "running" || r.status === "pending"
  );
  const hasCompleted = runStates.some((r) => r.status === "completed");

  return (
    <Sheet open={!!pack} onClose={onClose} side="right" width="75%">
      <div className="flex flex-1 min-h-0 flex-col">
        {/* Header */}
        <div className="flex h-12 shrink-0 items-center justify-between border-b px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Box className="h-4 w-4" />
            </div>
            <h2 className="text-base font-semibold capitalize">{pack?.name}</h2>
            {pack && (
              <Badge variant="secondary" className="text-xs">
                {pack.cases.length}
              </Badge>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {pack && (
            <>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {t(`pack.${pack.name}`)}
              </p>

              {pack.capabilities.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {pack.capabilities.map((cap) => (
                    <Badge
                      key={cap}
                      variant="outline"
                      className="text-[11px] cursor-pointer hover:bg-muted"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(cap);
                      }}
                    >
                      {cap}
                    </Badge>
                  ))}
                </div>
              )}

              {runStates.length > 0 && (
                <div className="space-y-2.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("pack.recentRuns")}
                  </h3>
                  {runStates.map((rs) => {
                    const pct =
                      rs.progress.total > 0
                        ? Math.round(
                            (rs.progress.completed / rs.progress.total) * 100
                          )
                        : 0;
                    return (
                      <div key={rs.runId}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="font-medium capitalize">
                            {rs.adapter}
                          </span>
                          <span className="tabular-nums text-muted-foreground">
                            {rs.status === "completed"
                              ? t("pack.passed", {
                                  passed: rs.progress.passed,
                                  total: rs.progress.total,
                                })
                              : t("pack.progress", {
                                  completed: rs.progress.completed,
                                  total: rs.progress.total,
                                })}
                          </span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all duration-300",
                              rs.status === "completed"
                                ? "bg-success"
                                : "bg-primary"
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="space-y-2.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t("pack.cases", { count: pack.cases.length })}
                </h3>
                <div className="space-y-2">
                  {pack.cases.map((c) => (
                    <div
                      key={c.id}
                      className="rounded-lg border px-4 py-3 text-sm hover:bg-muted/40 cursor-pointer transition-colors"
                      onClick={() => onEditCase(c.id)}
                    >
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <span className="font-medium text-foreground leading-snug">
                          {c.title}
                        </span>
                        {c.difficulty && (
                          <Badge
                            variant={difficultyVariant(c.difficulty)}
                            className="shrink-0 text-[10px] capitalize"
                          >
                            {c.difficulty}
                          </Badge>
                        )}
                      </div>
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        <Badge
                          variant="secondary"
                          className="text-[10px] cursor-pointer hover:bg-muted"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(c.type);
                          }}
                        >
                          {c.type}
                        </Badge>
                        {c.capability.map((cap) => (
                          <Badge
                            key={cap}
                            variant="outline"
                            className="text-[10px] cursor-pointer hover:bg-muted"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigator.clipboard.writeText(cap);
                            }}
                          >
                            {cap}
                          </Badge>
                        ))}
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                        {c.timeout_s != null && (
                          <span>{t("pack.timeout", { seconds: c.timeout_s })}</span>
                        )}
                        <span className="truncate font-mono">{c.source}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t px-6 py-4">
          <Button
            variant={!hasRunning && !hasCompleted ? "default" : "outline"}
            className="w-full"
            onClick={onRun}
            disabled={hasRunning}
          >
            <PlayCircle className="h-3.5 w-3.5" />
            {hasRunning
              ? t("common.running")
              : hasCompleted
                ? t("common.runAgain")
                : t("common.run")}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
