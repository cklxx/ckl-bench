# Adapters

Adapters isolate the runner from model APIs and agent frameworks. The runner
ships with mainstream API adapters, a universal command adapter, and custom
Python adapter loading.

All built-in HTTP adapters (OpenAI-compatible, Anthropic, Gemini, HTTP-JSON)
share one helper (`evalbench/adapters/_http.py`) that retries transient failures
(429 / 5xx / timeouts) with exponential backoff and jitter, honoring
`Retry-After`. They also report token usage in `GenerateResponse.metadata`
(`{"usage": {"input_tokens", "output_tokens", "total_tokens"}}`), which the
runner sums into `summary.json` and converts to dollar cost. A custom adapter
that sets the same `metadata["usage"]` shape gets usage/cost tracking for free.
See [docs/ENV.md](ENV.md) for `EVB_MAX_RETRIES` and pricing overrides.

## Mock

Useful for smoke tests and case authoring:

```bash
uv run evb run chat
uv run evb run mock chat --config configs/mock.responses.json
```

Config:

```json
{
  "responses": {
    "case.id": "response text"
  },
  "default_response": "optional fallback",
  "echo": true
}
```

## OpenAI-Compatible

Works with OpenAI and compatible `/chat/completions` providers:

```bash
# OPENAI_API_KEY can live in .env.
uv run evb run openai:gpt-4.1-mini chat
```

Config keys:

- `base_url`: Defaults to `OPENAI_BASE_URL`, then `https://api.openai.com/v1`.
- `api_key`: Optional direct key. Prefer environment variables.
- `api_key_env`: Custom environment variable name.
- `model`: Required unless `EVAL_MODEL` is set.
- `temperature`: Defaults to `0`.
- `max_tokens`: Optional.
- `extra_body`: Extra JSON fields sent to the API.

OpenRouter and local OpenAI-compatible servers use the same adapter:

```bash
export OPENROUTER_API_KEY=...
uv run evb run openrouter:openai/gpt-4.1-mini chat

export EVAL_LOCAL_BASE_URL=http://127.0.0.1:8000/v1
export EVAL_LOCAL_MODEL=local-model
uv run evb run local chat
```

Named model namespaces can be registered as plain JSONL under `registries/models/`:

```bash
uv run evb namespaces
uv run evb namespaces deepseekv4
uv run evb run deepseekv4 chat
uv run evb probe deepseekv4
```

The DSv4 registration defaults to public DeepSeek API settings from the official
docs: `DSV4_BASE_URL=https://api.deepseek.com` and
`DSV4_MODEL=deepseek-v4-flash`. Fill either `DSV4_API_KEY` or
`DEEPSEEK_API_KEY`. For an internal tunnel, override `DSV4_BASE_URL` with the
OpenAI-compatible HTTP endpoint, not the tn SSH port.

## Anthropic

```bash
export ANTHROPIC_API_KEY=...
uv run evb run anthropic:claude-3-5-haiku-latest chat
```

Config keys:

- `base_url`: Defaults to `https://api.anthropic.com`.
- `api_key`: Optional direct key. Prefer `ANTHROPIC_API_KEY`.
- `model`: Required unless `ANTHROPIC_MODEL` is set.
- `anthropic_version`: Defaults to `2023-06-01`.
- `temperature`: Defaults to `0`.
- `max_tokens`: Defaults to `512`.

## Gemini

```bash
export GEMINI_API_KEY=...
uv run evb run gemini:gemini-3.5-flash chat
```

Config keys:

- `base_url`: Defaults to `https://generativelanguage.googleapis.com/v1beta`.
- `api_key`: Optional direct key. Prefer `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
- `model`: Required unless `GEMINI_MODEL` is set.
- `temperature`: Defaults to `0`.
- `max_tokens`: Optional.

## Generic HTTP JSON

For APIs that are not exactly OpenAI-compatible:

```bash
uv run evb run http-json chat --config configs/http-json.example.json
```

The adapter posts:

```json
{
  "model": "model-name",
  "messages": [{"role": "user", "content": "..."}],
  "prompt": "...",
  "case_id": "case.id",
  "metadata": {}
}
```

Use `text_path` to select the response text from returned JSON, for example
`choices.0.message.content` or `text`.

## Command Agent

This is the universal bridge for agent frameworks.

```bash
uv run evb run command agent
uv run evb run command agent --command "python scripts/command_agent_example.py"
uv run evb run claude-code agent
```

The command receives stdin:

```json
{
  "case_id": "agent.fix_binary_search_off_by_one.v1",
  "messages": [{"role": "user", "content": "..."}],
  "prompt": "...",
  "workspace_path": "/tmp/evalbench-agent.fix_binary_search_off_by_one.v1-...",
  "metadata": {},
  "timeout_s": 30
}
```

The command may print plain text or JSON:

```json
{"text": "DONE"}
```

Wrap any framework by writing a small script that reads this payload, calls the
framework, edits `workspace_path` when needed, and prints the final answer.

For real agent CLIs, keep the wrapper explicit:

```bash
export EVAL_AGENT_COMMAND="python path/to/your_agent_wrapper.py"
uv run evb probe agent
```

`probe` also recognizes `EVAL_CODEX_COMMAND`, `EVAL_CLAUDE_COMMAND`, and
`EVAL_GEMINI_COMMAND` when you maintain separate wrappers.

### Claude Code Wrapper

`claude-code` uses `scripts/claude_code_wrapper.py`. The wrapper reads the
evalbench JSON payload, copies the ephemeral workspace into a stable inspect
directory, runs Claude Code there, then syncs files back for grading.

```bash
uv run evb run claude-code agent
uv run evb probe agent
```

Relevant env:

```bash
EVAL_CLAUDE_COMMAND=python scripts/claude_code_wrapper.py
EVB_CLAUDE_COMMAND=claude
EVB_CLAUDE_MODEL=deepseek-v4-flash
EVB_CLAUDE_WORKSPACE_DIR=.tmp-runs/claude-code-workspaces
DSV4_ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
```

The model endpoint must expose Anthropic Messages API format. The wrapper maps
`DSV4_API_KEY` or `DEEPSEEK_API_KEY` to `ANTHROPIC_API_KEY` before invoking
Claude Code.

## Judge Model

Cases can use `{"kind":"judge"}` expectations for semantic grading. The judge
uses the same target syntax as normal runs:

```bash
uv run evb run deepseekv4 chat --judge deepseekv4
EVB_JUDGE=deepseekv4 uv run evb run deepseekv4 chat
uv run evb run deepseekv4 chat --judge openai:gpt-4.1-mini
```

Use `--judge same` to reuse the tested adapter as the judge. API keys still live
in `.env` or shell env.

## Custom Python Adapter

Pass `module.path:ClassName` as `--adapter`.

```bash
uv run evb run --adapter mypkg.adapters:MyAdapter --config my_config.json
```

The class is initialized with the config dictionary and must implement:

```python
def generate(self, request) -> GenerateResponse:
    ...
```
