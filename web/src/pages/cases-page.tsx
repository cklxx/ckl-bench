import { useEffect, useState } from "react";
import { listCases, getCase, createCase, updateCase, deleteCase, getConfig } from "@/lib/api";
import type { CaseDetail, CaseListItem, ConfigInfo } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2, Save, X, ArrowLeft, Box } from "lucide-react";

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

// Human-readable pack descriptions.
const PACK_DESC: Record<string, string> = {
  chat: "API-only and chat cases covering reasoning, math, code, and long-tail knowledge.",
  agent: "Agent cases with temporary workspaces and artifact checks.",
  "doc-writing": "Documentation writing: API docs, READMEs, changelogs.",
  "infra-code": "Infrastructure code: Docker, systemd, nginx, deploy scripts.",
  "paper-reading": "Paper reading: abstract comprehension, method comparison, results.",
};

function difficultyColor(d: string | null): string {
  if (!d) return "text-muted-foreground";
  if (d === "hard" || d === "high") return "text-destructive";
  if (d === "medium" || d === "mid") return "text-warning";
  return "text-success";
}

interface PackInfo {
  name: string;
  cases: CaseListItem[];
  capabilities: string[];
  difficulty: string | null;
}

export function CasesPage() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [selectedPack, setSelectedPack] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<CaseDetail> | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string>("");

  const refresh = () => {
    listCases().then(setCases).catch((e) => setError(String(e)));
  };

  useEffect(() => {
    refresh();
    getConfig().then(setConfig).catch(() => {});
  }, []);

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
  const packMap = new Map<string, CaseListItem[]>();
  for (const c of cases) {
    const p = packFromSource(c.source);
    if (!packMap.has(p)) packMap.set(p, []);
    packMap.get(p)!.push(c);
  }

  const packs: PackInfo[] = Array.from(packMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, packCases]) => {
      const capSet = new Set<string>();
      let difficulty: string | null = null;
      for (const c of packCases) {
        c.capability.forEach((cap) => capSet.add(cap));
        if (c.difficulty) difficulty = c.difficulty;
      }
      return { name, cases: packCases, capabilities: Array.from(capSet), difficulty };
    });

  const currentPack = selectedPack ? packs.find((p) => p.name === selectedPack) : null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          {selectedPack ? (
            <button
              onClick={() => setSelectedPack(null)}
              className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" /> All Packs
            </button>
          ) : (
            <h1 className="text-xl font-semibold tracking-tight">Bench Collections</h1>
          )}
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

      {/* Pack cover cards gallery */}
      {!selectedPack && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
          {packs.map((pack) => (
            <PackCard
              key={pack.name}
              pack={pack}
              onClick={() => setSelectedPack(pack.name)}
            />
          ))}
        </div>
      )}

      {/* Pack detail: case cards */}
      {selectedPack && currentPack && (
        <div className="space-y-4">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold capitalize tracking-tight">{currentPack.name}</h2>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {PACK_DESC[currentPack.name] || `${currentPack.cases.length} cases`}
              </p>
            </div>
            <Badge variant="secondary">
              {currentPack.cases.length} case{currentPack.cases.length !== 1 ? "s" : ""}
            </Badge>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
            {currentPack.cases.map((c) => (
              <CaseCard
                key={c.id}
                caseItem={c}
                onEdit={() => beginEdit(c.id)}
                onDelete={() => remove(c.id)}
              />
            ))}
          </div>
        </div>
      )}

      {cases.length === 0 && (
        <p className="text-center text-sm text-muted-foreground">No cases found.</p>
      )}
    </div>
  );
}

/**
 * Pack cover card — the "封面卡牌" of a bench collection.
 * Shows pack name, description, case count, and capability tags.
 * Reusable for showing pass counts later (see ProgressPage).
 */
function PackCard({ pack, onClick }: { pack: PackInfo; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group relative flex min-h-[200px] flex-col overflow-hidden rounded-xl bg-card p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      {/* Accent gradient bar at top */}
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary/60 to-primary/20" />

      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Box className="h-6 w-6" />
        </div>
        <Badge variant="secondary" className="text-xs">
          {pack.cases.length}
        </Badge>
      </div>

      <h3 className="mb-1.5 text-lg font-bold capitalize tracking-tight">{pack.name}</h3>
      <p className="mb-4 flex-1 text-xs leading-relaxed text-muted-foreground">
        {PACK_DESC[pack.name] || `${pack.cases.length} cases`}
      </p>

      <div className="mt-auto flex flex-wrap gap-1">
        {pack.capabilities.slice(0, 4).map((cap) => (
          <Badge key={cap} variant="outline" className="text-[10px]">{cap}</Badge>
        ))}
        {pack.capabilities.length > 4 && (
          <Badge variant="outline" className="text-[10px]">+{pack.capabilities.length - 4}</Badge>
        )}
      </div>
    </button>
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
    <div className="group relative flex min-h-[140px] flex-col rounded-xl bg-card p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="mb-3 flex items-start justify-between gap-2">
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
      <div className="mb-3 flex flex-1 flex-wrap gap-1 content-start">
        {caseItem.capability.map((cap) => (
          <Badge key={cap} variant="secondary" className="text-[10px]">{cap}</Badge>
        ))}
      </div>
      {caseItem.difficulty && (
        <div className="mt-auto flex items-center gap-1.5">
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
