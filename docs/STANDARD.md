# The Top-Tier Eval Repository Standard

This is the canonical standard evalbench measures itself against. It distills the
twelve leading evaluation frameworks — lm-evaluation-harness, HELM, Inspect AI,
OpenAI evals/simple-evals, lighteval, promptfoo, DeepEval, Ragas, SWE-bench,
LiveCodeBench, Braintrust+LangSmith, and the agent-benchmark family
(terminal-bench / tau-bench / GAIA / AgentBench) — into **13 dimensions**, each
with a 0–3 maturity scale.

- **0 — Absent**: not present.
- **1 — Basic**: minimal/naive; works but not defensible.
- **2 — Solid**: correct, usable, comparable to mid-tier OSS frameworks.
- **3 — World-class**: matches or exceeds the best framework in that dimension.

A non-negotiable constraint frames every "world-class" target:
**the core stays Python-stdlib-only, portable, fast on first run, and
evidence-oriented.** Heavyweight exemplars (torch / Docker / HF-datasets) are
inspiration for *behavior*, never for dependencies.

The per-dimension "evalbench" notes are a **dated assessment snapshot**
(first taken 2026-06-04); the scorecard at the end tracks progress. "Latent"
means a level reachable by wiring in code that already exists with no new deps.

---

## 1. Scoring & Grader Library

The breadth, correctness, and composability of the checks that turn an output
into a score: deterministic string/structured graders, numeric/set/choice,
logprob-based MCQ, execution-based grading, and model-graded (LLM-as-judge)
rubrics — all with explicit weights and a typed result.

World-class: Inspect AI's typed `Score` (CORRECT/PARTIAL/INCORRECT + answer +
explanation + metadata) over a scorer registry; promptfoo's uniform type-tagged
`assert` array with `not-` negation, per-assertion weight + threshold; DeepEval's
QAG verdict-counting; lm-eval-harness's logprob MCQ scoring (acc / acc_norm /
acc_mutual_info) needing no generation.

| Level | Description |
|---|---|
| 0 | Only exact/contains. |
| 1 | A few deterministic string/regex checks, weighted. |
| 2 | Deterministic + structured (json_path, file_*) + LLM-judge, typed results, weights, threshold. |
| 3 | Above + numeric-tolerance/set/choice + execution-based + logprob-MCQ + QAG-style judge; uniform assertion taxonomy with negation. |

---

## 2. Statistical Rigor (CIs, stderr, significance)

Every reported number ships with honest uncertainty, and run-vs-run deltas can be
called real or noise.

World-class: lm-eval-harness bootstrapped stderr per metric; Inspect AI analytic
CLT stderr + `bootstrap_stderr`; lighteval `_stderr` on every score. Paired
significance (McNemar / paired bootstrap) for A/B is rare across the field — a
place to *lead*.

| Level | Description |
|---|---|
| 0 | Bare pass rate only. |
| 1 | Pass rate + naive normal-approx stderr. |
| 2 | Wilson interval + bootstrap CI on every aggregate, reported by default. |
| 3 | Above + per-capability/subgroup CIs + paired significance for run-vs-run verdicts. |

---

## 3. Repeats, pass@k & Reliability (pass^k)

Re-running each case N times to measure variance and compute sampling metrics:
pass@k (optimistic, code-style) and pass^k (reliability — all k must pass, which
exposes agent flakiness).

World-class: Inspect AI `--epochs N` with pluggable reducers
(mean/median/mode/max/pass_at_k/at_least_k); lighteval PassAtK / MajAtN / AvgAtN;
LiveCodeBench n=10 → pass@1 and pass@5; tau-bench pass^k reliability curves.

| Level | Description |
|---|---|
| 0 | Single attempt only. |
| 1 | `--repeat N` raw repeats, no estimator. |
| 2 | `--repeat N` + unbiased pass@k + mean/majority reducers. |
| 3 | Above + pass^k reliability + per-k curve + answer-order permutation for MCQ position-bias. |

---

## 4. Execution-based / Sandboxed Grading

Grading code/agent output by *running* it (tests, exit codes, state transitions)
inside an isolated, resource-limited sandbox — not by string matching.

World-class: SWE-bench FAIL_TO_PASS + PASS_TO_PASS test-transition verdicts in
per-instance Docker; LiveCodeBench hardened checker with dual timeout and
`reliability_guard()`; terminal-bench per-task pytest in the agent's container.

| Level | Description |
|---|---|
| 0 | No code execution; agent output graded by string matching. |
| 1 | Run a script in a subprocess with a timeout. |
| 2 | Subprocess + wall-clock timeout + resource limits + credential-stripped env, wired as a grader. |
| 3 | Above + FAIL_TO_PASS/PASS_TO_PASS transitions + tiered isolation (Docker if available, else venv/tempdir) + gold self-test mode. |

---

## 5. Concurrency & Throughput

Running many cases (and repeats) in parallel with bounded saturation, so a
200-case suite is minutes not hours, without melting provider rate limits.

World-class: Inspect AI async with max_connections / max_samples /
max_subprocesses; promptfoo `--max-concurrency` + `--delay`.

| Level | Description |
|---|---|
| 0 | Strictly sequential. |
| 1 | Thread pool with a fixed worker count. |
| 2 | `--concurrency N` (ThreadPoolExecutor), per-provider cap, deterministic result ordering. |
| 3 | Above + separate sandbox/subprocess concurrency cap + optional inter-request delay/throttle. |

---

## 6. Reliability: Retry, Backoff & Timeouts

Surviving transient API failures (429/5xx/timeouts) without discarding a whole
run; bounded timeouts everywhere.

World-class: Ragas RunConfig (max_retries, exponential backoff, max_wait);
lighteval `--retry-on-error`; Inspect AI per-request timeouts + rate-limit
handling.

| Level | Description |
|---|---|
| 0 | One attempt; any error aborts or zeroes the case. |
| 1 | Try/except records the error (no retry). |
| 2 | Exponential backoff with jitter on retryable errors, max attempts, per-request timeout. |
| 3 | Above + respects Retry-After, distinguishes retryable vs fatal, surfaces retry counts in results. |

---

## 7. Caching & Cost Decoupling

A content-addressed response cache so reruns and scorer iteration don't re-spend
tokens, and so grading is decoupled from (expensive) generation.

World-class: HELM's request/response store; lm-eval-harness SQLite `--use_cache`;
promptfoo disk cache on by default; Ragas pluggable cache (~50–60% cost saved,
large speedups on reruns); DeepEval cache keyed by (test_case + metric + judge).

| Level | Description |
|---|---|
| 0 | No cache; every run re-calls the API. |
| 1 | Ad-hoc manual caching. |
| 2 | Opt-in disk cache keyed by sha256(provider+model+params+prompt), `--no-cache` to bypass. |
| 3 | Above + judge-call caching + re-grading saved generations without regeneration. |

---

## 8. Reproducibility & Run Manifest

A run records exactly what produced it — git SHA, seed, model + params, per-case
content hashes, dataset version, timestamps — so any run is replayable and only
comparable runs are compared.

World-class: lm-eval-harness 4-tuple seed + per-task version + git commit +
resolved config; Inspect AI `export-config`; lighteval content hashes; SWE-bench
pinned report card with schema_version.

| Level | Description |
|---|---|
| 0 | summary.json has scores but no provenance. |
| 1 | Records adapter name + timestamp. |
| 2 | Manifest: git SHA, seed, model+params, dataset sha256, per-case input hash, schema_version, timestamps. |
| 3 | Above + flags comparison across mismatched dataset/case versions + reproduce/export-config command. |

---

## 9. Usage & Cost Tracking

Per-case prompt/completion token counts, latency, and derived dollar cost, rolled
up to an accuracy-vs-cost view.

World-class: HELM treats efficiency as a first-class metric; Inspect AI surfaces
`EvalLog.stats` token usage; promptfoo `cost`/`latency` as deterministic
assertions with cost in the results table; agent leaderboards report cost-per-task
Pareto frontiers.

| Level | Description |
|---|---|
| 0 | No token/cost tracking. |
| 1 | Latency only. |
| 2 | Per-case prompt/completion tokens captured from provider response, summed in summary. |
| 3 | Above + per-model price table → dollar cost + accuracy-vs-cost table + `cost`/`latency` graders. |

---

## 10. Reporting, Inspection & Run Comparison

Drill-down into any case (prompt/response/target/score/reason), aggregate
scoreboards, and run-vs-run diffing that flags regressions.

World-class: Inspect AI `inspect view`; Braintrust auto experiment diffing with
improved/regressed highlighting; HELM helm-summarize; promptfoo interactive
matrix + before/after compare.

| Level | Description |
|---|---|
| 0 | Pass rate printed to stdout. |
| 1 | Terminal bars + static HTML scoreboard. |
| 2 | Above + interactive HTML (filter/expand per case, inline prompt/response/reason) + JSONL details. |
| 3 | Above + `diff RUN_A RUN_B` regression table (improved/regressed/unchanged, deltas) + CI gate. |

---

## 11. Dataset & Contamination Hygiene

Schema-validated, versioned, content-hashed case packs with release dates and
contamination guards (cutoff filtering, verbatim-leakage detection), plus
separation of dataset from run.

World-class: LiveCodeBench release-dated problems with date windows; SWE-bench
post-cutoff splits + human-verified tier; DeepEval/Ragas Golden vs actual_output
separation; lighteval per-task integer `version`.

| Level | Description |
|---|---|
| 0 | Loose JSONL, no validation, no versioning. |
| 1 | Hand-rolled validation, capability/difficulty tags. |
| 2 | Above + per-case version + dataset content hash + difficulty stratification + Golden/expected separation. |
| 3 | Above + release_date + `--cutoff-date` filtering + verbatim answer-leakage check + post-cutoff subscore. |

---

## 12. Adapter / Provider Abstraction

A tiny model interface that runs unchanged across many providers and a local agent
bridge, with credential redaction and a readiness probe.

World-class: lm-eval-harness's minimal LM interface; simple-evals SamplerBase;
Inspect AI provider + sandbox + tool plug-points; promptfoo 60+ providers.

| Level | Description |
|---|---|
| 0 | One hardcoded provider. |
| 1 | A couple of providers. |
| 2 | mock + several APIs + command-agent bridge + custom module:Class, via a registry, no SDK deps. |
| 3 | Above + namespaces/aliases + credential redaction + readiness probe + optional logprob exposure for MCQ scoring. |

---

## 13. Repo Hygiene, CI & Extensibility

The repo is trustworthy and easy to contribute to: green CI across versions,
tests, LICENSE/CONTRIBUTING/CHANGELOG, clear docs, registry-based extension
points.

World-class: lm-eval-harness `--check_integrity` + `@register_*` decorators;
Inspect AI `@task/@solver/@scorer/@metric` registries; promptfoo GitHub Action
gating on pass-rate + junit.xml.

| Level | Description |
|---|---|
| 0 | No tests, no CI, no license. |
| 1 | Some tests; missing CI or license/contributing. |
| 2 | CI across versions + unittest suite + LICENSE/CONTRIBUTING/CHANGELOG + docs. |
| 3 | Above + grader/adapter registries documented for drop-in extension + CI gate flag + coverage of stats/sandbox/cache. |

---

## Scorecard

Baseline column is the 2026-06-04 snapshot; Target is the level this initiative
drives toward. "Latent" marks a level reachable by wiring existing stdlib code
(`stats.py`, `sandbox.py`, `cache.py`, `usage.py`).

| # | Dimension | Baseline | Latent | Target | Exemplar |
|---|---|---|---|---|---|
| 1 | Scoring & grader library | 2 | — | 3 | Inspect AI / promptfoo |
| 2 | Statistical rigor (CIs) | 1 | 2 | 3 | lm-eval-harness / Inspect |
| 3 | Repeats / pass@k / pass^k | 0 | 1 | 3 | Inspect / lighteval / tau-bench |
| 4 | Execution / sandbox grading | 1 | 2 | 3 | SWE-bench / LiveCodeBench |
| 5 | Concurrency & throughput | 0 | — | 2 | Inspect AI |
| 6 | Retry / backoff / timeouts | 1 | — | 2 | Ragas |
| 7 | Caching & cost decoupling | 0 | 2 | 3 | HELM / promptfoo / Ragas |
| 8 | Reproducibility & manifest | 1 | — | 2 | lm-eval-harness / SWE-bench |
| 9 | Usage & cost tracking | 1 | 2 | 3 | HELM / Inspect |
| 10 | Reporting & run comparison | 1 | — | 3 | Braintrust / Inspect |
| 11 | Dataset & contamination hygiene | 1 | — | 2 | LiveCodeBench / SWE-bench |
| 12 | Adapter / provider abstraction | 3 | — | 3 | lm-eval-harness / promptfoo |
| 13 | Repo hygiene, CI & extensibility | 2 | — | 3 | promptfoo / Inspect |

**Headline.** evalbench is a world-class adapter layer (level 3) wrapped around an
under-powered runner. The defining surprise: the two dimensions that look hardest
on paper — statistical rigor and execution grading — are already *built*
(`stats.py`, `sandbox.py`, plus `cache.py`/`usage.py`) and merely *unwired*. The
fastest path to top-tier is to connect existing engines, add a repeat loop and
thread concurrency to the runner, and layer cache / usage / manifest / diff around
it — all stdlib, all honoring the dependency-light constraint.

## Progress (2026-06-04)

The first build against this standard shipped the full critical path. Honest
post-build levels (see `CHANGELOG.md` for the changes):

| # | Dimension | Baseline → Now | Notes |
|---|---|---|---|
| 1 | Scoring & grader library | 2 → ~3 | added `numeric`, `set_equals`, `choice`, `code_test`; logprob-MCQ still open |
| 2 | Statistical rigor | 1 → ~3 | Wilson + bootstrap CIs everywhere; paired significance in `diff` still open |
| 3 | Repeats / pass@k / pass^k | 0 → ~2.5 | `--repeat` + unbiased pass@k + pass^k; MCQ permutation still open |
| 4 | Execution / sandbox grading | 1 → 2 | `code_test` wired to the sandbox; Docker tier still open |
| 5 | Concurrency & throughput | 0 → 2 | `--concurrency`, deterministic ordering |
| 6 | Retry / backoff / timeouts | 1 → ~3 | backoff + jitter + `Retry-After` |
| 7 | Caching & cost decoupling | 0 → 2 | opt-in content-addressed cache; judge-cache/regrade still open |
| 8 | Reproducibility & manifest | 1 → 2 | git SHA, seed, model+params, dataset hashes, schema version |
| 9 | Usage & cost tracking | 1 → ~2.5 | tokens + dollar cost; `cost`/`latency` graders still open |
| 10 | Reporting & run comparison | 1 → ~3 | interactive report + `evb diff` + CI gates |
| 11 | Dataset & contamination hygiene | 1 → ~3 | per-case version + release_date; execution-graded packs; a regenerable, contamination-resistant frontier generator with recorded difficulty evidence |
| 12 | Adapter / provider abstraction | 3 → 3 | unchanged (already world-class) |
| 13 | Repo hygiene, CI & extensibility | 2 → ~3 | CI, LICENSE/CONTRIBUTING/CHANGELOG, EXTENDING docs, broad tests |

Remaining stretch items (logprob-MCQ scoring, paired significance in `diff`,
judge-call caching + `evb regrade`, a Docker sandbox tier, and `cost`/`latency`
graders) are tracked for follow-up. Re-take this scorecard after major changes.

## Critical path

`usage plumbing → run manifest → stats wiring → repeats/pass@k → execution grader
→ concurrency`, with cache, additional graders, `evb diff`, case packs, CI gate,
and docs fanned out alongside.
