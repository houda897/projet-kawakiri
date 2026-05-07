import os
from pathlib import Path

import clickhouse_connect
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", "11123"))
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "")
CH_DB = os.getenv("CH_DATABASE", "lab_db")
META_DB = os.getenv("META_DB", "lab_meta")
def get_client(database: str | None = None):
    print("DEBUG CH_HOST =", CH_HOST)
    print("DEBUG CH_PORT =", CH_PORT)
    print("DEBUG CH_DB =", CH_DB)
    print("DEBUG CH_USER =", CH_USER)
    print("DEBUG CH_PASSWORD length =", len(CH_PASSWORD))

    return clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=database or CH_DB,
    )