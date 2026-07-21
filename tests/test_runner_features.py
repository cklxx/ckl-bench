from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ckl_bench.adapters.base import GenerateResponse
from ckl_bench.core.cache import ResponseCache
from ckl_bench.core.cases import EvalCase
from ckl_bench.core.runner import RunOptions, _aggregate_case, run_cases


class CountingAdapter:
    """Mock adapter that counts calls and reports token usage."""

    name = "counting"
    model = "fake-model"
    temperature = 0.0
    max_tokens = 16

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request) -> GenerateResponse:
        self.calls += 1
        return GenerateResponse(
            text='{"ok": true}',
            raw={"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            metadata={"model": self.model, "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
        )


class FailingAdapter:
    name = "failing"
    model = "fake-model"

    def generate(self, request) -> GenerateResponse:
        raise RuntimeError("adapter boom")


class SequenceAdapter:
    name = "sequence"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request) -> GenerateResponse:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("second attempt failed")
        return GenerateResponse(text='{"ok": true}')


def chat_case(case_id: str = "c.ok.v1") -> EvalCase:
    return EvalCase(
        id=case_id,
        title="ok",
        type="chat",
        input={"prompt": "go"},
        expectations=[{"kind": "json_path", "path": "ok", "equals": True}],
        capability=["test"],
        difficulty=None,
        timeout_s=None,
        metadata={},
        source_path=Path("inline.jsonl"),
        source_line=1,
    )


class RunnerFeatureTests(unittest.TestCase):
    def test_summary_has_manifest_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cases([chat_case()], CountingAdapter(), RunOptions(out_dir=Path(tmp), run_name="m"))
            s = res["summary"]
            self.assertIn("manifest", s)
            self.assertEqual(s["manifest"]["schema_version"], "1.3")
            self.assertEqual(s["manifest"]["scoring_policy_version"], "1.0")
            self.assertEqual(s["manifest"]["error_policy_version"], "1.0")
            self.assertEqual(s["manifest"]["repeat_policy_version"], "1.0")
            self.assertEqual(s["manifest"]["model"]["model"], "fake-model")
            self.assertIn("comparability_signature", s["manifest"])
            self.assertEqual(s["manifest"]["comparability"]["cases"][0]["expectations"][0]["kind"], "json_path")
            self.assertEqual(s["usage"]["total_tokens"], 15)
            self.assertIn("pass_rate_ci", s)
            self.assertIn("score_ci", s)

    def test_repeat_produces_pass_at_k(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cases([chat_case()], CountingAdapter(), RunOptions(out_dir=Path(tmp), run_name="r", repeat=4))
            s = res["summary"]
            self.assertEqual(s["repeat"], 4)
            self.assertEqual(s["pass_at_1"], 1.0)
            self.assertEqual(s["pass_at_k"], 1.0)
            self.assertEqual(s["pass_pow_k"], 1.0)
            self.assertEqual(len(res["results"][0]["attempts"]), 4)

    def test_adapter_error_does_not_grade_empty_response(self) -> None:
        case = chat_case()
        case = EvalCase(
            **{
                **case.__dict__,
                "expectations": [{"kind": "not_contains", "value": "forbidden"}],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cases([case], FailingAdapter(), RunOptions(out_dir=Path(tmp), run_name="error"))
        result = res["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"], [])
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertEqual(result["error_message"], "adapter boom")
        self.assertEqual(result["error"], "RuntimeError: adapter boom")

    def test_repeat_mixed_execution_failure_fails_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cases(
                [chat_case()], SequenceAdapter(),
                RunOptions(out_dir=Path(tmp), run_name="mixed", repeat=3),
            )
        result = res["results"][0]
        # Score averages only completed attempts (error = infra failure, not 0.0)
        self.assertAlmostEqual(result["score"], 1.0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(result["completed_count"], 2)
        self.assertEqual(result["passed_count"], 2)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual([a["status"] for a in result["attempts"]], ["completed", "error", "completed"])
        # pass@k uses completed_count (errors are infra failures, not model failures)
        self.assertEqual(result["pass_at_1"], round(2 / 2, 6))

    def test_concurrency_matches_sequential(self) -> None:
        cases = [chat_case(f"c.{i}.v1") for i in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            seq = run_cases(cases, CountingAdapter(), RunOptions(out_dir=Path(tmp), run_name="seq", concurrency=1))
            par = run_cases(cases, CountingAdapter(), RunOptions(out_dir=Path(tmp), run_name="par", concurrency=4))
        self.assertEqual(seq["summary"]["passed"], par["summary"]["passed"])
        self.assertEqual([r["case_id"] for r in seq["results"]], [r["case_id"] for r in par["results"]])

    def test_cache_avoids_second_call(self) -> None:
        adapter = CountingAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            cache = ResponseCache(Path(tmp) / "cache")
            run_cases([chat_case()], adapter, RunOptions(out_dir=Path(tmp), run_name="c1", cache=cache))
            self.assertEqual(adapter.calls, 1)
            run_cases([chat_case()], adapter, RunOptions(out_dir=Path(tmp), run_name="c2", cache=cache))
            self.assertEqual(adapter.calls, 1)  # second run served from cache

    def test_manifest_signature_is_deterministic_and_excludes_secrets(self) -> None:
        class SecretAdapter(CountingAdapter):
            api_key = "super-secret"
            headers = {"Authorization": "Bearer secret", "X-Mode": "strict"}
            extra_body = {"reasoning": {"effort": "high"}, "access_token": "hidden"}

        with tempfile.TemporaryDirectory() as tmp:
            first = run_cases(
                [chat_case()], SecretAdapter(),
                RunOptions(out_dir=Path(tmp), run_name="sig1", concurrency=1),
            )["summary"]["manifest"]
            second = run_cases(
                [chat_case()], SecretAdapter(),
                RunOptions(out_dir=Path(tmp), run_name="sig2", concurrency=8),
            )["summary"]["manifest"]
        self.assertEqual(first["comparability_signature"], second["comparability_signature"])
        serialized = str(first["comparability"])
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("Bearer secret", serialized)
        self.assertNotIn("hidden", serialized)
        self.assertEqual(first["comparability"]["primary_adapter"]["extra_body"]["access_token"], "<redacted>")
        self.assertEqual(first["comparability"]["primary_adapter"]["headers"]["Authorization"], "<redacted>")
        self.assertEqual(first["comparability"]["primary_adapter"]["headers"]["X-Mode"], "strict")

    def test_cache_hit_preserves_estimate_but_has_no_provider_cost(self) -> None:
        import os

        adapter = CountingAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            pricing = Path(tmp) / "pricing.json"
            pricing.write_text('{"fake-model": {"input": 1000.0, "output": 1000.0}}', encoding="utf-8")
            os.environ["CKL_PRICING_FILE"] = str(pricing)
            try:
                cache = ResponseCache(Path(tmp) / "cache")
                run_cases([chat_case()], adapter, RunOptions(out_dir=Path(tmp), run_name="fresh", cache=cache))
                cached = run_cases([chat_case()], adapter, RunOptions(out_dir=Path(tmp), run_name="cached", cache=cache))
            finally:
                os.environ.pop("CKL_PRICING_FILE", None)
        result = cached["results"][0]
        self.assertGreater(result["estimated_cost_usd"], 0.0)
        self.assertEqual(result["provider_cost_usd"], 0.0)
        self.assertEqual(result["cost_status"], "estimated")
        self.assertEqual(result["cache_hits"], 1)

    def test_mixed_known_unknown_attempt_cost_is_unknown(self) -> None:
        attempt = {
            "attempt": 0, "status": "completed", "score": 1.0, "passed": True,
            "checks": [], "latency_ms": 1.0, "response_text": "ok", "error": None,
            "error_type": None, "error_message": None, "usage": {}, "model": "x",
            "cache_hit": False, "provider_cost_usd": 0.1,
        }
        result = _aggregate_case(
            chat_case(),
            [
                {**attempt, "estimated_cost_usd": 0.1, "cost_usd": 0.1},
                {**attempt, "attempt": 1, "estimated_cost_usd": None, "cost_usd": None, "provider_cost_usd": None},
            ],
            2,
        )
        self.assertIsNone(result["estimated_cost_usd"])
        self.assertIsNone(result["cost_usd"])
        self.assertEqual(result["known_cost_attempts"], 1)
        self.assertEqual(result["unknown_cost_attempts"], 1)

    def test_cost_estimated_with_pricing_env(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            pricing = Path(tmp) / "pricing.json"
            pricing.write_text('{"fake-model": {"input": 1000.0, "output": 1000.0}}', encoding="utf-8")
            os.environ["CKL_PRICING_FILE"] = str(pricing)
            try:
                res = run_cases([chat_case()], CountingAdapter(), RunOptions(out_dir=Path(tmp), run_name="cost"))
            finally:
                os.environ.pop("CKL_PRICING_FILE", None)
            # 15 tokens total at $1000/M each side -> > 0 cost recorded.
            self.assertGreater(res["summary"]["cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
