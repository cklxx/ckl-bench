#!/usr/bin/env python3
"""Checkout-compatible shim for :mod:`ckl_bench.wrappers.dsx`."""
from ckl_bench.wrappers.dsx import main

if __name__ == "__main__":
    raise SystemExit(main())
