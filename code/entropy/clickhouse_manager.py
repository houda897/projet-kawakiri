import os
import clickhouse_connect
from dotenv import load_dotenv
from pathlib import Path



class clickhouse_manager :
    """ This class connects the client to the clickhouse server """

    def __init__ (self) :
        '''Client initialization'''
        
        env_path = Path(__file__).with_name(".env")
        load_dotenv(dotenv_path=env_path)

        self.CH_HOST = os.getenv("CH_HOST", "54.36.175.8")
        #print("self.CH_HOST", self.CH_HOST)
        self.CH_PORT = int(os.getenv("CH_PORT", "19123"))
        #print("self.CH_PORT", self.CH_PORT)
        self.CH_USER = os.getenv("CH_USER", "lab_admin")
        #print("self.CH_USER", self.CH_USER)
        self.CH_PASSWORD = os.getenv("CH_PASSWORD", "S!7mZ@9w#LpT3eXq")
        #print("self.CH_PASSWORD", self.CH_PASSWORD)
        self.CH_DATABASE = os.getenv("CH_DATABASE", "default")
        #print("self.CH_DATABASE", self.CH_DATABASE)


        self.client = None
        self.connect()

    def connect(self) :
        '''Connects the client to the database'''
        try:
            self.client = clickhouse_connect.get_client(
                host=self.CH_HOST,
                port=self.CH_PORT,
                username=self.CH_USER,
                password=self.CH_PASSWORD
            )
            print("Clickhouse sucessfully connected.")
        except Exception as e:
            print(f"Error during clickhouse connection : {e}")
            exit()

    def query(self, sql):
        '''Executes a request and return the corresponding data'''
        return self.client.query(sql)
    
    def query_df(self, sql):
        '''Executes a request and return the corresponding Pandas Dataframe'''
        return self.client.query_df(sql)

    def get_CH_DB(self) :
        return self.CH_DATABASE