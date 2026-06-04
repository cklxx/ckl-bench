from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from evalbench.cli import main
from evalbench.core.env import load_default_env, load_env_file
from evalbench.core.providers import load_provider


class EvalBenchCLITests(unittest.TestCase):
    def test_env_file_loader_keeps_existing_shell_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("EVB_TEST_KEY=from_file\nEVB_TEST_QUOTED=\"hello world\"\n", encoding="utf-8")
            import os

            old_key = os.environ.get("EVB_TEST_KEY")
            old_quoted = os.environ.get("EVB_TEST_QUOTED")
            try:
                os.environ["EVB_TEST_KEY"] = "from_shell"
                load_env_file(env_path)
                self.assertEqual(os.environ["EVB_TEST_KEY"], "from_shell")
                self.assertEqual(os.environ["EVB_TEST_QUOTED"], "hello world")
            finally:
                if old_key is None:
                    os.environ.pop("EVB_TEST_KEY", None)
                else:
                    os.environ["EVB_TEST_KEY"] = old_key
                if old_quoted is None:
                    os.environ.pop("EVB_TEST_QUOTED", None)
                else:
                    os.environ["EVB_TEST_QUOTED"] = old_quoted

    def test_default_env_file_can_be_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("EVB_DOTENV_TEST=loaded\n", encoding="utf-8")
            import os

            old_env_file = os.environ.get("EVB_ENV_FILE")
            old_value = os.environ.get("EVB_DOTENV_TEST")
            try:
                os.environ["EVB_ENV_FILE"] = str(env_path)
                os.environ.pop("EVB_DOTENV_TEST", None)
                loaded = load_default_env()
                self.assertIn("EVB_DOTENV_TEST", loaded)
                self.assertEqual(os.environ["EVB_DOTENV_TEST"], "loaded")
            finally:
                if old_env_file is None:
                    os.environ.pop("EVB_ENV_FILE", None)
                else:
                    os.environ["EVB_ENV_FILE"] = old_env_file
                if old_value is None:
                    os.environ.pop("EVB_DOTENV_TEST", None)
                else:
                    os.environ["EVB_DOTENV_TEST"] = old_value

    def test_help_mentions_short_entrypoint(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(StringIO()) as stdout:
                main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn("Quick commands:", help_text)
        self.assertIn("run command agent", help_text)
        self.assertIn("report.html", help_text)
        self.assertIn("EVB_JUDGE", help_text)

    def test_namespaces_lists_deepseekv4(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            code = main(["namespaces"])
        self.assertEqual(code, 0)
        self.assertIn("deepseekv4", stdout.getvalue())

    def test_jsonl_namespace_alias_loads_provider(self) -> None:
        provider = load_provider("dsv4", environ={})
        self.assertIsNotNone(provider)
        provider = provider or {}
        self.assertEqual(provider["id"], "deepseekv4")
        self.assertEqual(provider["config"]["base_url"], "https://api.deepseek.com")
        self.assertEqual(provider["config"]["api_key_envs"], ["DSV4_API_KEY", "DEEPSEEK_API_KEY"])

    def test_short_chat_command_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                code = main(["run", "chat", "--out", tmp, "--run-name", "chat"])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "chat" / "report.html").exists())

    def test_short_command_agent_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                code = main(["run", "command", "agent", "--out", tmp, "--run-name", "agent"])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "agent" / "summary.json").exists())

    def test_run_repeat_writes_pass_at_k(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                code = main(["run", "chat", "--out", tmp, "--run-name", "rep", "--repeat", "3"])
            self.assertEqual(code, 0)
            summary = json.loads((Path(tmp) / "rep" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["repeat"], 3)
            self.assertIn("pass_at_k", summary)

    def test_diff_command_detects_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                main(["run", "chat", "--out", tmp, "--run-name", "A"])
                main(["run", "chat", "--out", tmp, "--run-name", "B"])
            with redirect_stdout(StringIO()) as out:
                code = main(["diff", str(Path(tmp) / "A"), str(Path(tmp) / "B")])
            self.assertEqual(code, 0)
            self.assertIn("Diff", out.getvalue())

    def test_fail_under_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                code = main(["run", "chat", "--out", tmp, "--run-name", "gate", "--fail-under", "0.99"])
            self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
