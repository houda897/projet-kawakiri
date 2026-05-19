import os
from pathlib import Path

import clickhouse_connect
from clickhouse_connect.driver import Client
from dotenv import load_dotenv

from core.logger import get_logger

logger = get_logger(__name__)

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", "11123"))
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "")
CH_DB = os.getenv("CH_DATABASE", "lab_db")
META_DB = os.getenv("META_DB", "lab_meta")


class clickhouse_manager:
    """
    Central access point to ClickHouse.

    The manager keeps one connection and exposes query, command, and insert
    methods used by all engines.
    """

    _instance = None

    def __init__(self):
        self.host = CH_HOST
        self.port = CH_PORT
        self.user = CH_USER
        self.password = CH_PASSWORD
        self.database = CH_DB
        self.meta_database = META_DB
        self.client: Client | None = None
        self.connect()

    def connect(self) -> Client:
        if self.client is not None:
            return self.client

        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
            )
            return self.client

        except Exception as exc:
            logger.error("ClickHouse connection failed: %s", exc)
            raise ConnectionError(f"ClickHouse connection failed: {exc}") from exc

    def query(self, sql: str, parameters: dict | None = None):
        if parameters is None:
            return self.connect().query(sql)

        return self.connect().query(sql, parameters=parameters)

    def queryDf(self, sql: str, parameters: dict | None = None):
        if parameters is None:
            return self.connect().query_df(sql)

        return self.connect().query_df(sql, parameters=parameters)

    def command(self, sql: str, parameters: dict | None = None):
        if parameters is None:
            return self.connect().command(sql)

        return self.connect().command(sql, parameters=parameters)

    def insert(
        self,
        table: str,
        data: list,
        column_names: list[str] | None = None,
    ):
        if column_names is None:
            return self.connect().insert(table, data)

        return self.connect().insert(table, data, column_names=column_names)

    def get_CH_DB(self) -> str:
        return self.database

    def get_meta_database(self) -> str:
        return self.meta_database

    @classmethod
    def get_instance(cls) -> "clickhouse_manager":
        if cls._instance is None:
            cls._instance = cls()

        return cls._instance


def get_manager() -> clickhouse_manager:
    return clickhouse_manager.get_instance()
