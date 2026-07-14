from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ckl_bench.adapters.base import GenerateResponse
from ckl_bench.core.cache import ResponseCache
from ckl_bench.core.cases import EvalCase
from ckl_bench.core.runner import RunOptions, run_cases


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
            self.assertEqual(s["manifest"]["schema_version"], "1.1")
            self.assertEqual(s["manifest"]["model"]["model"], "fake-model")
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
