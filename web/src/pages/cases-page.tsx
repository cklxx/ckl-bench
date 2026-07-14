import { useEffect, useState } from "react";
import { listCases, getCase, createCase, updateCase, deleteCase, getConfig } from "@/lib/api";
import type { CaseDetail, CaseListItem, ConfigInfo } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2, Save, X, ChevronDown, ChevronRight } from "lucide-react";

const EMPTY_CASE: Partial<CaseDetail> = {
  id: "",
  title: "",
  type: "chat",
  input: { prompt: "" },
  expectations: [{ kind: "contains", value: "" }],
  capability: [],
};

// Extract pack name from source path like "cases/chat/foo.jsonl:12" → "chat"
function packFromSource(source: string): string {
  const m = source.match(/cases\/([^/]+)/);
  return m ? m[1] : "other";
}

function difficultyColor(d: string | null): string {
  if (!d) return "text-muted-foreground";
  if (d === "hard" || d === "high") return "text-destructive";
  if (d === "medium" || d === "mid") return "text-warning";
  return "text-success";
}

export function CasesPage() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [pack, setPack] = useState<string>("");
  const [expandedPack, setExpandedPack] = useState<string>("");
  const [editing, setEditing] = useState<Partial<CaseDetail> | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string>("");

  const refresh = () => {
    listCases(pack || undefined).then(setCases).catch((e) => setError(String(e)));
  };

  useEffect(() => {
    refresh();
    getConfig().then(setConfig).catch(() => {});
  }, [pack]);

  const beginNew = () => {
    setEditing({ ...EMPTY_CASE });
    setIsNew(true);
  };

  const beginEdit = async (id: string) => {
    try {
      const c = await getCase(id);
      setEditing(c);
      setIsNew(false);
    } catch (e) {
      setError(String(e));
    }
  };

  const save = async () => {
    if (!editing || !editing.id) {
      setError("Case id is required");
      return;
    }
    try {
      if (isNew) {
        await createCase(editing);
      } else {
        await updateCase(editing.id, editing);
      }
      setEditing(null);
      setIsNew(false);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: string) => {
    if (!confirm(`Delete case ${id}?`)) return;
    try {
      await deleteCase(id);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  // Group cases by pack.
  const packs = config?.case_packs || [];
  const grouped = new Map<string, CaseListItem[]>();
  for (const c of cases) {
    const p = packFromSource(c.source);
    if (!grouped.has(p)) grouped.set(p, []);
    grouped.get(p)!.push(c);
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <select
            value={pack}
            onChange={(e) => setPack(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm"
          >
            <option value="">All packs</option>
            {packs.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <Button onClick={beginNew} size="sm">
          <Plus className="h-4 w-4" /> New Case
        </Button>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {editing && (
        <CaseEditor
          caseData={editing}
          isNew={isNew}
          onChange={setEditing}
          onSave={save}
          onCancel={() => { setEditing(null); setIsNew(false); }}
        />
      )}

      {/* Pack cards */}
      <div className="space-y-4">
        {Array.from(grouped.entries()).map(([packName, packCases]) => {
          const isExpanded = expandedPack === packName;
          return (
            <Card key={packName} className="overflow-hidden">
              <button
                onClick={() => setExpandedPack(isExpanded ? "" : packName)}
                className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-muted/50"
              >
                <div className="flex items-center gap-2">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="text-base font-semibold capitalize">{packName}</span>
                  <Badge variant="secondary" className="text-xs">
                    {packCases.length}
                  </Badge>
                </div>
                <div className="flex items-center gap-1.5">
                  {packCases.slice(0, 4).map((c) =>
                    c.capability.slice(0, 2).map((cap) => (
                      <Badge key={cap} variant="outline" className="text-[10px]">{cap}</Badge>
                    ))
                  )}
                </div>
              </button>
              {isExpanded && (
                <CardContent className="border-t border-border/50 bg-muted/20 p-4">
                  <div className="grid gap-3">
                    {packCases.map((c) => (
                      <CaseCard
                        key={c.id}
                        caseItem={c}
                        onEdit={() => beginEdit(c.id)}
                        onDelete={() => remove(c.id)}
                      />
                    ))}
                  </div>
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>

      {cases.length === 0 && (
        <p className="text-center text-sm text-muted-foreground">No cases found.</p>
      )}
    </div>
  );
}

function CaseCard({
  caseItem,
  onEdit,
  onDelete,
}: {
  caseItem: CaseListItem;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group rounded-lg bg-background p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium leading-snug">{caseItem.title}</h4>
        <div className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDelete}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="mb-2 flex flex-wrap gap-1">
        {caseItem.capability.map((cap) => (
          <Badge key={cap} variant="secondary" className="text-[10px]">{cap}</Badge>
        ))}
      </div>
      {caseItem.difficulty && (
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Difficulty</span>
          <span className={`text-[11px] font-medium capitalize ${difficultyColor(caseItem.difficulty)}`}>
            {caseItem.difficulty}
          </span>
        </div>
      )}
    </div>
  );
}

function CaseEditor({
  caseData,
  isNew,
  onChange,
  onSave,
  onCancel,
}: {
  caseData: Partial<CaseDetail>;
  isNew: boolean;
  onChange: (c: Partial<CaseDetail>) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const update = (patch: Partial<CaseDetail>) => onChange({ ...caseData, ...patch });

  return (
    <Card className="bg-primary/5">
      <div className="border-b border-border/50 px-5 py-4">
        <h3 className="text-base font-semibold">{isNew ? "New Case" : "Edit Case"}</h3>
      </div>
      <div className="space-y-4 p-5">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">ID *</label>
            <Input
              value={caseData.id || ""}
              disabled={!isNew}
              onChange={(e) => update({ id: e.target.value })}
              placeholder="my-case-id"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Title</label>
            <Input
              value={caseData.title || ""}
              onChange={(e) => update({ title: e.target.value })}
              placeholder="Human-readable title"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Type</label>
            <select
              value={caseData.type || "chat"}
              onChange={(e) => update({ type: e.target.value })}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm"
            >
              {["chat", "agent", "doc-writing", "infra-code", "paper-reading"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Capability (comma-separated)</label>
            <Input
              value={(caseData.capability || []).join(", ")}
              onChange={(e) => update({ capability: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
              placeholder="reasoning, math"
            />
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Prompt</label>
          <textarea
            value={caseData.input?.prompt || ""}
            onChange={(e) => update({ input: { ...caseData.input, prompt: e.target.value } })}
            className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
            placeholder="The prompt to send to the model"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Expectations (JSON)</label>
          <textarea
            value={JSON.stringify(caseData.expectations || [], null, 2)}
            onChange={(e) => {
              try {
                update({ expectations: JSON.parse(e.target.value) });
              } catch {
                // Allow invalid JSON while typing.
              }
            }}
            className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X className="h-4 w-4" /> Cancel
          </Button>
          <Button size="sm" onClick={onSave}>
            <Save className="h-4 w-4" /> Save
          </Button>
        </div>
      </div>
    </Card>
  );
}
