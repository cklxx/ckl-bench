from __future__ import annotations

import unittest

from evalbench.core.usage import (
    DEFAULT_PRICING,
    Usage,
    estimate_cost,
    normalize_usage,
)


class UsageTests(unittest.TestCase):
    def test_openai_shape(self) -> None:
        raw = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        u = normalize_usage(raw)
        self.assertEqual(u.input_tokens, 10)
        self.assertEqual(u.output_tokens, 5)
        self.assertEqual(u.total_tokens, 15)

    def test_anthropic_shape(self) -> None:
        raw = {"usage": {"input_tokens": 7, "output_tokens": 3}}
        u = normalize_usage(raw)
        self.assertEqual(u.input_tokens, 7)
        self.assertEqual(u.output_tokens, 3)
        self.assertEqual(u.total_tokens, 10)  # derived

    def test_gemini_shape(self) -> None:
        raw = {"usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8, "totalTokenCount": 20}}
        u = normalize_usage(raw)
        self.assertEqual(u.input_tokens, 12)
        self.assertEqual(u.output_tokens, 8)
        self.assertEqual(u.total_tokens, 20)

    def test_missing_usage(self) -> None:
        self.assertEqual(normalize_usage({"choices": []}), Usage())
        self.assertEqual(normalize_usage(None), Usage())
        self.assertEqual(normalize_usage("nope"), Usage())

    def test_usage_addition(self) -> None:
        total = Usage(1, 2, 3) + Usage(4, 5, 9)
        self.assertEqual(total.as_dict(), {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12})

    def test_cost_known_model(self) -> None:
        rates = DEFAULT_PRICING["gpt-4.1-mini"]
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000)
        expected = rates["input"] + rates["output"]
        self.assertAlmostEqual(estimate_cost(usage, "gpt-4.1-mini"), round(expected, 6))

    def test_cost_unknown_model_is_zero(self) -> None:
        self.assertEqual(estimate_cost(Usage(100, 100, 200), "mystery-model"), 0.0)
        self.assertEqual(estimate_cost(Usage(100, 100, 200), None), 0.0)

    def test_cost_override(self) -> None:
        pricing = {"x": {"input": 1000.0, "output": 0.0}}
        usage = Usage(input_tokens=1_000_000, output_tokens=0, total_tokens=1_000_000)
        self.assertAlmostEqual(estimate_cost(usage, "x", pricing), 1000.0)


if __name__ == "__main__":
    unittest.main()
