import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "benchmark",
    Path(__file__).resolve().parents[1] / "scripts/benchmark_long_range_retrieval.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BenchmarkTests(unittest.TestCase):
    def test_dedup_uses_numeric_latest_version(self):
        self.assertEqual(
            mod.deduplicate([{"id": "2601.00001v9"}, {"id": "2601.00001v10"}]),
            [{"id": "2601.00001v10"}],
        )

    def test_sql_literals_escape_quotes(self):
        self.assertEqual(mod.literal("a'b"), "'a''b'")

    def test_judge_must_return_exact_ids_and_valid_score(self):
        row = {"id": "x", "score": 8, "label": "direct", "reason": "明确研究该方法"}
        self.assertEqual(mod.validate_labels({"papers": [row]}, ["x"]), [row])
        with self.assertRaises(AssertionError):
            mod.validate_labels({"papers": [row, row]}, ["x"])
        with self.assertRaises(AssertionError):
            mod.validate_labels({"papers": [dict(row, score=11)]}, ["x"])
        with self.assertRaises(AssertionError):
            mod.validate_labels({"papers": [dict(row, score=7)]}, ["x"])

    def test_evidence_requires_source_text_not_fabricated_ellipsis(self):
        self.assertTrue(
            mod.evidence_is_verbatim("asymmetric TSP", "We study asymmetric\nTSP.")
        )
        self.assertFalse(
            mod.evidence_is_verbatim("We ... TSP", "We study asymmetric TSP.")
        )
        self.assertFalse(mod.evidence_is_verbatim("", "Any paper"))


if __name__ == "__main__":
    unittest.main()
