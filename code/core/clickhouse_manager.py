import os
import threading
from pathlib import Path

import clickhouse_connect
from clickhouse_connect.driver import Client
from core.logger import get_logger
from dotenv import load_dotenv

logger = get_logger(__name__)

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", "11123"))
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "")
CH_DB = os.getenv("CH_DATABASE", "lab_db")
META_DB = os.getenv("META_DB", "lab_meta")


class ClickHouseManager:
    """
    Central access point to ClickHouse.

    The manager keeps one ClickHouse client per thread (via threading.local)
    and exposes query, command, and insert methods used by all engines.
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self.host = CH_HOST
        self.port = CH_PORT
        self.user = CH_USER
        self.password = CH_PASSWORD
        self.database = CH_DB
        self.meta_database = META_DB
        self._local = threading.local()
        self._clients_lock = threading.Lock()
        self._clients: list[Client] = []
        self.connect()

    def connect(self) -> Client:
        """Return this thread's ClickHouse client, opening one on first use."""
        client = getattr(self._local, "client", None)
        if client is not None:
            return client

        try:
            client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
            )
        except Exception as exc:
            logger.error("ClickHouse connection failed: %s", exc)
            raise ConnectionError(f"ClickHouse connection failed: {exc}") from exc

        self._local.client = client
        with self._clients_lock:
            self._clients.append(client)

        return client

    def close_all(self) -> None:
        """
        Close every per-thread ClickHouse client opened so far.

        Call this from the calling thread once a parallel batch (e.g. a
        ThreadPoolExecutor block) has finished: it closes the clients opened
        by the worker threads as well as the caller's own client, which is
        simply reopened lazily on its next query.
        """
        with self._clients_lock:
            clients, self._clients = self._clients, []

        if hasattr(self._local, "client"):
            del self._local.client

        for client in clients:
            try:
                client.close()
            except Exception:
                logger.warning("Failed to close ClickHouse client", exc_info=True)

    def query(self, sql: str, parameters: dict | None = None):
        """Execute a SELECT query and return the result object."""
        if parameters is None:
            return self.connect().query(sql)

        return self.connect().query(sql, parameters=parameters)

    def command(self, sql: str, parameters: dict | None = None):
        """Execute a DDL or INSERT/TRUNCATE statement that does not return rows."""
        if parameters is None:
            return self.connect().command(sql)

        return self.connect().command(sql, parameters=parameters)

    def insert(
        self,
        table: str,
        data: list,
        column_names: list[str] | None = None,
    ):
        """Insert rows into a ClickHouse table, optionally specifying column names."""
        if column_names is None:
            return self.connect().insert(table, data)

        return self.connect().insert(table, data, column_names=column_names)

    def get_CH_DB(self) -> str:
        return self.database

    def get_meta_database(self) -> str:
        return self.meta_database

    @classmethod
    def get_instance(cls) -> "ClickHouseManager":
        """Return the shared singleton instance, creating it on first call."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()

        return cls._instance


def get_manager() -> ClickHouseManager:
    """Module-level shorthand for ClickHouseManager.get_instance()."""
    return ClickHouseManager.get_instance()
