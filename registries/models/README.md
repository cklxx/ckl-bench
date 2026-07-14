# Model Namespaces

Model namespace registrations live here as plain JSONL config files. A namespace
is the stable top-level id users run, such as `deepseekv4`. Each line is one
target, so adding a new endpoint is append-only.

```bash
uv run ckl namespaces
uv run ckl namespaces deepseekv4
uv run ckl run deepseekv4 chat
uv run ckl probe deepseekv4
```

Minimal line:

```jsonl
{"namespace":"deepseekv4","aliases":["dsv4"],"target":"public","default":true,"adapter":"openai","base_url":"${DSV4_BASE_URL:-https://api.deepseek.com}","model":"${DSV4_MODEL:-deepseek-v4-flash}","max_tokens":"${DSV4_MAX_TOKENS:-2048}","api_key_env":["DSV4_API_KEY","DEEPSEEK_API_KEY"],"probe":{"case_set":"chat","limit":1}}
```

String values support `${ENV}` and `${ENV:-default}` placeholders. API keys stay
in `.env` or shell env, not in JSON.
