#!/usr/bin/env python3
"""Checkout-compatible shim for :mod:`ckl_bench.wrappers.codex`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ckl_bench.wrappers.codex import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
