from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from ckl_bench.core.reporting import _load_web_template
from ckl_bench.resources import resource_path

ROOT = Path(__file__).resolve().parent.parent


class ReleaseContractTests(unittest.TestCase):
    def test_generated_resources_are_in_sync(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_resources.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_checkout_wrapper_is_thin_package_shim(self) -> None:
        wrapper = (ROOT / "scripts" / "claude_code_wrapper.py").read_text(encoding="utf-8")
        self.assertIn("from ckl_bench.wrappers.claude_code import main", wrapper)
        self.assertNotIn("subprocess", wrapper)
        self.assertFalse((ROOT / "scripts" / "_common.py").exists())

    def test_packaged_resources_and_frontend_are_available(self) -> None:
        self.assertTrue((resource_path("cases/chat") / "hard_programming.jsonl").is_file())
        self.assertTrue((resource_path("configs") / "mock.responses.json").is_file())
        self.assertTrue((resource_path("registries/models") / "deepseekv4.jsonl").is_file())
        template = _load_web_template()
        self.assertIn("<html", template)
        self.assertIn('id="root"', template)

    def test_supported_node_version_is_pinned(self) -> None:
        package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
        expected = ">=20.19 <21 || >=22.12 <23"
        self.assertEqual(package["engines"]["node"], expected)
        self.assertEqual(lock["packages"][""]["engines"]["node"], expected)
        self.assertEqual((ROOT / ".nvmrc").read_text(encoding="utf-8").strip(), "22")


if __name__ == "__main__":
    unittest.main()
