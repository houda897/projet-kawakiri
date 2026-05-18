import unittest
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
from unittest.mock import patch, MagicMock, call
from stats.stats_computing import *


class TestStatsComputing(unittest.TestCase):
    """Test suite for the stats_computing module"""

    def setUp(self):
        """Method called before each test. Initializes mock db_manager and sample data."""
        self.mock_db_manager = MagicMock()
        self.mock_db_manager.CH_DATABASE = "test_db"
        self.mock_db_manager.client = MagicMock()

        self.sample_columns_df = pd.DataFrame([
            {"table": "users",    "name": "id",    "type": "UInt64"},
            {"table": "users",    "name": "name",  "type": "String"},
            {"table": "users",    "name": "age",   "type": "Int32"},
            {"table": "products", "name": "price", "type": "Float64"},
            {"table": "products", "name": "label", "type": "String"},
        ])

    # ------------------------------------------------------------------ #
    #  initialize_meta_table                                             #
    # ------------------------------------------------------------------ #

    def test_initialize_meta_table_creates_database(self):
        """Test that initialize_meta_table issues a CREATE DATABASE command."""

        initialize_meta_table(self.mock_db_manager, "users")

        calls_str = [str(c) for c in self.mock_db_manager.client.command.call_args_list]
        self.assertTrue(
            any("CREATE DATABASE IF NOT EXISTS meta" in s for s in calls_str),
            "initialize_meta_table should issue a 'CREATE DATABASE IF NOT EXISTS meta' command."
        )

    def test_initialize_meta_table_creates_stats_table(self):
        """Test that initialize_meta_table creates the correct stats table."""

        result = initialize_meta_table(self.mock_db_manager, "users")

        self.assertEqual(result, "stats_test_db_users",
                         "initialize_meta_table should return the correct stats table name.")
        calls_str = [str(c) for c in self.mock_db_manager.client.command.call_args_list]
        self.assertTrue(
            any("stats_test_db_users" in s for s in calls_str),
            "initialize_meta_table should create a table named 'stats_test_db_users'."
        )

    def test_initialize_meta_table_returns_correct_name(self):
        """Test that the returned table name follows the naming convention."""

        result = initialize_meta_table(self.mock_db_manager, "products")

        self.assertEqual(result, "stats_test_db_products")

    # ------------------------------------------------------------------ #
    #  compute_stats_for_column                                            #
    # ------------------------------------------------------------------ #

    def test_compute_stats_numeric_column_calls_client(self):
        """Test that compute_stats_for_column issues an INSERT command for a numeric column."""

        col = Col(name="age", ch_type="Int32")
        compute_stats_for_column(
            self.mock_db_manager.client, "2024-01-01 00:00:00",
            "test_db", "users", col
        )

        self.mock_db_manager.client.command.assert_called_once()
        sql_arg = self.mock_db_manager.client.command.call_args[0][0]
        self.assertIn("INSERT INTO", sql_arg, "Command should contain an INSERT INTO statement.")

    def test_compute_stats_numeric_column_sql_contains_avg(self):
        """Test that numeric columns include avg/stddev/skew in the generated SQL."""

        col = Col(name="price", ch_type="Float64")
        compute_stats_for_column(
            self.mock_db_manager.client, "2024-01-01 00:00:00",
            "test_db", "products", col
        )

        sql_arg = self.mock_db_manager.client.command.call_args[0][0]
        self.assertIn("avg", sql_arg, "Numeric column SQL should include 'avg'.")
        self.assertIn("stddevPop", sql_arg, "Numeric column SQL should include 'stddevPop'.")
        self.assertIn("skewPop", sql_arg, "Numeric column SQL should include 'skewPop'.")

    def test_compute_stats_string_column_no_avg(self):
        """Test that non-numeric columns do NOT use avg/stddev/skew in the SQL."""

        col = Col(name="name", ch_type="String")
        compute_stats_for_column(
            self.mock_db_manager.client, "2024-01-01 00:00:00",
            "test_db", "users", col
        )

        sql_arg = self.mock_db_manager.client.command.call_args[0][0]
        self.assertNotIn("stddevPop", sql_arg,
                         "Non-numeric column SQL should not contain 'stddevPop'.")

    def test_compute_stats_parameters_passed_correctly(self):
        """Test that the correct parameters are passed to the client command."""

        col = Col(name="id", ch_type="UInt64")
        run_ts = "2024-06-01 12:00:00"

        compute_stats_for_column(
            self.mock_db_manager.client, run_ts, "test_db", "users", col
        )

        params = self.mock_db_manager.client.command.call_args[1].get("parameters", {})
        self.assertEqual(params.get("db"), "test_db")
        self.assertEqual(params.get("table"), "users")
        self.assertEqual(params.get("col"), "id")
        self.assertEqual(params.get("typ"), "UInt64")
        self.assertEqual(params.get("run_ts"), run_ts)

    # ------------------------------------------------------------------ #
    #  run_full_profiling                                                  #
    # ------------------------------------------------------------------ #

    def test_run_full_profiling_iterates_all_tables(self):
        """Test that run_full_profiling processes all distinct tables found in the database."""

        self.mock_db_manager.client.query_df.return_value = self.sample_columns_df

        with patch("stats.stats_computing.initialize_meta_table") as mock_init, \
             patch("stats.stats_computing.compute_stats_for_column") as mock_compute:

            mock_init.return_value = "stats_test_db_users"
            run_full_profiling(self.mock_db_manager)

            tables_processed = {c.args[1] for c in mock_init.call_args_list}
            self.assertIn("users", tables_processed, "'users' table should be profiled.")
            self.assertIn("products", tables_processed, "'products' table should be profiled.")

    def test_run_full_profiling_calls_compute_for_each_column(self):
        """Test that compute_stats_for_column is called once per column."""

        self.mock_db_manager.client.query_df.return_value = self.sample_columns_df

        with patch("stats.stats_computing.initialize_meta_table"), \
             patch("stats.stats_computing.compute_stats_for_column") as mock_compute:

            run_full_profiling(self.mock_db_manager)

            self.assertEqual(
                mock_compute.call_count,
                len(self.sample_columns_df),
                "compute_stats_for_column should be called once per column."
            )

    def test_run_full_profiling_truncates_before_insert(self):
        """Test that each stats table is truncated before new data is inserted."""

        self.mock_db_manager.client.query_df.return_value = self.sample_columns_df

        with patch("stats.stats_computing.initialize_meta_table"), \
             patch("stats.stats_computing.compute_stats_for_column"):

            run_full_profiling(self.mock_db_manager)

            calls_str = [str(c) for c in self.mock_db_manager.client.command.call_args_list]
            truncate_calls = [s for s in calls_str if "TRUNCATE" in s]
            self.assertEqual(len(truncate_calls), 2,
                             "There should be one TRUNCATE call per table (2 tables).")

    def test_run_full_profiling_handles_compute_exception(self):
        """Test that run_full_profiling continues even if a column computation fails."""

        self.mock_db_manager.client.query_df.return_value = self.sample_columns_df

        with patch("stats.stats_computing.initialize_meta_table"), \
             patch("stats.stats_computing.compute_stats_for_column",
                   side_effect=Exception("SQL error")):
            try:
                run_full_profiling(self.mock_db_manager)
            except Exception:
                self.fail("run_full_profiling should not propagate column-level exceptions.")

    # ------------------------------------------------------------------ #
    #  stats_pipeline                                                      #
    # ------------------------------------------------------------------ #

    @patch("stats.stats_computing.clickhouse_manager")
    @patch("stats.stats_computing.run_full_profiling")
    def test_stats_pipeline_calls_run_full_profiling(self, mock_profiling, mock_cm_class):
        """Test that stats_pipeline instantiates clickhouse_manager and calls run_full_profiling."""

        mock_manager = MagicMock()
        mock_cm_class.return_value = mock_manager

        stats_pipeline()

        mock_cm_class.assert_called_once()
        mock_profiling.assert_called_once_with(mock_manager)


if __name__ == "__main__":
    unittest.main()
