"""Tests for provider registry and default judge resolution."""

from __future__ import annotations

import unittest


class DsxProviderTests(unittest.TestCase):
    def test_dsx_resolves_as_command_provider(self) -> None:
        from ckl_bench.core.providers import load_provider

        provider = load_provider("dsx")
        self.assertIsNotNone(provider)
        self.assertEqual(provider["adapter"], "command")
        self.assertEqual(provider["config"].get("command"), "dsx")

    def test_default_judge_target_is_dsx(self) -> None:
        from ckl_bench.core.run_manager import DEFAULT_JUDGE_TARGET

        self.assertEqual(DEFAULT_JUDGE_TARGET, "dsx")

    def test_resolve_dsx_builds_command_adapter(self) -> None:
        from ckl_bench.core.run_manager import _resolve

        adapter = _resolve("dsx")
        self.assertIsNotNone(adapter)
        self.assertEqual(getattr(adapter, "display_name", None), "dsx")


if __name__ == "__main__":
    unittest.main()
