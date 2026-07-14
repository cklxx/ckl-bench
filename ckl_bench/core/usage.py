"""Normalize token usage across providers and estimate run cost.

Every serious eval platform reports tokens and dollars next to accuracy, because
a model that is one point better but five times the cost is rarely the right
pick. Providers report usage in different shapes:

- OpenAI-compatible: ``usage.prompt_tokens`` / ``completion_tokens`` / ``total_tokens``
- Anthropic:         ``usage.input_tokens`` / ``output_tokens``
- Gemini:            ``usageMetadata.promptTokenCount`` / ``candidatesTokenCount``

``normalize_usage`` collapses them to a common ``{input, output, total}`` shape.
Pricing is best-effort and fully overridable: pass a ``pricing`` dict (USD per
million tokens) or set ``CKL_PRICING_FILE`` to a JSON file. Unknown models cost
0.0 and are reported as such rather than guessed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_usage(raw: Any) -> Usage:
    """Extract a ``Usage`` from a raw provider response (dict) -- shape agnostic."""
    if not isinstance(raw, dict):
        return Usage()
    # OpenAI / Anthropic style under "usage".
    usage = raw.get("usage")
    if isinstance(usage, dict):
        inp = _int(usage.get("prompt_tokens", usage.get("input_tokens", 0)))
        out = _int(usage.get("completion_tokens", usage.get("output_tokens", 0)))
        total = _int(usage.get("total_tokens", 0)) or (inp + out)
        return Usage(input_tokens=inp, output_tokens=out, total_tokens=total)
    # Gemini style under "usageMetadata".
    meta = raw.get("usageMetadata")
    if isinstance(meta, dict):
        inp = _int(meta.get("promptTokenCount", 0))
        out = _int(meta.get("candidatesTokenCount", 0))
        total = _int(meta.get("totalTokenCount", 0)) or (inp + out)
        return Usage(input_tokens=inp, output_tokens=out, total_tokens=total)
    return Usage()


# USD per 1,000,000 tokens. Best-effort defaults; override per run. Kept small
# and obviously-approximate on purpose -- this is a guide rail, not billing.
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    "gemini-3.5-flash": {"input": 0.075, "output": 0.30},
    "deepseek-v4-flash": {"input": 0.07, "output": 0.28},
}


def load_pricing(overrides: dict[str, dict[str, float]] | None = None) -> dict[str, dict[str, float]]:
    """Merge default pricing with ``CKL_PRICING_FILE`` and explicit overrides."""
    pricing = {model: dict(rates) for model, rates in DEFAULT_PRICING.items()}
    pricing_file = os.environ.get("CKL_PRICING_FILE")
    if pricing_file and Path(pricing_file).exists():
        loaded = json.loads(Path(pricing_file).read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for model, rates in loaded.items():
                if isinstance(rates, dict):
                    pricing[str(model)] = {k: float(v) for k, v in rates.items()}
    if overrides:
        for model, rates in overrides.items():
            pricing[str(model)] = {k: float(v) for k, v in rates.items()}
    return pricing


def estimate_cost(usage: Usage, model: str | None, pricing: dict[str, dict[str, float]] | None = None) -> float:
    """Best-effort USD cost for ``usage`` at ``model`` rates. Unknown -> 0.0."""
    if not model:
        return 0.0
    table = pricing if pricing is not None else load_pricing()
    rates = table.get(model)
    if rates is None:
        return 0.0
    cost = (usage.input_tokens / 1_000_000) * float(rates.get("input", 0.0))
    cost += (usage.output_tokens / 1_000_000) * float(rates.get("output", 0.0))
    return round(cost, 6)
