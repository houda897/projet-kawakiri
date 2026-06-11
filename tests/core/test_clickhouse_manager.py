import os
from unittest.mock import MagicMock, patch

import pytest
from core.clickhouse_manager import ClickHouseManager


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    # Reset the singleton before each test to avoid state leaking between tests.
    ClickHouseManager._instance = None


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
@patch.dict(
    os.environ,
    {
        "CH_HOST": "localhost",
        "CH_PORT": "19123",
        "CH_USER": "test_user",
        "CH_PASSWORD": "test_password",
        "CH_DATABASE": "test_db",
    },
    clear=False,
)
def test_connect_success(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager()

    mock_get_client.assert_called_once()
    assert manager.client == mock_client


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_connect_failure_raises_connection_error(mock_get_client) -> None:
    mock_get_client.side_effect = Exception("Connection refused")

    with pytest.raises(ConnectionError):
        ClickHouseManager()


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_query_calls_client(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_client.query.return_value = [(("row1",))]
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager()
    manager.query("SELECT 1")

    mock_client.query.assert_called_once_with("SELECT 1")


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_query_with_parameters_calls_client(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager()
    manager.query("SELECT %(x)s", parameters={"x": 1})

    mock_client.query.assert_called_once_with("SELECT %(x)s", parameters={"x": 1})


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_insert_calls_client_with_column_names(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager()
    manager.insert("lab_db.test", [[1]], column_names=["id"])

    mock_client.insert.assert_called_once_with(
        "lab_db.test",
        [[1]],
        column_names=["id"],
    )


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_get_instance_singleton(mock_get_client) -> None:
    mock_get_client.return_value = MagicMock()

    instance1 = ClickHouseManager.get_instance()
    instance2 = ClickHouseManager.get_instance()

    # Both calls must return the exact same object.
    assert instance1 is instance2
    mock_get_client.assert_called_once()
