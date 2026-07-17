from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ckl_bench.adapters.base import GenerateResponse
from ckl_bench.core.cases import EvalCase
from ckl_bench.core.grading import _build_quality_criteria, grade_case


class StaticAdapter:
    """Adapter that returns a fixed JSON response."""

    name = "static"
    model = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0
        self.last_messages = None

    def generate(self, request):
        self.calls += 1
        self.last_messages = request.messages
        return GenerateResponse(text=self.text)


def make_case(expectations: list[dict], *, metadata: dict | None = None, input_payload: dict | None = None) -> EvalCase:
    return EvalCase(
        id="t.case.v1",
        title="t",
        type="chat",
        input=input_payload or {"prompt": "hi"},
        expectations=expectations,
        capability=["test"],
        difficulty=None,
        timeout_s=None,
        metadata=metadata or {},
        source_path=Path("inline.jsonl"),
        source_line=1,
    )


class GradingTests(unittest.TestCase):
    def test_contains_and_not_contains(self) -> None:
        case = make_case([
            {"kind": "contains", "value": "hello"},
            {"kind": "not_contains", "value": "goodbye"},
        ])
        grade = grade_case(case, "hello world", None)
        self.assertTrue(grade.passed)
        self.assertEqual(grade.score, 1.0)

    def test_contains_case_insensitive(self) -> None:
        case = make_case([{"kind": "contains", "value": "HELLO", "case_sensitive": False}])
        self.assertTrue(grade_case(case, "hello", None).passed)

    def test_exact_trims(self) -> None:
        case = make_case([{"kind": "exact", "value": "answer"}])
        self.assertTrue(grade_case(case, "  answer\n", None).passed)
        self.assertFalse(grade_case(case, "answer extra", None).passed)

    def test_regex(self) -> None:
        case = make_case([{"kind": "regex", "pattern": r"\d{3}-\d{4}"}])
        self.assertTrue(grade_case(case, "call 555-1234", None).passed)
        self.assertFalse(grade_case(case, "no number", None).passed)

    def test_json_path_equals_contains_exists(self) -> None:
        equals = make_case([{"kind": "json_path", "path": "a.b", "equals": 5}])
        self.assertTrue(grade_case(equals, '{"a": {"b": 5}}', None).passed)
        contains = make_case([{"kind": "json_path", "path": "name", "contains": "ell"}])
        self.assertTrue(grade_case(contains, '{"name": "hello"}', None).passed)
        exists = make_case([{"kind": "json_path", "path": "x.0"}])
        self.assertTrue(grade_case(exists, '{"x": [42]}', None).passed)

    def test_json_path_lenient_parsing(self) -> None:
        case = make_case([{"kind": "json_path", "path": "top", "equals": 42}])
        # prose-wrapped and fenced answers should still be graded on their JSON
        self.assertTrue(grade_case(case, 'After tracing: {"top": 42}', None).passed)
        self.assertTrue(grade_case(case, '```json\n{"top": 42}\n```', None).passed)
        # a wrong embedded answer still fails
        self.assertFalse(grade_case(case, 'the answer is {"top": 7}', None).passed)

    def test_weighting_partial_score(self) -> None:
        case = make_case([
            {"kind": "contains", "value": "yes", "weight": 3},
            {"kind": "contains", "value": "missing", "weight": 1},
        ])
        grade = grade_case(case, "yes", None)
        self.assertAlmostEqual(grade.score, 0.75)
        self.assertFalse(grade.passed)  # default threshold 1.0

    def test_explicit_threshold_uses_score_but_default_uses_check_passes(self) -> None:
        expectation = {"kind": "judge", "criteria": "correct", "threshold": 0.4}
        judge = StaticAdapter('{"score":0.5,"passed":false,"reason":"partial"}')
        default_grade = grade_case(make_case([expectation]), "", None, judge_adapter=judge)
        explicit_grade = grade_case(
            make_case([expectation], metadata={"pass_threshold": 0.7}),
            "",
            None,
            judge_adapter=judge,
        )
        self.assertEqual(default_grade.score, 0.5)
        self.assertTrue(default_grade.checks[0].passed)
        self.assertTrue(default_grade.passed)
        self.assertFalse(explicit_grade.passed)

    def test_pass_threshold_metadata(self) -> None:
        case = make_case(
            [
                {"kind": "contains", "value": "yes", "weight": 3},
                {"kind": "contains", "value": "missing", "weight": 1},
            ],
            metadata={"pass_threshold": 0.7},
        )
        self.assertTrue(grade_case(case, "yes", None).passed)

    def test_grader_error_is_recorded_not_raised(self) -> None:
        # json_path on non-JSON should fail gracefully, not crash the run.
        case = make_case([{"kind": "json_path", "path": "a"}])
        grade = grade_case(case, "not json at all", None)
        self.assertFalse(grade.passed)
        self.assertIn("grader error", grade.checks[0].detail)

    def test_unknown_kind_records_error(self) -> None:
        case = make_case([{"kind": "does_not_exist"}])
        grade = grade_case(case, "x", None)
        self.assertFalse(grade.passed)
        self.assertIn("unknown expectation kind", grade.checks[0].detail)

    def test_file_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "out.txt").write_text("result=ok\n", encoding="utf-8")
            case = make_case([
                {"kind": "file_exists", "path": "out.txt"},
                {"kind": "file_contains", "path": "out.txt", "value": "result=ok"},
                {"kind": "file_regex", "path": "out.txt", "pattern": r"result=\w+"},
                {"kind": "contains", "target": "file", "path": "out.txt", "value": "ok"},
            ])
            self.assertTrue(grade_case(case, "", workspace).passed)

    def test_unsafe_workspace_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            case = make_case([{"kind": "file_exists", "path": "../escape.txt"}])
            grade = grade_case(case, "", Path(tmp))
            self.assertFalse(grade.passed)
            self.assertIn("grader error", grade.checks[0].detail)

    def test_numeric_tolerance(self) -> None:
        case = make_case([{"kind": "numeric", "value": 3.14159, "abs_tol": 1e-3}])
        self.assertTrue(grade_case(case, "The answer is 3.1416 exactly.", None).passed)
        self.assertFalse(grade_case(case, "3.20", None).passed)

    def test_numeric_rel_tol_and_path(self) -> None:
        case = make_case([{"kind": "numeric", "path": "result", "value": 1000.0, "rel_tol": 0.01}])
        self.assertTrue(grade_case(case, '{"result": 1005}', None).passed)
        self.assertFalse(grade_case(case, '{"result": 1100}', None).passed)

    def test_set_equals_order_independent(self) -> None:
        case = make_case([{"kind": "set_equals", "values": [3, 1, 2]}])
        self.assertTrue(grade_case(case, "[2, 3, 1, 1]", None).passed)
        self.assertFalse(grade_case(case, "[1, 2]", None).passed)

    def test_choice_picks_last_token(self) -> None:
        case = make_case([{"kind": "choice", "value": "C", "choices": ["A", "B", "C", "D"]}])
        self.assertTrue(grade_case(case, "Maybe A or B, but the answer is C.", None).passed)
        self.assertFalse(grade_case(case, "The answer is D.", None).passed)

    def test_code_test_with_response_file(self) -> None:
        case = make_case([
            {
                "kind": "code_test",
                "response_file": "solution.py",
                "extract_code": True,
                "test": "from solution import inc\nassert inc(4) == 5\nprint('ok')\n",
                "timeout_s": 10,
            }
        ])
        response = "Here you go:\n```python\ndef inc(n):\n    return n + 1\n```\n"
        self.assertTrue(grade_case(case, response, None).passed)

    def test_code_test_failure_reports_detail(self) -> None:
        case = make_case([
            {"kind": "code_test", "test": "assert 1 == 2, 'nope'\n", "timeout_s": 10}
        ])
        grade = grade_case(case, "", None)
        self.assertFalse(grade.passed)
        self.assertIn("exit=", grade.checks[0].detail)

    def test_code_test_runs_against_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "lib.py").write_text("def two():\n    return 2\n", encoding="utf-8")
            case = make_case([
                {"kind": "code_test", "test": "from lib import two\nassert two() == 2\n", "timeout_s": 10}
            ])
            self.assertTrue(grade_case(case, "", workspace).passed)

    def test_quality_rubric_covers_all_seven_dimensions(self) -> None:
        criteria = _build_quality_criteria(None)
        for zh in ("清晰", "连贯", "简洁", "具体", "准确", "完整", "得体"):
            self.assertIn(zh, criteria)

    def test_quality_dimensions_filter(self) -> None:
        criteria = _build_quality_criteria(["clear", "accurate"])
        self.assertIn("清晰", criteria)
        self.assertIn("准确", criteria)
        self.assertNotIn("连贯", criteria)

    def test_quality_expectation_uses_judge(self) -> None:
        judge = StaticAdapter('{"score":0.9,"passed":true,"reason":"good"}')
        case = make_case(
            [{"kind": "quality", "threshold": 0.7}],
            metadata={"pass_threshold": 0.7},
        )
        grade = grade_case(case, "A clear, accurate response.", None, judge_adapter=judge)
        self.assertTrue(grade.passed)
        self.assertAlmostEqual(grade.score, 0.9)
        self.assertEqual(judge.calls, 1)
        # The judge prompt must carry the quality rubric.
        prompt = judge.last_messages[-1]["content"]
        self.assertIn("清晰", prompt)
        self.assertIn("得体", prompt)

    def test_quality_expectation_uses_score_not_self_reported_passed(self) -> None:
        judge = StaticAdapter('{"score":0.9,"passed":false,"reason":"good"}')
        case = make_case(
            [{"kind": "quality", "threshold": 0.7}],
            metadata={"pass_threshold": 0.7},
        )
        grade = grade_case(case, "A clear, accurate response.", None, judge_adapter=judge)
        self.assertTrue(grade.checks[0].passed)
        self.assertTrue(grade.passed)
        self.assertAlmostEqual(grade.score, 0.9)

    def test_quality_expectation_without_judge_fails_gracefully(self) -> None:
        case = make_case([{"kind": "quality"}])
        grade = grade_case(case, "response", None)
        self.assertFalse(grade.passed)
        self.assertIn("requires --judge", grade.checks[0].detail)

    def test_writing_quality_alias(self) -> None:
        judge = StaticAdapter('{"score":0.5,"passed":false,"reason":"vague"}')
        case = make_case([{"kind": "writing_quality", "threshold": 0.7}])
        grade = grade_case(case, "response", None, judge_adapter=judge)
        self.assertFalse(grade.passed)
        self.assertEqual(judge.calls, 1)


if __name__ == "__main__":
    unittest.main()
