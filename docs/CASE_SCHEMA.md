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

- `contains`: Text or file contains a value.
- `not_contains`: Text or file does not contain a value.
- `exact`: Text or file exactly equals a value after trimming.
- `regex`: Text or file matches a regex.
- `json_path`: JSON text has a dotted path, optionally matching `equals` or `contains`.
- `file_exists`: Workspace file exists.
- `file_contains`: Workspace file contains a value.
- `file_regex`: Workspace file matches a regex.
- `python`: Calls a trusted local Python grader.

Use `{"target": "file", "path": "relative/path"}` with text expectations when
you want `contains`, `not_contains`, `exact`, or `regex` to inspect a workspace
file instead of the model response.

Python graders use:

```json
{"kind": "python", "callable": "my_graders.module:grade"}
```

The callable receives keyword arguments `case`, `response_text`,
`workspace_path`, and `expectation`. It may return a boolean or a dictionary
like `{"passed": true, "detail": "why"}`. Treat Python graders as trusted code.
