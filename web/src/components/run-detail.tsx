import { useEffect, useState } from "react";
import { getRun } from "@/lib/api";
import type { Result, RunInfo } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { Loader2, X } from "lucide-react";
import { formatPercent, formatNumber, scoreVariant } from "@/lib/utils";
import { useT } from "@/lib/i18n";
import { useCopyToast } from "@/lib/use-copy-toast";

interface RunDetailProps {
  runId: string | null;
  onClose: () => void;
}

export function RunDetail({ runId, onClose }: RunDetailProps) {
  const t = useT();
  const copyTag = useCopyToast();
  const [run, setRun] = useState<RunInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedCase, setExpandedCase] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError("");
    getRun(runId)
      .then(setRun)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [runId]);

  const summary = run?.summary;
  const results: Result[] = (run as any)?.results || [];
  const adapter = summary?.adapter_display || summary?.adapter || "unknown";

  return (
    <Sheet open={!!runId} onClose={onClose} side="right" width="60%" titleId="run-detail-title">
      <div className="flex flex-1 min-h-0 flex-col">
        {/* Header */}
        <div className="flex h-12 shrink-0 items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <h2 id="run-detail-title" className="text-base font-semibold">{t("runDetail.title")}</h2>
            <Badge variant="secondary">{adapter}</Badge>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("common.close")}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("runDetail.loading")}
            </div>
          ) : summary ? (
            <>
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded-lg bg-muted/60 px-4 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {t("runDetail.score")}
                  </div>
                  <div className="text-xl font-semibold font-variant-numeric">
                    {formatPercent(summary.score)}
                  </div>
                </div>
                <div className="rounded-lg bg-muted/60 px-4 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {t("runDetail.passed")}
                  </div>
                  <div className="text-xl font-semibold font-variant-numeric">
                    {summary.passed}/{summary.total}
                    {summary.errored ? (
                      <span className="ml-1 text-xs font-normal text-amber-600">
                        +{summary.errored} err
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="rounded-lg bg-muted/60 px-4 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {t("runDetail.cost")}
                  </div>
                  <div className="text-xl font-semibold font-variant-numeric">
                    {summary.cost_usd != null && summary.cost_usd > 0
                      ? `$${summary.cost_usd.toFixed(4)}`
                      : "—"}
                  </div>
                </div>
                <div className="rounded-lg bg-muted/60 px-4 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {t("runDetail.tokens")}
                  </div>
                  <div className="text-xl font-semibold font-variant-numeric">
                    {summary.usage?.total_tokens != null
                      ? formatNumber(summary.usage.total_tokens)
                      : "—"}
                  </div>
                </div>
              </div>

              {results.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("runDetail.cases", { count: results.length })}
                  </h3>
                  {results.map((r) => {
                    const isOpen = expandedCase === r.case_id;
                    return (
                    <div
                      key={r.case_id}
                      className="rounded-lg bg-muted/40 px-4 py-3.5 space-y-2"
                    >
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-3 text-left"
                        onClick={() => setExpandedCase(isOpen ? null : r.case_id)}
                      >
                        <span className="text-sm font-medium truncate">
                          {r.case_id}
                        </span>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant={scoreVariant(r.score)}>
                            {formatPercent(r.score, 0)}
                          </Badge>
                          <span className="text-muted-foreground text-xs transition-transform" style={{ transform: isOpen ? "rotate(90deg)" : "none" }}>
                            ▶
                          </span>
                        </div>
                      </button>
                      {r.capability && r.capability.length > 0 && (
                        <div className="flex gap-1.5">
                          {r.capability.map((c) => (
                            <Badge
                              key={c}
                              variant="outline"
                              className="text-[10px] cursor-pointer hover:bg-muted"
                              onClick={(e) => copyTag(e, c)}
                            >
                              {c}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {r.checks && r.checks.length > 0 && (
                        <div className="space-y-1">
                          {r.checks.map((ch, i) => (
                            <div
                              key={i}
                              className="flex items-start gap-2 text-xs"
                            >
                              <span
                                className={
                                  ch.passed
                                    ? "text-success shrink-0"
                                    : "text-destructive shrink-0"
                                }
                              >
                                {ch.passed ? "✓" : "✗"}
                              </span>
                              <span className="font-medium shrink-0">{ch.kind}</span>
                              {ch.detail && (
                                <span className={isOpen ? "text-muted-foreground break-words whitespace-pre-wrap" : "text-muted-foreground truncate"}>
                                  {ch.detail}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {r.error && (
                        <div className="text-xs text-destructive break-words whitespace-pre-wrap">
                          {r.error}
                        </div>
                      )}
                      {isOpen && r.response_text && (
                        <div className="mt-2 border-t border-border pt-2">
                          <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
                            {t("runDetail.response")}
                          </div>
                          <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words max-h-60 overflow-y-auto">
                            {r.response_text}
                          </pre>
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              )}

              {results.length === 0 && (
                <div className="text-sm text-muted-foreground">
                  {t("runDetail.empty")}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </Sheet>
  );
}
