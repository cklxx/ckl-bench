# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Standard**: `docs/STANDARD.md` — a 13-dimension rubric for a top-tier eval
  repo, distilled from 12 leading frameworks, with a tracked scorecard.
- **Statistics**: Wilson confidence intervals and bootstrap CIs on every score,
  reported in `summary.json`, the terminal, and the HTML report (`core/stats.py`).
- **Repeats & sampling**: `--repeat N` runs each case N times and reports unbiased
  `pass@k` and `pass^k` reliability.
- **Execution-based grading**: a `code_test` grader runs candidate code in a
  sandboxed subprocess with timeout, resource limits, and a credential-stripped
  environment (`core/sandbox.py`).
- **More graders**: `numeric` (tolerance), `set_equals`, and `choice`/`mcq`.
- **Concurrency**: `--concurrency N` runs cases in parallel with deterministic
  result ordering.
- **Reliability**: shared HTTP layer with exponential backoff + jitter and
  `Retry-After` handling on transient API errors (`EVB_MAX_RETRIES`, ...).
- **Caching**: opt-in content-addressed response cache (`--cache`,
  `EVB_CACHE_DIR`) for free, deterministic reruns of chat cases (`core/cache.py`).
- **Usage & cost**: per-case token usage captured from provider responses and
  dollar-cost estimates from an overridable price table (`core/usage.py`,
  `EVB_PRICING_FILE`).
- **Reproducibility**: every `summary.json` carries a manifest — git SHA, seed,
  model + params, dataset content hashes, schema version, and timestamps.
- **Run comparison**: `evb diff RUN_A RUN_B` classifies cases as
  regressed/improved/unchanged/added/removed, with `--fail-on-regression`.
- **CI gate**: `evb run --fail-under FRACTION`.
- **Interactive report**: filter by status, search, and expand any case to see
  the response, per-check detail, usage, and repeat metrics.
- **Frontier-breaker pack** (`cases/chat/frontier_compute.jsonl`, 24 cases) plus a
  reproducible case factory (`scripts/frontier_cases.py`): 12 families of exact
  long-horizon computation (stack VM, 40-step cellular automaton, 30 composed
  permutations, 40-round xorshift, deep run-length decode, CRT, edge-of-2^53
  isqrt, 80-step pointer chasing, custom-precedence eval, Levenshtein, base
  arithmetic, modular exponentiation). Each answer is computed by cross-checked
  reference code and confirmed by independent re-implementations; an adversarial
  pass had three strong models attempt each blind, and several cases (e.g.
  `modexp`, `xorshift`) defeated even code-using agents (0/3 reproductions). Each
  case records `metadata.agent_solver_score` and `no_tool_difficulty`.
- **New hard case packs** (13 → 59 cases total), every one verified to
  discriminate (the correct artifact passes the grader, a wrong one fails):
  - `cases/chat/execution_graded.jsonl`: graded by *running* the model's code
    (balanced brackets with string-literal awareness, strict RFC 8259 JSON-number
    validator, RFC 4180 CSV parser, LRU recency, topological sort, union-find,
    interval merge, Unicode-aware palindrome, and more).
  - `cases/chat/language_semantics.jsonl`: cross-language and SQL semantics
    gotchas (Go typed-nil interface, Java Integer cache boundary, JS coercion,
    Python mutable default + closure late binding, `NOT IN` with NULL, default
    window RANGE frame, join cardinality, large-integer `isqrt`).
  - `cases/agent/execution_graded.jsonl`: execution-graded fixes (mutable default
    argument, path-traversal confinement, command-injection to arg-list).
- Per-case `metadata.version` and `metadata.release_date` on every case.
- `docs/EXTENDING.md`: how to add adapters and graders.
- `LICENSE` (MIT), `CONTRIBUTING.md`, and this `CHANGELOG.md`.
- GitHub Actions CI: validate cases, run unit tests, and smoke on Python
  3.10–3.13, plus a package build check.

### Changed
- API adapters (OpenAI-compatible, Anthropic, Gemini, HTTP-JSON) now route
  through the shared retrying HTTP helper and report token usage.
- `summary.json` / `results.jsonl` schema version is now `1.1` (additive).

## [0.1.0]

### Added
- Dependency-light, stdlib-only core runner for LLM and agent evaluation.
- JSONL case packs under `cases/chat` and `cases/agent` with hard,
  mainstream-gap programming cases.
- Adapters: mock, OpenAI-compatible, Anthropic, Gemini, generic HTTP JSON,
  command-agent bridge, and custom `module:Class` loading.
- Graders: `contains`, `not_contains`, `exact`, `regex`, `json_path`,
  `file_exists`, `file_contains`, `file_regex`, `python`, and LLM `judge`.
- Model namespace registries (`registries/models/*.jsonl`) with `${ENV:-default}`
  expansion and secret redaction.
- `evb` / `evalbench` CLI: `run`, `list`, `validate`, `smoke`, `probe`,
  `namespaces`.
- Terminal score bars plus a one-glance HTML scorecard and a probe readiness
  dashboard per run.
