import { useEffect, useState } from "react";
import { getCase, updateCase } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { X, Save, Loader2 } from "lucide-react";

interface CaseEditorProps {
  caseId: string | null;
  onClose: () => void;
  onSaved?: () => void;
}

export function CaseEditor({ caseId, onClose, onSaved }: CaseEditorProps) {
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

  if (!caseId) return null;

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
      setError("Expectations must be valid JSON array");
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
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex w-[640px] max-h-[85vh] flex-col bg-background shadow-lg rounded-lg">
        <div className="flex h-12 items-center justify-between px-5">
          <h2 className="text-base font-semibold">Edit Case</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 pb-4 space-y-4">
          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading case...
            </div>
          ) : c ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">ID</label>
                  <Input value={c.id} disabled />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">Type</label>
                  <Input
                    value={c.type}
                    onChange={(e) => updateField("type", e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Title</label>
                <Input
                  value={c.title}
                  onChange={(e) => updateField("title", e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Prompt</label>
                <Textarea
                  rows={6}
                  value={c.input?.prompt || ""}
                  onChange={(e) =>
                    updateField("input", { ...c.input, prompt: e.target.value })
                  }
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Expectations (JSON)
                </label>
                <Textarea
                  rows={6}
                  value={expectationsText}
                  onChange={(e) => setExpectationsText(e.target.value)}
                  className="font-mono text-xs"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Capability
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
                    placeholder="reasoning, code"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Difficulty
                  </label>
                  <Input
                    value={c.difficulty || ""}
                    onChange={(e) => updateField("difficulty", e.target.value || null)}
                    placeholder="easy / medium / hard"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Timeout (s)
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

        <div className="px-5 pb-5">
          <Button className="w-full" onClick={handleSave} disabled={saving || !c}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </div>
    </div>
  );
}
