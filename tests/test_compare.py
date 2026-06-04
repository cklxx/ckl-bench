from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evalbench.core.compare import compare_runs, load_run


def results(*pairs: tuple[str, bool, float]) -> list[dict]:
    return [{"case_id": cid, "passed": p, "score": s} for cid, p, s in pairs]


class CompareTests(unittest.TestCase):
    def test_classifies_regression_and_improvement(self) -> None:
        a = results(("x", True, 1.0), ("y", False, 0.0), ("z", True, 1.0))
        b = results(("x", False, 0.0), ("y", True, 1.0), ("z", True, 1.0))
        diff = compare_runs({"run_id": "A", "score": 0.66}, a, {"run_id": "B", "score": 0.66}, b)
        self.assertEqual(diff["counts"]["regressed"], 1)
        self.assertEqual(diff["counts"]["improved"], 1)
        self.assertEqual(diff["counts"]["unchanged"], 1)
        # Regressions sort first.
        self.assertEqual(diff["cases"][0]["status"], "regressed")
        self.assertEqual(diff["cases"][0]["case_id"], "x")

    def test_added_and_removed(self) -> None:
        a = results(("only_a", True, 1.0))
        b = results(("only_b", True, 1.0))
        diff = compare_runs({}, a, {}, b)
        self.assertEqual(diff["counts"]["added"], 1)
        self.assertEqual(diff["counts"]["removed"], 1)

    def test_score_delta_without_pass_flip(self) -> None:
        a = results(("x", True, 0.8))
        b = results(("x", True, 1.0))
        diff = compare_runs({"score": 0.8}, a, {"score": 1.0}, b)
        self.assertEqual(diff["counts"]["improved"], 1)
        self.assertAlmostEqual(diff["cases"][0]["delta"], 0.2)

    def test_load_run_from_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run1"
            run.mkdir()
            (run / "summary.json").write_text(json.dumps({"run_id": "run1", "score": 0.5}), encoding="utf-8")
            (run / "results.jsonl").write_text(
                json.dumps({"case_id": "x", "passed": True, "score": 1.0}) + "\n", encoding="utf-8"
            )
            summary, res = load_run(run)
            self.assertEqual(summary["run_id"], "run1")
            self.assertEqual(len(res), 1)
            # Also loadable directly via summary.json path.
            summary2, _ = load_run(run / "summary.json")
            self.assertEqual(summary2["run_id"], "run1")


if __name__ == "__main__":
    unittest.main()
