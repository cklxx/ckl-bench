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
- `DSV4_BASE_URL`, `DSV4_MODEL`, `DSV4_API_KEY`, `DEEPSEEK_API_KEY`

DSv4:

```bash
DSV4_BASE_URL=https://api.deepseek.com
DSV4_MODEL=deepseek-v4-flash
DSV4_API_KEY=
```

For the public DeepSeek API, `DSV4_BASE_URL` is `https://api.deepseek.com`.
For an internal tunnel, it must be the OpenAI-compatible HTTP endpoint. Do not
point it at the tn SSH port.
