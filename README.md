# ckl-bench

ckl's personal benchmark for **doc writing**, **infra code**, and **paper
reading** — designed to one-click test the latest model capabilities via TUI
coding CLIs (claude code, codex, dsx), with interactive visualization and
automatic data analysis.

The repository is intentionally small and dependency-light, yet built to a
[top-tier eval standard](docs/STANDARD.md):

- `uv run ckl ...` works after cloning the repo — **stdlib-only core, zero
  required installs**.
- `uv run ckl-bench ...` and `python -m ckl_bench ...` remain compatible.
- Cases are JSONL files under `cases/` (chat, agent, doc-writing, infra-code,
  paper-reading).
- Results are JSONL, summary JSON, and an **interactive** `report.html` under
  `runs/` (filter, search, per-case drill-down).
- `ckl dashboard` aggregates all runs into an interactive HTML dashboard with
  score trends, a capability heatmap, and auto analysis.
- Model APIs and agent frameworks plug in through adapters (urllib, no SDKs).
- **TUI coding CLI agents**: run claude code, codex, and dsx as first-class
  targets (`ckl run codex agent`, `ckl run dsx agent`).
- **Statistics by default**: Wilson + bootstrap confidence intervals on every
  score, with `--repeat N` for unbiased `pass@k` and `pass^k` reliability.
- **Execution-based grading**: grade agent/code output by *running* it in a
  sandbox, not by matching strings.
- **Fast and cheap to iterate**: `--concurrency N` parallelism, retry/backoff on
  transient API errors, an opt-in `--cache`, and token + dollar cost tracking.
- **Reproducible & comparable**: every run records a redacted manifest and
  deterministic comparability signature. `ckl diff` fails closed when datasets,
  scoring policies, models, judges, or repeat settings differ.
- Optional judge-model grading is available for semantic checks.

## Quick Start

```bash
cp .env.example .env
uv run ckl smoke
uv run ckl list
uv run ckl run chat
uv run ckl run command agent
uv run ckl probe
uv run ckl namespaces
uv run ckl dashboard
uv run ckl serve            # interactive dashboard (live progress, case editor, run launcher)
```

Run the three domain benchmarks:

```bash
uv run ckl run doc-writing
uv run ckl run infra-code
uv run ckl run paper-reading
```

Run a mainstream API:

```bash
# Put API keys in .env, or export them in your shell.
uv run ckl run openai:gpt-4.1-mini chat

export ANTHROPIC_API_KEY=...
uv run ckl run anthropic:claude-3-5-haiku-latest chat

export GEMINI_API_KEY=...
uv run ckl run gemini:gemini-3.5-flash chat

export OPENROUTER_API_KEY=...
uv run ckl run openrouter:openai/gpt-4.1-mini chat

uv run ckl run deepseekv4 chat
uv run ckl run deepseekv4 chat --judge deepseekv4
```

Run TUI coding CLI agents (claude code, codex, dsx):

```bash
uv run ckl run claude-code agent
uv run ckl run codex agent
uv run ckl run dsx agent
```

Each agent target runs through a packaged wrapper module (`ckl_bench.wrappers`)
that isolates workspaces and follows the JSON stdin/stdout contract. The legacy
`scripts/*_wrapper.py` entrypoints remain thin checkout-compatible shims. Override
the binary with `CKL_CLAUDE_COMMAND`, `CKL_CODEX_COMMAND`, or `CKL_DSX_COMMAND`.

Run at scale with statistics, parallelism, caching, and a CI gate:

```bash
# Repeat each case 5x for pass@k / pass^k, 8 in parallel, cache responses.
uv run ckl run openai:gpt-4.1-mini chat --repeat 5 --concurrency 8 --cache

# Gate CI on score, and compare two runs to catch regressions.
uv run ckl run deepseekv4 chat --run-name baseline --fail-under 0.6
uv run ckl diff runs/baseline runs/candidate --fail-on-regression
```

Use any local agent framework by wrapping it as a command:

```bash
uv run ckl run command agent --command "python path/to/your_agent_wrapper.py"
```

The command receives one JSON object on stdin and should print either plain text
or JSON like `{"text": "final answer"}`. For agent cases it also receives a
temporary `workspace_path` containing the files declared by the case.

## One-Glance Reports

Every run prints a score bar and writes an interactive `report.html`:

```text
Score  [############################]  100.0%  95% CI [56.6, 100.0]
Cases  2/2 passed  |  failed 0  |  run runs/...
Reps   5x  |  pass@1 100.0%  pass@5 100.0%  pass^5 100.0%
Usage  1284 tokens (910 in / 374 out)  |  cost $0.0012

Capability
- private-longtail       [##################] 100.0%  2/2
```

`uv run ckl probe` gives a compact readiness table for OpenAI,
Anthropic, Gemini, OpenRouter, local OpenAI-compatible servers, and command
agent bridges (including codex and dsx wrappers). Missing keys or wrappers are
marked `skip`, not `fail`.

## Dashboard

`uv run ckl dashboard` scans the `runs/` directory, aggregates every run
summary, and writes `runs/dashboard.html` — an interactive overview with:

- **Run table**: every run's score, pass rate, adapter, model, tokens, cost.
- **Score trend**: a line chart across all runs (Recharts).
- **Capability heatmap**: per-capability scores across runs (green/yellow/red).
- **Auto analysis**: strongest and weakest capabilities (latest run), improving
  and regressing trends (last two runs).

```bash
uv run ckl dashboard                  # generate runs/dashboard.html
uv run ckl dashboard --open           # open in browser
uv run ckl dashboard --runs runs      # custom runs dir
```

## Interactive Dashboard

`ckl serve` starts a local server with a live, interactive dashboard — browse
and edit cases, launch evaluations, watch progress in real time, and see
auto-classified results with analysis.

```bash
uv run ckl serve                    # start server (http://127.0.0.1:8765)
uv run ckl serve --port 9000        # custom port
uv run ckl serve --host 0.0.0.0     # listen on all interfaces
uv run ckl serve --open             # open browser after start
uv run ckl serve stop               # stop a background server
uv run ckl serve status             # check if server is running
```

The dashboard has four pages:

- **Cases** — browse all cases by pack, create/edit/delete cases (full CRUD,
  persisted to `cases/` JSONL).
- **Launch** — select an adapter/provider, pick cases, set options (repeat,
  concurrency, seed, judge), and launch a run.
- **Progress** — live attempt-aware progress via WebSocket, with cooperative run
  cancellation. Falls back to polling only active runs when WebSocket is unavailable.
- **Reports** — aggregated run table, score trend chart, capability heatmap,
  and auto analysis (strongest/weakest capabilities, improving/regressing
  trends).

Install the optional `serve` extra for live WebSocket progress:

```bash
uv run --with ckl-bench[serve] ckl serve
```

Without it, the dashboard still works — the frontend polls the progress API
every 2 seconds.

## Web Frontend

Reports, dashboards, probe results, diffs, and the interactive server app are
rendered by a **React 19 + TypeScript** single-page app (`web/`), built with
Vite and inlined into a self-contained HTML file via
`vite-plugin-singlefile`. The Python side injects data as
`window.__CKL_BENCH_DATA__`; the app reads it and renders the appropriate page.

The UI uses **shadcn/ui** (Radix UI primitives), **Tailwind CSS**,
**Recharts**, and **lucide-react**, with HSL design tokens and dark mode
support.

```bash
cd web
npm install
npm run build:copy    # builds + copies dist/index.html into ckl_bench/web/
npm run dev           # live dev server (data falls back to empty state)
```

The pre-built template is committed at `ckl_bench/web/index.html`, so the
package works out of the box without building the frontend.

## Frontier-breaker cases

`cases/chat/frontier_compute.jsonl` is a pack designed to *defeat* the strongest
models. Each case requires the exact, deterministic execution of a long process
(a stack-machine trace, a 40-step cellular automaton, 30 composed permutations,
a 40-round xorshift, deep run-length decoding, CRT, edge-of-`2^53` integer math,
data-dependent pointer chasing, custom-precedence evaluation, and more) — work a
no-tool model cannot reliably do in its head, but that a literal reference
implementation computes exactly.

Every case is verified twice: its answer is computed by cross-checked reference
code (`scripts/frontier_cases.py`), and an adversarial filter has three
independent strong models attempt it blind (no tools) — only cases they fail are
kept, and each case records its `metadata.solver_accuracy` as difficulty
evidence. Regenerate fresh, contamination-free instances any time:

```bash
python scripts/frontier_cases.py --selfcheck                       # cross-verify the reference logic
python scripts/frontier_cases.py --out cases/chat/frontier_compute.jsonl
```

## Repository Layout

```text
ckl_bench/core/         Runner, grading, reporting, stats, sandbox, cache, usage, compare
ckl_bench/adapters/     Model + agent adapters (urllib, no SDKs) and shared HTTP retry
ckl_bench/web/          Pre-built React frontend template (index.html) — bundled
ckl_bench/resources/   Packaged default cases, mock config, and provider registries
ckl_bench/wrappers/    Packaged Claude Code, Codex, and DSX command bridges
cases/                 Writable checkout case packs and user overrides
configs/                Example adapter configs
registries/models/      Plain JSONL model namespace configs
docs/                   Standard, case schema, adapter, env, and probe docs
scripts/                Generators and checkout-compatible wrapper shims
tests/                  Stdlib unittest suite
web/                    React 19 + TypeScript frontend (Vite, shadcn/ui, Tailwind, Recharts)
.github/workflows/      CI: validate + tests + smoke + build on py3.10-3.13
```

## Design Principles

1. Fast first run: no required package install, no database, no service.
2. Portable: Python standard library only for the core runner.
3. Hard-case friendly: cases are local JSONL files; if a model passes a case on
   the first serious try, treat that case as simple and remove or graduate it.
4. Adapter based: built-ins cover OpenAI-compatible APIs, generic HTTP JSON,
   command-line agents, mocks, and custom Python adapters.
5. Evidence oriented: every run writes per-case checks, raw response text, and a
   machine-readable summary.

## What "top-tier" means here

[docs/STANDARD.md](docs/STANDARD.md) is the canonical rubric: 13 dimensions
distilled from the leading frameworks (lm-evaluation-harness, HELM, Inspect AI,
OpenAI evals, lighteval, promptfoo, DeepEval, Ragas, SWE-bench, LiveCodeBench,
Braintrust, and the agent-benchmark family), each scored 0–3, with ckl-bench's
level and the target tracked in the scorecard.

See [docs/STANDARD.md](docs/STANDARD.md),
[docs/CASE_SCHEMA.md](docs/CASE_SCHEMA.md),
[docs/ADAPTERS.md](docs/ADAPTERS.md), [docs/PROBES.md](docs/PROBES.md), and
[docs/ENV.md](docs/ENV.md). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
