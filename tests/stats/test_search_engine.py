import unittest
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
from unittest.mock import patch, MagicMock
from stats.clickhouse_manager import clickhouse_manager
from stats.search_engine import *


class TestSearchEngine(unittest.TestCase):
    """Test suite for the search_engine module"""

    def setUp(self):
        """Method called before each test. Initializes a sample stats DataFrame."""
        self.database = "test_db"
        self.table = "test_table"

        self.sample_stats_df = pd.DataFrame([
            {"column": "id",    "rows": 1000, "distinct_est": 1000, "entropy": 0.99, "sparsity": 0.0,  "var_coef": 0.1, "skewness": 0.05},
            {"column": "name",  "rows": 1000, "distinct_est": 950,  "entropy": 0.85, "sparsity": 0.02, "var_coef": 0.0, "skewness": 0.0},
            {"column": "age",   "rows": 1000, "distinct_est": 80,   "entropy": 0.50, "sparsity": 0.10, "var_coef": 0.3, "skewness": 0.2},
            {"column": "flag",  "rows": 1000, "distinct_est": 2,    "entropy": 0.10, "sparsity": 0.50, "var_coef": 0.0, "skewness": 0.0},
            {"column": "empty", "rows": 1000, "distinct_est": 0,    "entropy": 0.0,  "sparsity": 1.0,  "var_coef": 0.0, "skewness": 0.0},
        ])

        self.env_vars = {
            "W_UNIQUENESS": "0.5",
            "W_ENTROPY": "0.3",
            "W_COMPLETENESS": "0.2",
            "TH_PK": "0.85",
            "TH_info": "0.5",
            "TH_cat": "0.2",
            "Result": "False",
            "Calculation": "False",
        }

    # ------------------------------------------------------------------ #
    #  get_table_stats                                                     #
    # ------------------------------------------------------------------ #

    @patch("stats.search_engine.clickhouse_manager")
    def test_get_table_stats_returns_dict(self, mock_cm_class):
        """Test that get_table_stats returns a non-empty dict when data exists."""

        mock_manager = MagicMock()
        mock_manager.client.query_df.return_value = self.sample_stats_df
        mock_cm_class.return_value = mock_manager

        result = get_table_stats(self.database, self.table)

        self.assertIsInstance(result, dict, "get_table_stats should return a dict.")
        self.assertGreater(len(result), 0, "Result dict should not be empty.")
        self.assertIn("id", result, "Column 'id' should be present in the result.")

    @patch("stats.search_engine.clickhouse_manager")
    def test_get_table_stats_empty_dataframe(self, mock_cm_class):
        """Test that get_table_stats returns an empty dict when the query returns no rows."""

        mock_manager = MagicMock()
        mock_manager.client.query_df.return_value = pd.DataFrame()
        mock_cm_class.return_value = mock_manager

        result = get_table_stats(self.database, self.table)

        self.assertEqual(result, {}, "get_table_stats should return an empty dict for an empty DataFrame.")

    @patch("stats.search_engine.clickhouse_manager")
    def test_get_table_stats_query_exception(self, mock_cm_class):
        """Test that get_table_stats returns an empty dict on query exception."""

        mock_manager = MagicMock()
        mock_manager.client.query_df.side_effect = Exception("DB error")
        mock_cm_class.return_value = mock_manager

        result = get_table_stats(self.database, self.table)

        self.assertEqual(result, {}, "get_table_stats should return empty dict when an exception is raised.")

    # ------------------------------------------------------------------ #
    #  calculate_identifiability                                           #
    # ------------------------------------------------------------------ #

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.2",
                              "TH_PK": "0.85", "TH_info": "0.5", "TH_cat": "0.2",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_returns_all_columns(self, mock_stats):
        """Test that calculate_identifiability returns a result for every column."""

        mock_stats.return_value = self.sample_stats_df.set_index("column").to_dict(orient="index")

        result = calculate_identifiability(self.database, self.table)

        self.assertIsNotNone(result, "Result should not be None.")
        for col in ["id", "name", "age", "flag", "empty"]:
            self.assertIn(col, result, f"Column '{col}' should be present in the result.")

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.2",
                              "TH_PK": "0.85", "TH_info": "0.5", "TH_cat": "0.2",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_score_structure(self, mock_stats):
        """Test that each column result contains the expected keys."""

        mock_stats.return_value = self.sample_stats_df.set_index("column").to_dict(orient="index")

        result = calculate_identifiability(self.database, self.table)

        for col, data in result.items():
            self.assertIn("identifiability_score", data,
                          f"'identifiability_score' key missing for column '{col}'.")
            self.assertIn("diagnostic", data,
                          f"'diagnostic' key missing for column '{col}'.")

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.2",
                              "TH_PK": "0.85", "TH_info": "0.5", "TH_cat": "0.2",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_pk_candidate(self, mock_stats):
        """Test that a highly unique column is diagnosed as PK CANDIDATE."""

        mock_stats.return_value = {
            "id": {"rows": 1000, "distinct_est": 1000, "entropy": 1.0, "sparsity": 0.0,
                   "var_coef": 0.0, "skewness": 0.0}
        }

        result = calculate_identifiability(self.database, self.table)

        self.assertEqual(result["id"]["diagnostic"], "PK CANDIDATE",
                         "A fully unique column with max entropy should be diagnosed as 'PK CANDIDATE'.")

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.2",
                              "TH_PK": "0.85", "TH_info": "0.5", "TH_cat": "0.2",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_non_usable(self, mock_stats):
        """Test that a fully sparse column with no entropy is diagnosed as Non usable data."""

        mock_stats.return_value = {
            "empty": {"rows": 1000, "distinct_est": 0, "entropy": 0.0, "sparsity": 1.0,
                      "var_coef": 0.0, "skewness": 0.0}
        }

        result = calculate_identifiability(self.database, self.table)

        self.assertEqual(result["empty"]["diagnostic"], "Non usable data",
                         "A fully sparse column with no entropy should be 'Non usable data'.")

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.2",
                              "TH_PK": "0.85", "TH_info": "0.5", "TH_cat": "0.2",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_score_range(self, mock_stats):
        """Test that all identifiability scores are in the range [0, 1]."""

        mock_stats.return_value = self.sample_stats_df.set_index("column").to_dict(orient="index")

        result = calculate_identifiability(self.database, self.table)

        for col, data in result.items():
            score = data["identifiability_score"]
            self.assertGreaterEqual(score, 0.0, f"Score for '{col}' should be >= 0.")
            self.assertLessEqual(score, 1.0, f"Score for '{col}' should be <= 1.")

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.3",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_invalid_weights(self, mock_stats):
        """Test that weights not summing to 1 cause the function to return None."""

        mock_stats.return_value = self.sample_stats_df.set_index("column").to_dict(orient="index")

        result = calculate_identifiability(self.database, self.table)

        self.assertIsNone(result, "calculate_identifiability should return None when weights don't sum to 1.")

    @patch("stats.search_engine.get_table_stats")
    @patch.dict(os.environ, {"W_UNIQUENESS": "0.5", "W_ENTROPY": "0.3", "W_COMPLETENESS": "0.2",
                              "TH_PK": "0.85", "TH_info": "0.5", "TH_cat": "0.2",
                              "Result": "False", "Calculation": "False"})
    def test_calculate_identifiability_empty_stats(self, mock_stats):
        """Test that an empty stats dict causes the function to return None."""

        mock_stats.return_value = {}

        result = calculate_identifiability(self.database, self.table)

        self.assertIsNone(result, "calculate_identifiability should return None when stats are empty.")


if __name__ == "__main__":
    unittest.main()
