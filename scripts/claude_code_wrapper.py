#!/usr/bin/env python3
"""Checkout-compatible shim for :mod:`ckl_bench.wrappers.claude_code`."""

from ckl_bench.wrappers.claude_code import main

if __name__ == "__main__":
    raise SystemExit(main())
