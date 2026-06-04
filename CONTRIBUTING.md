# Contributing

evalbench is a small, dependency-light evaluation runner. Contributions that
keep it fast, portable, and evidence-oriented are very welcome.

## Non-negotiable design constraints

1. **Stdlib-only core.** Everything under `evalbench/core/` and the built-in
   adapters must run on a clean CPython (>=3.10) with no third-party packages.
   Optional power features may use extras, but a fresh clone must always pass
   `python -m evalbench smoke` with zero installs.
2. **Fast first run.** No required database, service, or network for the smoke
   path. Missing credentials are reported as `skip`, never `fail`.
3. **Evidence first.** Every run writes per-case checks, raw signal, and a
   machine-readable `summary.json`. Never hide a grader error — record it.
4. **Hard-case friendly.** If a model passes a case on its first serious try,
   the case is too easy. Graduate it or replace it with something harder.

## Local development

```bash
# No install needed for the stdlib core.
python -m evalbench validate           # validate every case file
python -m unittest discover -s tests   # run the unit tests
python -m evalbench smoke              # mock chat + command-agent smoke
```

`uv run evb ...` and `uv run evalbench ...` work after cloning.

## Adding a case

Cases are newline-delimited JSON under `cases/`. See
[docs/CASE_SCHEMA.md](docs/CASE_SCHEMA.md). Checklist:

- Stable, unique `id` (ends in a version suffix such as `.v1`).
- A concrete `metadata.mainstream_gap` explaining why a model might miss it.
- Deterministic, checkable expectations. Prefer `json_path`, `file_*`, or a
  code-execution grader over loose `contains` when the answer is verifiable.
- Record a `metadata.source_url` when the correct answer is spec-defined.
- Run `python -m evalbench validate` before sending.

## Adding an adapter

Implement the `ModelAdapter` protocol (`evalbench/adapters/base.py`):

```python
def generate(self, request: GenerateRequest) -> GenerateResponse: ...
```

Register built-ins in `evalbench/adapters/registry.py`, or load a custom one
with `--adapter module.path:ClassName`. See [docs/ADAPTERS.md](docs/ADAPTERS.md).

## Tests

Add or update a `tests/test_*.py` (stdlib `unittest`) for any behavior change.
CI runs `validate`, the unit tests, and `smoke` on Python 3.10–3.13.

## Pull requests

- Keep diffs focused; one capability per PR.
- Update the relevant doc under `docs/` and the `CHANGELOG.md` Unreleased
  section.
- Ensure `python -m evalbench smoke` and the unit tests pass.
