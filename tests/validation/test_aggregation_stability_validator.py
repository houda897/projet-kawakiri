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

    def test_select_additive_measure_rejects_keys_and_flat_counters(self):
        self.assertFalse(
            self.validator.select_additive_measure(
                column_name="ProductKey",
                column_type="Int64",
                distinct_count=100,
                entropy_ratio=0.9,
                variation_coefficient=0.4,
            )
        )
        self.assertFalse(
            self.validator.select_additive_measure(
                column_name="OrderLineItem",
                column_type="Int64",
                distinct_count=1,
                entropy_ratio=0.0,
                variation_coefficient=0.0,
            )
        )
        self.assertTrue(
            self.validator.select_additive_measure(
                column_name="revenue",
                column_type="Float64",
                distinct_count=25,
                entropy_ratio=0.7,
                variation_coefficient=0.5,
            )
        )

    @patch(
        "validation.aggregation_stability_validator.DecisionModelCandidateBuilder.load_candidates"
    )
    def test_validate_stored_candidates_requires_models(self, mock_load_candidates):
        mock_load_candidates.return_value = []

        with self.assertRaisesRegex(ValueError, "No decision model candidates"):
            self.validator.validate_stored_candidates()

    @patch.object(AggregationStabilityValidator, "_get_best_measure")
    def test_check_stability_skips_edges_outside_fact_dimension_scope(self, mock_measure):
        edge = DummyEdge("dim_A", "dim_B", "fk_id", "pk_id")
        candidate = DummyCandidate(["fact_A"], ["dim_A", "dim_B"], [edge])

        reports = self.validator.check_stability(candidate)  # type: ignore[arg-type]

        self.assertEqual(reports, [])
        mock_measure.assert_not_called()

    @patch.object(AggregationStabilityValidator, "_get_best_dimension_grouping")
    @patch.object(AggregationStabilityValidator, "_get_best_measure")
    def test_check_stability_skips_fact_without_measure(self, mock_measure, mock_grouping):
        edge = DummyEdge("fact_A", "dim_B", "fk_id", "pk_id")
        candidate = DummyCandidate(["fact_A"], ["dim_B"], [edge])
        mock_measure.return_value = None

        reports = self.validator.check_stability(candidate)  # type: ignore[arg-type]

        self.assertEqual(reports, [])
        mock_grouping.assert_not_called()

    def test_get_best_measure_skips_keys_and_selects_variable_numeric_column(self):
        self.mock_db.query.return_value.result_rows = [
            ("ProductKey", "Int64", 100, 0.9, 0.5),
            ("revenue", "Float64", 50, 0.7, 0.4),
        ]

        measure = self.validator._get_best_measure("fact_sales")

        self.assertEqual(measure, "revenue")

    def test_get_best_dimension_grouping_prefers_descriptive_attribute(self):
        self.mock_db.query.return_value.result_rows = [
            ("latitude", "Float64"),
            ("country", "String"),
        ]

        group = self.validator._get_best_dimension_grouping("dim_customer")

        self.assertEqual(group, "country")

    def test_store_stability_persists_report_and_empty_input_only_clears(self):
        report = {
            "model_id": "model",
            "fact_table": "fact_sales",
            "dimension_table": "dim_customer",
            "measure_column": "revenue",
            "group_column": "country",
            "fine_sum": 10.0,
            "agg_sum": 10.0,
            "delta_sum": 0.0,
            "fine_count": 2,
            "agg_count": 2,
            "delta_count": 0,
            "fine_avg": 5.0,
            "agg_avg": 5.0,
            "delta_avg": 0.0,
            "fine_min": 4.0,
            "agg_min": 4.0,
            "delta_min": 0.0,
            "fine_max": 6.0,
            "agg_max": 6.0,
            "delta_max": 0.0,
            "is_stable": True,
            "reason": "stable",
        }

        self.validator.store_stability([report])

        self.mock_db.insert.assert_called_once()

    def test_is_close_accepts_absolute_or_relative_tolerance(self):
        self.assertTrue(self.validator._is_close(0.0, 0.0005))
        self.assertTrue(self.validator._is_close(1_000_000.0, 1_000_000.5))
        self.assertFalse(self.validator._is_close(10.0, 11.0))
