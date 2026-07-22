# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **React frontend**: reports, dashboards, probe results, and diffs are now
  rendered by a React 19 + TypeScript single-page app (`web/`), built with Vite
  and inlined into a self-contained HTML file via `vite-plugin-singlefile`. The
  UI uses shadcn/ui (Radix UI primitives), Tailwind CSS, Recharts, and
  lucide-react, with HSL design tokens and dark mode support. The Python side
  injects data as `window.__CKL_BENCH_DATA__`; the pre-built template is
  bundled at `ckl_bench/web/index.html` so the package works out of the box.
- **Dashboard**: `ckl dashboard` scans `runs/`, aggregates all run summaries,
  and writes an interactive HTML dashboard (`runs/dashboard.html`) with a run
  overview table, a score-trend sparkline, a capability heatmap, and automatic
  data analysis (strongest/weakest capabilities, improving/regressing trends,
  cost summary). `--open` launches it in a browser.
- **Three domain case packs** (12 new cases, all hard and checkable):
  - `cases/doc-writing/doc_writing.jsonl`: API documentation, README from a
    project tree, changelog from commits, user guide from a CLI spec. Each has
    `not_contains` checks to prevent hallucination.
  - `cases/infra-code/infra_code.jsonl`: multi-stage Dockerfile, hardened
    systemd service, nginx reverse proxy with TLS/rate limiting, deployment
    shell script.
  - `cases/paper-reading/paper_reading.jsonl`: abstract comprehension, method
    comparison, result interpretation with arithmetic, contribution/limitation
    extraction.
- **TUI coding CLI targets**: `codex` and `dsx` are now first-class runnable
  targets (`ckl run codex agent`, `ckl run dsx agent`), each backed by a
  wrapper script (`scripts/codex_wrapper.py`, `scripts/dsx_wrapper.py`) that
  isolates workspaces, handles timeouts, and follows the JSON stdin/stdout
  contract. Override the binary with `CKL_CODEX_COMMAND` / `CKL_DSX_COMMAND`.
- **Case set aliases**: `doc-writing`, `infra-code`, `paper-reading` added to
  `ckl list`, `ckl run`, `ckl validate`.
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
  `Retry-After` handling on transient API errors (`CKL_MAX_RETRIES`, ...).
- **Caching**: opt-in content-addressed response cache (`--cache`,
  `CKL_CACHE_DIR`) for free, deterministic reruns of chat cases (`core/cache.py`).
- **Usage & cost**: per-case token usage captured from provider responses and
  dollar-cost estimates from an overridable price table (`core/usage.py`,
  `CKL_PRICING_FILE`).
- **Reproducibility**: every `summary.json` carries a manifest — git SHA, seed,
  model + params, dataset content hashes, schema version, and timestamps.
- **Run comparison**: `ckl diff RUN_A RUN_B` classifies cases as
  regressed/improved/unchanged/added/removed, with `--fail-on-regression`.
- **CI gate**: `ckl run --fail-under FRACTION`.
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
- Checkout wrapper scripts are thin package shims; the duplicate
  `scripts/_common.py` implementation was removed without changing wrapper
  runtime, security, or stdin/stdout contracts.
- Root `cases/`, `configs/`, and `registries/` are canonical. A deterministic
  stdlib sync/check command generates package resources and CI rejects drift.
- Frontend builds now require Node 20.19+ or Node 22.12+ (`.nvmrc` pins Node 22),
  and CI verifies the rebuilt single-file HTML exactly matches the packaged
  template.
- Release CI installs the wheel in a clean directory and runs validate, smoke,
  registry, packaged-resource, frontend-availability, and entry-point checks.
- Result schema is now `1.3`: scoring, execution-error, repeat, cost, and
  comparability policies are explicit. Adapter failures cannot aggregate into a
  passing case, unknown pricing remains unknown, and regression gates reject
  incompatible or legacy comparisons.
- Run management now uses collision-safe IDs, attempt-aware progress,
  cooperative cancellation, transactional SQLite indexing, deterministic cache
  rebuilds, and graceful HTTP/WebSocket/database/logging shutdown.
- The dashboard now owns one canonical settings state, supports case create and
  delete, provider discovery, targeted progress polling, and cancellation.
- Default cases, configuration, provider registries, and agent wrappers are
  packaged in the wheel and resolved with `importlib.resources`; clean-wheel
  smoke runs work outside a source checkout.
- Confidence intervals remain visible as descriptive uncertainty; the UI no
  longer labels interval overlap as a hypothesis test or `p < 0.05` result.
- API adapters (OpenAI-compatible, Anthropic, Gemini, HTTP-JSON) now route
  through the shared retrying HTTP helper and report token usage.

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
- `ckl` (alias `evb`) / `ckl-bench` CLI: `run`, `list`, `validate`, `smoke`, `probe`,
  `namespaces`.
- Terminal score bars plus a one-glance HTML scorecard and a probe readiness
  dashboard per run.
