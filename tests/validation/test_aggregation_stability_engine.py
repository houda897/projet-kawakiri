import unittest
from unittest.mock import MagicMock, patch

from validation.aggregation_stability_engine import AggregationStabilityEngine


class DummyEdge:
    def __init__(self, src, tgt, src_col, tgt_col):
        self.source_table = src
        self.target_table = tgt
        self.source_columns = [src_col]
        self.target_columns = [tgt_col]


class DummyCandidate:
    def __init__(self, facts, dims, edges):
        self.model_id = "test_model"
        self.fact_tables = facts
        self.dimension_tables = dims
        self.edges = edges


class TestAggregationStabilityEngine(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.engine = AggregationStabilityEngine(self.mock_db)

    @patch.object(AggregationStabilityEngine, "_get_best_measure")
    def test_check_stability_stable(self, mock_get_measure):
        """Tests the case where SQL queries return exactly the same results (Stable)"""
        edge = DummyEdge("fact_A", "dim_B", "fk_id", "pk_id")
        candidate = DummyCandidate(["fact_A"], ["dim_B"], [edge])

        mock_get_measure.return_value = "amount"

        mock_fine = MagicMock()
        mock_fine.result_rows = [[100.0, 5, 20.0]]
        mock_agg = MagicMock()
        mock_agg.result_rows = [[100.0, 5, 20.0]]
        self.mock_db.query.side_effect = [mock_fine, mock_agg]

        reports = self.engine.check_stability(candidate)  # type: ignore

        self.assertEqual(len(reports), 1)
        self.assertTrue(reports[0]["is_stable"])
        self.assertEqual(reports[0]["delta_sum"], 0.0)
        self.assertEqual(reports[0]["reason"], "Stable")

    @patch.object(AggregationStabilityEngine, "_get_best_measure")
    def test_check_stability_unstable_fanout(self, mock_get_measure):
        """Tests the case where the join generates duplicates (Fan-out)"""
        edge = DummyEdge("fact_A", "dim_B", "fk_id", "pk_id")
        candidate = DummyCandidate(["fact_A"], ["dim_B"], [edge])

        mock_get_measure.return_value = "amount"

        mock_fine = MagicMock()
        mock_fine.result_rows = [[100.0, 5, 20.0]]
        mock_agg = MagicMock()
        mock_agg.result_rows = [[250.0, 10, 25.0]]
        self.mock_db.query.side_effect = [mock_fine, mock_agg]

        reports = self.engine.check_stability(candidate)  # type: ignore

        self.assertEqual(len(reports), 1)
        self.assertFalse(reports[0]["is_stable"])
        self.assertTrue("SUM instability" in reports[0]["reason"])
        self.assertTrue("COUNT instability" in reports[0]["reason"])
        self.assertEqual(reports[0]["delta_sum"], 150.0)
