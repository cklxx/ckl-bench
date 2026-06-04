from __future__ import annotations

import unittest

from evalbench.core.stats import (
    bootstrap_mean_ci,
    mean,
    pass_at_k,
    standard_error,
    wilson_interval,
)


class StatsTests(unittest.TestCase):
    def test_mean_handles_empty(self) -> None:
        self.assertEqual(mean([]), 0.0)
        self.assertAlmostEqual(mean([1.0, 2.0, 3.0]), 2.0)

    def test_standard_error_bounds(self) -> None:
        self.assertEqual(standard_error(0.5, 0), 0.0)
        self.assertAlmostEqual(standard_error(0.5, 100), 0.05)

    def test_wilson_interval_brackets_point_estimate(self) -> None:
        low, high = wilson_interval(8, 10)
        self.assertLess(low, 0.8)
        self.assertGreater(high, 0.8)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 1.0)

    def test_wilson_interval_handles_boundaries(self) -> None:
        low, high = wilson_interval(0, 5)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.0)
        low, high = wilson_interval(5, 5)
        self.assertLess(low, 1.0)
        self.assertEqual(high, 1.0)

    def test_wilson_interval_empty(self) -> None:
        self.assertEqual(wilson_interval(0, 0), (0.0, 0.0))

    def test_pass_at_k_basic(self) -> None:
        # All samples correct -> certainty.
        self.assertEqual(pass_at_k(5, 5, 1), 1.0)
        # No samples correct -> zero.
        self.assertEqual(pass_at_k(5, 0, 1), 0.0)
        # pass@1 with half correct == c/n.
        self.assertAlmostEqual(pass_at_k(10, 5, 1), 0.5)

    def test_pass_at_k_unbiased_vs_naive(self) -> None:
        # n=5, c=1, k=2: 1 - C(4,2)/C(5,2) = 1 - 6/10 = 0.4
        self.assertAlmostEqual(pass_at_k(5, 1, 2), 0.4)
        # k capped at n.
        self.assertEqual(pass_at_k(3, 1, 10), 1.0)

    def test_pass_at_k_validates(self) -> None:
        with self.assertRaises(ValueError):
            pass_at_k(3, 5, 1)

    def test_bootstrap_is_deterministic(self) -> None:
        values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        a = bootstrap_mean_ci(values, seed=42)
        b = bootstrap_mean_ci(values, seed=42)
        self.assertEqual(a, b)
        low, high = a
        self.assertLessEqual(low, mean(values))
        self.assertGreaterEqual(high, mean(values))

    def test_bootstrap_edge_cases(self) -> None:
        self.assertEqual(bootstrap_mean_ci([]), (0.0, 0.0))
        self.assertEqual(bootstrap_mean_ci([0.7]), (0.7, 0.7))


if __name__ == "__main__":
    unittest.main()
