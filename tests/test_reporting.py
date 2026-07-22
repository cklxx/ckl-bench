from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ckl_bench.core.reporting import (
    _render_react_page,
    render_diff_terminal,
    render_terminal_report,
    write_probe_html_report,
)


class ReportingTests(unittest.TestCase):
    def test_react_bootstrap_is_inert_and_escapes_html(self) -> None:
        payload = "</script><script>alert(1)</script> &"
        page = _render_react_page({"payload": payload})
        self.assertIn('type="application/json"', page)
        self.assertNotIn(payload, page)
        self.assertIn("\\u003c/script\\u003e", page)
        self.assertIn("\\u0026", page)
        self.assertIn("\\u2028", page)

    def test_terminal_report_renders_unavailable_metrics(self) -> None:
        report = render_terminal_report(
            {
                "score": None,
                "passed": 0,
                "failed": 0,
                "errored": 1,
                "total": 1,
                "repeat": 2,
                "pass_at_1": None,
                "pass_at_k": None,
                "pass_pow_k": None,
                "by_capability": {"chat": {"score": None, "passed": 0, "count": 1}},
            },
            [{"case_id": "x", "score": None, "passed": None, "error": "boom"}],
            "run",
        )
        self.assertIn("Score  N/A", report)
        self.assertIn("pass@1", report)
        self.assertIn("N/A", report)
        self.assertIn("score=N/A", report)

    def test_probe_html_keeps_unavailable_average_nullable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_probe_html_report(
                Path(tmp) / "probe.html",
                [{"target": "x", "kind": "api", "status": "fail", "score": None, "detail": "error"}],
            )
            self.assertIn('"score": null', path.read_text(encoding="utf-8"))

    def test_diff_terminal_handles_unavailable_scores(self) -> None:
        output = render_diff_terminal(
            {
                "run_a": "A",
                "run_b": "B",
                "score_a": None,
                "score_b": None,
                "score_delta": None,
                "comparability": {"status": "indeterminate", "differences": []},
                "counts": {"regressed": 0, "improved": 0, "unchanged": 0, "added": 0, "removed": 0, "indeterminate": 1},
                "cases": [{"case_id": "x", "status": "indeterminate", "a_score": None, "b_score": None}],
            }
        )
        self.assertIn("Score", output)
        self.assertEqual(output.count("N/A"), 2)
        self.assertIn("UNKNOWN", output)


if __name__ == "__main__":
    unittest.main()
