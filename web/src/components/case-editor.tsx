import { useEffect, useState } from "react";
import { createCase, deleteCase, getCase, updateCase } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Sheet } from "@/components/ui/sheet";
import { Save, Loader2, X } from "lucide-react";
import { useT } from "@/lib/i18n";

interface CaseEditorProps {
  caseId: string | null;
  createPack?: string | null;
  onClose: () => void;
  onSaved?: () => void;
}

const blankCase = (pack?: string | null): CaseDetail => ({
  id: pack ? `${pack}.new_case.v1` : "new_case.v1",
  title: "New case",
  type: "chat",
  input: { prompt: "" },
  expectations: [{ kind: "contains", value: "" }],
  capability: pack ? [pack] : [],
  difficulty: null,
  timeout_s: null,
  metadata: {},
});

export function CaseEditor({ caseId, createPack, onClose, onSaved }: CaseEditorProps) {
  const t = useT();
  const [c, setC] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [expectationsText, setExpectationsText] = useState("");

  const creating = !caseId && createPack !== null && createPack !== undefined;

  useEffect(() => {
    if (creating) {
      const data = blankCase(createPack);
      setC(data);
      setExpectationsText(JSON.stringify(data.expectations, null, 2));
      setError("");
      return;
    }
    if (!caseId) {
      setC(null);
      return;
    }
    setLoading(true);
    setError("");
    getCase(caseId)
      .then((data) => {
        setC(data);
        setExpectationsText(JSON.stringify(data.expectations || [], null, 2));
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [caseId, createPack, creating]);

  const updateField = <K extends keyof CaseDetail>(key: K, value: CaseDetail[K]) => {
    setC((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  // Cases may store their prompt either as `input.prompt` or as the last
  // user message in `input.messages`. Read from whichever is present so the
  // editor never shows a blank prompt for messages-based cases.
  const promptText =
    c?.input?.prompt ||
    (() => {
      const msgs = c?.input?.messages;
      if (!msgs) return "";
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "user") return msgs[i].content;
      }
      return "";
    })() ||
    "";

  const updatePrompt = (value: string) => {
    setC((prev) => {
      if (!prev) return prev;
      const input = prev.input;
      // If the case uses messages (no flat prompt), update the last user
      // message in place rather than introducing a stray `prompt` key.
      if (!input.prompt && input.messages?.length) {
        const messages = [...input.messages];
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === "user") {
            messages[i] = { ...messages[i], content: value };
            return { ...prev, input: { ...input, messages } };
          }
        }
      }
      return { ...prev, input: { ...input, prompt: value } };
    });
  };

  const handleSave = async () => {
    if (!c) return;
    setError("");
    let expectations = c.expectations;
    try {
      expectations = JSON.parse(expectationsText);
      if (!Array.isArray(expectations)) throw new Error();
    } catch {
      setError(t("caseEditor.invalidJson"));
      return;
    }
    setSaving(true);
    try {
      const payload = { ...c, expectations };
      if (creating) {
        // Send the target pack so the backend writes the case into the
        // correct cases/<pack>/ directory instead of the root custom.jsonl.
        if (createPack) await createCase({ ...payload, pack: createPack });
        else await createCase(payload);
      } else {
        await updateCase(c.id, payload);
      }
      onSaved?.();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!c || creating || !window.confirm(t("caseEditor.deleteConfirm", { id: c.id }))) return;
    setSaving(true);
    setError("");
    try {
      await deleteCase(c.id);
      onSaved?.();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={!!caseId || creating} onClose={onClose} side="right" width="56%" zIndex={51} titleId="case-editor-title">
      <div className="flex flex-1 min-h-0 flex-col">
        {/* Header */}
        <div className="flex h-12 shrink-0 items-center justify-between px-6">
          <h2 id="case-editor-title" className="text-base font-semibold">{t("caseEditor.title")}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("common.close")}>
            <X className="h-4 w-4" />
          </Button>
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
                  <Input
                    value={c.id}
                    disabled={!creating}
                    onChange={(e) => updateField("id", e.target.value)}
                  />
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
                <label htmlFor="case-prompt" className="text-xs font-medium text-muted-foreground">{t("caseEditor.prompt")}</label>
                <Textarea
                  id="case-prompt"
                  rows={6}
                  value={promptText}
                  onChange={(e) => updatePrompt(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="case-expectations" className="text-xs font-medium text-muted-foreground">
                  {t("caseEditor.expectations")}
                </label>
                <Textarea
                  id="case-expectations"
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
        <div className="flex shrink-0 gap-2 px-6 py-4">
          {!creating && (
            <Button variant="destructive" onClick={handleDelete} disabled={saving || !c}>
              {t("caseEditor.delete")}
            </Button>
          )}
          <Button className="flex-1" onClick={handleSave} disabled={saving || !c}>
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
