from .clickhouse_manager import clickhouse_manager
import datetime


def stats_pipeline():
    """Main pipeline"""
    db_manager = clickhouse_manager()
    run_full_profiling(db_manager)


def q_ident(name):
    """Use of an object to protect the name"""
    return f"`{name}`"


class Col:
    """Simple definition for column object"""

    def __init__(self, name, ch_type):
        self.name = name
        self.ch_type = ch_type


def compute_stats_for_column(client, run_ts, database, table, col):
    """Request and calcultate the needed stats from all columns of a table"""

    META_DB = "meta"

    num_types = ["Int", "Float", "Decimal", "UInt"]
    is_numeric = any(t in col.ch_type for t in num_types)

    """Sparsity, variation coefficient and skewness calcuation"""
    if is_numeric:
        metrics_calc = f"""
            avg({q_ident(col.name)}) as _avg,
            stddevPop({q_ident(col.name)}) as _std,
            skewPop({q_ident(col.name)}) as _skew
        """
        var_coef_expr = "if(_avg != 0, (abs(_std / _avg) / (1 + abs(_std / _avg))), 0)"
        skew_expr = "(abs(_skew) / (1 + abs(_skew)))"
    else:
        metrics_calc = "0 as _avg, 0 as _std, 0 as _skew"
        var_coef_expr = "0.0"
        skew_expr = "0.0"

    destination_table = f"stats_{database}_{table}"

    sql = f"""
    INSERT INTO {META_DB}.`{destination_table}`
    WITH
      base AS (
        SELECT
          count() AS total,
          countIf({q_ident(col.name)} IS NOT NULL) AS non_null,
          {metrics_calc}
        FROM {q_ident(database)}.{q_ident(table)}
      ),
      freqs AS (
        SELECT toString({q_ident(col.name)}) AS v, count() AS c
        FROM {q_ident(database)}.{q_ident(table)}
        WHERE {q_ident(col.name)} IS NOT NULL
        GROUP BY v
      ),
      tot AS (SELECT sum(c) AS n FROM freqs),
      probs AS (
        SELECT c, (c / n) AS p, n
        FROM freqs CROSS JOIN tot
      )
    SELECT
      toDateTime(%(run_ts)s) AS run_ts,
      %(db)s AS db,
      %(table)s AS table,
      %(col)s AS column,
      %(typ)s AS ch_type,
      (SELECT total FROM base) AS rows,
      (SELECT non_null FROM base) AS non_null_rows,
      toUInt64(count()) AS distinct_est,

      -- ENTROPY
      if(max(n) > 1, 
        (-sum(p * log2(p))) / log2(max(n)), 
        0.0) AS entropy,

      -- SPARSITY
      (SELECT if(total > 0, 1 - (non_null / total), 0) FROM base) AS sparsity,

      -- VARIATION COEFFICIENT
      (SELECT {var_coef_expr} FROM base) AS var_coef,

      -- SKEWNESS
      (SELECT {skew_expr} FROM base) AS skewness
    FROM probs
    """

    client.command(
        sql,
        parameters={
            "run_ts": run_ts,
            "db": database,
            "table": table,
            "col": col.name,
            "typ": col.ch_type,
        },
    )


def run_full_profiling(db_manager):
    """
    Find all the table of a database and loop the stats calculation on each one
    Clear the table before inserting to make sure to not duplicate stat datas
    """

    database = db_manager.CH_DATABASE
    query = f"SELECT table, name, type FROM system.columns WHERE database = '{database}'"
    df_cols = db_manager.client.query_df(query)

    run_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # print(f"Calculation for the table : {db_manager.CH_DATABASE}")

    for table_name in df_cols["table"].unique():
        dest_stats_table = f"stats_{database}_{table_name}"

        initialize_meta_table(db_manager, table_name)

        try:
            db_manager.client.command(f"TRUNCATE TABLE `meta`.`{dest_stats_table}`")
        except Exception as e:
            print(f"Impossible to clear : {dest_stats_table}: {e}")

        table_cols = df_cols[df_cols["table"] == table_name]

        for _, row in table_cols.iterrows():
            col_obj = Col(name=row["name"], ch_type=row["type"])

            try:
                compute_stats_for_column(
                    db_manager.client,
                    run_ts,
                    database,
                    table_name,
                    col_obj,
                )
            except Exception as e:
                print(f"Error on : {table_name}.{col_obj.name}: {e}")

    # print(f"\n Results are in database meta, table stats_{db_manager.CH_DATABASE}")


def initialize_meta_table(db_manager, table_name):
    """Create the destination table if it doesn't exist and return the created table name"""
    # print("Checking for stats table")

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
            entropy Float64,
            sparsity Float64,      
            var_coef Float64,            
            skewness Float64
        ) ENGINE = MergeTree()
        ORDER BY (run_ts, db, table)
    """)
    return stats_table_name
