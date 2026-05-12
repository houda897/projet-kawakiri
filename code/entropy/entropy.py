import math
from collections import Counter
from clickhouse_manager import clickhouse_manager
import datetime

def entropy_pipeline():
    '''Main pipeline'''
    db_manager = clickhouse_manager()
    run_full_profiling(db_manager)
    
def q_ident(name):
    '''Use of an object to protect the name'''
    return f"`{name}`"

class Col:
    '''Simple definition for column object'''
    def __init__(self, name, ch_type):
        self.name = name
        self.ch_type = ch_type

def compute_entropy_for_column(client, run_ts, database, table, col):
    '''Request for the database : write all the necessaries stats into a table in format {stats_database_table}'''

    META_DB = "meta"

    destination_table = f"stats_{database}_{table}"
    
    sql = f"""
    INSERT INTO {META_DB}.`{destination_table}`
    WITH
      base AS (
        SELECT
          count() AS rows,
          countIf({q_ident(col.name)} IS NOT NULL) AS non_null_rows
        FROM {q_ident(database)}.{q_ident(table)}
      ),
      freqs AS (
        SELECT
          toString({q_ident(col.name)}) AS v,
          count() AS c
        FROM {q_ident(database)}.{q_ident(table)}
        WHERE {q_ident(col.name)} IS NOT NULL
        GROUP BY v
      ),
      tot AS (
        SELECT sum(c) AS n FROM freqs
      ),
      probs AS (
        SELECT
          c,
          (c / n) AS p,
          n
        FROM freqs
        CROSS JOIN tot
      )
    SELECT
      toDateTime(%(run_ts)s) AS run_ts,
      %(db)s AS db,
      %(table)s AS table,
      %(col)s AS column,
      %(typ)s AS ch_type,
      (SELECT rows FROM base) AS rows,
      (SELECT non_null_rows FROM base) AS non_null_rows,
      toUInt64(count()) AS distinct_est,
      if(max(n)=0, 0.0, -sum(p * log2(p))) AS entropy
    FROM probs
    """
    
    client.command(
        sql,
        parameters={
            "run_ts": run_ts, 
            "db": database, 
            "table": table, 
            "col": col.name, 
            "typ": col.ch_type
        },
    )

def run_full_profiling(db_manager):
        '''Find all the table of a database and loop the stats calculation on each one'''
        
        query = f"SELECT table, name, type FROM system.columns WHERE database = '{db_manager.CH_DATABASE}'"
        df_cols = db_manager.client.query_df(query)
        
        run_ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        #print(f"Calculation for the table : {db_manager.CH_DATABASE}")

        for _, row in df_cols.iterrows():
            table_name = row['table']
            col_obj = Col(name=row['name'], ch_type=row['type'])

            initialize_meta_table(db_manager, table_name)
            
            try:
                #print(f"  Calculating : {table_name}.{col_obj.name}...")
                compute_entropy_for_column(
                    db_manager.client, 
                    run_ts, 
                    db_manager.CH_DATABASE,
                    table_name, 
                    col_obj,
                )
            except Exception as e:
                print(f"Errot in {col_obj.name}: {e}")

        print(f"\n Results are in database meta, table stats_{db_manager.CH_DATABASE}")

def initialize_meta_table(db_manager, table_name):
    '''Create the destination table if it doesn't exist'''
    #print("Checking for stats table")

    stats_table_name = f"stats_{db_manager.CH_DATABASE}_{table_name}"

    db_manager.client.command("CREATE DATABASE IF NOT EXISTS meta")
    db_manager.client.command(f"""
        CREATE TABLE IF NOT EXISTS meta.`{stats_table_name}` (
            run_ts DateTime,
            db String,
            table String,
            column String,
            ch_type String,
            rows UInt64,
            non_null_rows UInt64,
            distinct_est UInt64,
            entropy Float64
        ) ENGINE = MergeTree()
        ORDER BY (run_ts, db, table)
    """)
    return stats_table_name