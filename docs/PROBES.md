# Probes

`probe` checks whether the common model APIs and agent bridges are configured.
It is designed for fast onboarding: missing credentials are reported as `skip`
instead of failing the whole command.

```bash
cp .env.example .env
uv run evb probe
uv run evb probe api
uv run evb probe agent
uv run evb probe deepseekv4
```

API targets:

- `openai`: `OPENAI_API_KEY` or `EVAL_OPENAI_API_KEY`
- `anthropic`: `ANTHROPIC_API_KEY`
- `gemini`: `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- `openrouter`: `OPENROUTER_API_KEY`
- `local-openai`: `EVAL_LOCAL_BASE_URL`
- `deepseekv4`: registered in `registries/models/deepseekv4.jsonl`; override with
  `DSV4_BASE_URL`, `DSV4_MODEL`, and `DSV4_API_KEY`

Agent targets:

- `command-example`: built-in local smoke wrapper
- `env-agent`: `EVAL_AGENT_COMMAND`
- `codex-wrapper`: `EVAL_CODEX_COMMAND`
- `claude-wrapper`: `EVAL_CLAUDE_COMMAND`, defaulting to `scripts/claude_code_wrapper.py` when `claude` is on PATH
- `gemini-wrapper`: `EVAL_GEMINI_COMMAND`

The command adapter requires a JSON-stdin wrapper. Mainstream CLIs are detected,
but they are not run directly because their native stdin contracts differ and
may start real paid sessions. Wrap them explicitly and point one of the
environment variables above at the wrapper command.

Every probe writes:

- `runs/probe-*/probe.html`
- One nested `report.html` per executed target
- JSONL results for executed targets
