import threading
from unittest.mock import MagicMock, patch

import pytest
from core.clickhouse_manager import ClickHouseManager, get_manager


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    ClickHouseManager._instance = None


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_singleton_behavior(mock_get_client) -> None:
    mock_get_client.return_value = MagicMock()

    manager1 = ClickHouseManager.get_instance()
    manager2 = get_manager()

    assert manager1 is manager2
    mock_get_client.assert_called_once()


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_connect_creates_client_once_per_thread(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager.get_instance()

    client1 = manager.connect()
    client2 = manager.connect()

    mock_get_client.assert_called_once_with(
        host=manager.host,
        port=manager.port,
        username=manager.user,
        password=manager.password,
    )
    assert client1 is mock_client
    assert client2 is mock_client


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_connect_creates_separate_clients_per_thread(mock_get_client) -> None:
    clients = [MagicMock(name=f"client_{index}") for index in range(3)]
    mock_get_client.side_effect = clients

    manager = ClickHouseManager.get_instance()
    worker_clients = []

    threads = [
        threading.Thread(target=lambda: worker_clients.append(manager.connect()))
        for _ in range(2)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert mock_get_client.call_count == 3
    assert manager.connect() is clients[0]
    assert set(worker_clients) == set(clients[1:])


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_query_passes_parameters(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager.get_instance()
    sql = "SELECT * FROM my_table WHERE id = %(id)s"
    params = {"id": 42}

    manager.query(sql, parameters=params)

    mock_client.query.assert_called_once_with(sql, parameters=params)


@patch("core.clickhouse_manager.clickhouse_connect.get_client")
def test_close_all(mock_get_client) -> None:
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    manager = ClickHouseManager.get_instance()
    manager.connect()

    manager.close_all()

    mock_client.close.assert_called_once()
    assert not hasattr(manager._local, "client")
