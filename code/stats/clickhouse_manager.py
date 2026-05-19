import os
import clickhouse_connect
from dotenv import load_dotenv
from pathlib import Path


class clickhouse_manager:
    """This class connects the client to the clickhouse server"""

    _instance = None

    def __init__(self):

        current_file_path = os.path.abspath(__file__)
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)))
        env_path = os.path.join(root_dir, ".env")

        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path)
        else:
            print(f"Error, .env not found {env_path}")

        self.CH_HOST = os.getenv("CH_HOST")
        raw_port = os.getenv("CH_PORT")
        self.CH_PORT = int(raw_port) if raw_port else 19123
        self.CH_USER = os.getenv("CH_USER")
        self.CH_PASSWORD = os.getenv("CH_PASSWORD","")
        self.CH_DATABASE = os.getenv("CH_DATABASE")

        self.client = None
        self.connect()

    def connect(self):
        """Connects the client to the database"""

        if self.client is None:
            try:
                self.client = clickhouse_connect.get_client(
                    host=self.CH_HOST,
                    port=self.CH_PORT,
                    username=self.CH_USER,
                    password=self.CH_PASSWORD
                )
                # print("Clickhouse sucessfully connected.")
            except Exception as e:
                print(f"Error during clickhouse connection : {e}")
                exit()

    def query(self, sql):
        """Executes a request and return the corresponding data"""
        if self.client is None :
            raise RuntimeError("Clickhouse is not connected")
        return self.client.query(sql)

    def queryDf(self, sql):
        """Executes a request and return the corresponding Pandas Dataframe"""
        if self.client is None :
            raise RuntimeError("Clickhouse is not connected")
        return self.client.query_df(sql)

    def get_CH_DB(self):
        """Getter"""
        return self.CH_DATABASE

    @classmethod
    def get_client(cls):
        """Static method to get the client from everywhere"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.connect()
        return cls._instance.client
