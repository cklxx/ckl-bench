# Case Schema

Cases are newline-delimited JSON objects. Each line is one independent case.

Required fields:

- `id`: Stable unique case id.
- `input`: Object with either `prompt` or `messages`.
- `expectations`: Non-empty list of grader expectations.

Recommended fields:

- `title`: Human-readable title.
- `type`: `chat` or `agent`.
- `capability`: String or list of capability tags.
- `difficulty`: Free-form tier such as `s1`, `s2`, or `hard`.
- `timeout_s`: Per-case timeout for adapters that support it.
- `metadata.mainstream_gap`: Why this case belongs in the private suite.
- `metadata.pass_threshold`: Normalized score required to pass. Defaults to `1.0`.
- `metadata.version`: Integer case version. Bump when you change the prompt or
  expectations so old runs are not compared to new ones.
- `metadata.release_date`: When the case was authored (e.g. `2026-06`). Enables
  contamination/cutoff reasoning across model knowledge cutoffs.
- `metadata.source_url`: Spec/doc URL when the correct answer is spec-defined.
- `metadata.smoke`: `true` to include the case in `ckl smoke`.

## Chat Case

```json
{
  "id": "chat.example.v1",
  "type": "chat",
  "capability": ["structured-output"],
  "input": {
    "messages": [
      {"role": "system", "content": "Return JSON only."},
      {"role": "user", "content": "Return {\"ok\": true}."}
    ]
  },
  "expectations": [
    {"kind": "json_path", "path": "ok", "equals": true}
  ]
}
```

## Agent Case

Agent cases may define an ephemeral workspace:

```json
{
  "id": "agent.example.v1",
  "type": "agent",
  "input": {
    "prompt": "Edit config.txt and print DONE.",
    "workspace": {
      "files": {
        "config.txt": "enabled=false\n"
      }
    }
  },
  "expectations": [
    {"kind": "file_contains", "path": "config.txt", "value": "enabled=true"},
    {"kind": "contains", "value": "DONE"}
  ]
}
```

## Built-In Expectations

Deterministic string/structured graders:

- `contains`: Text or file contains a value.
- `not_contains`: Text or file does not contain a value.
- `exact`: Text or file exactly equals a value after trimming.
- `regex`: Text or file matches a regex.
- `json_path`: JSON text has a dotted path, optionally matching `equals` or `contains`.
- `numeric` (alias `close`): Parse a number from the target and compare to
  `value` within `abs_tol` (default `1e-6`) and/or `rel_tol`. Add `path` to pull
  the number from a JSON field. Robust to prose like "the answer is 3.14".
- `set_equals`: Parse a JSON array from the target and compare as a set to
  `values` (order- and duplicate-insensitive). Add `path` to drill in.
- `choice` (alias `mcq`): Extract the selected option from the response (the last
  matching token among `choices`) and compare to `value`. Set
  `case_sensitive: true` to match exactly.

Workspace file graders:

- `file_exists`: Workspace file exists.
- `file_contains`: Workspace file contains a value.
- `file_regex`: Workspace file matches a regex.

Execution and custom graders:

- `code_test` (aliases `execute`, `run`): Run a Python `test` script (optionally
  prefixed with `setup`) inside the workspace and pass on exit code 0. This is
  the SWE-bench / LiveCodeBench standard: grade code by running it, not by
  matching strings. See below.
- `python`: Calls a trusted local Python grader.
- `judge` (alias `llm_judge`): Calls a configured judge model and expects JSON
  scoring.

Use `{"target": "file", "path": "relative/path"}` with text expectations when
you want `contains`, `not_contains`, `exact`, `regex`, `numeric`, `set_equals`,
or `choice` to inspect a workspace file instead of the model response.

## Execution-Based Grading

`code_test` runs the candidate's code and grades by exit status. It works two
ways:

For **agent cases** (a workspace exists), the test runs against the agent's
edited files:

```json
{
  "kind": "code_test",
  "test": "from bisect import bisect_left\nassert bisect_left([1,3,5], 6) == 3\nassert bisect_left([], 1) == 0\n",
  "timeout_s": 10
}
```

For **chat cases** that ask the model to write code, capture the response into a
file (optionally stripping a Markdown fence) and import it:

```json
{
  "kind": "code_test",
  "response_file": "solution.py",
  "extract_code": true,
  "setup": "from solution import solve",
  "test": "assert solve(10) == 55\n",
  "timeout_s": 10
}
```

Options: `setup`, `test` (or `code`), `response_file`, `extract_code`, `files`
(extra files to seed), `timeout_s`, `memory_mb`. The script runs in a subprocess
with a wall-clock timeout, best-effort CPU/memory limits (POSIX), and a
credential-stripped environment. For untrusted agents, run the whole evaluation
inside a container or VM.

Python graders use:

```json
{"kind": "python", "callable": "my_graders.module:grade"}
```

The callable receives keyword arguments `case`, `response_text`,
`workspace_path`, and `expectation`. It may return a boolean or a dictionary
like `{"passed": true, "detail": "why"}`. Treat Python graders as trusted code.

## Judge Model

Use judge checks when the expected answer is semantic rather than a stable
string or JSON value:

```json
{
  "id": "chat.semantic.example.v1",
  "input": {"prompt": "Name the invariant and the minimal repair."},
  "expectations": [
    {
      "kind": "judge",
      "criteria": "Score 1.0 only if the answer identifies idempotency and ties the repair to task_id reuse.",
      "threshold": 0.7
    }
  ],
  "metadata": {"pass_threshold": 0.7}
}
```

Run with:

```bash
uv run ckl run deepseekv4 chat --judge deepseekv4
CKL_JUDGE=deepseekv4 uv run ckl run deepseekv4 chat
```

The judge is prompted to return:

```json
{"score": 0.0, "passed": false, "reason": "short reason"}
```

`threshold` controls whether the judge check passes. `metadata.pass_threshold`
still controls whether the whole case passes after all weighted checks are
combined.
