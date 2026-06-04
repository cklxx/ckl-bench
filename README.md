# eval

Personal evaluation cases for model and agent capabilities that are not well
covered by mainstream benchmarks.

The repository is intentionally small and dependency-light, yet built to a
[top-tier eval standard](docs/STANDARD.md):

- `uv run evb ...` works after cloning the repo — **stdlib-only core, zero
  required installs**.
- `uv run evalbench ...` and `python -m evalbench ...` remain compatible.
- Cases are JSONL files under `cases/`.
- Results are JSONL, summary JSON, and an **interactive** `report.html` under
  `runs/` (filter, search, per-case drill-down).
- Model APIs and agent frameworks plug in through adapters (urllib, no SDKs).
- **Statistics by default**: Wilson + bootstrap confidence intervals on every
  score, with `--repeat N` for unbiased `pass@k` and `pass^k` reliability.
- **Execution-based grading**: grade agent/code output by *running* it in a
  sandbox, not by matching strings.
- **Fast and cheap to iterate**: `--concurrency N` parallelism, retry/backoff on
  transient API errors, an opt-in `--cache`, and token + dollar cost tracking.
- **Reproducible & comparable**: every run records a manifest (git SHA, seed,
  model+params, dataset hash); `evb diff` flags regressions between runs.
- Optional judge-model grading is available for semantic checks.

## Quick Start

```bash
cp .env.example .env
uv run evb smoke
uv run evb list
uv run evb run chat
uv run evb run command agent
uv run evb probe
uv run evb namespaces
```

Run a mainstream API:

```bash
# Put API keys in .env, or export them in your shell.
uv run evb run openai:gpt-4.1-mini chat

export ANTHROPIC_API_KEY=...
uv run evb run anthropic:claude-3-5-haiku-latest chat

export GEMINI_API_KEY=...
uv run evb run gemini:gemini-3.5-flash chat

export OPENROUTER_API_KEY=...
uv run evb run openrouter:openai/gpt-4.1-mini chat

uv run evb run deepseekv4 chat
uv run evb run deepseekv4 chat --judge deepseekv4
```

Run at scale with statistics, parallelism, caching, and a CI gate:

```bash
# Repeat each case 5x for pass@k / pass^k, 8 in parallel, cache responses.
uv run evb run openai:gpt-4.1-mini chat --repeat 5 --concurrency 8 --cache

# Gate CI on score, and compare two runs to catch regressions.
uv run evb run deepseekv4 chat --run-name baseline --fail-under 0.6
uv run evb diff runs/baseline runs/candidate --fail-on-regression
```

Use any local agent framework by wrapping it as a command:

```bash
uv run evb run command agent --command "python path/to/your_agent_wrapper.py"
uv run evb run claude-code agent
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

`uv run evb probe` gives a compact readiness table for OpenAI,
Anthropic, Gemini, OpenRouter, local OpenAI-compatible servers, and command
agent bridges. Missing keys or wrappers are marked `skip`, not `fail`.

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
evalbench/core/         Runner, grading, reporting, stats, sandbox, cache, usage, compare
evalbench/adapters/     Model + agent adapters (urllib, no SDKs) and shared HTTP retry
cases/chat/             Chat or API-only case packs
cases/agent/            Agent cases with temporary workspaces and artifact checks
configs/                Example adapter configs
registries/models/      Plain JSONL model namespace configs
docs/                   Standard, case schema, adapter, env, and probe docs
scripts/                Example command adapter wrappers
tests/                  Stdlib unittest suite
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
Braintrust, and the agent-benchmark family), each scored 0–3, with evalbench's
level and the target tracked in the scorecard.

See [docs/STANDARD.md](docs/STANDARD.md),
[docs/CASE_SCHEMA.md](docs/CASE_SCHEMA.md),
[docs/ADAPTERS.md](docs/ADAPTERS.md), [docs/PROBES.md](docs/PROBES.md), and
[docs/ENV.md](docs/ENV.md). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
