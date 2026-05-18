import unittest
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from unittest.mock import patch, MagicMock, PropertyMock
from stats.clickhouse_manager import clickhouse_manager

class TestClickhouseManager(unittest.TestCase):
    """Test suite for the clickhouse_manager class"""

    def setUp(self):
        """Method called before each test. Resets the singleton and mocks environment variables."""
        clickhouse_manager._instance = None

        self.env_vars = {
            "CH_HOST": "localhost",
            "CH_PORT": "19123",
            "CH_USER": "test_user",
            "CH_PASSWORD": "test_password",
            "CH_DATABASE": "test_db"
        }

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "19123",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_connect_success(self, mock_get_client):
        """Test that the client connects successfully when credentials are valid."""

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        manager = clickhouse_manager()

        mock_get_client.assert_called_once_with(
            host="localhost",
            port=19123,
            username="test_user",
            password="test_password"
        )
        self.assertIsNotNone(manager.client, "Client should not be None after a successful connection.")
        self.assertEqual(manager.client, mock_client)

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "19123",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_connect_failure_exits(self, mock_get_client):
        """Test that a connection failure triggers a system exit."""

        mock_get_client.side_effect = Exception("Connection refused")

        with self.assertRaises(SystemExit):
            clickhouse_manager()

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "19123",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_query_returns_result(self, mock_get_client):
        """Test that query() calls the client and returns a result."""

        mock_client = MagicMock()
        mock_client.query.return_value = [("row1",), ("row2",)]
        mock_get_client.return_value = mock_client

        manager = clickhouse_manager()
        result = manager.query("SELECT 1")

        mock_client.query.assert_called_once_with("SELECT 1")
        self.assertEqual(result, [("row1",), ("row2",)])

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "19123",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_query_df_returns_dataframe(self, mock_get_client):
        """Test that query_df() calls the client and returns a DataFrame."""
        import pandas as pd
        

        mock_client = MagicMock()
        mock_df = pd.DataFrame({"col": [1, 2, 3]})
        mock_client.query_df.return_value = mock_df
        mock_get_client.return_value = mock_client

        manager = clickhouse_manager()
        result = manager.query_df("SELECT col FROM table")

        mock_client.query_df.assert_called_once_with("SELECT col FROM table")
        self.assertIsInstance(result, pd.DataFrame, "query_df should return a Pandas DataFrame.")
        self.assertEqual(len(result), 3)

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "19123",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_get_CH_DB_returns_database_name(self, mock_get_client):
        """Test that get_CH_DB() returns the correct database name from env."""

        mock_get_client.return_value = MagicMock()

        manager = clickhouse_manager()
        db = manager.get_CH_DB()

        self.assertEqual(db, "test_db", "get_CH_DB should return the CH_DATABASE env variable value.")

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "19123",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_get_client_singleton(self, mock_get_client):
        """Test that get_client() always returns the same singleton instance."""

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        client1 = clickhouse_manager.get_client()
        client2 = clickhouse_manager.get_client()

        self.assertIs(client1, client2, "get_client should return the same singleton instance.")
        mock_get_client.assert_called_once()

    @patch("stats.clickhouse_manager.clickhouse_connect.get_client")
    @patch.dict(os.environ, {"CH_HOST": "localhost", "CH_PORT": "bad_port",
                              "CH_USER": "test_user", "CH_PASSWORD": "test_password",
                              "CH_DATABASE": "test_db"})
    def test_invalid_port_raises_error(self, mock_get_client):
        """Test that an invalid (non-integer) CH_PORT raises a ValueError."""

        with self.assertRaises((ValueError, SystemExit)):
            clickhouse_manager()


if __name__ == "__main__":
    unittest.main()
