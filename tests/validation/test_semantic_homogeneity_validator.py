import unittest
from unittest.mock import MagicMock

from inference.table_role import TableRoleCandidate
from validation.semantic_homogeneity_validator import SemanticHomogeneityValidator


class TestSemanticHomogeneityValidator(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.validator = SemanticHomogeneityValidator(self.mock_db)

    def test_is_key_like_column(self):
        """Test key detection"""
        self.assertTrue(self.validator.is_key_like_column("customer_id"))
        self.assertTrue(self.validator.is_key_like_column("ProductKey"))
        self.assertTrue(self.validator.is_key_like_column("ticket_no"))
        self.assertTrue(self.validator.is_key_like_column("status_code"))

        self.assertFalse(self.validator.is_key_like_column("order_quantity"))
        self.assertFalse(self.validator.is_key_like_column("CustomerName"))
        self.assertFalse(self.validator.is_key_like_column("created_date"))
        self.assertFalse(self.validator.is_key_like_column("valid"))
        self.assertFalse(self.validator.is_key_like_column("paid"))
        self.assertFalse(self.validator.is_key_like_column("rapid"))
        self.assertFalse(self.validator.is_key_like_column("casino"))
        self.assertFalse(self.validator.is_key_like_column("unicode"))

    def test_check_fact_homogeneity_valid(self):
        """Test a valid fact (only keys, dates and measurements)"""
        mock_result = MagicMock()
        mock_result.result_rows = [
            ("order_id", "String", 1.0, 0.0, 0.0, 1.0),
            ("order_date", "Date", 0.9, 0.5, 0.0, 0.5),
            ("total_amount", "Float64", 0.8, 1.2, 0.0, 0.8),
            ("good_measure", "Int32", 0.8, 0.9, 0.0, 0.1),
        ]
        fk_result = MagicMock()
        fk_result.result_rows = []
        self.mock_db.query.side_effect = [fk_result, mock_result]
        self.validator.threshold = 0.85

        report = self.validator.check_fact_homogeneity("fact_sales")

        self.assertTrue(report["is_valid"])
        self.assertEqual(report["issue_count"], 0)
        self.assertEqual(report["homogeneity_score"], 1.0)

    def test_check_fact_homogeneity_invalid(self):
        """A descriptive text field is invalid, while a discrete number is inconclusive."""
        mock_result = MagicMock()
        mock_result.result_rows = [
            ("customer_name", "String", 0.5, 0.0, 0.0, 0.1),
            ("bad_flag", "Int32", 0.0, 0.0, 0.0, 0.0),
        ]
        fk_result = MagicMock()
        fk_result.result_rows = []
        self.mock_db.query.side_effect = [fk_result, mock_result]
        self.validator.threshold = 0.5

        report = self.validator.check_fact_homogeneity("fact_bad")

        self.assertFalse(report["is_valid"])
        self.assertEqual(report["issue_count"], 1)
        self.assertTrue("customer_name" in report["descriptive_like_columns"])
        self.assertFalse("bad_flag" in report["descriptive_like_columns"])

    def test_check_fact_homogeneity_allows_string_foreign_key(self):
        fk_result = MagicMock()
        fk_result.result_rows = [("Product_ID,Product_Name",)]
        stats_result = MagicMock()
        stats_result.result_rows = [
            ("Product_Name", "String", 0.5, 0.0, 0.0, 0.1),
            ("Sales", "Float64", 0.8, 1.2, 0.0, 0.8),
        ]
        self.mock_db.query.side_effect = [fk_result, stats_result]

        report = self.validator.check_fact_homogeneity("fact_sales")

        self.assertTrue(report["is_valid"])
        self.assertEqual(report["issue_count"], 0)

    def test_check_fact_homogeneity_excludes_validated_grain_columns(self):
        structural_result = MagicMock()
        structural_result.result_rows = [("order_id, payment_sequential",)]
        stats_result = MagicMock()
        stats_result.result_rows = [
            ("payment_sequential", "Int64", 0.02, 0.39, 0.0, 0.0),
            ("payment_value", "Float64", 0.8, 1.2, 0.0, 0.8),
        ]
        self.mock_db.query.side_effect = [structural_result, stats_result]

        report = self.validator.check_fact_homogeneity("fact_payments")

        self.assertTrue(report["is_valid"])
        self.assertEqual(report["issue_count"], 0)

    def test_dimension_query_filters_latest_stats_by_table(self):
        mock_result = MagicMock()
        mock_result.result_rows = []
        self.mock_db.query.return_value = mock_result

        self.validator.check_dimension_homogeneity("dim_customer")

        sql = self.mock_db.query.call_args[0][0]
        assert "AND table_name = %(table)s" in sql

    def test_fact_query_filters_latest_stats_by_table(self):
        mock_result = MagicMock()
        mock_result.result_rows = []
        self.mock_db.query.side_effect = [mock_result, mock_result]

        self.validator.check_fact_homogeneity("fact_sales")

        sql = self.mock_db.query.call_args_list[1][0][0]
        assert "AND table_name = %(table)s" in sql

    def test_check_homogeneity_skips_roles_outside_model_scope(self):
        roles = [
            TableRoleCandidate(
                table_name="geography",
                row_count=10,
                outgoing_edges=0,
                incoming_edges=0,
                numeric_columns=2,
                text_columns=1,
                date_columns=0,
                has_primary_key=False,
                role="ISOLATED",
                confidence=0.9,
                reason="table_has_no_confirmed_relationships",
            ),
            TableRoleCandidate(
                table_name="uncertain_table",
                row_count=10,
                outgoing_edges=1,
                incoming_edges=0,
                numeric_columns=1,
                text_columns=1,
                date_columns=0,
                has_primary_key=False,
                role="UNKNOWN",
                confidence=0.4,
                reason="not_enough_evidence_to_choose_fact_or_dimension",
            ),
        ]

        reports = self.validator.check_homogeneity(roles)

        assert reports == []
        self.mock_db.query.assert_not_called()
