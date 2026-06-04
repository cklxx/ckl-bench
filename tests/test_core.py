from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evalbench.adapters.mock import MockAdapter
from evalbench.core.cases import EvalCase, load_cases
from evalbench.core.runner import RunOptions, run_cases


class EvalBenchCoreTests(unittest.TestCase):
    def test_load_repo_cases(self) -> None:
        cases = load_cases(["cases"])
        ids = {case.id for case in cases}
        self.assertIn("chat.js_event_loop_microtask_order.v1", ids)
        self.assertIn("agent.fix_binary_search_off_by_one.v1", ids)

    def test_mock_run_passes_chat_case(self) -> None:
        cases = [
            case for case in load_cases(["cases/chat"])
            if case.id == "chat.js_event_loop_microtask_order.v1"
        ]
        adapter = MockAdapter(
            {
                "responses": {
                    "chat.js_event_loop_microtask_order.v1": (
                        '{"order":["A","D","C","B"]}'
                    )
                }
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cases(cases, adapter, RunOptions(out_dir=Path(tmp), run_name="unit"))
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["summary"]["failed"], 0)

    def test_judge_expectation_uses_judge_adapter(self) -> None:
        case = EvalCase(
            id="chat.judge.inline.v1",
            title="Judge inline answer",
            type="chat",
            input={"prompt": "Explain the invariant."},
            expectations=[
                {
                    "kind": "judge",
                    "criteria": "Pass if the answer identifies idempotency tied to task_id.",
                    "threshold": 0.7,
                }
            ],
            capability=["judge"],
            difficulty="s1",
            timeout_s=None,
            metadata={"pass_threshold": 0.7},
            source_path=Path("inline.jsonl"),
            source_line=1,
        )
        adapter = MockAdapter({"default_response": "The invariant is idempotency by task_id."})
        judge = MockAdapter(
            {
                "responses": {
                    "chat.judge.inline.v1:judge": (
                        '{"score":0.82,"passed":true,"reason":"captures the required invariant"}'
                    )
                }
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cases(
                [case],
                adapter,
                RunOptions(out_dir=Path(tmp), run_name="judge", judge_adapter=judge, judge_name="mock-judge"),
            )
        self.assertEqual(result["summary"]["judge"], "mock-judge")
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertAlmostEqual(result["summary"]["score"], 0.82)
        self.assertIn("judge score=0.820", result["results"][0]["checks"][0]["detail"])

    def test_claude_code_wrapper_syncs_fixed_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "answer.txt").write_text("before\n", encoding="utf-8")
            fake_claude = root / "fake_claude.py"
            fake_claude.write_text(
                (
                    "from pathlib import Path\n"
                    "Path('answer.txt').write_text('after\\n', encoding='utf-8')\n"
                    "print('{\"result\":\"DONE\"}')\n"
                ),
                encoding="utf-8",
            )
            payload = {
                "case_id": "agent.fake.v1",
                "prompt": "edit answer.txt",
                "workspace_path": str(workspace),
                "timeout_s": 10,
            }
            env = os.environ.copy()
            env.update(
                {
                    "EVB_CLAUDE_COMMAND": f"{sys.executable} {fake_claude}",
                    "EVB_CLAUDE_API_KEY": "test-key",
                    "EVB_CLAUDE_ANTHROPIC_BASE_URL": "https://example.test/anthropic",
                    "EVB_CLAUDE_WORKSPACE_DIR": str(root / "inspect"),
                }
            )
            completed = subprocess.run(
                [sys.executable, "scripts/claude_code_wrapper.py"],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                env=env,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual((workspace / "answer.txt").read_text(encoding="utf-8"), "after\n")
            self.assertTrue((root / "inspect" / "agent.fake.v1" / "answer.txt").exists())


if __name__ == "__main__":
    unittest.main()
