# eval

Personal evaluation cases for model and agent capabilities that are not well
covered by mainstream benchmarks.

The repository is intentionally small and dependency-light:

- `uv run evb ...` works after cloning the repo.
- `uv run evalbench ...` and `python -m evalbench ...` remain compatible.
- Cases are JSONL files under `cases/`.
- Results are JSONL, summary JSON, and a visual `report.html` under `runs/`.
- Model APIs and agent frameworks plug in through adapters.

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
```

Use any local agent framework by wrapping it as a command:

```bash
uv run evb run command agent --command "python path/to/your_agent_wrapper.py"
```

The command receives one JSON object on stdin and should print either plain text
or JSON like `{"text": "final answer"}`. For agent cases it also receives a
temporary `workspace_path` containing the files declared by the case.

## One-Glance Reports

Every run prints a score bar and writes `report.html`:

```text
Score  [############################]  100.0%
Cases  2/2 passed  |  failed 0  |  run runs/...

Capability
- private-longtail       [##################] 100.0%  2/2
```

`uv run evb probe` gives a compact readiness table for OpenAI,
Anthropic, Gemini, OpenRouter, local OpenAI-compatible servers, and command
agent bridges. Missing keys or wrappers are marked `skip`, not `fail`.

## Repository Layout

```text
evalbench/              Core runner, graders, and adapters
cases/chat/             Chat or API-only case packs
cases/agent/            Agent cases with temporary workspaces and artifact checks
configs/                Example adapter configs
registries/models/      Plain JSONL model namespace configs
docs/                   Case schema and adapter contracts
scripts/                Example command adapter wrappers
tests/                  Stdlib unittest smoke tests
```

## Design Principles

1. Fast first run: no required package install, no database, no service.
2. Portable: Python standard library only for the core runner.
3. Private-case friendly: cases are local JSONL files and can stay out of public
   benchmark taxonomies.
4. Adapter based: built-ins cover OpenAI-compatible APIs, generic HTTP JSON,
   command-line agents, mocks, and custom Python adapters.
5. Evidence oriented: every run writes per-case checks, raw response text, and a
   machine-readable summary.

See [docs/CASE_SCHEMA.md](docs/CASE_SCHEMA.md),
[docs/ADAPTERS.md](docs/ADAPTERS.md), [docs/PROBES.md](docs/PROBES.md), and
[docs/ENV.md](docs/ENV.md).
