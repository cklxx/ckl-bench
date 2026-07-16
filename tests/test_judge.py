"""Tests for the adversarial judge/reviewer/verifier pipeline."""

from __future__ import annotations

import unittest
from pathlib import Path

from ckl_bench.adapters.base import GenerateResponse
from ckl_bench.core.cases import EvalCase
from ckl_bench.core.grading import grade_case
from ckl_bench.core.judge import (
    AdversarialVerdict,
    JudgeConfig,
    _parse_json,
    adversarial_judge,
)


def make_case() -> EvalCase:
    return EvalCase(
        id="t.judge.v1",
        title="judge test",
        type="chat",
        input={"prompt": "hi"},
        expectations=[
            {
                "kind": "judge",
                "criteria": "Is the answer correct?",
                "threshold": 0.7,
            }
        ],
        capability=["test"],
        difficulty=None,
        timeout_s=None,
        metadata={"pass_threshold": 0.7},
        source_path=Path("inline.jsonl"),
        source_line=1,
    )


class StaticAdapter:
    """Adapter that returns a fixed JSON response."""

    name = "static"
    model = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def generate(self, request) -> GenerateResponse:
        self.calls += 1
        return GenerateResponse(text=self.text)


class FailingAdapter:
    """Adapter that always raises."""

    name = "failing"
    model = "fake"

    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc or RuntimeError("boom")
        self.calls = 0

    def generate(self, request) -> GenerateResponse:
        self.calls += 1
        raise self.exc


JUDGE_JSON = '{"score": 0.8, "passed": true, "reason": "correct"}'
REVIEWER_JSON = (
    '{"agreed": false, "score_adjustment": -0.2, '
    '"concerns": ["too lenient"], "revised_score": 0.6}'
)
VERIFIER_JSON = (
    '{"verified": true, "confidence": 0.9, "edge_cases": ["edge1"], '
    '"final_score": 0.5, "final_passed": false}'
)


class ParseJsonTests(unittest.TestCase):
    def test_strict_json(self) -> None:
        self.assertEqual(_parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_and_prose(self) -> None:
        self.assertEqual(
            _parse_json('Here is the result:\n```json\n{"a": 1}\n```'),
            {"a": 1},
        )

    def test_non_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            _parse_json("no json here")

    def test_braces_inside_string_value(self) -> None:
        # The old greedy regex \{.*\} would over-match here.
        text = '{"score": 0.8, "reason": "value is {0.5} roughly"}'
        self.assertEqual(
            _parse_json(text),
            {"score": 0.8, "reason": "value is {0.5} roughly"},
        )

    def test_prose_before_and_after(self) -> None:
        text = 'Sure! Here you go:\n{"score": 0.5, "passed": false}\nLet me know.'
        self.assertEqual(
            _parse_json(text), {"score": 0.5, "passed": False}
        )

    def test_nested_braces(self) -> None:
        text = '{"outer": {"inner": 1}, "passed": true}'
        self.assertEqual(
            _parse_json(text), {"outer": {"inner": 1}, "passed": True}
        )

    def test_multiple_objects_picks_first(self) -> None:
        text = '{"a": 1} then some prose {"b": 2}'
        self.assertEqual(_parse_json(text), {"a": 1})

    def test_non_dict_raises(self) -> None:
        with self.assertRaises(ValueError):
            _parse_json("[1, 2, 3]")

    def test_unbalanced_raises(self) -> None:
        # Truncated JSON: json-repair can fix it (adds the missing brace), so
        # this only raises in the stdlib-only configuration.
        try:
            import json_repair  # noqa: F401
        except ImportError:
            with self.assertRaises(ValueError):
                _parse_json('{"score": 0.5, "passed": true')
        else:
            result = _parse_json('{"score": 0.5, "passed": true')
            self.assertEqual(result, {"score": 0.5, "passed": True})

    def test_json_repair_fallback(self) -> None:
        # Single quotes + trailing comma — invalid JSON, repairable only if
        # json-repair is installed. Skip the assertion if it's not.
        text = "{'score': 0.5, 'passed': True,}"
        try:
            import json_repair  # noqa: F401
        except ImportError:
            self.skipTest("json-repair not installed")
        result = _parse_json(text)
        self.assertEqual(result["score"], 0.5)
        self.assertEqual(result["passed"], True)


class AdversarialJudgeTests(unittest.TestCase):
    def test_judge_only(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        verdict = adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            config=JudgeConfig(max_retries=0),
        )
        self.assertIsInstance(verdict, AdversarialVerdict)
        self.assertEqual(verdict.score, 0.8)
        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.confidence, 0.5)
        self.assertIsNone(verdict.reviewer)
        self.assertIsNone(verdict.verifier)
        self.assertEqual(judge.calls, 1)
        self.assertIn("judge score=0.800", verdict.detail)

    def test_full_pipeline_uses_verifier(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(REVIEWER_JSON)
        verifier = StaticAdapter(VERIFIER_JSON)
        verdict = adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            verifier_adapter=verifier,
            config=JudgeConfig(max_retries=0),
        )
        # Verifier has final say.
        self.assertEqual(verdict.score, 0.5)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.confidence, 0.9)
        self.assertIsNotNone(verdict.reviewer)
        self.assertIsNotNone(verdict.verifier)
        self.assertEqual(verdict.verifier.edge_cases, ["edge1"])
        self.assertEqual(judge.calls, 1)
        self.assertEqual(reviewer.calls, 1)
        self.assertEqual(verifier.calls, 1)

    def test_reviewer_revises_when_no_verifier(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(REVIEWER_JSON)
        verdict = adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            config=JudgeConfig(max_retries=0),
        )
        # Reviewer's revised_score is used (0.6), below threshold 0.7.
        self.assertEqual(verdict.score, 0.6)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.confidence, 0.4)  # disagreed
        self.assertIsNotNone(verdict.reviewer)
        self.assertIsNone(verdict.verifier)

    def test_reviewer_agrees_keeps_judge(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(
            '{"agreed": true, "score_adjustment": 0.0, "concerns": [], "revised_score": null}'
        )
        verdict = adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            config=JudgeConfig(max_retries=0),
        )
        # No revised_score, reviewer agreed → judge score used.
        self.assertEqual(verdict.score, 0.8)
        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.confidence, 0.5)

    def test_graceful_degradation_reviewer_fails(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = FailingAdapter()
        verdict = adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            config=JudgeConfig(max_retries=0, graceful_degradation=True),
        )
        # Falls back to judge-only.
        self.assertEqual(verdict.score, 0.8)
        self.assertTrue(verdict.passed)
        self.assertIsNone(verdict.reviewer)

    def test_graceful_degradation_verifier_fails(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(REVIEWER_JSON)
        verifier = FailingAdapter()
        verdict = adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            verifier_adapter=verifier,
            config=JudgeConfig(max_retries=0, graceful_degradation=True),
        )
        # Verifier failed → falls back to reviewer's revised score.
        self.assertEqual(verdict.score, 0.6)
        self.assertIsNone(verdict.verifier)
        self.assertIsNotNone(verdict.reviewer)

    def test_no_graceful_degradation_raises(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = FailingAdapter()
        with self.assertRaises(RuntimeError):
            adversarial_judge(
                case, "Is it correct?", "42",
                judge_adapter=judge,
                reviewer_adapter=reviewer,
                config=JudgeConfig(max_retries=0, graceful_degradation=False),
            )

    def test_events_emitted(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(REVIEWER_JSON)
        verifier = StaticAdapter(VERIFIER_JSON)
        events: list[dict] = []
        adversarial_judge(
            case, "Is it correct?", "42",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            verifier_adapter=verifier,
            config=JudgeConfig(max_retries=0),
            trace_id="trace-123",
            on_event=events.append,
        )
        types = [e["type"] for e in events]
        self.assertEqual(
            types,
            [
                "judge_started",
                "judge_completed",
                "reviewer_started",
                "reviewer_completed",
                "verifier_started",
                "verifier_completed",
            ],
        )
        for e in events:
            self.assertEqual(e["trace_id"], "trace-123")
            self.assertEqual(e["case_id"], "t.judge.v1")

    def test_trace_id_auto_generated(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        verdict = adversarial_judge(
            case, "x", "y",
            judge_adapter=judge,
            config=JudgeConfig(max_retries=0),
        )
        self.assertTrue(verdict.trace_id.startswith("t.judge.v1-"))

    def test_as_dict_serializable(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(REVIEWER_JSON)
        verifier = StaticAdapter(VERIFIER_JSON)
        verdict = adversarial_judge(
            case, "x", "y",
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            verifier_adapter=verifier,
            config=JudgeConfig(max_retries=0),
        )
        import json

        d = verdict.as_dict()
        json.dumps(d)  # should not raise
        self.assertEqual(d["score"], 0.5)
        self.assertIn("reviewer", d)
        self.assertIn("verifier", d)

    def test_grade_case_integration(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        reviewer = StaticAdapter(REVIEWER_JSON)
        verifier = StaticAdapter(VERIFIER_JSON)
        result = grade_case(
            case, "42", None,
            judge_adapter=judge,
            reviewer_adapter=reviewer,
            verifier_adapter=verifier,
        )
        # Verifier says final_score=0.5, final_passed=false.
        self.assertAlmostEqual(result.score, 0.5)
        self.assertFalse(result.passed)
        self.assertIn("verifier", result.checks[0].detail)

    def test_grade_case_judge_only_backward_compat(self) -> None:
        case = make_case()
        judge = StaticAdapter(JUDGE_JSON)
        result = grade_case(case, "42", None, judge_adapter=judge)
        self.assertAlmostEqual(result.score, 0.8)
        self.assertTrue(result.passed)

    def test_grade_case_no_judge_adapter(self) -> None:
        case = make_case()
        result = grade_case(case, "42", None)
        self.assertFalse(result.passed)
        self.assertIn("requires --judge", result.checks[0].detail)


if __name__ == "__main__":
    unittest.main()
