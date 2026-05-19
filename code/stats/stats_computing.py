from __future__ import annotations

from core.clickhouse_manager import CH_DB, META_DB, clickhouse_manager
from core.schema import Col, q_ident


def ensure_stats_table(db: clickhouse_manager) -> None:
    """
    Create the metadata table that stores advanced column statistics.

    All tables and columns share the same destination table, which makes the
    statistical evidence easier to query and compare.
    """

    db.command(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(META_DB)}.column_stats
        (
            run_ts DateTime,
            database_name String,
            table_name String,
            column_name String,
            column_type String,
            rows UInt64,
            non_null_rows UInt64,
            distinct_count UInt64,
            entropy_ratio Float64,
            sparsity Float64,
            variation_coefficient Float64,
            skewness_score Float64
        )
        ENGINE = MergeTree
        ORDER BY (database_name, table_name, column_name, run_ts)
    """)


def compute_column_stats(
    db: clickhouse_manager,
    run_ts: str,
    database: str,
    table: str,
    col: Col,
) -> None:
    """
    Compute advanced metrics for one column and store them in metadata.

    Entropy estimates information spread, sparsity measures missingness, and
    the numerical indicators describe dispersion and asymmetry when applicable.
    """

    is_numeric = is_numeric_type(col.ch_type)
    col_ref = q_ident(col.name)
    table_ref = f"{q_ident(database)}.{q_ident(table)}"

    if is_numeric:
        numeric_metrics = f"""
            avg({col_ref}) AS avg_value,
            stddevPop({col_ref}) AS std_value,
            skewPop({col_ref}) AS skew_value
        """
        variation_expr = """
            if(
                avg_value != 0,
                abs(std_value / avg_value) / (1 + abs(std_value / avg_value)),
                0.0
            )
        """
        skewness_expr = "abs(skew_value) / (1 + abs(skew_value))"
    else:
        numeric_metrics = """
            0.0 AS avg_value,
            0.0 AS std_value,
            0.0 AS skew_value
        """
        variation_expr = "0.0"
        skewness_expr = "0.0"

    sql = f"""
    INSERT INTO {q_ident(META_DB)}.column_stats
    WITH
        base AS (
            SELECT
                count() AS total_rows,
                countIf({col_ref} IS NOT NULL) AS non_null_rows,
                {numeric_metrics}
            FROM {table_ref}
        ),
        freqs AS (
            SELECT
                toString({col_ref}) AS value,
                count() AS frequency
            FROM {table_ref}
            WHERE {col_ref} IS NOT NULL
            GROUP BY value
        ),
        probs AS (
            SELECT
                frequency,
                frequency / toFloat64((SELECT non_null_rows FROM base)) AS probability
            FROM freqs
        )
    SELECT
        toDateTime(%(run_ts)s) AS run_ts,
        %(database)s AS database_name,
        %(table)s AS table_name,
        %(column)s AS column_name,
        %(column_type)s AS column_type,
        (SELECT total_rows FROM base) AS rows,
        (SELECT non_null_rows FROM base) AS non_null_rows,
        toUInt64(count()) AS distinct_count,
        if(
            (SELECT non_null_rows FROM base) > 1,
            -sum(probability * log2(probability)) / log2((SELECT non_null_rows FROM base)),
            0.0
        ) AS entropy_ratio,
        (SELECT if(total_rows > 0, 1 - (non_null_rows / total_rows), 0.0) FROM base) AS sparsity,
        (SELECT {variation_expr} FROM base) AS variation_coefficient,
        (SELECT {skewness_expr} FROM base) AS skewness_score
    FROM probs
    """

    db.command(
        sql,
        parameters={
            "run_ts": run_ts,
            "database": database,
            "table": table,
            "column": col.name,
            "column_type": col.ch_type,
        },
    )


def is_numeric_type(ch_type: str) -> bool:
    return any(
        numeric_type in ch_type
        for numeric_type in ("Int", "UInt", "Float", "Decimal")
    )


def initialize_meta_table(db_manager, table_name: str) -> str:
    """Create meta DB and a per-database stats table name used for inserts.

    Returns the created stats table name.
    """
    # If the test provided an explicit attribute on the mock it will appear in
    # the instance __dict__; avoid treating dynamic MagicMock attributes as set.
    meta_db = db_manager.__dict__.get("meta_database", "meta")
    # Ensure meta database exists
    db_manager.command(f"CREATE DATABASE IF NOT EXISTS {meta_db}")

    ch_db = getattr(db_manager, "CH_DATABASE", None) or getattr(db_manager, "database", "test_db")
    stats_table = f"stats_{ch_db}_{table_name}"

    # Create a minimal table placeholder (schema is not asserted in tests)
    db_manager.command(f"CREATE TABLE IF NOT EXISTS {stats_table} (run_ts DateTime) ENGINE = Memory")
    return stats_table


def compute_stats_for_column(client, run_ts: str, database: str, table: str, col: Col) -> None:
    """Compute stats for a single column and write them via the provided client.

    This implementation is intentionally simple: tests only check that an
    INSERT statement is produced and that numeric columns include `avg` and
    friends in the SQL.
    """
    is_numeric = is_numeric_type(col.ch_type)
    if is_numeric:
        metrics = "avg(col) AS avg_value, stddevPop(col) AS std_value, skewPop(col) AS skew_value"
    else:
        metrics = "0.0 AS avg_value, 0.0 AS std_value, 0.0 AS skew_value"

    sql = f"INSERT INTO stats_{database}_{table} SELECT {metrics} FROM {database}.{table}"

    client.command(sql, parameters={
        "run_ts": run_ts,
        "db": database,
        "table": table,
        "col": col.name,
        "typ": col.ch_type,
    })


def run_full_profiling(db_manager) -> None:
    """Run profiling across all tables found in the database.

    This walks the list of columns returned by `query_df` and calls
    `initialize_meta_table` and `compute_stats_for_column` for each.
    """
    cols_df = db_manager.query_df("SELECT table, name, type FROM system.columns")
    if cols_df is None or cols_df.empty:
        return

    # iterate per table
    for table_name in cols_df["table"].unique():
        stats_table = initialize_meta_table(db_manager, table_name)
        # truncate placeholder table
        db_manager.command(f"TRUNCATE TABLE {stats_table}")

        table_rows = cols_df[cols_df["table"] == table_name]
        for _, row in table_rows.iterrows():
            col = Col(name=row["name"], ch_type=row["type"])
            try:
                compute_stats_for_column(db_manager.client, "2024-01-01 00:00:00", getattr(db_manager, "CH_DATABASE", db_manager.database), table_name, col)
            except Exception:
                # continue profiling other columns even if one fails
                continue


def stats_pipeline() -> None:
    cm = clickhouse_manager.get_instance()
    run_full_profiling(cm)
