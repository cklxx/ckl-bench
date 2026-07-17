from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ckl_bench.core.compare import compare_runs, load_run


def results(*pairs: tuple[str, bool, float]) -> list[dict]:
    return [{"case_id": cid, "passed": p, "score": s} for cid, p, s in pairs]


def summary(run_id: str, score: float, signature: str | None = "same", policy: dict | None = None) -> dict:
    manifest = {}
    if signature is not None:
        manifest = {"comparability_signature": signature, "comparability": policy or {"seed": 0}}
    return {"run_id": run_id, "score": score, "manifest": manifest}


class CompareTests(unittest.TestCase):
    def test_classifies_regression_and_improvement(self) -> None:
        a = results(("x", True, 1.0), ("y", False, 0.0), ("z", True, 1.0))
        b = results(("x", False, 0.0), ("y", True, 1.0), ("z", True, 1.0))
        diff = compare_runs(summary("A", 0.66), a, summary("B", 0.66), b)
        self.assertEqual(diff["counts"]["regressed"], 1)
        self.assertEqual(diff["counts"]["improved"], 1)
        self.assertEqual(diff["counts"]["unchanged"], 1)
        # Regressions sort first.
        self.assertEqual(diff["cases"][0]["status"], "regressed")
        self.assertEqual(diff["cases"][0]["case_id"], "x")

    def test_added_and_removed(self) -> None:
        a = results(("only_a", True, 1.0))
        b = results(("only_b", True, 1.0))
        diff = compare_runs(summary("A", 0.0), a, summary("B", 0.0), b)
        self.assertEqual(diff["counts"]["added"], 1)
        self.assertEqual(diff["counts"]["removed"], 1)

    def test_score_delta_without_pass_flip(self) -> None:
        a = results(("x", True, 0.8))
        b = results(("x", True, 1.0))
        diff = compare_runs(summary("A", 0.8), a, summary("B", 1.0), b)
        self.assertEqual(diff["counts"]["improved"], 1)
        self.assertAlmostEqual(diff["cases"][0]["delta"], 0.2)

    def test_compatible_compare_has_aggregate_verdict(self) -> None:
        diff = compare_runs(
            summary("A", 0.5), results(("x", False, 0.0)),
            summary("B", 1.0), results(("x", True, 1.0)),
        )
        self.assertEqual(diff["comparability"]["status"], "compatible")
        self.assertEqual(diff["aggregate_verdict"], "improved")
        self.assertEqual(diff["score_delta"], 0.5)

    def test_incompatible_compare_suppresses_aggregate_verdict(self) -> None:
        diff = compare_runs(
            summary("A", 0.5, "a", {"seed": 0}), results(("x", False, 0.0)),
            summary("B", 1.0, "b", {"seed": 1}), results(("x", True, 1.0)),
        )
        self.assertEqual(diff["comparability"]["status"], "incompatible")
        self.assertIn("seed", [d["path"] for d in diff["comparability"]["differences"]])
        self.assertIsNone(diff["aggregate_verdict"])
        self.assertIsNone(diff["score_delta"])
        self.assertEqual(diff["cases"][0]["status"], "improved")

    def test_legacy_compare_is_unknown(self) -> None:
        diff = compare_runs(
            summary("A", 0.5, None), results(("x", False, 0.0)),
            summary("B", 1.0), results(("x", True, 1.0)),
        )
        self.assertEqual(diff["comparability"]["status"], "unknown")
        self.assertIsNotNone(diff["comparability"]["warning"])
        self.assertIsNone(diff["aggregate_verdict"])

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
