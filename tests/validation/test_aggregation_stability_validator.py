import unittest
from unittest.mock import MagicMock, patch

from validation.aggregation_stability_validator import AggregationStabilityValidator


class DummyEdge:
    def __init__(self, src, tgt, src_col, tgt_col):
        self.source_table = src
        self.target_table = tgt
        self.source_columns = (src_col,)
        self.target_columns = (tgt_col,)


class DummyCandidate:
    def __init__(self, facts, dims, edges):
        self.model_id = "test_model"
        self.fact_tables = facts
        self.dimension_tables = dims
        self.edges = edges


class TestAggregationStabilityValidator(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.validator = AggregationStabilityValidator(self.mock_db)

    @patch.object(AggregationStabilityValidator, "_get_best_dimension_grouping")
    @patch.object(AggregationStabilityValidator, "_get_best_measure")
    def test_check_stability_stable(self, mock_get_measure, mock_get_grouping):
        edge = DummyEdge("fact_A", "dim_B", "fk_id", "pk_id")
        candidate = DummyCandidate(["fact_A"], ["dim_B"], [edge])

        mock_get_measure.return_value = "amount"
        mock_get_grouping.return_value = "category"

        mock_fine = MagicMock()
        mock_fine.result_rows = [[100.0, 5, 20.0, 5.0, 35.0]]
        mock_agg = MagicMock()
        mock_agg.result_rows = [[100.0, 5, 20.0, 5.0, 35.0]]
        self.mock_db.query.side_effect = [mock_fine, mock_agg]

        reports = self.validator.check_stability(candidate)  # type: ignore[arg-type]

        self.assertEqual(len(reports), 1)
        self.assertTrue(reports[0]["is_stable"])
        self.assertEqual(reports[0]["group_column"], "category")
        self.assertEqual(reports[0]["delta_sum"], 0.0)
        self.assertEqual(reports[0]["delta_min"], 0.0)
        self.assertEqual(reports[0]["delta_max"], 0.0)

    @patch.object(AggregationStabilityValidator, "_get_best_dimension_grouping")
    @patch.object(AggregationStabilityValidator, "_get_best_measure")
    def test_check_stability_unstable_fanout(self, mock_get_measure, mock_get_grouping):
        edge = DummyEdge("fact_A", "dim_B", "fk_id", "pk_id")
        candidate = DummyCandidate(["fact_A"], ["dim_B"], [edge])

        mock_get_measure.return_value = "amount"
        mock_get_grouping.return_value = "category"

        mock_fine = MagicMock()
        mock_fine.result_rows = [[100.0, 5, 20.0, 5.0, 35.0]]
        mock_agg = MagicMock()
        mock_agg.result_rows = [[250.0, 10, 25.0, 5.0, 60.0]]
        self.mock_db.query.side_effect = [mock_fine, mock_agg]

        reports = self.validator.check_stability(candidate)  # type: ignore[arg-type]

        self.assertEqual(len(reports), 1)
        self.assertFalse(reports[0]["is_stable"])
        self.assertIn("SUM instability", reports[0]["reason"])
        self.assertIn("COUNT instability", reports[0]["reason"])
        self.assertIn("AVG instability", reports[0]["reason"])
        self.assertIn("MAX instability", reports[0]["reason"])
        self.assertEqual(reports[0]["delta_sum"], 150.0)
