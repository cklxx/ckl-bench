"""Adversarial judge/reviewer/verifier pipeline for LLM-as-judge evaluation.

Three-agent sequential pipeline that runs on top of the existing
``ModelAdapter`` abstraction:

1. **Judge** — evaluates a response against the criteria (score, passed, reason).
2. **Reviewer** — challenges the judge's score, looking for bias, leniency,
   harshness, missed criteria, or reasoning errors.
3. **Verifier** — makes the final verdict, checking edge cases both the judge
   and reviewer may have missed.

The pipeline is sequential (each stage depends on the previous). Multiple
cases run concurrently via the thread pool in :mod:`ckl_bench.core.runner`.

Observability
    Each evaluation gets a ``trace_id``. Per-agent latency and the full
    rationale chain are captured in the :class:`AdversarialVerdict`. Progress
    events (``judge_started``, ``reviewer_completed``, …) are emitted to an
    optional ``on_event`` callback.

Recovery
    Agent calls retry with exponential backoff (``max_retries``). If the
    reviewer or verifier fails and ``graceful_degradation`` is enabled, the
    pipeline falls back to judge-only rather than aborting the case.

Concurrency
    A bounded semaphore limits concurrent agent calls so a large parallel run
    does not overwhelm the upstream API (``max_concurrent``).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from ckl_bench.adapters.base import GenerateRequest, ModelAdapter

from .cases import EvalCase

_log = logging.getLogger(__name__)


@cache
def _get_semaphore(max_concurrent: int) -> threading.Semaphore:
    """Get or create a semaphore for the given concurrency limit."""
    return threading.Semaphore(max(1, max_concurrent))


# --- Output dataclasses -----------------------------------------------------


@dataclass
class JudgeOutput:
    score: float
    passed: bool
    reason: str
    latency_ms: float = 0.0


@dataclass
class ReviewOutput:
    agreed: bool
    score_adjustment: float  # -1.0 to 1.0
    concerns: list[str] = field(default_factory=list)
    revised_score: float | None = None
    latency_ms: float = 0.0


@dataclass
class VerifyOutput:
    verified: bool
    confidence: float  # 0.0 to 1.0
    final_score: float
    final_passed: bool
    edge_cases: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class AdversarialVerdict:
    score: float
    passed: bool
    confidence: float
    detail: str
    trace_id: str
    judge: JudgeOutput
    reviewer: ReviewOutput | None = None
    verifier: VerifyOutput | None = None
    total_latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "confidence": self.confidence,
            "detail": self.detail,
            "trace_id": self.trace_id,
            "total_latency_ms": self.total_latency_ms,
            "judge": {
                "score": self.judge.score,
                "passed": self.judge.passed,
                "reason": self.judge.reason,
                "latency_ms": self.judge.latency_ms,
            },
            "reviewer": (
                {
                    "agreed": self.reviewer.agreed,
                    "score_adjustment": self.reviewer.score_adjustment,
                    "concerns": self.reviewer.concerns,
                    "revised_score": self.reviewer.revised_score,
                    "latency_ms": self.reviewer.latency_ms,
                }
                if self.reviewer is not None
                else None
            ),
            "verifier": (
                {
                    "verified": self.verifier.verified,
                    "confidence": self.verifier.confidence,
                    "edge_cases": self.verifier.edge_cases,
                    "final_score": self.verifier.final_score,
                    "final_passed": self.verifier.final_passed,
                    "latency_ms": self.verifier.latency_ms,
                }
                if self.verifier is not None
                else None
            ),
        }


# --- Configuration ----------------------------------------------------------


@dataclass(frozen=True)
class JudgeConfig:
    """Configuration for the adversarial judge pipeline."""

    threshold: float = 0.7
    max_retries: int = 2
    retry_base_delay_s: float = 1.0
    timeout_s: float = 120.0
    max_concurrent: int = 8
    graceful_degradation: bool = True


# --- Helpers ----------------------------------------------------------------


_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n(.*?)\n```\s*$", re.S)


def _strip_fence(text: str) -> str:
    """Strip a surrounding ``` ...``` / ```json ...``` code fence if present."""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


def _extract_json_object(text: str) -> str:
    """Return the first balanced JSON object substring starting at the first '{'.

    Walks the string tracking brace depth and string-literal state so that
    braces inside JSON string values (e.g. ``"reason": "x is {0.5}"``) do not
    break the match. Returns the substring of the first complete ``{...}``.
    """
    start = text.find("{")
    if start < 0:
        raise ValueError(f"non-JSON response (no '{{' found): {text[:200]}")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError(f"unbalanced JSON in response: {text[:200]}")


def _try_json_repair(text: str) -> Any | None:
    """Try to repair and parse malformed JSON using *json-repair* if installed.

    Returns ``None`` if *json-repair* is not installed or it cannot repair the
    text. This keeps the core stdlib-only while gaining extra robustness (e.g.
    truncated JSON, single quotes, missing commas) when the user opts in.
    """
    try:
        import json_repair
    except ImportError:
        return None
    try:
        return json_repair.loads(text)
    except Exception:  # noqa: BLE001 — json-repair raises various errors
        return None


def _parse_json(text: str) -> dict[str, Any]:
    """Parse JSON, tolerating fenced code blocks or surrounding prose.

    Strategy (cheap → expensive):

    1. Strip a surrounding `````json``` fence and try ``json.loads``.
    2. Extract the first balanced JSON object and ``json.loads`` it. This
       handles prose around the JSON and braces inside string values.
    3. If *json-repair* is installed, attempt to repair malformed JSON
       (truncated output, single quotes, missing commas, …).

    Steps 1–2 are pure stdlib; step 3 is an optional enhancement.
    """
    text = _strip_fence(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = json.loads(_extract_json_object(text))
        except (json.JSONDecodeError, ValueError):
            repaired = _try_json_repair(text)
            if repaired is None:
                raise
            data = repaired
    if not isinstance(data, dict):
        raise ValueError("response JSON must be an object")
    return data


def _call_agent(
    adapter: ModelAdapter,
    *,
    case_id: str,
    role: str,
    system_prompt: str,
    user_prompt: str,
    config: JudgeConfig,
    trace_id: str,
) -> dict[str, Any]:
    """Call an agent with retries, timeout, and bounded concurrency.

    Returns the parsed JSON response with ``_latency_ms`` and ``_attempt``
    metadata keys added.
    """
    sem = _get_semaphore(config.max_concurrent)
    last_exc: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            with sem:
                started = time.perf_counter()
                response = adapter.generate(
                    GenerateRequest(
                        case_id=f"{case_id}:{role}",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        prompt=user_prompt,
                        metadata={
                            "case_type": role,
                            "trace_id": trace_id,
                            "judge_for": case_id,
                        },
                        timeout_s=config.timeout_s,
                    )
                )
                latency_ms = (time.perf_counter() - started) * 1000
            data = _parse_json(response.text)
            data["_latency_ms"] = latency_ms
            data["_attempt"] = attempt
            return data
        except Exception as exc:
            last_exc = exc
            if attempt < config.max_retries:
                delay = config.retry_base_delay_s * (2**attempt)
                _log.warning(
                    "agent %s attempt %d failed: %s; retrying in %.1fs",
                    role,
                    attempt,
                    exc,
                    delay,
                )
                time.sleep(delay)
    raise RuntimeError(
        f"agent {role} failed after {config.max_retries + 1} attempts: {last_exc}"
    )


# --- Agent stages -----------------------------------------------------------


_JUDGE_SYSTEM = (
    "You are a strict evaluation judge. Return JSON only with "
    "keys score, passed, and reason. score must be between 0 and 1."
)

_REVIEWER_SYSTEM = (
    "You are a skeptical review judge. Your job is to challenge the "
    "evaluation judge's score. Look for bias, leniency, harshness, "
    "missed criteria, or reasoning errors. Return JSON only with keys "
    "agreed, score_adjustment, concerns, and revised_score. "
    "score_adjustment must be between -1.0 and 1.0."
)

_VERIFIER_SYSTEM = (
    "You are the final verification judge. You review both the judge's "
    "and reviewer's evaluations and make the final verdict. Check for "
    "edge cases, hidden assumptions, and criteria that may have been "
    "missed. Return JSON only with keys verified, confidence, "
    "edge_cases, final_score, and final_passed. "
    "confidence must be between 0 and 1. final_score must be between 0 and 1."
)


def _judge_user_prompt(case: EvalCase, criteria: str, target_text: str) -> str:
    return (
        f"Case id: {case.id}\n"
        f"Title: {case.title}\n\n"
        "Task prompt/messages:\n"
        f"{json.dumps(case.messages, ensure_ascii=False)}\n\n"
        "Candidate response or artifact:\n"
        f"{target_text}\n\n"
        "Evaluation criteria:\n"
        f"{criteria}\n\n"
        "Return only JSON:\n"
        '{"score":0.0,"passed":false,"reason":"short reason"}'
    )


def run_judge(
    case: EvalCase,
    criteria: str,
    target_text: str,
    judge_adapter: ModelAdapter,
    config: JudgeConfig,
    trace_id: str,
) -> JudgeOutput:
    """Run the judge agent: evaluate the response against the criteria."""
    raw = _call_agent(
        judge_adapter,
        case_id=case.id,
        role="judge",
        system_prompt=_JUDGE_SYSTEM,
        user_prompt=_judge_user_prompt(case, criteria, target_text),
        config=config,
        trace_id=trace_id,
    )
    score = float(raw.get("score", 1.0 if raw.get("passed") else 0.0))
    score = min(max(score, 0.0), 1.0)
    return JudgeOutput(
        score=score,
        passed=score >= config.threshold,
        reason=str(raw.get("reason") or raw.get("detail") or "").strip(),
        latency_ms=float(raw.get("_latency_ms", 0.0)),
    )


def run_reviewer(
    case: EvalCase,
    criteria: str,
    target_text: str,
    judge_output: JudgeOutput,
    reviewer_adapter: ModelAdapter,
    config: JudgeConfig,
    trace_id: str,
) -> ReviewOutput:
    """Run the reviewer agent: challenge the judge's score."""
    user = (
        f"Case id: {case.id}\n"
        f"Title: {case.title}\n\n"
        "Evaluation criteria:\n"
        f"{criteria}\n\n"
        "Candidate response or artifact:\n"
        f"{target_text}\n\n"
        "The judge evaluated this and returned:\n"
        f"- score: {judge_output.score}\n"
        f"- passed: {judge_output.passed}\n"
        f"- reason: {judge_output.reason}\n\n"
        "Review the judge's evaluation. Do you agree? If not, what is the "
        "correct score and what concerns do you have?\n\n"
        "Return only JSON:\n"
        '{"agreed":true,"score_adjustment":0.0,"concerns":[],"revised_score":null}'
    )
    raw = _call_agent(
        reviewer_adapter,
        case_id=case.id,
        role="reviewer",
        system_prompt=_REVIEWER_SYSTEM,
        user_prompt=user,
        config=config,
        trace_id=trace_id,
    )
    adjustment = float(raw.get("score_adjustment", 0.0))
    adjustment = min(max(adjustment, -1.0), 1.0)
    revised = raw.get("revised_score")
    return ReviewOutput(
        agreed=bool(raw.get("agreed", True)),
        score_adjustment=adjustment,
        concerns=[str(c) for c in raw.get("concerns", []) if c],
        revised_score=float(revised) if revised is not None else None,
        latency_ms=float(raw.get("_latency_ms", 0.0)),
    )


def run_verifier(
    case: EvalCase,
    criteria: str,
    target_text: str,
    judge_output: JudgeOutput,
    review_output: ReviewOutput | None,
    verifier_adapter: ModelAdapter,
    config: JudgeConfig,
    trace_id: str,
) -> VerifyOutput:
    """Run the verifier agent: final verdict, checking edge cases."""
    if review_output is not None:
        review_text = (
            f"- agreed: {review_output.agreed}\n"
            f"- score_adjustment: {review_output.score_adjustment}\n"
            f"- concerns: {review_output.concerns}\n"
            f"- revised_score: {review_output.revised_score}"
        )
    else:
        review_text = "No reviewer (judge-only)."
    user = (
        f"Case id: {case.id}\n"
        f"Title: {case.title}\n\n"
        "Evaluation criteria:\n"
        f"{criteria}\n\n"
        "Candidate response or artifact:\n"
        f"{target_text}\n\n"
        "Judge evaluation:\n"
        f"- score: {judge_output.score}\n"
        f"- passed: {judge_output.passed}\n"
        f"- reason: {judge_output.reason}\n\n"
        "Reviewer evaluation:\n"
        f"{review_text}\n\n"
        "Make the final verdict. Consider both evaluations, check for edge "
        "cases, and return the final score and pass/fail decision.\n\n"
        "Return only JSON:\n"
        '{"verified":true,"confidence":0.8,"edge_cases":[],"final_score":0.0,"final_passed":false}'
    )
    raw = _call_agent(
        verifier_adapter,
        case_id=case.id,
        role="verifier",
        system_prompt=_VERIFIER_SYSTEM,
        user_prompt=user,
        config=config,
        trace_id=trace_id,
    )
    final_score = float(raw.get("final_score", judge_output.score))
    final_score = min(max(final_score, 0.0), 1.0)
    confidence = float(raw.get("confidence", 0.5))
    confidence = min(max(confidence, 0.0), 1.0)
    return VerifyOutput(
        verified=bool(raw.get("verified", True)),
        confidence=confidence,
        edge_cases=[str(c) for c in raw.get("edge_cases", []) if c],
        final_score=final_score,
        final_passed=final_score >= config.threshold,
        latency_ms=float(raw.get("_latency_ms", 0.0)),
    )


# --- Pipeline ---------------------------------------------------------------


def adversarial_judge(
    case: EvalCase,
    criteria: str,
    target_text: str,
    *,
    judge_adapter: ModelAdapter,
    reviewer_adapter: ModelAdapter | None = None,
    verifier_adapter: ModelAdapter | None = None,
    config: JudgeConfig | None = None,
    trace_id: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> AdversarialVerdict:
    """Run the full adversarial judge/reviewer/verifier pipeline.

    Flow: judge → reviewer → verifier. Each stage depends on the previous.

    If the reviewer or verifier fails and *graceful_degradation* is enabled,
    the pipeline falls back to judge-only (or judge+reviewer) rather than
    raising.

    Parameters
    ----------
    case:
        The evaluation case.
    criteria:
        The evaluation criteria / rubric.
    target_text:
        The candidate response or artifact text to evaluate.
    judge_adapter:
        The adapter for the judge agent (required).
    reviewer_adapter:
        Optional adapter for the reviewer agent.
    verifier_adapter:
        Optional adapter for the verifier agent.
    config:
        Pipeline configuration (retries, timeouts, etc.).
    trace_id:
        Optional trace id for observability (auto-generated if omitted).
    on_event:
        Optional callback for progress events.

    Returns
    -------
    AdversarialVerdict
        The final verdict with full rationale chain.
    """
    config = config or JudgeConfig()
    trace_id = trace_id or f"{case.id}-{int(time.time() * 1000)}"
    started = time.perf_counter()

    def _emit(event_type: str, **extra: Any) -> None:
        if on_event is None:
            return
        try:
            on_event(
                {"type": event_type, "trace_id": trace_id, "case_id": case.id, **extra}
            )
        except Exception:  # noqa: BLE001 — events are a side channel
            _log.exception("on_event callback failed")

    # Stage 1: Judge (always runs).
    _emit("judge_started")
    judge_output = run_judge(case, criteria, target_text, judge_adapter, config, trace_id)
    _emit(
        "judge_completed",
        score=judge_output.score,
        passed=judge_output.passed,
        latency_ms=judge_output.latency_ms,
    )

    def _run_stage(stage: str, run, completed_fields):
        """Run an optional stage with graceful degradation."""
        _emit(f"{stage}_started")
        try:
            output = run()
        except Exception as exc:
            _log.warning("%s failed for %s: %s", stage, case.id, exc)
            if not config.graceful_degradation:
                raise
            _emit(f"{stage}_failed", error=str(exc))
            return None
        _emit(f"{stage}_completed", **completed_fields(output))
        return output

    # Stage 2: Reviewer (optional).
    review_output: ReviewOutput | None = None
    if reviewer_adapter is not None:
        review_output = _run_stage(
            "reviewer",
            lambda: run_reviewer(
                case, criteria, target_text, judge_output, reviewer_adapter, config, trace_id
            ),
            lambda r: {"agreed": r.agreed, "concerns": r.concerns, "latency_ms": r.latency_ms},
        )

    # Stage 3: Verifier (optional).
    verify_output: VerifyOutput | None = None
    if verifier_adapter is not None:
        verify_output = _run_stage(
            "verifier",
            lambda: run_verifier(
                case, criteria, target_text, judge_output, review_output, verifier_adapter, config, trace_id
            ),
            lambda v: {"final_score": v.final_score, "confidence": v.confidence, "latency_ms": v.latency_ms},
        )

    # --- Compute final verdict -------------------------------------------
    if verify_output is not None:
        final_score = verify_output.final_score
        final_passed = verify_output.final_passed
        confidence = verify_output.confidence
    elif review_output is not None and review_output.revised_score is not None:
        final_score = review_output.revised_score
        final_passed = final_score >= config.threshold
        confidence = 0.6 if review_output.agreed else 0.4
    else:
        final_score = judge_output.score
        final_passed = judge_output.passed
        confidence = 0.5

    total_latency = (time.perf_counter() - started) * 1000

    # --- Build detail string --------------------------------------------
    parts = [f"judge score={judge_output.score:.3f} | {judge_output.reason}"]
    if review_output is not None:
        parts.append(
            f"reviewer agreed={review_output.agreed} adj={review_output.score_adjustment:+.3f}"
        )
        if review_output.concerns:
            parts.append(f"concerns: {'; '.join(review_output.concerns)}")
    if verify_output is not None:
        parts.append(
            f"verifier final={verify_output.final_score:.3f} conf={verify_output.confidence:.2f}"
        )
        if verify_output.edge_cases:
            parts.append(f"edge_cases: {'; '.join(verify_output.edge_cases)}")
    detail = " || ".join(parts)

    return AdversarialVerdict(
        score=final_score,
        passed=final_passed,
        confidence=confidence,
        detail=detail,
        trace_id=trace_id,
        judge=judge_output,
        reviewer=review_output,
        verifier=verify_output,
        total_latency_ms=total_latency,
    )
