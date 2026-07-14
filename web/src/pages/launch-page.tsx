import { useEffect, useState } from "react";
import { getConfig, listProviders, launchRun } from "@/lib/api";
import type { ConfigInfo, ProviderInfo } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PlayCircle } from "lucide-react";

interface LaunchPageProps {
  onRunLaunched: (runId: string) => void;
}

export function LaunchPage({ onRunLaunched }: LaunchPageProps) {
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [adapter, setAdapter] = useState("mock");
  const [providerTarget, setProviderTarget] = useState("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [command, setCommand] = useState("");
  const [pack, setPack] = useState("");
  const [caseIds, setCaseIds] = useState("");
  const [repeat, setRepeat] = useState(1);
  const [concurrency, setConcurrency] = useState(1);
  const [seed, setSeed] = useState(0);
  const [judge, setJudge] = useState("");
  const [error, setError] = useState("");
  const [launching, setLaunching] = useState(false);

  useEffect(() => {
    getConfig().then(setConfig).catch(() => {});
    listProviders().then(setProviders).catch(() => {});
  }, []);

  const handleLaunch = async () => {
    setError("");
    setLaunching(true);
    try {
      const adapter_config: Record<string, any> = {};
      if (model) adapter_config.model = model;
      if (baseUrl) adapter_config.base_url = baseUrl;
      if (command) adapter_config.command = command;

      const params: any = {
        adapter: providerTarget || adapter,
        adapter_config,
        repeat: Number(repeat),
        concurrency: Number(concurrency),
        seed: Number(seed),
      };
      if (pack) params.case_paths = [`cases/${pack}`];
      if (caseIds.trim()) {
        params.case_ids = caseIds.split(",").map((s) => s.trim()).filter(Boolean);
      }
      if (judge) params.judge = judge;

      const result = await launchRun(params);
      onRunLaunched(result.run_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Launch Evaluation</h1>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Adapter</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Provider</label>
              <select
                value={providerTarget}
                onChange={(e) => setProviderTarget(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">— Select provider —</option>
                {providers.map((p) => (
                  <option key={p.namespace} value={p.namespace}>
                    {p.namespace} ({p.aliases.join(", ")})
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Adapter (fallback)</label>
              <select
                value={adapter}
                onChange={(e) => setAdapter(e.target.value)}
                disabled={!!providerTarget}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                {config?.adapters.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Model</label>
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="e.g. gpt-4.1-mini"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Base URL</label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="e.g. https://api.openai.com/v1"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Command (command adapter)</label>
              <Input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="python scripts/codex_wrapper.py"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Judge target</label>
              <Input
                value={judge}
                onChange={(e) => setJudge(e.target.value)}
                placeholder="e.g. deepseekv4 (optional)"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Case Selection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Case pack</label>
              <select
                value={pack}
                onChange={(e) => setPack(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">All cases</option>
                {config?.case_packs.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Case IDs (comma-separated, overrides pack)</label>
              <Input
                value={caseIds}
                onChange={(e) => setCaseIds(e.target.value)}
                placeholder="case-1, case-2"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Options</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-3 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Repeat</label>
            <Input
              type="number"
              min={1}
              value={repeat}
              onChange={(e) => setRepeat(Number(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Concurrency</label>
            <Input
              type="number"
              min={1}
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Seed</label>
            <Input
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleLaunch} disabled={launching} size="lg">
          <PlayCircle className="h-4 w-4" />
          {launching ? "Launching..." : "Launch Run"}
        </Button>
      </div>
    </div>
  );
}
