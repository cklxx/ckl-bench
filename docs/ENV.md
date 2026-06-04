# Environment

The CLI auto-loads `.env` from the repository root before running commands:

```bash
cp .env.example .env
uv run evb probe
```

The real `.env` file is gitignored. Keep API keys there or in your shell. Shell
environment variables win over `.env` values.

Model/provider structure belongs in `registries/models/*.jsonl`; API keys belong
in `.env`.

Use a custom env file:

```bash
EVB_ENV_FILE=/path/to/env uv run evb probe
```

Core keys:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
- `EVAL_LOCAL_BASE_URL`, `EVAL_LOCAL_MODEL`, `EVAL_LOCAL_API_KEY`
- `DSV4_BASE_URL`, `DSV4_ANTHROPIC_BASE_URL`, `DSV4_MODEL`, `DSV4_MAX_TOKENS`, `DSV4_API_KEY`, `DEEPSEEK_API_KEY`
- `EVB_JUDGE`
- `EVAL_CLAUDE_COMMAND`, `EVB_CLAUDE_COMMAND`, `EVB_CLAUDE_MODEL`, `EVB_CLAUDE_WORKSPACE_DIR`

Runner reliability, caching, and cost:

- `EVB_MAX_RETRIES` (default 3), `EVB_RETRY_BASE_DELAY` (default 0.5s),
  `EVB_RETRY_MAX_DELAY` (default 20s): exponential backoff with jitter on
  transient API errors (429 / 5xx / timeouts), honoring `Retry-After`.
- `EVB_CACHE=1` and `EVB_CACHE_DIR` (default `.evalbench_cache`): enable the
  content-addressed response cache (equivalent to `--cache` / `--cache-dir`).
  Only chat (no-workspace) cases are cached.
- `EVB_PRICING_FILE`: path to a JSON file of `{ "model": {"input": usd_per_1M,
  "output": usd_per_1M} }` overrides for dollar-cost estimates.

Run flags that have no env equivalent: `--repeat N` (pass@k / pass^k),
`--concurrency N` (parallel cases), `--seed` (deterministic bootstrap CIs),
`--fail-under FRACTION` and `--fail-on-failed-cases` (CI gates).

DSv4:

```bash
DSV4_BASE_URL=https://api.deepseek.com
DSV4_ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
DSV4_MODEL=deepseek-v4-flash
DSV4_MAX_TOKENS=2048
DSV4_API_KEY=
```

For the public DeepSeek API, `DSV4_BASE_URL` is `https://api.deepseek.com`.
For an internal tunnel, it must be the OpenAI-compatible HTTP endpoint. Do not
point it at the tn SSH port.

Judge model:

```bash
EVB_JUDGE=deepseekv4
```

`EVB_JUDGE` is optional. It is used only for case expectations with
`{"kind":"judge"}`. The command-line `--judge` flag overrides it.

Claude Code wrapper:

```bash
EVAL_CLAUDE_COMMAND=python scripts/claude_code_wrapper.py
EVB_CLAUDE_COMMAND=claude
EVB_CLAUDE_MODEL=deepseek-v4-flash
EVB_CLAUDE_WORKSPACE_DIR=.tmp-runs/claude-code-workspaces
```

The wrapper maps `DSV4_API_KEY` or `DEEPSEEK_API_KEY` into
`ANTHROPIC_API_KEY`, and maps `DSV4_ANTHROPIC_BASE_URL` into
`ANTHROPIC_BASE_URL`. The endpoint must support the Anthropic Messages API
format; an OpenAI `/chat/completions` endpoint is not enough.
