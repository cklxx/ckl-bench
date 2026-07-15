import { useEffect, useState } from "react";
import { getCase, updateCase } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Sheet } from "@/components/ui/sheet";
import { Save, Loader2 } from "lucide-react";
import { useT } from "@/lib/i18n";

interface CaseEditorProps {
  caseId: string | null;
  onClose: () => void;
  onSaved?: () => void;
}

export function CaseEditor({ caseId, onClose, onSaved }: CaseEditorProps) {
  const t = useT();
  const [c, setC] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [expectationsText, setExpectationsText] = useState("");

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    setError("");
    getCase(caseId)
      .then((data) => {
        setC(data);
        setExpectationsText(JSON.stringify(data.expectations || [], null, 2));
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [caseId]);

  const updateField = <K extends keyof CaseDetail>(key: K, value: CaseDetail[K]) => {
    setC((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const handleSave = async () => {
    if (!c) return;
    setError("");
    let expectations = c.expectations;
    try {
      expectations = JSON.parse(expectationsText);
    } catch {
      setError(t("caseEditor.invalidJson"));
      return;
    }
    setSaving(true);
    try {
      await updateCase(c.id, { ...c, expectations });
      onSaved?.();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={!!caseId} onClose={onClose} side="right" width="56%" zIndex={51}>
      <div className="flex flex-1 min-h-0 flex-col">
        {/* Header */}
        <div className="flex h-12 shrink-0 items-center justify-between border-b px-6">
          <h2 className="text-base font-semibold">{t("caseEditor.title")}</h2>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("caseEditor.loading")}
            </div>
          ) : c ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">{t("caseEditor.id")}</label>
                  <Input value={c.id} disabled />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">{t("caseEditor.type")}</label>
                  <Input
                    value={c.type}
                    onChange={(e) => updateField("type", e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t("caseEditor.caseTitle")}</label>
                <Input
                  value={c.title}
                  onChange={(e) => updateField("title", e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t("caseEditor.prompt")}</label>
                <Textarea
                  rows={6}
                  value={c.input?.prompt || ""}
                  onChange={(e) =>
                    updateField("input", { ...c.input, prompt: e.target.value })
                  }
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  {t("caseEditor.expectations")}
                </label>
                <Textarea
                  rows={6}
                  value={expectationsText}
                  onChange={(e) => setExpectationsText(e.target.value)}
                  className="font-mono text-xs"
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t("caseEditor.capability")}
                  </label>
                  <Input
                    value={(c.capability || []).join(", ")}
                    onChange={(e) =>
                      updateField(
                        "capability",
                        e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean)
                      )
                    }
                    placeholder={t("caseEditor.capabilityPh")}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t("caseEditor.difficulty")}
                  </label>
                  <Input
                    value={c.difficulty || ""}
                    onChange={(e) => updateField("difficulty", e.target.value || null)}
                    placeholder={t("caseEditor.difficultyPh")}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t("caseEditor.timeout")}
                  </label>
                  <Input
                    type="number"
                    value={c.timeout_s ?? ""}
                    onChange={(e) =>
                      updateField(
                        "timeout_s",
                        e.target.value === "" ? null : Number(e.target.value)
                      )
                    }
                  />
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t px-6 py-4">
          <Button className="w-full" onClick={handleSave} disabled={saving || !c}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
