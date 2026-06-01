from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evalbench.adapters.mock import MockAdapter
from evalbench.core.cases import load_cases
from evalbench.core.runner import RunOptions, run_cases


class EvalBenchCoreTests(unittest.TestCase):
    def test_load_repo_cases(self) -> None:
        cases = load_cases(["cases"])
        ids = {case.id for case in cases}
        self.assertIn("chat.noisy_spec_extraction.v1", ids)
        self.assertIn("agent.config_patch.v1", ids)

    def test_mock_run_passes_chat_case(self) -> None:
        cases = [
            case for case in load_cases(["cases/chat"])
            if case.id == "chat.noisy_spec_extraction.v1"
        ]
        adapter = MockAdapter(
            {
                "responses": {
                    "chat.noisy_spec_extraction.v1": (
                        '{"city":"shenzhen","window":"02:00-03:00","rollback_owner":"mira"}'
                    )
                }
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cases(cases, adapter, RunOptions(out_dir=Path(tmp), run_name="unit"))
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["summary"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
