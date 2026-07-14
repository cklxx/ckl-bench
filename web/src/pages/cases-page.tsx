import { useEffect, useState } from "react";
import { listCases, getCase, createCase, updateCase, deleteCase, getConfig } from "@/lib/api";
import type { CaseDetail, CaseListItem, ConfigInfo } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Plus, Pencil, Trash2, Save, X } from "lucide-react";

const EMPTY_CASE: Partial<CaseDetail> = {
  id: "",
  title: "",
  type: "chat",
  input: { prompt: "" },
  expectations: [{ kind: "contains", value: "" }],
  capability: [],
};

export function CasesPage() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [pack, setPack] = useState<string>("");
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <select
            value={pack}
            onChange={(e) => setPack(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All packs</option>
            {config?.case_packs.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <Button onClick={beginNew} size="sm">
          <Plus className="h-4 w-4" /> New Case
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
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

      <Card>
        <CardHeader>
          <CardTitle>Cases ({cases.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Capability</TableHead>
                <TableHead>Difficulty</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono text-xs">{c.id}</TableCell>
                  <TableCell>{c.title}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{c.type}</Badge>
                  </TableCell>
                  <TableCell>
                    {c.capability.map((cap) => (
                      <Badge key={cap} variant="secondary" className="mr-1">{cap}</Badge>
                    ))}
                  </TableCell>
                  <TableCell>{c.difficulty || "-"}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" onClick={() => beginEdit(c.id)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => remove(c.id)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
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
    <Card className="border-primary">
      <CardHeader>
        <CardTitle>{isNew ? "New Case" : "Edit Case"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
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
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
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
            className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
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
            className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
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
      </CardContent>
    </Card>
  );
}
