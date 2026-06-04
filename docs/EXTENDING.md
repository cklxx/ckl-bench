# Extending evalbench

evalbench is built around two small extension points: **adapters** (where a model
or agent plugs in) and **graders** (how an output becomes a score). Both stay
dependency-light and are designed for drop-in extension.

## Custom adapters

An adapter is any class with a `name` attribute and a `generate` method:

```python
from evalbench.adapters.base import GenerateRequest, GenerateResponse

class MyAdapter:
    name = "my-adapter"

    def __init__(self, config: dict):
        self.model = config.get("model")
        self.temperature = config.get("temperature", 0)
        self.max_tokens = config.get("max_tokens")

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        text = call_my_model(request.messages)
        return GenerateResponse(
            text=text,
            raw=...,
            # Set this shape and you get token + dollar tracking for free:
            metadata={"model": self.model, "usage": {
                "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            }},
        )
```

Load it without touching the repo:

```bash
uv run evb run --adapter mypkg.adapters:MyAdapter --config my_config.json chat
```

The `model`, `temperature`, and `max_tokens` attributes (when present) flow into
the run manifest and the cache key automatically.

To register a built-in shorthand instead, add it to the `BUILT_INS` map in
`evalbench/adapters/registry.py`.

## Custom graders

### Trusted Python grader (no code change)

The `python` expectation calls any importable callable:

```json
{"kind": "python", "callable": "my_graders.module:grade"}
```

It receives `case`, `response_text`, `workspace_path`, and `expectation`, and
returns a bool or `{"passed": true, "score": 1.0, "detail": "why"}`.

### Adding a new built-in expectation kind

Built-in graders live in `evalbench/core/grading.py`. The registry is the
`_evaluate` dispatcher: each `kind` is one branch returning an `_EvalOutcome`
(`passed`, `score_fraction` in `[0, 1]`, `detail`). To add one:

1. Add a `if kind == "my_kind":` branch in `_evaluate`.
2. Use `_target_text(...)` to read the response or a workspace file
   (`{"target": "file", "path": "..."}` is handled for you).
3. Return `_bool_outcome(passed, detail)` or an `_EvalOutcome` with a partial
   `score_fraction`.
4. Add a unit test in `tests/test_grading.py`.

Grader errors are caught and recorded as a failing check with the message, so a
buggy grader never crashes a run.

### Current built-in kinds

`contains`, `not_contains`, `exact`, `regex`, `json_path`, `numeric`,
`set_equals`, `choice`, `file_exists`, `file_contains`, `file_regex`,
`code_test`, `python`, `judge`. See [CASE_SCHEMA.md](CASE_SCHEMA.md) for each.

## Model namespaces

Register reusable provider configs as JSONL under `registries/models/` with
`${ENV:-default}` expansion — no code required. See
[ADAPTERS.md](ADAPTERS.md) and `registries/models/README.md`.
