"""Small, dependency-free statistics for evaluation reporting.

Top-tier eval harnesses never report a bare pass rate: they report it with an
uncertainty interval and, when cases are sampled multiple times, an unbiased
``pass@k``. This module provides those primitives using only the standard
library so the core runner stays install-free.

References:
- Wilson score interval for a binomial proportion.
- ``pass@k`` unbiased estimator from Chen et al., 2021 ("Evaluating Large
  Language Models Trained on Code", the HumanEval paper).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean, 0.0 for an empty sequence."""
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def standard_error(p: float, n: int) -> float:
    """Standard error of a proportion ``p`` over ``n`` observations."""
    if n <= 0:
        return 0.0
    p = min(max(p, 0.0), 1.0)
    return math.sqrt(p * (1.0 - p) / n)


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    Defaults to a 95% interval (``z`` ~= 1.96). Unlike the naive normal
    interval, Wilson behaves well at the boundaries (0% / 100%) and for small
    ``n``, which is exactly where eval suites with a handful of hard cases live.

    Returns ``(low, high)`` clamped to ``[0, 1]``.
    """
    if n <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > n:
        raise ValueError(f"successes {successes} out of range for n {n}")
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of ``pass@k`` given ``c`` correct out of ``n`` samples.

    ``pass@k`` is the probability that at least one of ``k`` independent samples
    is correct. The unbiased estimator avoids the optimistic bias of
    ``1 - (1 - c/n)**k`` when ``n`` is small:

        pass@k = 1 - C(n - c, k) / C(n, k)

    Edge cases: ``k`` is capped at ``n``; if every fix-window sample without a
    correct answer is too small to fill ``k`` (``n - c < k``) the chance of an
    all-wrong draw is zero, so ``pass@k`` is 1.
    """
    if n <= 0:
        return 0.0
    if c < 0 or c > n:
        raise ValueError(f"c {c} out of range for n {n}")
    k = min(k, n)
    if k <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_pow_k(n: int, c: int, k: int) -> float:
    """Reliability ``pass^k``: probability that ``k`` independent samples ALL pass.

    Where ``pass@k`` is optimistic (at least one of k succeeds), ``pass^k`` is the
    pessimistic reliability metric used by agent benchmarks (tau-bench): the
    chance every one of ``k`` attempts succeeds. Estimated without replacement as
    ``C(c, k) / C(n, k)``. A 90%-pass@1 agent can sit near 57% at ``pass^8`` --
    this is what surfaces flakiness a single shot hides.
    """
    if n <= 0:
        return 0.0
    if c < 0 or c > n:
        raise ValueError(f"c {c} out of range for n {n}")
    k = min(k, n)
    if k <= 0:
        return 1.0
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


def bootstrap_mean_ci(
    values: Sequence[float],
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean of ``values``.

    Deterministic given ``seed`` so reports are reproducible. Useful for scoring
    distributions (e.g. per-case fractional scores) where a closed-form binomial
    interval does not apply. Returns ``(low, high)``.
    """
    data = [float(v) for v in values]
    if not data:
        return (0.0, 0.0)
    if len(data) == 1:
        return (data[0], data[0])
    rng = random.Random(seed)
    n = len(data)
    means: list[float] = []
    for _ in range(max(1, resamples)):
        sample = (data[rng.randrange(n)] for _ in range(n))
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((1.0 - confidence) / 2.0 * len(means))
    hi_idx = min(len(means) - 1, int((1.0 + confidence) / 2.0 * len(means)))
    return (means[lo_idx], means[hi_idx])
