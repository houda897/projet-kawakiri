import unittest
from unittest.mock import MagicMock

from semantic.semantic_homogeneity_engine import SemanticHomogeneityEngine


class TestSemanticHomogeneityEngine(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.engine = SemanticHomogeneityEngine(self.mock_db)

    def test_is_key_like_column(self):
        """Test key detection"""
        self.assertTrue(self.engine.is_key_like_column("customer_id"))
        self.assertTrue(self.engine.is_key_like_column("ProductKey"))
        self.assertTrue(self.engine.is_key_like_column("ticket_no"))
        self.assertTrue(self.engine.is_key_like_column("status_code"))

        self.assertFalse(self.engine.is_key_like_column("order_quantity"))
        self.assertFalse(self.engine.is_key_like_column("CustomerName"))
        self.assertFalse(self.engine.is_key_like_column("created_date"))

    def test_check_fact_homogeneity_valid(self):
        """Test a valid fact (only keys, dates and measurements)"""
        mock_result = MagicMock()
        mock_result.result_rows = [
            ("order_id", "String", 1.0, 0.0, 0.0, 1.0),
            ("order_date", "Date", 0.9, 0.5, 0.0, 0.5),
            ("total_amount", "Float64", 0.8, 1.2, 0.0, 0.8),
            ("good_measure", "Int32", 0.8, 0.9, 0.0, 0.1),
        ]
        self.mock_db.query.return_value = mock_result
        self.engine.threshold = 0.85

        report = self.engine.check_fact_homogeneity("fact_sales")

        self.assertTrue(report["is_valid"])
        self.assertEqual(report["issue_count"], 0)
        self.assertEqual(report["homogeneity_score"], 1.0)

    def test_check_fact_homogeneity_invalid(self):
        """Test an invalid fact with a descriptive text field and a variance-free measure"""
        mock_result = MagicMock()
        mock_result.result_rows = [
            ("customer_name", "String", 0.5, 0.0, 0.0, 0.1),
            ("bad_flag", "Int32", 0.0, 0.0, 0.0, 0.0),
        ]
        self.mock_db.query.return_value = mock_result
        self.engine.threshold = 0.5

        report = self.engine.check_fact_homogeneity("fact_bad")

        self.assertFalse(report["is_valid"])
        self.assertEqual(report["issue_count"], 2)
        self.assertTrue("customer_name" in report["descriptive_like_columns"])
        self.assertTrue("bad_flag" in report["descriptive_like_columns"])
