import * as React from "react";
import { Button } from "@/components/ui/button";
import { Languages } from "lucide-react";

export type Locale = "en" | "zh";

type Trans = string | { [key: string]: Trans };

const translations: Record<Locale, Record<string, Trans>> = {
  en: {
    app: {
      footer: "ckl-bench · generated evaluation report",
      empty: {
        title: "No data available",
        subtitle: "The {{page}} page has no data to display yet.",
      },
    },
    common: {
      score: "Score",
      passed: "Passed",
      total: "Total",
      cost: "Cost",
      tokens: "Tokens",
      status: "Status",
      detail: "Detail",
      run: "Run",
      runAgain: "Run Again",
      running: "Running...",
      launching: "Launching...",
      runAll: "Run All",
      view: "View",
      save: "Save Changes",
      saving: "Saving...",
      cancel: "Cancel",
      test: "Test",
      testing: "Testing...",
      cases: "Cases",
      capabilities: "Capabilities",
      ci: "95% CI: [{{low}}, {{high}}]",
      copied: "Copied: {{value}}",
    },
    bench: {
      title: "Bench Collections",
      reports: "Reports",
      overview: "Overview",
      heatmap: "Heatmap",
      allRuns: "All Runs",
      scoreTrend: "Score Trend",
      capabilityHeatmap: "Capability Heatmap",
      cases: "{{count}} cases",
      noAdapters:
        "No active adapters selected. Configure adapters in Settings.",
      settings: "Settings",
    },
    pack: {
      recentRuns: "Recent Runs",
      cases: "Cases ({{count}})",
      timeout: "{{seconds}}s timeout",
      passed: "{{passed}}/{{total}} passed",
      progress: "{{completed}}/{{total}}",
      chat:
        "API-only and chat cases covering reasoning, math, code, and long-tail knowledge.",
      agent: "Agent cases with temporary workspaces and artifact checks.",
      "doc-writing": "Documentation writing: API docs, READMEs, changelogs.",
      "infra-code": "Infrastructure code: Docker, systemd, nginx, deploy scripts.",
      "paper-reading":
        "Paper reading: abstract comprehension, method comparison, results.",
    },
    runDetail: {
      title: "Run Details",
      score: "Score",
      passed: "Passed",
      cost: "Cost",
      tokens: "Tokens",
      cases: "Cases ({{count}})",
      loading: "Loading run...",
      empty: "No case results available for this run.",
    },
    caseEditor: {
      title: "Edit Case",
      id: "ID",
      type: "Type",
      caseTitle: "Title",
      prompt: "Prompt",
      expectations: "Expectations (JSON)",
      capability: "Capability",
      difficulty: "Difficulty",
      timeout: "Timeout (s)",
      capabilityPh: "reasoning, code",
      difficultyPh: "easy / medium / hard",
      invalidJson: "Expectations must be valid JSON array",
      loading: "Loading case...",
    },
    settings: {
      title: "Settings",
      activeAdapters: "Active Adapters",
      activeDesc: "Select which adapters to benchmark side-by-side.",
      command: "Command",
      commandPh: "dsx\n# or any bash command",
      apiKey: "API Key",
      apiKeyPh: "sk-...",
      baseUrl: "Base URL",
      model: "Model",
      modelPh: "e.g. deepseek-v4-flash",
      testingCommand: "Testing: {{command}}",
      testOk: "OK — command responded successfully",
      testCancelled: "cancelled by user",
      defaultOptions: "Default Options",
      repeat: "Repeat",
      concurrency: "Concurrency",
      seed: "Seed",
      judge: "Judge",
      judgePh: "e.g. deepseekv4 (optional)",
      reviewer: "Reviewer",
      reviewerPh: "e.g. claude-sonnet (optional, challenges judge)",
      verifier: "Verifier",
      verifierPh: "e.g. gpt-4o (optional, final verdict)",
      save: "Save Settings",
      saving: "Saving...",
    },
    runTable: {
      runId: "Run ID",
      adapter: "Adapter",
      score: "Score",
      passed: "Passed",
      total: "Total",
      passRate: "Pass Rate",
      cost: "Cost",
      tokens: "Tokens",
    },
    analysis: {
      strongest: "Strongest Capability",
      weakest: "Weakest Capability",
      mostImproved: "Most Improved",
      regressed: "Regressed",
      overall: "Overall Score",
      strongestDesc: "{{score}} ({{passed}}/{{count}})",
      vsPrev: "vs previous run ({{prev}} → {{curr}})",
      overallDesc: "{{passed}}/{{total}} cases passed",
    },
    trend: {
      score: "Score",
      passRate: "Pass Rate",
    },
    dashboard: {
      title: "Dashboard",
      collected: "{{count}} run{{plural}} collected",
      scoreTrend: "Score Trend",
      heatmap: "Capability Heatmap",
      allRuns: "All Runs",
    },
    report: {
      title: "Evaluation Report",
      run: "Run",
      passed: "{{passed}}/{{total}} passed",
      repeat: "repeat={{repeat}}",
      score: "Score",
      passRate: "Pass Rate",
      passAt1: "Pass@1",
      passAtK: "Pass@{{k}}",
      usage: "Usage",
      totalTokens: "Total Tokens",
      inputTokens: "Input Tokens",
      outputTokens: "Output Tokens",
      cost: "Cost",
      capabilities: "Capabilities",
      difficulty: "Difficulty",
      cases: "Cases ({{count}})",
    },
    probe: {
      title: "Probe Report",
      summary: "{{count}} probe{{plural}}",
      passed: "Passed",
      failed: "Failed",
      skipped: "Skipped",
      passedDesc: "{{count}} of {{total}} probes",
      failedDesc: "{{count}} of {{total}} probes",
      skippedDesc: "{{count}} of {{total}} probes",
      results: "Probe Results",
      target: "Target",
      kind: "Kind",
      status: "Status",
      score: "Score",
      detail: "Detail",
      pass: "PASS",
      fail: "FAIL",
      skip: "SKIP",
    },
    diff: {
      title: "Run Diff",
      runA: "Run A",
      runB: "Run B",
      delta: "Delta",
      summary: "{{improved}} improved, {{regressed}} regressed",
      caseChanges: "Case Changes ({{count}})",
      case: "Case",
      status: "Status",
      scoreA: "Score A",
      scoreB: "Score B",
      improved: "↑ Improved",
      regressed: "↓ Regressed",
      added: "+ Added",
      removed: "− Removed",
      unchanged: "→ Unchanged",
      significant: "Significant",
      notSignificant: "Not significant",
      unknownSig: "Insufficient data",
    },
    caseTable: {
      case: "Case",
      difficulty: "Difficulty",
      status: "Status",
      score: "Score",
      capabilities: "Capabilities",
      cost: "Cost",
      tokens: "Tokens",
      pass: "PASS",
      fail: "FAIL",
    },
    capabilityTable: {
      capability: "Capability",
      score: "Score",
      passed: "Passed",
      total: "Total",
      passRate: "Pass Rate",
    },
    difficultyTable: {
      difficulty: "Difficulty",
      score: "Score",
      passed: "Passed",
      total: "Total",
      passRate: "Pass Rate",
    },
    comparison: {
      title: "Adapter Comparison",
      subtitle: "Side-by-side comparison across capabilities",
      score: "Score",
      passRate: "Pass Rate",
      ci: "95% CI",
      best: "Best",
      significant: "Significant",
      notSignificant: "Not significant",
      unknown: "—",
      scorePerDollar: "Score / $",
      scorePerMTokens: "Score / 1M tokens",
      costEffectiveness: "Cost Effectiveness",
      noCostData: "No cost data available",
    },
    failure: {
      title: "Failure Analysis",
      subtitle: "Aggregated failure patterns across runs",
      byCapability: "By Capability",
      byCheckType: "By Check Type",
      byError: "By Error Pattern",
      failureRate: "Failure Rate",
      failed: "Failed",
      total: "Total",
      noFailures: "No failures found",
      checkKind: "Check Kind",
      count: "Count",
      errorPattern: "Error Pattern",
      topFailed: "Top Failed Capabilities",
    },
    theme: {
      toggle: "Toggle theme",
    },
    language: {
      toggle: "Toggle language",
    },
  },

  zh: {
    app: {
      footer: "ckl-bench · 自动生成的评测报告",
      empty: {
        title: "暂无数据",
        subtitle: "{{page}} 页面暂无数据可展示。",
      },
    },
    common: {
      score: "得分",
      passed: "通过",
      total: "总计",
      cost: "费用",
      tokens: "Token",
      status: "状态",
      detail: "详情",
      run: "运行",
      runAgain: "重新运行",
      running: "运行中...",
      launching: "启动中...",
      runAll: "全部运行",
      view: "查看",
      save: "保存更改",
      saving: "保存中...",
      cancel: "取消",
      test: "测试",
      testing: "测试中...",
      cases: "用例",
      capabilities: "能力",
      ci: "95% 置信区间: [{{low}}, {{high}}]",
      copied: "已复制: {{value}}",
    },
    bench: {
      title: "评测集合",
      reports: "报告",
      overview: "概览",
      heatmap: "热力图",
      allRuns: "全部运行",
      scoreTrend: "得分趋势",
      capabilityHeatmap: "能力热力图",
      cases: "{{count}} 个用例",
      noAdapters: "未选择活跃适配器，请在设置中配置适配器。",
      settings: "设置",
    },
    pack: {
      recentRuns: "最近运行",
      cases: "用例 ({{count}})",
      timeout: "{{seconds}} 秒超时",
      passed: "{{passed}}/{{total}} 通过",
      progress: "{{completed}}/{{total}}",
      chat: "API 和聊天用例，涵盖推理、数学、代码和长尾知识。",
      agent: "智能体用例，含临时工作区和产物检查。",
      "doc-writing": "文档写作：API 文档、README、更新日志。",
      "infra-code": "基础设施代码：Docker、systemd、nginx、部署脚本。",
      "paper-reading": "论文阅读：摘要理解、方法对比、结果分析。",
    },
    runDetail: {
      title: "运行详情",
      score: "得分",
      passed: "通过",
      cost: "费用",
      tokens: "Token",
      cases: "用例 ({{count}})",
      loading: "加载运行中...",
      empty: "本次运行暂无可用的用例结果。",
    },
    caseEditor: {
      title: "编辑用例",
      id: "ID",
      type: "类型",
      caseTitle: "标题",
      prompt: "提示词",
      expectations: "期望值 (JSON)",
      capability: "能力",
      difficulty: "难度",
      timeout: "超时（秒）",
      capabilityPh: "reasoning, code",
      difficultyPh: "easy / medium / hard",
      invalidJson: "期望值必须是合法的 JSON 数组",
      loading: "加载用例中...",
    },
    settings: {
      title: "设置",
      activeAdapters: "活跃适配器",
      activeDesc: "选择要并排评测的适配器。",
      command: "命令",
      commandPh: "dsx\n# 或任意 bash 命令",
      apiKey: "API Key",
      apiKeyPh: "sk-...",
      baseUrl: "基础地址",
      model: "模型",
      modelPh: "例如 deepseek-v4-flash",
      testingCommand: "测试中: {{command}}",
      testOk: "正常 — 命令响应成功",
      testCancelled: "已被用户取消",
      defaultOptions: "默认选项",
      repeat: "重复次数",
      concurrency: "并发数",
      seed: "随机种子",
      judge: "评判模型",
      judgePh: "例如 deepseekv4（可选）",
      reviewer: "复核模型",
      reviewerPh: "例如 claude-sonnet（可选，挑战评判）",
      verifier: "验证模型",
      verifierPh: "例如 gpt-4o（可选，最终裁定）",
      save: "保存设置",
      saving: "保存中...",
    },
    runTable: {
      runId: "运行 ID",
      adapter: "适配器",
      score: "得分",
      passed: "通过",
      total: "总计",
      passRate: "通过率",
      cost: "费用",
      tokens: "Token",
    },
    analysis: {
      strongest: "最强能力",
      weakest: "最弱能力",
      mostImproved: "进步最大",
      regressed: "退步",
      overall: "总得分",
      strongestDesc: "{{score}} ({{passed}}/{{count}})",
      vsPrev: "对比上一次运行 ({{prev}} → {{curr}})",
      overallDesc: "{{passed}}/{{total}} 个用例通过",
    },
    trend: {
      score: "得分",
      passRate: "通过率",
    },
    dashboard: {
      title: "仪表盘",
      collected: "已收集 {{count}} 次运行",
      scoreTrend: "得分趋势",
      heatmap: "能力热力图",
      allRuns: "全部运行",
    },
    report: {
      title: "评测报告",
      run: "运行",
      passed: "{{passed}}/{{total}} 通过",
      repeat: "重复={{repeat}}",
      score: "得分",
      passRate: "通过率",
      passAt1: "Pass@1",
      passAtK: "Pass@{{k}}",
      usage: "用量",
      totalTokens: "总 Token",
      inputTokens: "输入 Token",
      outputTokens: "输出 Token",
      cost: "费用",
      capabilities: "能力",
      difficulty: "难度",
      cases: "用例 ({{count}})",
    },
    probe: {
      title: "探测报告",
      summary: "{{count}} 项探测",
      passed: "通过",
      failed: "失败",
      skipped: "跳过",
      passedDesc: "{{total}} 项中通过 {{count}} 项",
      failedDesc: "{{total}} 项中失败 {{count}} 项",
      skippedDesc: "{{total}} 项中跳过 {{count}} 项",
      results: "探测结果",
      target: "目标",
      kind: "类型",
      status: "状态",
      score: "得分",
      detail: "详情",
      pass: "通过",
      fail: "失败",
      skip: "跳过",
    },
    diff: {
      title: "运行对比",
      runA: "运行 A",
      runB: "运行 B",
      delta: "差值",
      summary: "{{improved}} 项改善，{{regressed}} 项退步",
      caseChanges: "用例变化 ({{count}})",
      case: "用例",
      status: "状态",
      scoreA: "得分 A",
      scoreB: "得分 B",
      improved: "↑ 改善",
      regressed: "↓ 退步",
      added: "+ 新增",
      removed: "− 移除",
      unchanged: "→ 无变化",
      significant: "显著",
      notSignificant: "不显著",
      unknownSig: "数据不足",
    },
    caseTable: {
      case: "用例",
      difficulty: "难度",
      status: "状态",
      score: "得分",
      capabilities: "能力",
      cost: "费用",
      tokens: "Token",
      pass: "通过",
      fail: "失败",
    },
    capabilityTable: {
      capability: "能力",
      score: "得分",
      passed: "通过",
      total: "总计",
      passRate: "通过率",
    },
    difficultyTable: {
      difficulty: "难度",
      score: "得分",
      passed: "通过",
      total: "总计",
      passRate: "通过率",
    },
    comparison: {
      title: "适配器对比",
      subtitle: "跨能力并排对比",
      score: "得分",
      passRate: "通过率",
      ci: "95% 置信区间",
      best: "最佳",
      significant: "显著",
      notSignificant: "不显著",
      unknown: "—",
      scorePerDollar: "得分 / 美元",
      scorePerMTokens: "得分 / 百万 Token",
      costEffectiveness: "性价比",
      noCostData: "暂无费用数据",
    },
    failure: {
      title: "失败分析",
      subtitle: "跨运行的聚合失败模式",
      byCapability: "按能力",
      byCheckType: "按检查类型",
      byError: "按错误模式",
      failureRate: "失败率",
      failed: "失败",
      total: "总计",
      noFailures: "暂无失败",
      checkKind: "检查类型",
      count: "数量",
      errorPattern: "错误模式",
      topFailed: "高频失败能力",
    },
    theme: {
      toggle: "切换主题",
    },
    language: {
      toggle: "切换语言",
    },
  },
};

function resolve(obj: Record<string, Trans>, key: string): string {
  const parts = key.split(".");
  let cur: Trans = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object") return key;
    cur = cur[p];
  }
  return typeof cur === "string" ? cur : key;
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = React.createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = React.useState<Locale>(() => {
    if (typeof window === "undefined") return "en";
    const stored = localStorage.getItem("ckl-bench-locale") as Locale | null;
    if (stored === "en" || stored === "zh") return stored;
    return navigator.language?.startsWith("zh") ? "zh" : "en";
  });

  React.useEffect(() => {
    localStorage.setItem("ckl-bench-locale", locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const t = React.useCallback(
    (key: string, params?: Record<string, string | number>) => {
      let s = resolve(translations[locale], key);
      if (params) {
        s = s.replace(/{{(\w+)}}/g, (_, k) =>
          params[k] != null ? String(params[k]) : ""
        );
      }
      return s;
    },
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = React.useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

export function useT() {
  return useI18n().t;
}

export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n();
  const next: Locale = locale === "en" ? "zh" : "en";
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setLocale(next)}
      aria-label={t("language.toggle")}
      title={next === "en" ? "English" : "中文"}
    >
      <Languages className="h-4 w-4" />
    </Button>
  );
}
